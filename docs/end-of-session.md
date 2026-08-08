# End of session — 2026-08-08

## Goal
Build a chat-first interface to the bball-GM NBA Trade Machine where conversation is the primary way to construct, refine, and validate a two-team, multi-asset trade, with a live GUI mirror and verdicts rendered legibly in both chat and GUI — proving a clean, bounded LLM harness + tool boundary, not a clever prompt. See `docs/human-plan.md`.

## Status
- **Done:** Human Thinking (MVP scoped via clarifying questions). `docs/human-plan.md` and `docs/ai-plan.md` drafted, revised once, and current. Full API contract confirmed from `bball-gm-engine-teardown.md`. **AI Plan §12 tasks 1–5 complete** (API spike, catalog + resolution, state + contracts, providers, LangGraph machine + tools) — see below.
- **In progress:** AI Execute proceeding task-by-task. **AI Plan §12 task 8 (frontend) complete** — see below. Tasks 9–12 not started. Three low-stakes steers still open (see Open questions). Task 5's biggest open risk (no live LLM test) resolved mid-session — human supplied `ANTHROPIC_API_KEY`, full harness verified live, including over real HTTP and now through a real browser UI.
- **Blocked / not started:** No application code yet. `docs/qa-plan.md` and this file's final version are downstream.
- **Repo housekeeping:** `origin` was already `yonatanleitner-coder/gambit-hapi-onboarding` (own repo, not the `gambit-lab` template) on feature branch `yonatan_project` — the repo-creation step was already done, correcting a stale note in an earlier version of this file. Docs and `CLAUDE.md` relocated from `claude-git-workshop/Docs/` to root `docs/` + root `CLAUDE.md` to match the delivery spec (project root, alongside `backend/`/`frontend/` to come); unrelated instructor-workshop PDFs/Figma file stayed in `claude-git-workshop/`.

## API spike (AI Plan §12 task 1) — done, 2026-08-08
Three live calls against `POST https://bball-gm.com/api/trades/validate`, no mock — confirmed against `bball-gm-engine-teardown.md` field-for-field, **no schema drift found**:
- **Legal** — real IDs (team `2` Celtics/BOS, team `20` Knicks/NYK, players `16998` Neemias Queta ↔ `17338` Andre Drummond) → `200 {isValid:true, ...}`, full shape as documented.
- **Illegal** — same teams, player `17329` Paul George for Drummond (deliberately lopsided) → `200 {isValid:false, ...}`; confirms `isValid` exists both top-level *and* per-team, with `violations` populated only for the failing team.
- **Hard error** — 1-team request (API requires ≥2) → `400 {"error": "..."}`.
- **Nuance not obvious from the doc:** the `400` channel's `error` value is sometimes a JSON-stringified Zod issue array, not guaranteed prose. Pinned in the schema's docstring so `respond` doesn't assume it's directly narratable — needs a plain-language wrapper, not a pass-through.
- **Schema pinned** in `contracts.py` (`TeamLeg`, `ValidateRequest`, `TeamVerdict`, `Verdict`, `ApiHardError`) — currently in the session scratchpad only, not yet in a repo (see Continue from here).

## Catalog + resolution (AI Plan §12 task 2) — done, 2026-08-08
`backend/catalog.py`: `Catalog.load()` preloads `/teams`, `/players`, `/draft-picks` (async, one round trip via `asyncio.gather`) into id-keyed pydantic models (`Team`, `Player`, `Pick`); `resolve_team`/`resolve_player`/`resolve_pick` do local name→id resolution, no network calls. Verified live against the real API (30 teams, 506 players, 443 picks) — matched all fixture-based unit tests (`backend/tests/test_catalog.py`, 10 passing).

Resolution tiers, in order: exact match → unambiguous substring containment (handles partial names like "Queta") → fuzzy match (typo tolerance) → `ResolutionError{error, suggestions}`.

