# CLAUDE.md — Chat-first NBA Trade Machine

Project memory for Claude Code. Read `docs/human-plan.md` (the contract) and `docs/ai-plan.md` (the how) before executing. Current stage: **AI Execute**, in progress. Tasks 1–6 done (API spike, catalog + resolution, state + Phase + contracts, providers, LangGraph machine + tools, LLMClient caching + cost) — see `docs/end-of-session.md`. Harness is live-verified end-to-end (real Anthropic + real bball-GM), including a confirmed prompt-cache hit. Next: AI Plan §12 task 7 (SSE endpoint — first real app scaffolding beyond `backend/`).

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
