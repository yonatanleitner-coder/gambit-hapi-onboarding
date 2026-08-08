# AI Plan — Chat-first NBA Trade Machine

**HAPI stage:** AI Plan (AI proposes; human approves or corrects)
**Approves:** Yonatan Leitner
**Date:** 2026-08-07
**Contract:** `docs/human-plan.md` — this plan implements that goal and scope. Where they conflict, the Human Plan wins.

---

## 1. Stack & topology

| Layer | Choice | Why |
|-------|--------|-----|
| Harness core | **LangGraph state machine (≤5 nodes)** | Closed, phase-gated tool availability — the "clear boundaries / specific tool calling" guarantee, made a legible artifact |
| Language | **Python / FastAPI** | The graded core in the language the loop is built in |
| Model | **Claude (Anthropic tool use)** | Native tool-calling; single-model in v1, behind an `LLMClient` seam that allows per-task routing later |
| Contracts | **pydantic** | Typed, validated tool args + verdict response — the boundary reviewers inspect |
| Frontend | **React + Vite (TS)** | Live GUI mirror, inline verdict cards, trace + cost strip; Playwright targets it |
| Transport | **SSE** | Stream `tool_call → state_diff → verdict → assistant → cost`; the event log *is* the trace |
| Cost | **Built-in token/cost accounting** + **Anthropic prompt caching** | Real token lever, zero external deps; Langfuse deferred |
| Deploy | **One Render web service** | FastAPI serves the built SPA + `/api`; `/trades/validate` called server-side, no CORS, no key in browser |

## 2. Trade state (single source of truth) + phase

State is a team pair + a flat asset list, carried inside the graph state alongside the current phase. The validate request is *projected* from assets at verdict time; `route_pick` just flips `to_team_id`, so routing can never be half-applied.

```python
# state.py
class Phase(str, Enum):
    EMPTY = "empty"           # no teams yet
    TEAMS_SET = "teams_set"   # two teams, no assets
    HAS_ASSETS = "has_assets" # ≥1 asset — verdict now reachable

@dataclass
class Asset:
    kind: Literal["player","pick"]; asset_id: int; name: str
    from_team_id: int; to_team_id: int; salary: int | None

@dataclass
class TradeState:
    team_ids: list[int] = field(default_factory=list)   # exactly 2 when set
    assets: list[Asset] = field(default_factory=list)
    def phase(self) -> Phase: ...
    def to_validate_request(self) -> ValidateRequest:    # project assets → per-team legs
        ...
```

## 3. Tool schema + pydantic contracts (the boundary under evaluation)

Tools are the **only** state mutators. Each tool has a **pydantic args model**; the executor validates raw model args → model, so "natural language → standardized, measurable input" is enforced at the seam. Validation failure returns a structured, recoverable error (not an exception). Names resolve to IDs locally against the preloaded catalog.

```python
# contracts.py
class SetTeamsArgs(BaseModel):   team_a: str; team_b: str
class AddPlayerArgs(BaseModel):  player: str; from_team: str; to_team: str
class AddPickArgs(BaseModel):    pick: str;   from_team: str; to_team: str
class RoutePickArgs(BaseModel):  pick: str;   to_team: str
class RemovePlayerArgs(BaseModel): player: str
class RemovePickArgs(BaseModel):   pick: str
class RequestVerdictArgs(BaseModel): pass
# Verdict response is also a pydantic model → API drift fails loud.
```

**Phase gates availability** (closed boundaries, enforced not just prompted):

| Phase | Tools offered to the model |
|-------|----------------------------|
| `EMPTY` | `set_teams` only |
| `TEAMS_SET` | `add_player`, `add_pick` |
| `HAS_ASSETS` | `add_*`, `remove_*`, `route_pick`, **`request_verdict`** |

Each executor returns a **state snapshot + diff** as its `tool_result`, so the model always reasons against ground truth. Resolution failure → `{"error":"no player 'Jaylen Browne'","suggestions":["Jaylen Brown"]}` → model disambiguates. **Tool errors are results, never exceptions.**

## 4. LangGraph state machine (replaces the hand-rolled loop)

