# QA Plan — Chat-first NBA Trade Machine

**HAPI stage:** artifact for Human Review & QA (gates shipping)
**Siblings:** `docs/human-plan.md` (contract) · `docs/ai-plan.md` (how) · `docs/end-of-session.md` (handoff)
**Principle:** this plan leans on **both** manual and automated checks, not one at the other's expense — a script can assert "the tool call fired" but not "the prose reads naturally"; a human can judge tone but won't re-run 76 assertions before every merge. Neither alone is a QA plan.

---

## Scope

Ties to `docs/human-plan.md`'s acceptance criteria. This MVP claims to support:

- Two-team trades, built and refined across turns, via natural language only.
- Players **and** draft picks, including explicit re-routing.
- A verdict (legal/illegal, per-team salary math, violations, rule citations) rendered in **both** chat (prose) and the GUI mirror — never raw JSON.
- Resolution errors (ambiguous/typo names) surfaced as a chat turn, not a crash or silent failure.
- A per-turn trace ("what changed") and a per-turn cost badge.
- Real `bball-gm.com` validation, with a deterministic mock fallback badged `source: mock`.

Out of scope for this plan (see `human-plan.md`'s deferred-scope section for why): 3+ team trades, sign-and-trade, auth/multi-user, cross-session persistence, production-grade CBA coverage, load/performance testing.

---

## Automated checks

| # | Check | Command | What it proves |
|---|-------|---------|-----------------|
| 1 | Backend unit + integration suite | `.venv/Scripts/python.exe -m pytest backend/tests -q` | Catalog resolution, state/phase transitions, pydantic contracts, provider fallback, tool executors, LangGraph node wiring (via a scripted fake LLM — no network/cost), SSE formatting, session-store bounds, input-length rejection, security headers. Runs with **zero** external dependencies — no API key, no network. At time of writing: 76 passed, 6 skipped (the 5 golden cases + 1 live-graph test, both gated on a real key). |
| 2 | Golden-case eval | `.venv/Scripts/python.exe -m pytest backend/tests/test_golden.py -q` (or `python golden/run_golden.py` standalone) — needs `ANTHROPIC_API_KEY` | Replays 5 fixed utterance sequences through the **real** interpret/respond loop (real Claude calls) against `MockProvider` (deterministic CBA math). Asserts the tool-call subsequence and outcome: `legal_two_team`, `illegal_apron`, `pick_routing_refine`, `ambiguous_name` (resolution error, not a hallucinated player), `remove_asset`. This is the closest thing to an automated proof that NL → tool calls → verdict actually works end to end, without paying for a browser. |
| 3 | Live graph smoke test | `.venv/Scripts/python.exe -m pytest backend/tests/test_graph_live.py -q` — needs a key | One real round trip through all 4 nodes against the real Anthropic + bball-GM APIs — catches API/SDK drift the fake-LLM tests can't see. |
| 4 | Browser happy-path (Playwright) | `npx playwright test` (needs Node on PATH, `.venv` set up, and `ANTHROPIC_API_KEY` in the environment — see `playwright.config.ts`) | Derived from `legal_two_team`: boots both dev servers itself (`webServer` config, backend on `PROVIDER=mock`), drives a real Chromium browser through the full utterance, and asserts the GUI panel and chat verdict card independently agree on the final state — the only automated check that exercises the rendered frontend, not just the API/graph. Live-passing (~18s) as of 2026-08-09. |
| 5 | Manual-equivalent smoke script (used this session, worth keeping as a repeatable checklist, not yet a script) | `curl` the running server: `GET /api/health`, `GET /api/teams`, `POST /api/chat` with an empty message (expect `422`), with a >4000-char message (expect `422`), and a real short trade utterance (expect a full `tool_call → state_diff → assistant → done` SSE sequence) | Confirms the process boots, the catalog loads, input validation rejects malformed requests before they reach the model, and a real turn streams correctly — the fastest way to tell "is the deployed service actually alive" apart from "did a unit test pass." |

**Honest gap:** #4 covers one happy path, one browser, one viewport. It does not replace manual QA below — visual polish, dark mode, mobile stacking, and every non-happy-path branch (resolution errors, illegal verdicts, provider fallback) still rely on a human running the checklist.

---

## Manual checks

Run against the live URL once deployed (or `http://localhost:5173` locally with the backend on `:8000`). Each step names the expected result — if it doesn't match, that's a fail, not a judgment call.

1. **Load the app.** Chat shows an empty state with example prompts; GUI panel shows no teams. No console errors.
2. **"Set up a trade between the Boston Celtics and the New York Knicks."** GUI panel fills in both team names (not raw ids); chat replies in prose asking what to trade — no JSON visible anywhere.
3. **"Boston sends Neemias Queta to New York for Andre Drummond."** GUI shows both players under the correct Sending/Receiving side for each team; the "what changed" trace strip lists the tool calls that fired.
4. **"Get me a verdict."** A verdict appears in **both** chat (headline + per-team money card, collapsible CBA citations) and the GUI panel — the two must agree on legality and figures.
5. **Build an illegal trade** (e.g. an expensive player into an apron team with no matching salary back). The violation reason is stated in chat in plain language and the GUI shows illegal styling — never a silent failure, never a blank verdict.
6. **"Why is that illegal?"** Plain-language answer citing the failing team, the rule, and the shortfall — grounded in the verdict payload, not an invented number.
7. **Refine mid-conversation:** "route the pick to New York instead" / remove an asset. GUI updates immediately; verdict re-validates and can flip from legal→illegal or vice versa; the old verdict is visibly superseded, not left stale on screen.
8. **Ambiguous/typo name** (e.g. a misspelled player). A resolution error with suggestions appears in chat — not a crash, not a hallucinated player added to the trade.
9. **Nonsense asset** ("trade a bag of chips"). Model asks a clarifying question instead of inventing a tool call.
10. **Reload the page mid-conversation.** `session_id` persists via `localStorage`; the conversation and GUI state reload from the server. (If this doesn't hold, it's a real bug, not a scope gap — session persistence within a browser tab is in scope even though cross-device/cross-session persistence is explicitly deferred.)
11. **Resize to mobile width (<860px).** Layout stacks vertically, no horizontal scroll, trace/cost strip still usable.
12. **Toggle OS dark mode.** Text stays readable, verdict colors (legal/illegal) stay distinguishable.
13. **Cost/trace strip.** A token/cost badge appears every turn; collapsed by default, expands on click; a turn with zero tool calls doesn't show a confusing "(0 tool calls)" toggle.
14. **Provider fallback (dev-only).** Run with `PROVIDER=mock` (or block the bball-GM host) and confirm a verdict still returns, badged `source: mock`, instead of the turn dying.
15. **Security spot-checks:**
    - Submit an empty message → the composer should block it client-side (send button disabled); if bypassed, the server returns a clean validation error, not a hang or a raw traceback.
    - Paste a very long message (thousands of characters) → rejected gracefully (see automated check #5), not a frozen UI.
    - Open the browser's network tab during a forced error (e.g. kill the backend mid-turn) → confirm no API key, stack trace, or internal file path ever appears in a response body or the UI.
    - Confirm response headers on any request include `x-content-type-options: nosniff` and `x-frame-options: DENY`.

---

## Known gaps (honest scoping)

- **No automated cross-browser matrix** — the Playwright test targets Chromium at one viewport; manual check #11/#12 is the only cross-viewport/theme coverage.
- **No load or concurrency testing** — a prototype scoped to one demo session at a time; `SessionStore`'s capacity cap (see security notes below) is a safety net, not a performance guarantee.
- **No accessibility (a11y) audit** beyond semantic HTML and native form controls — screen-reader/keyboard-only walkthroughs are not part of this plan.
- **`MockProvider`'s CBA math is a simplified approximation**, explicitly badged and documented as non-authoritative — automated checks confirm it's *deterministic and internally consistent*, not that it matches every real CBA edge case beyond the two cases confirmed live in the API spike.
- **No SAST/dependency-vulnerability scan wired into CI** (there is no CI) — recommend `pip-audit -r requirements.txt` and `npm audit` (or `npm audit --omit=dev` for the deploy bundle) as a manual pre-release step; both are read-only and require no new runtime dependency.
- **No automated regression test for the security hardening added this session** (session-store eviction, message-length limits, sanitized error messages, security headers) beyond the new unit tests in `backend/tests/test_harness.py` and `test_main.py` — there's no browser-level or load-level proof the cap actually prevents memory growth under real concurrent traffic, only that the eviction logic is correct in isolation.

---

## Definition of "QA passed"

All automated checks (1–3, and 4 once built) green; all 15 manual checks confirmed on the live deployed URL by a human, in one sitting, without needing to re-explain the app to themselves first. If a manual step feels wrong but can't be named precisely, that's a signal to pause — not to check the box.
