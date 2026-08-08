# End of session — 2026-08-08

## Goal
Build a chat-first interface to the bball-GM NBA Trade Machine where conversation is the primary way to construct, refine, and validate a two-team, multi-asset trade, with a live GUI mirror and verdicts rendered legibly in both chat and GUI — proving a clean, bounded LLM harness + tool boundary, not a clever prompt. See `docs/human-plan.md`.

## Status
- **Done:** Human Thinking (MVP scoped via clarifying questions). `docs/human-plan.md` and `docs/ai-plan.md` drafted, revised once, and current. Full API contract confirmed from `bball-gm-engine-teardown.md`. **AI Plan §12 tasks 1–5 complete** (API spike, catalog + resolution, state + contracts, providers, LangGraph machine + tools) — see below.
- **In progress:** AI Execute proceeding task-by-task. **AI Plan §12 task 9 (golden cases) complete** — see below. Tasks 10–12 not started. Three low-stakes steers still open (see Open questions). Task 5's biggest open risk (no live LLM test) resolved mid-session — human supplied `ANTHROPIC_API_KEY`, full harness verified live end to end: real HTTP, real browser UI, and now a real golden-case eval suite.
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

## Golden cases (AI Plan §12 task 9) — done, all 5 passing live, 2026-08-09
`golden/cases.yaml` (5 cases, matching `ai-plan.md` §9's exact names) + `golden/run_golden.py` (standalone script and importable library) + `backend/tests/test_golden.py` (pytest wrapper, one parametrized test per case for a named failure instead of one opaque pass/fail).

**Design call, made explicit since the plan was ambiguous here:** cases replay through the **real** `interpret`/`respond` loop (real Anthropic calls) with `MockProvider` standing in only for the CBA math (`PROVIDER=mock` per the plan's own comment on this file) — this is a real-model eval, not a network-free unit test, so it's skipped without `ANTHROPIC_API_KEY` (same precedent as `test_graph_live.py`). The alternative reading (a fully scripted fake-LLM regression suite) was considered and rejected: it would make the "expect tools" assertion tautological, since the fake would be scripted to already match. Tool-sequence checks use subsequence matching (expected tools must appear in order, extra calls tolerated) rather than exact-sequence matching, since a real model's exact batching is expected to vary run to run.

**Running this for real caught three genuine, separate issues** — none were product bugs of the "code is wrong" kind except one real one:

1. **Real product bug, fixed:** `Catalog.resolve_pick` silently returned whichever pick happened to come first in iteration order when a team held *two* picks for the same year+round (a real scenario — a team's own 1st plus another team's via an earlier trade; confirmed live that Boston holds both a 2031 1st and the 76ers' 2031 1st). Now detects the ambiguity and returns a `ResolutionError` with both descriptors as suggestions, exactly like a name conflict. Test added (`test_resolve_pick_ambiguous_year_round_returns_error_not_first_match`).
2. **Real robustness gap, fixed:** `resolve_pick`'s parser only matched exact tokens (`"first"`), so a model passing through natural phrasing like `"their 2027 first-round pick"` (rather than normalizing to `"2027 first"`) would fail to parse. Switched to word-boundary regex matching (`\bfirst\b` matches inside `"first-round"`) and added a format hint to the `add_pick`/`route_pick`/`remove_pick` tool descriptions. Test added.
3. **Two test-design mistakes, not product bugs, both fixed by observing real model behavior:** (a) `pick_routing_refine` originally asserted a specific order between the swap's `add_pick`/`remove_pick` — a real model did `remove_pick` first in one run, both orders are legitimately valid, so only the reliably-ordered first-turn prefix is asserted now, with `final_assets` as the authoritative check. (b) `ambiguous_name` originally used "Michael Jordan" and expected a resolution error — the real model recognized him as an unambiguously real-world retired legend and asked a clarifying question *without even attempting the tool call*, which is arguably better behavior but meant no resolution error ever fired, defeating the case's purpose. Switched to a plausible-but-fake name ("Marcus Webb"), which forces a real lookup attempt. Also had to correct the case's own expected outcome: a failed `add_player` for Boston doesn't roll back an independent, valid `add_player` for New York (each tool call is independent per `ai-plan.md` §3) — the original expectation of `final_assets: []` was simply wrong about how the (correctly-designed) system behaves.

All 5 cases pass live. Full backend suite with a key present: 77 passed (0 skipped). Without a key: 71 passed, 6 skipped (5 golden + the task-5 live graph test).

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

---

# Checkpoint — 2026-08-09 (continued): branding, landing page, closed-list pickers, stream reliability

Same-day continuation after the security/qa-plan checkpoint and task 10. Two rounds of work, both committed and pushed (`20cea84`).

## Branding + landing page + closed-list pickers
- Incorporated the user-supplied Gambit logo (horse/basketball mark): cropped icon in the compact header, full lockup on the landing screen, new favicon (`frontend/public/gambit-logo.png`, `gambit-mark.png`). Both styled as rounded/shadowed "badges" rather than fighting the source image's baked-in light background — a flood-fill transparency attempt was tried first and discarded (the artwork's intentionally textured/distressed border defeated a clean cutout).
- The empty chat state is now a real landing section: what the app does, a 4-step how-to-interact list, above the existing example prompts.
- **Closed-list pickers**, the "just like bball-GM" ask for users who don't know exact names: `TeamPicker.tsx` (two team dropdowns on the landing screen) and `AssetPicker.tsx` (a "+ Add from list" control per GUI panel column, scoped to that team's real roster). New backend endpoint `GET /api/teams/{id}/assets` (players + picks for a team, from the already-loaded `Catalog`) backs the latter. **Both pickers only draft a chat utterance and send it through the normal composer path** — they do not mutate `TradeState` directly. This was a deliberate design constraint: the brief's non-negotiable is that tools are the *only* state mutators, and a second, click-driven mutation path would have quietly reopened exactly the thing the harness is supposed to close off. Verified live end-to-end (screenshots): team picker → real `set_teams` tool call → GUI mirror updates; asset picker → real `add_player` tool call → GUI + chat both update.

## Stream reliability fix (real bug, caught live)
While testing, restarting the backend process mid-conversation (to pick up code changes) left the user's browser tab with a rendered-but-incomplete assistant message and a permanently stuck "thinking" indicator — no error, no recovery. Root-caused to: a killed backend process's connection isn't always signaled cleanly through Vite's dev proxy, so the frontend's `fetch()` reader can wait forever for bytes that will never arrive. This was initially misdiagnosed as possible `max_tokens` truncation; live reproduction attempts against the real API ruled that out (actual responses used well under the 1024-token cap).

Fixed in `useTradeStream.ts`: a 30-second inactivity timeout on the SSE stream, reset on every received frame (so a genuinely slow turn is never penalized). On timeout, the fetch aborts and a clear "lost the connection, try again" message renders instead of a silent hang. **Verified live, not just reasoned about:** a script that starts a real turn and kills the backend process an instant later confirmed the fix recovers cleanly (composer re-enables, visible error) where the prior code would have hung. This is also real insurance for production — a Render restart or network blip mid-turn now degrades to a retryable error instead of a stuck UI.

## AI Plan §12 task 11 (deploy) — prep done, actual deploy still pending
`backend/main.py` now conditionally mounts `frontend/dist` as `StaticFiles` at `/` (only when the directory exists, so local API-only dev is unaffected), verified locally by running a second instance on a spare port and confirming both `/` (SPA) and `/api/*` serve correctly from one origin — the exact shape Render will run. `render.yaml` added at repo root with the build/start commands and env vars from `ai-plan.md` §11.

**What's still outstanding:** actually creating the Render service. This requires the human's own Render account (OAuth through Render's dashboard to connect the GitHub repo) — not something completable from this session. Exact steps are already in chat history / can be re-given on request: Render dashboard → New → Blueprint → connect `yonatanleitner-coder/gambit-hapi-onboarding` on branch `yonatan_project` → it auto-detects `render.yaml` → paste `ANTHROPIC_API_KEY` when prompted → Apply.

## Human guidance given (this session)
- Wanted to see the app running live, not just told it works — a real browser window was opened against the local dev servers throughout, and every feature (pickers, branding) was interactively verified via Playwright screenshots/scripts before being reported as done, not just build-checked.
- Caught a real live bug themselves (the stuck stream) via direct use of the running app rather than a prepared test case — a good reminder that live human use surfaces failure modes a scripted eval won't.

## Open questions (carried forward)
- Prompt-cache breakpoint on growing conversation history (flagged in the earlier checkpoint) — still not implemented, still the highest-leverage remaining data-engineering improvement.
- `docs/architecture-diagram.pdf` — still deliberately untracked, pending a decision on whether to commit it.

## Continue from here (2026-08-09 end of day)
- **Local dev servers were stopped cleanly** at end of session — nothing left running. Next session: source `.env`, then backend (`.venv/Scripts/python.exe -m uvicorn backend.main:app --reload`) and frontend (`cd frontend && npm run dev`, Node needs the portable-PATH export from task 8's notes) same as before.
- **Next task:** actually deploy to Render (finish task 11 — needs the human at the dashboard), then task 12 (docs pass: **README is still the onboarding-task template, not a project README** — real, confirmed gap from the earlier checkpoint, still not fixed; final `end-of-session.md` pass; PR).
- All work through this point is committed and pushed to `origin/yonatan_project` at `20cea84`.

## Do not regress (additions)
- Closed-list pickers (`TeamPicker`, `AssetPicker`) must keep drafting chat messages only — never call a mutating endpoint directly. If this pattern is extended (e.g. a picks picker, a remove-asset picker), keep the same constraint.
- The SSE idle-timeout (`STREAM_IDLE_TIMEOUT_MS` in `useTradeStream.ts`) must stay in place — it's the only thing standing between a dead connection and a permanently stuck chat UI.

## Continue from here
- **Repo:** done — own public repo, feature branch `yonatan_project`. No further action needed here.
- **Files present:** `docs/human-plan.md`, `docs/ai-plan.md`, this file, root `CLAUDE.md`, `requirements.txt`, `.gitignore`, `.env` (local only, gitignored, real key — not present in a fresh clone), `.env.example` (committed, placeholder), `backend/{__init__.py,config.py,catalog.py,contracts.py,state.py,providers.py,tools.py,llm.py,graph.py,cost.py,schemas.py,harness.py,main.py}`, `backend/tests/{test_catalog,test_state,test_contracts,test_providers,test_tools,test_graph,test_graph_live,test_cost,test_schemas,test_harness,test_main,test_golden}.py`, `frontend/` (React + Vite + TS), and now `golden/{__init__.py,cases.yaml,run_golden.py}`.
- **Next task:** AI Plan §12 **task 10 — Playwright happy path.** One browser test derived from the `legal_two_team` golden case, `PROVIDER=mock` (this time the *verdict provider* env var driving the real backend server the test drives — not to be confused with golden cases' own separate mock-provider-in-process usage). `docs/qa-plan.md` is also still outstanding — worth writing alongside this, since it's explicitly one of the 5 required delivery docs and hasn't been started. Then proceed tasks 11→12.
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
- **New this session — do not undo:** `harness.py`'s exception handler must keep logging the real error server-side and returning a generic message to the client; `SessionStore` must stay capacity-bounded; `ChatRequest` must keep length constraints on `session_id`/`message`; CORS methods/headers must stay explicit (not `["*"]`); the security-headers middleware in `main.py` must stay on all responses.

---

# Checkpoint — 2026-08-09: requirements re-evaluation, data-engineering review, security hardening

Before continuing to task 10, the human asked for a stop-and-check: re-read the original brief against the current state of the project, review it through a data-engineering/data-science lens, harden it against the OWASP-style "Top 10 2025" categories the human specified, and smoke-test that nothing broke. No new features were built; task 10/11 were deliberately **not** started — this was a checkpoint, not forward progress on the build order.

## Requirements re-evaluation (`gambit-onboarding-task.md` vs current state)

Read the full brief fresh against `docs/human-plan.md`, `docs/ai-plan.md`, and the repo as it stands. Findings:

- **Confirmed aligned:** the harness/tool-boundary requirement (the brief's explicit hardest-graded criterion) is met — NL flows through a phase-gated tool-calling loop, no regex/mega-prompt-JSON path exists anywhere. Verdict renders in prose in both chat and GUI. Explainability ("why illegal?") and traceability (trace strip) are both built and live-verified. Golden cases satisfy the brief's measurable-behavior ask.
- **Real gap found: `README.md` is still the onboarding-task's own README** (the one describing *this exercise*, pointing at `gambit-onboarding-task.md` and the workshop materials) — it was never replaced with a README describing *the built project* (architecture, how to run locally, how it's deployed, demo link). The brief and its acceptance checklist both require this ("README explains the project clearly enough for a stranger to run it"). Flagged for the task-12 docs pass, not fixed now — a real project README is nontrivial content, not a config tweak, and belongs with the other end-of-build docs work.
- **Confirmed still open, not a surprise:** `docs/qa-plan.md` (this session closes this gap — see below), the Playwright happy path (task 10, bonus criterion), and deployment (task 11) — all already tracked as pending in this file and in `CLAUDE.md`. Nothing newly broken, just re-confirmed still outstanding.
- **No scope drift found** against the deferred-scope list (Mem0, Supabase, model routing, Langfuse, 3+ teams, sign-and-trade, auth, mobile) — nothing in the current codebase re-introduces any of them.

## Data-engineering / data-science review

Reviewed the data flow end to end (catalog load → per-turn LLM calls → tool execution → validation → SSE) for efficiency and for whether anything belongs in a faster-retrieval store. Conclusions:

- **The catalog (`Catalog.load()`) is already the right pattern at this scale** — 30 teams / ~500 players / ~450 picks fits trivially in memory; preloading once at startup and resolving names locally (zero network calls per turn except `request_verdict`) is exactly what a cache/DB would buy you, without the operational cost of one. No change warranted; this validates `ai-plan.md`'s original design rather than finding a gap.
- **`VerdictCache` / durable storage remain correctly deferred.** Re-confirmed the reasoning in `human-plan.md`: `/trades/validate` is a free API call, and the expensive resource (LLM tokens) is spent *before* a validate call even happens, so a cache would save latency, not cost — not worth a DB for a single-session prototype. No change.
- **Real inefficiency found, not fixed this session (flagged for a future task, not urgent):** prompt caching (`llm.py`'s `_cached_system`) only marks a `cache_control` breakpoint on the **system+tools** prefix. The **conversation message history** — which grows every turn and is resent in full on every `interpret`/`respond` call — is never cached. Anthropic supports up to 4 cache breakpoints per request; adding one at the end of the prior turn's message history (i.e., caching "everything before this turn's new content") would let a long session's growing history hit the cache too, not just the static system+tools block. This compounds: a 10-turn conversation currently re-sends (and re-bills, at the non-cached rate) all 9 prior turns' worth of tokens on every subsequent call. Not implemented now because it touches the hot path of a fully-tested, live-verified core (`graph.py`/`llm.py`) and deserves its own golden-case re-verification pass rather than a drive-by edit during a security checkpoint — but it's the single highest-leverage "make the data stream more effective" lever available, and cheap once picked up (a few lines in `llm.py`, no new dependency).
- **`SessionStore` was genuinely unbounded** (a plain `dict`, never evicted) — this is both a data-engineering smell (unbounded in-memory growth with no lifecycle) and a security issue (see A06 below). Fixed this session: capacity-bounded with LRU-style eviction (see Security section).
- **Cost/usage data is currently ephemeral** (only ever lives in the SSE stream for the browser to render, never persisted). This is intentionally the `Langfuse`-deferred seam per `human-plan.md` — re-confirmed correct to leave deferred at prototype volume, not a gap.

## Security review — OWASP-style Top 10 2025

Reviewed the backend (`main.py`, `harness.py`, `graph.py`, `providers.py`, `tools.py`, `llm.py`) and frontend (`Chat.tsx`'s `react-markdown` usage) against each category the human specified. Fixed what was cheap and real; documented the rest as accepted risk for a prototype with no auth in scope.

| Category | Finding | Action |
|---|---|---|
| **A01 Broken Access Control** | `session_id` is client-supplied, unauthenticated, and never validated as belonging to any identity — by design (auth is explicitly out of scope, `human-plan.md`). Any client can address any session it can guess/reuse. | **Accepted risk**, not fixed — matches the brief's stated scope. Documented here so it isn't mistaken for an oversight later. |
| **A02 Security Misconfiguration** | CORS allowed `methods=["*"]`/`headers=["*"]`; no baseline response headers. | **Fixed** — `main.py`: CORS narrowed to `["GET","POST"]`/`["Content-Type"]`; added a `security_headers` middleware setting `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer` on every response. |
| **A03 Software Supply Chain Failures** | Backend deps already exact-pinned (`requirements.txt`, `==`). Frontend deps use caret ranges but `package-lock.json` is committed, so `npm ci` (already the documented install command) installs exact locked versions. No SAST/dependency-audit step exists. | **No code change** — pinning/lockfile discipline already correct. Documented `pip-audit` / `npm audit` as a recommended manual pre-release step in `docs/qa-plan.md`'s known gaps (no new dependency needed to run them). |
| **A04 Cryptographic Failures** | No data at rest requiring encryption (no DB); the only secret is `ANTHROPIC_API_KEY`, held in a gitignored `.env`, read from the environment, never logged or echoed (re-verified). HTTPS is Render's responsibility once deployed. | **No gap found.** |
| **A05 Injection** | No SQL, shell, or `eval` anywhere. Tool arguments from the model are pydantic-validated before touching any executor, and executors only do local dict/name lookups — never string-built queries or commands. The one injection-shaped surface (a user steering the model's *narration* via prompt injection) is already structurally bounded: the system prompt forbids inventing numbers, and every figure the model narrates is grounded in a real `Verdict`/tool-result payload it can't fabricate around — worst case is misleading prose, not a wrong verdict. | **No gap found** — this is a case where the existing pydantic-contracts design (built for correctness, not security) already closes the security-relevant version of the same problem. |
| **A06 Insecure Design** | Two real gaps: (1) `SessionStore` was unbounded — many distinct `session_id`s (malicious or just organic traffic) grow memory forever. (2) `ChatRequest.message` had no length limit — an oversized message is a cheap way to inflate a real, billed Anthropic call. | **Fixed** — `harness.py`: `SessionStore` now takes `max_sessions` (default 1000) and evicts the least-recently-touched session once full (`OrderedDict` + `move_to_end`). `main.py`: `ChatRequest.message` capped at 4000 chars, `session_id` at 200, both via pydantic `Field` (empty strings also now rejected). |
| **A07 Authentication Failures** | No authentication exists — by design, out of scope. Nothing found pretending to be auth that isn't (no fake security theater to correct). | **Accepted risk**, matches scope. |
| **A08 Software or Data Integrity Failures** | Verdict data integrity is already strong: pydantic contracts at every boundary mean a shape change in the real API fails a test, not silently. No CI pipeline exists to enforce this automatically on every push (out of scope per the brief — "you do not need a full CI pipeline"). | **No code change** — existing design already addresses the security-relevant part of this category; CI itself is explicitly not required. |
| **A09 Security Logging & Alerting Failures** | No logging existed anywhere in the backend — an unhandled exception was visible only as a string sent to the client (see A10) and left no server-side trace at all. | **Fixed** — `harness.py` now logs the full exception server-side (`logger.exception(...)`) before returning a generic message to the client, and logs session evictions at `info` level. This is the minimum viable "someone can find out what broke" without adding an external logging dependency. |
| **A10 Mishandling of Exceptional Conditions** | The single most concrete finding this session: `handle_chat`'s catch-all exception handler sent `str(exc)` — the raw Python exception text — directly to the browser as the error event's `message`. This can leak internals (library repr, partial stack detail) to any client who can trigger a server-side error. | **Fixed** — the client now always receives a fixed, generic message ("Something went wrong on our end. Please try again."); the real exception goes to the server log only (see A09). Verified via a new test (`test_harness.py`) that a `GraphRecursionError`'s class name never appears in the SSE stream. |

**Frontend note (checked, not a finding):** `Chat.tsx` renders the model's prose via `react-markdown` with no `rehype-raw` plugin installed — by default `react-markdown` does not render raw HTML/`<script>` tags from its input, so a prompt-injected "output raw HTML" attempt can't become a stored/reflected XSS. Confirmed this is the actual default behavior (no raw-HTML plugin is in `frontend/package.json`), not just an assumption.

**Tests added:** `test_harness.py` — session-store eviction (LRU-order + capacity), sanitized error message; `test_main.py` — oversized/empty message rejection (422), presence of baseline security headers. Full suite: 76 passed + 6 skipped without a key (was 71 + 6; the 5 new tests all pass with no key required — none of this touches the LLM-gated paths).

## Smoke test (post-hardening)

Ran the real server (`uvicorn`, real `ANTHROPIC_API_KEY`, real bball-GM) end to end after the changes above, not just the unit suite:
- `GET /api/health` → `200`, carries the new `x-content-type-options`/`x-frame-options` headers.
- `GET /api/teams` → real catalog data, unaffected.
- `POST /api/chat` with an empty `message` → `422`, clean pydantic validation error, no server involvement.
- `POST /api/chat` with a 4001-character `message` → `422`, same clean rejection.
- `POST /api/chat` with a real trade-building utterance ("Set up a trade between the Boston Celtics and the New York Knicks") → real Claude call, `set_teams` tool call fired, `state_diff` correct, `cost` events present, `assistant` narration correct, stream ended on `done`. Confirms the hardening changes didn't regress the live path, not just the mocked one.

Server stopped cleanly after verification; no process left running.

## Open questions (added this session)
- Prompt-cache breakpoint on growing conversation history (see data-engineering section) — worth a dedicated task with its own golden-case re-run, not done here.
- README replacement — deferred to task 12 as originally planned, but now explicitly confirmed (not assumed) to still be the template's README.

## Continue from here (updated)
- `docs/qa-plan.md` now exists — both automated and manual sections, per this session's explicit requirement that the QA plan cover both, not lean on one alone.
- Task 10 is now done (see below); next is task 11 (deploy) and task 12 (docs pass, including the README rewrite flagged above).
- No new environment setup needed beyond what task 8/9 already documented (portable Node + PATH export, `.venv` + `.env`).

---

# Playwright happy path (AI Plan §12 task 10) — done and live-passing, 2026-08-09

The brief's bonus automated-browser-test criterion. New root-level `package.json` (`@playwright/test`, separate from `frontend/package.json` — this is an e2e harness for the built app, not an app dependency, matching `ai-plan.md` §10's file layout), `playwright.config.ts`, `tests/happy_path.spec.ts`.

**Derived directly from `golden/cases.yaml`'s `legal_two_team` case** — same utterance, same expected tool sequence, same expected outcome — but proves something the golden-case eval structurally can't: that the real rendered UI (chat bubble + GUI mirror) agrees with itself, not just that the graph produced the right events. The test asserts the verdict card in chat (legal, no raw JSON in the bubble) *and* the trade panel (both team names, both assets, correct phase badge) independently, since the panel is populated via `state_diff` events and the chat verdict via the `verdict` event — two different code paths that could in principle drift.

`playwright.config.ts` uses a two-entry `webServer` array (backend `uvicorn` with `PROVIDER=mock` for deterministic CBA math + frontend `vite dev`) so `npx playwright test` boots both dev servers itself — no manual "start two terminals" step. `interpret`/`respond` still make real Anthropic calls (same reasoning as the golden cases: NLU is the thing under test, and there's no fake-LLM path wired into the real server), so this needs `ANTHROPIC_API_KEY` in the environment, same as the golden-case eval.

**Real bug hit and fixed, not a test-writing mistake:** the `webServer` backend command was written as `.venv/Scripts/python.exe -m uvicorn ...` (forward slashes, matching every other command in this repo's docs). Node spawns `webServer` commands through `cmd.exe` on Windows, and `cmd.exe` parsed the forward-slash path as `.venv` (the command) followed by `/Scripts/python.exe` (a switch-like argument), failing with `'.venv' is not recognized as an internal or external command`. Fixed by backslash-escaping that one command (`String.raw` template literal) — every other command in this repo is invoked through git-bash or a Python subprocess that doesn't have this quirk, so this is the first place Windows's `cmd.exe` path-parsing behavior actually mattered.

A second, expected fix: the initial selector `page.getByRole('button', { name: 'Send' })` matched 2 elements (the composer's submit button *and* the empty-state's example-prompt button, which starts with "Send Boston's...") — Playwright's strict mode correctly refused to guess. Fixed with `{ name: 'Send', exact: true }`.

**Live-verified, not just "it compiled":** ran `npx playwright test` for real against the live Anthropic + `MockProvider` (verdict math only) stack — real browser (Chromium), real SSE stream, real multi-tool-call turn (`set_teams` → `add_player` → `request_verdict` → narration). Passed in ~18s. Confirmed no leftover `uvicorn`/`vite` processes after the run (Playwright's `webServer` lifecycle tears both down cleanly).

Chromium was already cached locally from task 8's scratch Playwright install (`~/AppData/Local/ms-playwright/`), so `npx playwright install chromium` was a no-op this session — worth knowing if a fresh machine needs the ~150MB download the first time.

`.gitignore` gained `test-results/`, `playwright-report/`, `blob-report/`, `playwright/.cache/` (Playwright's own run artifacts — never meant to be committed, unlike the test file itself). Root `package-lock.json` is committed alongside `package.json`, matching the same pinning discipline as `frontend/`'s lockfile.

**Not done:** no CI wiring (out of scope — the brief doesn't require a full pipeline); no cross-browser matrix (Chromium only, documented as a known gap in `docs/qa-plan.md`).
