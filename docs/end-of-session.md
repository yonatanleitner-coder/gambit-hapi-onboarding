# End of session — 2026-08-08

## Goal
Build a chat-first interface to the bball-GM NBA Trade Machine where conversation is the primary way to construct, refine, and validate a two-team, multi-asset trade, with a live GUI mirror and verdicts rendered legibly in both chat and GUI — proving a clean, bounded LLM harness + tool boundary, not a clever prompt. See `docs/human-plan.md`.

## Status
- **Done:** Human Thinking (MVP scoped via clarifying questions). `docs/human-plan.md` and `docs/ai-plan.md` drafted, revised once, and current. Full API contract confirmed from `bball-gm-engine-teardown.md`. **AI Plan §12 task 1 (API spike) complete** — see below.
- **In progress:** AI Plan → AI Execute gate cleared for task 1 only; tasks 2–12 not started. Three low-stakes steers still open (see Open questions).
- **Blocked / not started:** No application code yet. `docs/qa-plan.md` and this file's final version are downstream.
- **Repo housekeeping:** `origin` was already `yonatanleitner-coder/gambit-hapi-onboarding` (own repo, not the `gambit-lab` template) on feature branch `yonatan_project` — the repo-creation step was already done, correcting a stale note in an earlier version of this file. Docs and `CLAUDE.md` relocated from `claude-git-workshop/Docs/` to root `docs/` + root `CLAUDE.md` to match the delivery spec (project root, alongside `backend/`/`frontend/` to come); unrelated instructor-workshop PDFs/Figma file stayed in `claude-git-workshop/`.

## API spike (AI Plan §12 task 1) — done, 2026-08-08
Three live calls against `POST https://bball-gm.com/api/trades/validate`, no mock — confirmed against `bball-gm-engine-teardown.md` field-for-field, **no schema drift found**:
- **Legal** — real IDs (team `2` Celtics/BOS, team `20` Knicks/NYK, players `16998` Neemias Queta ↔ `17338` Andre Drummond) → `200 {isValid:true, ...}`, full shape as documented.
- **Illegal** — same teams, player `17329` Paul George for Drummond (deliberately lopsided) → `200 {isValid:false, ...}`; confirms `isValid` exists both top-level *and* per-team, with `violations` populated only for the failing team.
- **Hard error** — 1-team request (API requires ≥2) → `400 {"error": "..."}`.
- **Nuance not obvious from the doc:** the `400` channel's `error` value is sometimes a JSON-stringified Zod issue array, not guaranteed prose. Pinned in the schema's docstring so `respond` doesn't assume it's directly narratable — needs a plain-language wrapper, not a pass-through.
- **Schema pinned** in `contracts.py` (`TeamLeg`, `ValidateRequest`, `TeamVerdict`, `Verdict`, `ApiHardError`) — currently in the session scratchpad only, not yet in a repo (see Continue from here).

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

## Open questions
- **Model tier** (AI Plan §14): Sonnet for both nodes (default) or Opus for `interpret`?
- **Token streaming:** event-level only (default) or stream assistant tokens too?
- **Trace + cost strip:** collapsed-by-default (default) or always visible?
- **Human Plan edits:** replace illustrative money figures with real synthetic values (backfill from `GET /api/players` during the API spike); confirm the "why I'm the right person" framing reads in the author's voice.

## Continue from here
- **Repo:** done — own public repo, feature branch `yonatan_project`. No further action needed here.
- **Files present:** `docs/human-plan.md`, `docs/ai-plan.md`, this file, root `CLAUDE.md`. App not started. `contracts.py` (pinned schema from the spike) sits in the session scratchpad, not yet committed — move it into `backend/contracts.py` when task 3 (state + contracts) scaffolds the backend.
- **Next task:** AI Plan §12 **task 2 — catalog + resolution.** Preload `/teams`, `/players`, `/draft-picks`; fuzzy name→id resolution with suggestions. Then proceed tasks 3→12.
- **Reference:** `bball-gm-engine-teardown.md` (repo root) — request/response schema, confirmed live in the task 1 spike with no drift. Base URL `https://bball-gm.com/api` (open, no key).
- **Commands:** none yet (scaffold in task 3+).
- **Demo URL:** none yet.

## Do not regress
- NL → trade state must flow through the **tool-calling loop**. No hardcoded string parsing. No single mega-prompt that returns final JSON. (These are the brief's explicit disqualifiers.)
- **Tools are the only state mutators;** tool availability stays **closed per phase**.
- Verdict renders in **both chat and GUI**, in prose; illegal verdicts are never silent and never raw JSON.
- Keep `VerdictProvider` fallback + `source` badge; keep `MockProvider` **deterministic** (tests depend on it).
- Keep the deferred items deferred — don't let Mem0 / Supabase / routing / Langfuse creep back without a stated reason.
- Graph stays ≤5 nodes.
