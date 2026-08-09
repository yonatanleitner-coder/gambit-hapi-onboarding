# End of session — 2026-08-09 (final)

## Goal
Build a chat-first interface to the bball-GM NBA Trade Machine where conversation is the primary way to construct, refine, and validate a two-team, multi-asset trade — with a live GUI mirror and verdicts rendered legibly in both chat and GUI, proving a clean, bounded LLM harness + tool boundary, not a clever prompt. See [`docs/human-plan.md`](./human-plan.md).

## Status

**Done — all 12 build-order tasks from `docs/ai-plan.md` §12, plus deployment:**

1. API spike — three live calls against `bball-gm.com/api/trades/validate` (legal, illegal, hard-error), schema pinned in `contracts.py`, no drift vs. the teardown doc.
2. Catalog + resolution — preloaded teams/players/picks (30/506/443 live), 4-tier name resolution (exact → substring → fuzzy → error+suggestions).
3. State + Phase + pydantic contracts — `TradeState`/`Phase`/`Asset`, tool-arg models, `Verdict`/`ValidateRequest` pinned against the real API shape.
4. Providers — real `BballGmProvider` + deterministic `MockProvider` fallback, badged `source`.
5. LangGraph harness + tools — 4 nodes (`interpret → execute_tools → validate → respond`), phase-gated tool availability, 7 executors, pydantic-validated everywhere.
6. `LLMClient` — prompt caching on the system+tools prefix, per-turn token/cost accounting, zero external deps.
7. SSE endpoint — full `tool_call → state_diff → verdict → assistant → cost → error → done` contract, real incremental streaming.
8. Frontend — React + Vite, custom design system, dark mode, responsive layout.
9. Golden cases — 5 cases, real Anthropic + deterministic mock CBA math, all passing live.
10. Playwright happy-path test — derived from the `legal_two_team` golden case, boots both dev servers itself.
11. Deploy — live at **https://gambit-hapi-onboarding.onrender.com/**, 10-check smoke test passed against the real URL (`docs/deployment-smoke-test.md`).
12. Docs pass — this file, `docs/qa-plan.md`, `README.md` all current; PR next.

**Later additions beyond the original 12 tasks**, done in response to direct human requests after the build order was "complete": a security hardening pass (OWASP-style Top 10 2025 review), Gambit branding + a real landing page + closed-list team/asset pickers, and a stream-reliability fix (SSE could hang forever if the backend died mid-turn).

**Not done / deliberately out of scope:** see "Deliberate scope — designed, not built" in `docs/human-plan.md` (Mem0/cross-session memory, durable storage/verdict cache, model routing beyond the seam, Langfuse, 3+ team trades, sign-and-trade, auth, mobile polish, any hand-rolled CBA logic). Nothing in that list crept back in.

**Test status:** 79 passed, 6 skipped without `ANTHROPIC_API_KEY` (5 golden cases + 1 live-graph test); all pass with one set. Playwright happy-path passing live (~18–24s).

## Key decisions

- **LangGraph over a hand-rolled loop**, kept to 4 nodes — the explicit goal of closed, phase-bound tool availability made the graph earn its complexity. (Original plan allowed hand-rolling as a fallback if the graph fought the framework; never needed.)
- **Pydantic contracts at every boundary** (tool args, verdict response) — API drift fails a test, not silently; this caught the real `isSignAndTrade: null` serialization bug (see below) before it shipped.
- **Real bball-GM API as the source of legality truth**, `MockProvider` only for fallback + deterministic tests/golden-cases/Playwright — never treated as authoritative, always badged.
- **Closed-list pickers (TeamPicker, AssetPicker) only draft chat utterances**, never mutate state directly — added later per a direct human request ("give the user a closed list, like bball-GM"), but kept to the same tool-boundary rule as everything else: tools are the only mutator, full stop.
- **Cost/cache seam, not a cost subsystem** — single-model `LLMClient` with a `MODEL_POLICY` map; prompt caching only covers the static system+tools prefix today (see Open questions — the growing conversation history is the next lever, not yet pulled).
- **Deploy via Render's "Public Git Repository" path, not the `render.yaml` Blueprint flow** — the human's GitHub identity is under an org that restricts third-party OAuth app authorization, so the normal "connect your repo" flow was never available. This clones over a plain HTTPS URL instead, needing no GitHub permission at all. Trade-off: no auto-deploy on push, settings entered by hand (matching `render.yaml` exactly) instead of blueprint auto-detection.