Four nodes. A turn traverses several nodes; a single utterance can set teams *and* add assets *and* validate (multi-intent is fine — nodes loop, they don't lockstep).

```
        ┌────────────┐   tool calls (non-verdict)   ┌───────────────┐
 user ─▶│ interpret  │──────────────────────────────▶│ execute_tools │
        │ (LLM+tools │◀──────── more building ────────│ (pydantic     │
        │  for phase)│                                │  validated)   │
        └─────┬──────┘                                └───────┬───────┘
              │ request_verdict                               │ turn done
              ▼                                                ▼
        ┌────────────┐                                  ┌────────────┐
        │  validate  │─────────────────────────────────▶│  respond   │──▶ END
        │ (Provider) │                                  │ (narrate + │
        └────────────┘                                  │  cost)     │
                                                        └────────────┘
```

- **interpret** — LLM call, offered only the tools valid for `phase`; returns tool calls or final intent. The tool-loop brain.
- **execute_tools** — validate args (pydantic) → mutate `TradeState` → emit `tool_call` + `state_diff`; loop back to interpret while building.
- **validate** — reached only when `request_verdict` fires (only possible in `HAS_ASSETS`); calls `VerdictProvider`; emits `verdict`.
- **respond** — produces the chat turn (verdict narration / "why illegal" / disambiguation) from structured state; emits `assistant` + `cost`.

**Guards.** LangGraph `recursion_limit` caps runaway turns. Phase gating makes "verdict before a trade exists" structurally impossible. System prompt forbids asserting legality without a verdict, and forbids inventing numbers outside the payload.

## 5. Verdict provider (real + mock fallback)

```python
class VerdictProvider(Protocol):
    def validate(self, req: ValidateRequest) -> Verdict: ...   # Verdict.source ∈ {api, mock}

class BballGmProvider:   # POST https://bball-gm.com/api/trades/validate, timeout 6s
    # 200 → Verdict(source=api, ...incl isValid:false); 400 → hard_error; else raise ProviderUnavailable
class MockProvider:      # deterministic salary sums from catalog + simplified match; same schema
```

Harness tries real; on `ProviderUnavailable`/timeout → mock, and badges `source="mock"` in the UI (honest about the gap). `MockProvider` is the deterministic target for golden cases + Playwright (`PROVIDER=mock`).

## 6. Cost accounting + prompt caching

- **Prompt caching:** mark the static system prompt + tool schemas with `cache_control`. Usage reports `cache_read_input_tokens` → real per-turn token savings on the (largest, most repeated) prefix.
- **Built-in cost:** every `LLMClient` call captures `usage`; `cost.py` maps tokens → USD via a price table and accumulates per turn. Emits a `cost` event `{model, input, output, cached, usd}` → trace strip badge. Zero external deps.
- **Langfuse:** deferred; env-gated upgrade for aggregation, not needed at prototype volume.

## 7. LLMClient (single-model now, routing seam kept)

```python
# llm.py
MODEL_POLICY = {"interpret": SONNET, "respond": SONNET}   # v1: single model
class LLMClient:
    def create(self, task: str, system, messages, tools=None): ...  # picks MODEL_POLICY[task]
```

Routing later = change `MODEL_POLICY` (e.g. `respond → HAIKU`). No routing subsystem built; the seam is one map.

## 8. SSE event contract

```jsonc
event: tool_call   data: { name, args }
event: state_diff  data: { added, removed, rerouted, snapshot:{teams,assets,phase} }
event: verdict     data: { source, isValid, summary, teams:[{teamName,salaryOut,salaryIn,netSalaryChange,newCapStatus,allowances,violations}], appliedRules }
event: assistant   data: { text }
event: cost        data: { model, input_tokens, output_tokens, cached_tokens, usd }
event: error       data: { kind: "api_400|provider_down|resolution|validation", message }
event: done        data: {}
```

Three surfaces render from one stream — chat, GUI mirror, trace+cost strip — so they cannot desync.

## 9. Golden cases (measurable behavior reference)

```yaml
# golden/cases.yaml  — replayed via graph against PROVIDER=mock
- name: legal_two_team
  turns: ["Boston sends Jaylen Brown to New York for Julius Randle and their 2027 first"]
  expect: { tools: [set_teams, add_player, add_player, add_pick, request_verdict], verdict: legal }
- name: illegal_apron        # verdict isValid:false, violation surfaced
- name: pick_routing_refine  # add pick, then route_pick to other team, re-validate
- name: ambiguous_name       # resolution error → disambiguation, no state mutation
- name: remove_asset         # remove_player updates state + re-validates
```

`golden/run_golden.py` asserts tool sequence + verdict outcome. Feeds `docs/qa-plan.md`, a CI regression check, and seeds the Playwright happy path.

## 10. File layout

```
├── README.md
├── docs/{human-plan,ai-plan,end-of-session,qa-plan}.md
├── backend/
│   ├── main.py       # FastAPI: POST /api/chat (SSE), GET /api/health, serve dist
│   ├── graph.py      # LangGraph: nodes, edges, phase gating, guards
│   ├── harness.py    # session mgmt + event emission (thin; invokes graph)
│   ├── tools.py      # tool defs + executors (pydantic-validated)
│   ├── contracts.py  # pydantic arg models + Verdict/ValidateRequest
│   ├── state.py      # TradeState, Phase, projection
│   ├── providers.py  # VerdictProvider, BballGm, Mock  (+ deferred seams: MemoryProvider, VerdictCache)
│   ├── llm.py        # LLMClient + MODEL_POLICY (routing seam) + prompt-cache flag + usage capture
│   ├── cost.py       # tokens → USD, cost event builder
│   ├── catalog.py    # preload teams/players/picks; name→id resolution
│   ├── schemas.py    # SSE event models
│   └── config.py     # env
├── frontend/src/{App,Chat,TradePanel,VerdictCard,TraceStrip}.tsx + useTradeStream.ts
├── golden/{cases.yaml, run_golden.py}
├── tests/happy_path.spec.ts
├── requirements.txt · package.json · render.yaml · .env.example
```

Deferred seams (`MemoryProvider`, `VerdictCache`) ship as interface stubs + a design note only — not implemented in v1.

## 11. Deployment (Render, single service)

```yaml
services:
  - type: web
    name: gambit-trade-chat
    runtime: python
    buildCommand: "pip install -r requirements.txt && cd frontend && npm ci && npm run build"
    startCommand: "uvicorn backend.main:app --host 0.0.0.0 --port $PORT"
    envVars:
      - { key: ANTHROPIC_API_KEY, sync: false }
      - { key: PROVIDER, value: api }            # api | mock
      - { key: BBALL_GM_BASE, value: https://bball-gm.com/api }
```

bball-GM needs no key (open per teardown). README documents the ~30–60s free-tier cold start.

## 12. Build order (AI Execute tasks)

1. **API spike** — POST one known trade to `/trades/validate`; assert vs teardown; pin schema in `contracts.py`. *De-risks the bonus first.*
2. **Catalog + resolution** — preload; fuzzy name→id with suggestions.
3. **State + Phase + projection + pydantic contracts.**
4. **Providers** — real + mock + fallback + `source` badge.
5. **LangGraph machine + tools** — nodes, phase gates, guards. *The graded core.*
6. **LLMClient** — prompt caching, usage capture, `cost.py`; single-model policy (routing seam).
7. **SSE endpoint** — stream the full event contract.
8. **Frontend** — chat, GUI mirror, verdict card, trace + cost strip.
9. **Golden cases + runner.**
10. **Playwright happy path** (from a golden case, `PROVIDER=mock`).
11. **Deploy + smoke test** on Render.
12. **Docs pass** — end-of-session, qa-plan, README, PR.

## 13. Risks & mitigations

| Risk | Mitigation |
|------|-----------|
| API unreachable / shape drift | Spike (task 1) + pydantic verdict model (fail loud) + mock fallback with honest badge |
| Graph over-engineering | Hard cap ≤5 nodes; if it grows/fights the framework, drop to hand-rolled FSM (brief permits; more transparent) |
| Wrong/hallucinated player | Catalog resolution rejects unknowns → disambiguation |
| Model narrates numbers not in payload | System prompt bans it; golden cases assert verdict text only cites payload fields |
| Runaway / verdict-skipping turn | `recursion_limit`; phase gating makes premature verdict impossible |
| SSE buffering on free tier | Supported; fall back to chunked JSON — event contract unchanged |

## 14. Open questions (defaults if you don't steer)

1. **Model** — Sonnet for both nodes (default), or Opus for `interpret`?
2. **Token streaming** — event-level only (default), or stream assistant tokens too?
3. **Trace + cost strip** — collapsed by default, one tap to expand (default)?

---

**Approval:** on your sign-off (and any §14 steers), execution starts at task 1 (API spike). I hold to the Human Plan's goal and quality bar; correct anything here before we build.
