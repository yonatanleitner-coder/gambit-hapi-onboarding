# CLAUDE.md — Chat-first NBA Trade Machine

Project memory for Claude Code. Read `docs/human-plan.md` (the contract) and `docs/ai-plan.md` (the how) before executing. Current stage: **AI Execute**, in progress. Tasks 1–9 done (API spike, catalog + resolution, state + Phase + contracts, providers, LangGraph machine + tools, LLMClient caching + cost, SSE endpoint, frontend, golden cases) — see `docs/end-of-session.md`. Full stack is live-verified through a real browser and a real 5/5-passing golden-case eval (real Anthropic + real bball-GM). **Node.js needs a PATH export every session — see task 8 notes in end-of-session.md — it is not installed system-wide (no admin rights on this machine).** **`docs/qa-plan.md` is now written** (both automated + manual checks, per delivery requirement). A pre-task-10 checkpoint (2026-08-09) re-evaluated requirements against `gambit-onboarding-task.md`, reviewed the app from a data-engineering lens, and hardened it against the OWASP-style Top-10-2025 categories — see `docs/end-of-session.md`'s dated section for findings and fixes (sanitized error responses, bounded session store, input-length limits, tightened CORS, baseline security headers). **`README.md` is still the template's onboarding README, not a project README** — real gap, flagged for the docs pass (task 12). **AI Plan §12 task 10 (Playwright happy path) is now done** — live-passing, real browser + real Anthropic call. Gambit branding, a real landing page, and closed-list team/asset pickers (bball-GM-style) are also in, plus a real reliability fix (SSE stream could hang forever if the backend died mid-turn — now times out and recovers). See `docs/end-of-session.md`'s 2026-08-09 (continued) section. **AI Plan §12 task 11 is done — live and smoke-tested.** Deployed at https://gambit-hapi-onboarding.onrender.com/ (Render "Public Git Repository" path, not the Blueprint flow — this repo's GitHub identity restricts third-party OAuth apps, so the connect-a-repo flow wasn't available; see README's Deployment section). Two real deploy bugs hit and fixed: Render defaulting to Python 3.14 with no `pydantic-core` wheel (pinned `3.13.5` via `.python-version`), and nothing else. Full 10-check smoke test against the live URL — real Anthropic + real bball-GM, no mocking — passed; see `docs/deployment-smoke-test.md`. `README.md` has been rewritten (real project README, not the onboarding-task template) and includes the live link. Next: AI Plan §12 task 12 — final docs pass and PR.

## Goal
Conversation is the primary way to build, refine, and validate a two-team, multi-asset NBA trade. GUI mirrors chat state; verdicts render legibly in both. The deliverable proves a clean, bounded **LLM harness + tool boundary** — not a clever prompt.

## Non-negotiables (do not regress)
- NL → trade state flows through a **tool-calling loop**. **No** hardcoded string parsing. **No** single mega-prompt returning final JSON. These are disqualifiers.
- **Tools are the only state mutators.** Tool availability is **closed per phase** (`EMPTY → TEAMS_SET → HAS_ASSETS`); `request_verdict` unreachable until 2 teams + ≥1 asset.
- Verdict renders in **both chat and GUI**, in **prose** — never raw JSON. Illegal verdicts are never silent.
- Every tool arg + the verdict response is **pydantic-validated**; invalid args recover gracefully.

## Stack
- Backend: Python / FastAPI. Harness core: **LangGraph state machine, ≤5 nodes** (`interpret → execute_tools → validate → respond`).
- Frontend: React + Vite (TS). Live GUI mirror + verdict card + trace/cost strip.
- Model: Claude (Anthropic native tool use), **single-model v1** behind an `LLMClient` seam (`MODEL_POLICY` map) that allows per-task routing later.
- Validation: real `POST https://bball-gm.com/api/trades/validate` (open, no key) behind `VerdictProvider`; deterministic `MockProvider` fallback; badge `source`.
- Transport: SSE — `tool_call → state_diff → verdict → assistant → cost`.
- Cost: Anthropic **prompt caching** on the static system+tools prefix + built-in per-turn token/USD accounting (zero deps).
- Deploy: one Render web service (FastAPI serves built SPA + `/api`).

## Reference
- `bball-gm-engine-teardown.md` (repo root) — request/response schema. Two failure channels: `200 {isValid:false}` (salary/apron) vs `400 {error}` (hard rule).

## Deferred — keep deferred (named seams, not built in v1)
- Cross-session memory (Mem0) → `MemoryProvider`. Durable storage / verdict cache (Supabase) → `VerdictCache` (validation is free; a cache saves latency, not cost). Model routing → `MODEL_POLICY`. Langfuse → env-gated. Also out: 3+ teams, sign-and-trade, exceptions/TPE, auth, persistence, mobile.
- Do not re-add these without a stated reason. Filter for every addition: **lean and beneficial, not a flex.**

## Workflow
- Feature branch, never `main`. Small commits, especially before risky turns. Read the diff before pushing.
- Golden cases (`golden/cases.yaml`) are the measurable-behavior reference; keep `MockProvider` deterministic so they + the Playwright test stay stable.
- Update `docs/end-of-session.md` when pausing meaningful work.