### Real bugs found and fixed (chronological, all confirmed live before being called done)
- Fuzzy name matching coincidentally matched short strings (`resolve_team("Queta")` → Jazz via `"uta"` abbreviation) — excluded candidates under 5 chars from the fuzzy tier.
- `TeamLeg.model_dump()` sent explicit JSON `null` for `isSignAndTrade`; the live API rejects an explicit null for that optional field (wants it omitted) — fixed with `exclude_none=True`.
- An early graph draft routed no-tool-call responses through `respond` for a redundant second LLM call — caught by a fake-LLM test running out of scripted responses; `interpret` now ends the turn directly when there's no tool call.
- `resolve_pick` silently returned the first-iterated match when a team held two picks for the same year+round (a real scenario — a team's own 1st plus another team's via trade) — now returns a `ResolutionError` with both descriptors, same as a name conflict.
- `resolve_pick`'s parser only matched exact tokens (`"first"`), failing on natural phrasing like `"2027 first-round pick"` — switched to word-boundary regex.
- A flexbox `min-height: auto` default prevented `.chat`/`.chat__list` from shrinking to fit, so the app grew taller than the viewport instead of scrolling internally — caught by comparing `scrollHeight` to `clientHeight` after a long Playwright-driven conversation, not visible in a short screenshot.
- `formatUsd` showed `<$0.01` for exactly `$0`.
- The per-message "what changed" toggle counted the `cost` event (which fires every turn) toward its tool-call count, showing a confusing "(0 tool calls)" on turns that changed nothing.
- **Stream could hang forever**: restarting the backend mid-conversation left the frontend's `fetch()` reader waiting indefinitely for bytes that would never arrive (a dead connection isn't always signaled cleanly through Vite's dev proxy) — the UI showed a half-written message with the "thinking" indicator stuck on permanently, no error, no recovery. Root-caused live (not guessed) after ruling out `max_tokens` truncation by reproducing similar exchanges and checking actual token counts. Fixed with a 30-second inactivity timeout on the SSE stream, reset on every frame, that aborts and shows a recoverable error instead of hanging. Verified by scripting an actual backend kill mid-turn and confirming recovery.
- **First deploy attempt failed**: Render defaulted to Python 3.14.3 (its current newest default), which has no prebuilt wheel for `pydantic-core==2.23.4`, forcing a source build via Rust/maturin that then failed on Render's read-only build filesystem. Fixed by pinning `3.13.5` (the exact version already proven locally) via `.python-version`, confirmed against Render's docs as the correct mechanism before making the change.

### Security hardening (OWASP-style Top 10 2025 review, done as a mid-project checkpoint)
Reviewed all 10 categories against the running app. Fixed what was real and cheap: sanitized the catch-all exception handler (was leaking raw Python exception text to the client — now logged server-side only, generic message to the client), bounded `SessionStore` with LRU eviction (was unbounded — memory-exhaustion risk from unauthenticated, client-supplied `session_id`s), capped `ChatRequest.message`/`session_id` length (cost-amplification risk against a real billed API), narrowed CORS from wildcard methods/headers, added baseline security response headers. Auth (A01/A07) confirmed correctly out of scope per `human-plan.md`, not a gap. Full findings in git history (commit `ac8b66d`) — not reproduced in full here since none of it changes day-to-day usage.