Two real bugs found and fixed via a live smoke test before trusting the unit tests alone:
- Fuzzy matching against short candidates (3-letter team abbreviations) produced coincidentally-high `SequenceMatcher` ratios — `resolve_team("Queta")` was matching the Jazz (`"uta"` abbreviation) at exactly the auto-resolve threshold. Fixed by excluding candidates under 5 chars from the fuzzy tier; they only match exactly or by containment now.
- (Caught during review, not a code bug) `ai-plan.md` §3's worked example treats a typo like `"Jaylen Browne"` as a resolution error requiring model disambiguation. The implementation instead auto-resolves high-confidence typos (ratio ≥ 0.75) silently. Flagged to the human; **kept the auto-resolve behavior** — see Human guidance given.

## State + Phase + contracts (AI Plan §12 task 3) — done, 2026-08-08
- `backend/contracts.py` now holds the pinned bball-GM schema (moved out of the session scratchpad — `TeamLeg`, `ValidateRequest`, `TeamVerdict`, `Verdict`, `ApiHardError`) plus the tool-argument models from `ai-plan.md` §3 (`SetTeamsArgs`, `AddPlayerArgs`, `AddPickArgs`, `RoutePickArgs`, `RemovePlayerArgs`, `RemovePickArgs`, `RequestVerdictArgs`). One test locks the `Verdict` model against the real illegal-trade shape captured in the task 1 spike, so API drift fails a test, not silently.
- `backend/state.py`: `Phase` enum, `Asset` dataclass, `TradeState` dataclass with `phase()` (`EMPTY` unless exactly 2 team ids; `TEAMS_SET` until >=1 asset; else `HAS_ASSETS`) and `to_validate_request()` (projects the flat asset list into per-team `TeamLeg`s by grouping on `kind`/`from_team_id`/`to_team_id`). `route_pick`'s "flip `to_team_id` in place" atomicity claim is exercised directly: mutating one `Asset` field and re-projecting reflects the change with no other state touched.
- 12 new tests (`test_state.py`, `test_contracts.py`); 22 passing total across the backend.
- Nothing deferred or cut here — task 3 matched `ai-plan.md`'s design as written, no deviations to flag.

## Providers (AI Plan §12 task 4) — done, 2026-08-08
`backend/providers.py`: `VerdictProvider` protocol; `BballGmProvider` (real, `POST /trades/validate`, 6s timeout); `MockProvider` (deterministic salary-matching approximation using `Catalog` + the cap-tier table from `bball-gm-engine-teardown.md`, explicitly labeled non-authoritative). Two distinct exceptions instead of one generic failure: `ProviderUnavailable` (network/timeout/unexpected status — the harness's fallback-to-mock trigger, task 5) vs. `HardRuleViolation` (the API's own `400 {error}` channel — a working API correctly rejecting a hard rule; must NOT fall back to mock, must surface to the user per human-plan's two-distinct-channels requirement). `Verdict` gained a `source: Literal["api","mock"] = "api"` field (contracts.py) so every verdict can be badged; `MockProvider` sets `source="mock"` explicitly.

Extended `catalog.py`'s `Team` model with `totalSalary`/`capSpace`/apron flags (present in the live `/teams` response, not previously captured) since `MockProvider` needs them.

**Live smoke test caught a real bug** before it shipped: `TeamLeg.model_dump()` serializes `isSignAndTrade: None` as JSON `null`, and the live API's schema rejects an explicit `null` for that optional field (wants it omitted) — every real-provider call was failing as a false `HardRuleViolation`. Fixed with `model_dump(exclude_none=True)`; regression test added (`test_bball_gm_provider_omits_none_fields_from_request_body`). Also reassuring: `MockProvider`'s simplified math independently agreed with both live verdicts from the task 1 spike (legal Queta↔Drummond, illegal George-for-Drummond) on first try.

30 tests passing across the backend.

## LangGraph machine + tools (AI Plan §12 task 5) — done and live-verified, 2026-08-08
The graded core. `backend/tools.py`: phase-gated tool schema (`TOOLS_BY_PHASE` mirrors `ai-plan.md` §3's table exactly) + 7 executors (`set_teams`, `add_player`, `add_pick`, `route_pick`, `remove_player`, `remove_pick`, `request_verdict`), each resolving names via `catalog.py` then mutating `TradeState` — or returning a structured `{"error", "suggestions"}` dict, never raising. `backend/llm.py`: minimal `LLMClient` + `MODEL_POLICY` seam (prompt caching/cost capture deferred to task 6 as planned). `backend/graph.py`: 4-node LangGraph (`interpret → execute_tools → validate → respond`).

**No `ANTHROPIC_API_KEY` was available this session** (flagged and confirmed with the human before building — see Human guidance given). Built the graph and tools anyway per the human's direction; verified everything that doesn't require a live model:
- 16 new `tools.py` unit tests (phase gating, resolution scoping, duplicate/error recovery).
- `graph.py` exercised end-to-end via a `FakeLLMClient` that plays back scripted Anthropic-shaped tool-call/text responses — `MockProvider` runs for real (deterministic, no network) so `validate()` is genuinely exercised. Covers: happy path to a verdict, a resolution error looping back to `interpret` instead of dead-ending, a hallucinated `request_verdict` before `HAS_ASSETS` being blocked by `tools.py`'s defense-in-depth phase check, and `recursion_limit` raising `GraphRecursionError` on a runaway loop.
- **Live-verified mid-session:** human supplied a real `ANTHROPIC_API_KEY`, pasted directly in chat. Stored it only in a local, gitignored `.env` (confirmed `.gitignore` covers it before writing; never echoed or committed) — added `.env.example` alongside it (placeholder only, safe to commit, matches `ai-plan.md` §10's file layout). Ran the exact task-1-spike scenario (Boston sends Queta to New York for Drummond) through the real graph end-to-end: `interpret` correctly resolved free-text team/player names via tool calls across 3 loop iterations (`set_teams` → both `add_player` calls together, confirming multi-intent-in-one-turn works → `request_verdict`), `validate` got a real `200 {isValid:true}` from bball-GM, and `respond` produced accurate, well-grounded prose (correct dollar figures, cap statuses, and rule citations, all traceable to the verdict payload — no invented numbers observed, no raw JSON shown). Added `backend/tests/test_graph_live.py`, skipped by default via `pytest.mark.skipif` unless `ANTHROPIC_API_KEY` is set, so this check is repeatable without a mandatory network+cost dependency in normal test runs. Full suite: 50 passed + 1 skipped without a key; 51 passed with one set.

Two deliberate deviations from the `ai-plan.md` §4 diagram as literally drawn (both are engineering clarifications, not scope changes — documented in `graph.py`'s module docstring too):
1. `interpret` ends the turn directly (→ END) when it returns no tool calls, instead of routing through `respond`. Its own text (disambiguation, a "why illegal" answer, general conversation) already *is* the turn's answer; routing it through `respond` would trigger a second, redundant LLM call. A first draft did route through `respond` and a test caught the bug immediately (the fake script ran out of scripted responses because it correctly didn't expect a second call) — `respond` now exists specifically to narrate *structured* verdict/hard-error data that `interpret` never saw.
2. `request_verdict` is still routed through `execute_tools` (as a no-op mutator with its own phase check) rather than short-circuiting directly from `interpret`, so a turn that mixes building calls and `request_verdict` in one LLM response (multi-intent is explicitly fine per §4) applies the building calls before checking whether a verdict was requested.

Dependencies added: `anthropic==0.121.0`, `langgraph==1.2.10` (versions pinned to what actually installed, per this repo's existing convention).

50 tests passing across the backend (51 with the live test, when a key is set).

## LLMClient polish: caching + cost (AI Plan §12 task 6) — done and live-verified, 2026-08-08
`backend/llm.py`: added a `cache_control` breakpoint on the system prompt. Render order is tools → system → messages, so one marker on the (single) system block caches the tools that precede it too — no separate marker needed on the tools list itself. `backend/cost.py`: a price table (`PRICE_PER_MTOK`, standard non-introductory Claude Sonnet 5 rates — $3/$15 per MTok in/out, 1.25x/0.1x for cache write/read) and a pure `compute_cost()` + `cost_event()` pair, matching the SSE contract's `cost` event shape exactly. `graph.py`'s `interpret` and `respond` nodes now emit a `cost` event on every LLM call. Pricing sourced from the `claude-api` skill rather than recalled from training, given today's date (2026-08-08) falls inside Sonnet 5's temporary intro-pricing window (through 2026-08-31) — the table intentionally uses the durable standard rate, not the expiring intro rate, so costs don't silently change later.

**Live-verified the caching claim, not just the code path:** ran the same trade-building scenario twice through the real API (cold, then again). Real finding: only the `HAS_ASSETS`-phase interpret call (the one offering the most tools — `add_player`, `add_pick`, `remove_player`, `remove_pick`, `route_pick`, `request_verdict`) showed a cache hit (`cached_tokens: 1153`) on the second run. The `EMPTY`/`TEAMS_SET` phases (1–2 tools) and the `respond` call (no tools) never cached, in either run — their system+tools prefix falls under Claude Sonnet 5's 1024-token minimum cacheable prefix, so caching silently no-ops there (no error, per Anthropic's documented behavior). **This is not a bug** — `HAS_ASSETS` is exactly the largest and most-repeated phase in a real session (once a trade has assets, most turns stay there: add/remove/route/re-validate), so caching concentrates its savings precisely where ai-plan.md §6 aimed it ("the largest, most repeated prefix"). Worth knowing precisely rather than assuming caching helps uniformly across every phase.

4 new tests (`test_cost.py`); 54 passing + 1 skipped without a key (55 with one).

## SSE endpoint (AI Plan §12 task 7) — done and live-verified, 2026-08-09
First real app scaffolding beyond `backend/`'s pure logic: `main.py` (FastAPI: `POST /api/chat`, `GET /api/health`), `harness.py` (session store + SSE formatting), `schemas.py` (`SSEEvent` envelope validation).

Real streaming, not batch-and-flush: `graph.py` gained `stream_turn()` alongside `run_turn()`, using LangGraph's `astream(stream_mode=["updates","values"])` — probed empirically first (not guessed) to confirm `"updates"` yields each node's own return dict as it completes (exactly the per-node event delta, no recomputation needed) while `"values"` gives the fully-merged final state for persisting session messages once the turn ends. Verified via a live client that events arrive in true node-execution order, not all at once at the end.

Two things added beyond the literal task 7 scope, both because they closed real gaps found while building:
- **`error` events now fire for tool-execution failures, not just provider failures.** The SSE contract's `kind: resolution | validation` values had no emitter — `execute_tools` classifies each failed tool call as `resolution` (has a `suggestions` key, i.e. a name lookup failed) or `validation` (a pydantic arg error or domain-rule rejection) and emits an `error` event alongside the tool_result already fed back to the model, so the trace strip can surface these distinctly instead of only the model narrating them conversationally.
- **`handle_chat` never lets a stream die silently.** An unhandled exception mid-turn (a `GraphRecursionError`, an uncaught API error) is caught and turned into a `{"kind":"server_error"}` event followed by `done`, instead of the HTTP connection just cutting off. `session.messages` is deliberately *not* updated on this path, so the next turn retries from the last known-good history rather than compounding on a half-applied one.

**Live-verified over real HTTP, not just via ASGI TestClient:** ran `uvicorn backend.main:app` as an actual subprocess and `curl`'d `POST /api/chat` twice in the same session against the real Anthropic + bball-GM APIs. First turn: full tool-call sequence → verdict → assistant narration, correctly SSE-framed, ending in `done`. Second turn (same `session_id`, "why did Boston not need to match salary?"): correctly took the `interpret`-ends-directly path (no tool call needed, answered from conversation history) *and* got a real prompt-cache hit (`cached_tokens: 1153`) reusing the `HAS_ASSETS`-phase prefix cached by the first turn — confirms both session persistence and caching work correctly across separate real HTTP requests, not just within one process's memory during a single call.

`TestClient` tests (`test_main.py`) deliberately skip FastAPI's lifespan by never using it as a context manager (verified empirically first) — `app.state` is populated with fakes directly, so the test suite never touches the real network or needs a key.

11 new tests (`test_schemas.py`, `test_harness.py`, `test_main.py`, plus 3 more in `test_graph.py` for `stream_turn`/error-event classification); 68 passing + 1 skipped without a key.

Added `fastapi==0.141.1`, `uvicorn==0.52.1`.

**Not yet done:** serving the built frontend SPA (`StaticFiles` mount) — deferred to task 8/11 since `frontend/dist` doesn't exist yet; mounting it now against a missing directory would fail at startup.

## Frontend (AI Plan §12 task 8) — done and visually verified in a real browser, 2026-08-09
React + Vite (TS), scaffolded fresh: `App.tsx`, `Chat.tsx`, `TradePanel.tsx`, `VerdictCard.tsx`, `TraceStrip.tsx`, `useTradeStream.ts` (hand-rolled SSE parser in `sse.ts` — `EventSource` can't do POST, so `fetch()` + manual `event:`/`data:` frame parsing consumes `POST /api/chat`'s stream). One added backend endpoint: `GET /api/teams` — the `state_diff` snapshot only carries team **ids** (`tools.py`'s `_snapshot`), so the trade panel had no way to show real names without it.

**Environment blocker hit and resolved:** Node.js was not installed on this machine, and the `winget` MSI installer needs an interactive UAC elevation prompt this session can't satisfy (human confirmed: no admin rights). Worked around it with the **portable zip distribution** instead — no install, no admin needed: `node-v24.19.0-win-x64.zip` extracted to `C:\Users\YonatanLeitner\tools\node-v24.19.0-win-x64\`. **This is not on PATH permanently** — every session needs `export PATH="/c/Users/YonatanLeitner/tools/node-v24.19.0-win-x64:$PATH"` (bash) before `node`/`npm` commands work. Same trick was used for a scratch Playwright installation (`C:\Users\YonatanLeitner\tools\pw-scratch\`, outside the repo, not a project dependency) purely to drive a real Chromium browser for visual verification — Playwright is NOT in `frontend/package.json`.

**Real design pass, not just "make it functional":** custom CSS design system (`index.css`) — color tokens, an orange accent (deliberately not purple-gradient/Inter-font "AI slop" per the well-known anti-patterns), full `prefers-color-scheme: dark` support, responsive stacking below 860px. `react-markdown` renders the LLM's own markdown-formatted prose (confirmed live in task 5/7 that `respond` outputs real markdown — bold, bullet lists) instead of showing raw asterisks.

**Live-verified in an actual browser**, not just build-checked: ran `uvicorn` + `vite dev` together, drove the real UI with Playwright (typed a message, clicked send, waited for the real SSE stream from the real Anthropic + bball-GM APIs), and visually inspected screenshots at each step — desktop light, desktop dark, narrow/mobile-width, and an edge case (asked it to trade "a bag of chips" — `interpret` correctly asked a clarifying question instead of hallucinating an asset, `respond` never ran since no tool call happened, matching the ends-directly path from task 5).

**Real bug caught by the fullPage screenshot, not by eye:** `.chat` and `.chat__list` were missing `min-height: 0` — the classic flexbox gotcha where a flex child's content-based `min-height: auto` prevents it from shrinking to fit its container. The whole app grew taller than the viewport instead of scrolling internally once conversation + expanded trace strip exceeded 900px — invisible in the initial screenshot (short conversation, viewport captured fine) but caught by comparing `document.documentElement.scrollHeight` to `clientHeight` after a longer interaction. Fixed with `min-height: 0` on `.chat`, `.chat__list`, `.trade-panel`; verified `scrollHeight === clientHeight` afterward.

One minor UX fix along the way: the per-message "what changed" toggle was counting the `cost` event that rides along on every turn, so a turn with zero tool calls still showed a confusing "(0 tool calls)" toggle. Now filters to genuinely meaningful events before deciding whether to render the toggle at all.

**Not built:** no automated frontend test suite (Playwright happy-path test is task 10's explicit job, `PROVIDER=mock`); no `frontend/dist` served by the backend yet (that's task 11, deploy).

## Key decisions (this session)
- **Stack:** Python/FastAPI backend + React/Vite (TS) frontend, **single Render web service** (FastAPI serves built SPA + `/api`; validate called server-side, no CORS, no key in browser). Chose Python because the harness is the graded core and it's the author's strength.
- **Harness core = LangGraph state machine, ≤5 nodes** (`interpret → execute_tools → validate → respond`). Tools are **closed per phase** (`EMPTY → TEAMS_SET → HAS_ASSETS`); `request_verdict` is structurally unreachable until 2 teams + ≥1 asset exist. *Reversal:* earlier plan hand-rolled the loop; switched to LangGraph because the explicit goal of closed, state-bound tools makes the graph earn its complexity. **Tripwire:** if the graph exceeds ~5 nodes or fights the framework, drop to a hand-rolled FSM (brief permits; more transparent at this size).
- **Pydantic contracts** on every tool's args + the verdict response — "natural language → standardized, measurable input" enforced at the seam; API drift fails loud.
- **Validation:** real bball-GM `POST /api/trades/validate` behind a `VerdictProvider` abstraction, with a deterministic `MockProvider` fallback that **badges `source`** (honest about the gap). bball-GM API is open — no key.
- **Cost:** Anthropic **prompt caching** on the static system+tools prefix + **built-in per-turn token/cost accounting** emitted as a `cost` event → trace badge. Zero external deps.
- **Golden cases (4–6)** replayed against the deterministic mock; feed `qa-plan`, a CI regression check, and the Playwright seed.
- **Deliberately deferred, each behind a named seam** (this is scope judgment, not omission):
  - Mem0 / cross-session memory → `MemoryProvider` seam. In-session, `TradeState` is authoritative; a fuzzy layer risks a second, non-authoritative source of state.
  - Supabase / durable storage / verdict cache → `VerdictCache` seam. Validation is *free* and tokens are spent *upstream* of any cache key → a cache saves latency, not cost.
  - Model routing (cheap model for narration) → `LLMClient` `MODEL_POLICY` map seam; ships **single-model**. *Reversal:* earlier plan adopted node-based routing; cut it because a 2nd model is a 2nd behavior surface the golden cases must police, for negligible prototype savings. Seam kept, build dropped.
  - Langfuse → env-gated observability upgrade; built-in cost covers v1.
  - Out entirely: 3+ team trades, sign-and-trade, manual exception/TPE, salary overrides, auth/multi-user, persistence beyond in-memory session, mobile polish, any self-built CBA logic.

## Human guidance given
- "Lean and functional, benefits not flex" — the decisive filter that produced the deferral cuts above. Hold this line.
- Verdict must appear in **both** chat and GUI, in prose — never raw JSON; illegal verdicts never silent.
- Explainability + traceability are first-class (author works in AML/fintech — "trust and audit").
- Adopt LangGraph for closed boundaries; keep it small.
- **Task 5 without an API key: build now, verify live later.** Flagged before starting that `interpret`/`respond` need a real Claude call and no `ANTHROPIC_API_KEY` was set in this environment. Human chose to proceed with the graph/tools build (tested via a fake LLM client) rather than pause, deferring the live round-trip check to whenever a key is available. *Resolved same session:* human pasted a real key directly in chat; used it once to live-verify the full harness (see task 5 notes above), stored only in a local gitignored `.env`, never committed.
- **"Make sure it looks nice"** (task 8) — taken as a real requirement, not a throwaway line: full custom design system, dark mode, responsive layout, and actual browser-driven visual verification with screenshots at each step (not just a successful build) before calling the task done.
- **Node.js install blocker: use the portable zip, not the admin-gated installer.** Human confirmed no admin/UAC permissions on this machine. Chose the portable Node distribution over asking the human to install it themselves or writing untested frontend code — see task 8 notes above for the exact path and PATH-setup requirement every future session needs.
- **Catalog resolution: keep silent auto-resolve on high-confidence typos** (task 2). `ai-plan.md` §3's worked example (`"Jaylen Browne"` → resolution error + suggestion, model disambiguates) was the original design; I flagged that my implementation instead auto-resolves typos above a 0.75 fuzzy-match ratio with no disambiguation turn. Human chose to keep the auto-resolve behavior over the plan's stricter example — noted here since it's a deliberate deviation from a plan example, not an oversight. Still requires exact/unambiguous-substring or high fuzzy-confidence; true ambiguity (multiple candidates, or low-confidence match) still returns `ResolutionError` + suggestions.

## Open questions
- **Model tier** (AI Plan §14): Sonnet for both nodes (default) or Opus for `interpret`?
- **Token streaming:** event-level only (default) or stream assistant tokens too?
- **Trace + cost strip:** collapsed-by-default (default) or always visible?
- **Human Plan edits:** replace illustrative money figures with real synthetic values (backfill from `GET /api/players` during the API spike); confirm the "why I'm the right person" framing reads in the author's voice.

## Continue from here
- **Repo:** done — own public repo, feature branch `yonatan_project`. No further action needed here.
- **Files present:** `docs/human-plan.md`, `docs/ai-plan.md`, this file, root `CLAUDE.md`, `requirements.txt`, `.gitignore`, `.env` (local only, gitignored, real key — not present in a fresh clone), `.env.example` (committed, placeholder), `backend/{__init__.py,config.py,catalog.py,contracts.py,state.py,providers.py,tools.py,llm.py,graph.py,cost.py,schemas.py,harness.py,main.py}`, `backend/tests/{test_catalog,test_state,test_contracts,test_providers,test_tools,test_graph,test_graph_live,test_cost,test_schemas,test_harness,test_main}.py`, and now `frontend/` (React + Vite + TS: `src/{App,Chat,TradePanel,VerdictCard,TraceStrip}.tsx`, `src/{useTradeStream,sse,types,format}.ts`, `src/index.css`).
- **Next task:** AI Plan §12 **task 9 — Golden cases.** `golden/cases.yaml` (4–6 fixed utterances → expected tool sequence → expected verdict outcome) + `golden/run_golden.py`, replayed against `MockProvider` (deterministic). Feeds `docs/qa-plan.md` (not yet written — also outstanding), a regression check, and seeds task 10's Playwright test. Then proceed tasks 10→12.
- **Local dev setup:** `ANTHROPIC_API_KEY` is in the local `.env` from this session (not committed). A fresh clone needs to copy `.env.example` → `.env` and fill in a real key. Backend: `.venv/Scripts/python.exe -m uvicorn backend.main:app --reload` (port 8000). Frontend: needs Node — **not on PATH by default this session**, see the task 8 notes above for the portable-Node workaround; once on PATH, `cd frontend && npm install && npm run dev` (proxies `/api` to `127.0.0.1:8000` per `vite.config.ts`, port 5173).
- **Reference:** `bball-gm-engine-teardown.md` (repo root) — request/response schema, confirmed live in the task 1 spike with no drift. Base URL `https://bball-gm.com/api` (open, no key).
- **Commands:** `py -m venv .venv` (Windows, this session's Python was reached via the `py` launcher — plain `python`/`python3` weren't on PATH), `.venv/Scripts/python.exe -m pip install -r requirements.txt`, `.venv/Scripts/python.exe -m pytest backend/tests -q`.
- **Demo URL:** none yet.

## Do not regress
- NL → trade state must flow through the **tool-calling loop**. No hardcoded string parsing. No single mega-prompt that returns final JSON. (These are the brief's explicit disqualifiers.)
- **Tools are the only state mutators;** tool availability stays **closed per phase**.
- Verdict renders in **both chat and GUI**, in prose; illegal verdicts are never silent and never raw JSON.
- Keep `VerdictProvider` fallback + `source` badge; keep `MockProvider` **deterministic** (tests depend on it).
- Keep the deferred items deferred — don't let Mem0 / Supabase / routing / Langfuse creep back without a stated reason.
- Graph stays ≤5 nodes.