## Human guidance given (across the whole project)
- **"Lean and functional, benefits not flex"** — the decisive filter behind every deferral in `human-plan.md`. Held throughout, including when reviewing security/data-engineering findings (fixed the cheap, real ones; documented the rest as accepted risk rather than over-building).
- Verdict must appear in **both** chat and GUI, in prose — never raw JSON; illegal verdicts never silent. Explainability + traceability treated as first-class (author works in AML/fintech — "trust and audit" is not decoration).
- **Keep the auto-resolve behavior** on high-confidence typo matches, overriding `ai-plan.md`'s stricter worked example — a deliberate, flagged deviation, not an oversight.
- **"Make sure it looks nice"** (frontend build) — taken as a real requirement: full custom design system, dark mode, responsive layout, actual browser-driven visual verification before calling it done.
- **"I want to see the actual app, open a window"** — live browser verification became the standard for every feature after this, not just build-checks or unit tests.
- Caught the stuck-stream bug themselves through direct use of the running app, not a prepared test case — surfaced by describing the symptom precisely enough ("stuck on point 2: thinking spinner never resolves") to root-cause without more guessing.
- Flagged the real deploy blocker precisely (GitHub org OAuth-app restriction) rather than leaving it as "Render doesn't work," which let the fix (Public Git Repository path) be targeted instead of a broad platform switch.
- Explicit requirement: QA plan must cover **both** automated and manual checks, not lean on one alone.

## Open questions
- **Prompt-cache breakpoint on growing conversation history** — currently only the static system+tools prefix is cached; a long session re-bills the same prior turns' tokens on every call. Identified as the single highest-leverage remaining "make the data stream more effective" lever, deliberately not touched since it hits the tested hot path (`graph.py`/`llm.py`) and deserves its own golden-case re-verification pass, not a drive-by edit.
- **`docs/architecture-diagram.pdf`** — generated early in the project, still deliberately untracked (never committed) pending a decision on whether to include it.
- **Human Plan's illustrative dollar figures** were never backfilled with real synthetic values from the live catalog (a nice-to-have noted early on) — left as is since they're already clearly labeled illustrative and the plan is treated as a fixed contract snapshot, not something to retroactively polish.

## Continue from here
- **Everything is committed and pushed** to `origin/yonatan_project` (own repo, not the `gambit-lab` template). Latest: `af843fe`.
- **Live URL:** https://gambit-hapi-onboarding.onrender.com/ — remember it needs a **manual redeploy** (Render dashboard → Deploy latest commit) after any further commits; this deploy path doesn't auto-deploy on push.
- **Local dev:** `python -m venv .venv && .venv/Scripts/pip install -r requirements.txt`, copy `.env.example` → `.env` with a real `ANTHROPIC_API_KEY`, `uvicorn backend.main:app --reload` (backend, `:8000`) and `cd frontend && npm install && npm run dev` (frontend, `:5173`). Full instructions in `README.md`.
- **Remaining work:** open the PR (`yonatan_project` → this repo's own `main`, never the `gambit-lab` template) with the description template from `gambit-onboarding-task.md`'s Delivery section — Human Plan summary, AI Plan summary, pointer to this file, QA approach (link `docs/qa-plan.md`), a HAPI Flow reflection (human's own voice), and the live URL.

## Do not regress
- NL → trade state flows through the **tool-calling loop** only. No hardcoded string parsing, no single mega-prompt returning final JSON.
- **Tools are the only state mutators**; tool availability stays **closed per phase**. This includes the closed-list pickers — they draft chat messages, they never call a mutating endpoint directly.
- Verdict renders in **both chat and GUI**, in prose; illegal verdicts are never silent, never raw JSON.
- Keep `VerdictProvider` fallback + `source` badge; keep `MockProvider` **deterministic** (tests depend on it).
- Keep the deferred items deferred (Mem0, Supabase, model routing, Langfuse, 3+ teams, sign-and-trade, auth, hand-rolled CBA logic) — don't let them creep back without a stated reason.
- Graph stays small (currently 4 nodes).
- `SessionStore` stays capacity-bounded; unhandled exceptions stay sanitized to the client and logged server-side; `ChatRequest` keeps its length limits; the SSE idle-timeout (`STREAM_IDLE_TIMEOUT_MS` in `useTradeStream.ts`) stays in place.
- `.python-version` (3.13.5) stays pinned — Render's rolling default will otherwise drift onto a Python version without a `pydantic-core` wheel again.
