# Human Plan — Chat-first NBA Trade Machine

**HAPI stage:** Human Plan (the contract — written before heavy AI execution)
**Author:** Yonatan Leitner
**Date:** 2026-08-07
**Siblings:** `docs/ai-plan.md` (how) · `docs/end-of-session.md` (handoff) · `docs/qa-plan.md` (quality gate) · `README.md`

---

## Goal

**Build a chat-first interface to the bball-GM NBA Trade Machine where natural-language conversation is the primary way to construct, refine, and validate a two-team, multi-asset trade — with a live GUI that mirrors conversation state and verdicts (salary math, cap status, violations, CBA citations) rendered legibly in *both* chat and GUI.**

The point being proven is not a clever prompt. It is a clean, **bounded LLM harness**: the model reasons and chooses tools; my code does the deterministic work and owns the trade state. Tool availability is *closed per state* — a state machine decides which tools exist at each phase — and every tool boundary is a typed, validated contract. The mouse becomes optional; the GUI becomes a mirror.

## Why I'm the right person to plan this

I lead a data org and build agentic, tool-calling pipelines in production, so the harness/tool-boundary split is how I already work — the model reasons, deterministic tools mutate state. The HAPI premise (humans own the quality bar, AI owns throughput) maps directly onto how I run delivery. And I work in AML/fintech, where "trust and audit" is not a nice-to-have: a verdict a user can't trace is a verdict they can't act on. That's the exact bar Gambit names, so I'm treating **explainability, traceability, and bounded/measurable behavior as first-class**, not decoration.

*What I know that the agent does not:* the interesting risk here isn't CBA rules (the API owns those) — it's the interaction contract. Where state lives, how a turn mutates it under closed boundaries, how the model narrates a structured verdict without dumping JSON, and how a user reconstructs "what just changed." That's what I'm planning; the agent executes it.

## Problem framing

bball-GM.com is a conventional GUI trade builder: click teams, click players/picks onto each side, the app POSTs to a closed `/trades/validate` engine and renders a verdict with per-team money math and CBA citations. Legality lives server-side; the browser only presents. I am flipping the input model — **conversation drives state, GUI mirrors it** — while delegating all legality to bball-GM's real API.

---

## Scope — in

- **Two teams**, one trade at a time.
- **Players and draft picks**, with explicit **routing** ("route that 2027 first to New York instead").
- **Multi-turn building and refinement** — add, remove, re-route across turns.
- **A bounded state machine (LangGraph, ≤5 nodes)** driving the tool-calling loop, so the tools available to the model are *closed per phase* — e.g. `request_verdict` is unreachable until two teams and at least one asset exist. This is the "clear boundaries / specific tool calling" guarantee made enforceable.
- **Typed tool contracts (pydantic)** on every tool's arguments and on the verdict response — natural language resolves to *validated, standardized* structured intent; API drift fails loud.
- **Verdict in chat *and* GUI** — `summary`, per-team `salaryOut/In` + `netSalaryChange` + `newCapStatus`, `allowances`, `violations`, `appliedRules` citations.
- **Real bball-GM `POST /api/trades/validate`**, behind a `VerdictProvider` abstraction with a deterministic **mock fallback**.
- **User-facing traceability** — a visible trail per turn: *utterance → tool calls → state diff → verdict*.
- **Developer-facing cost visibility** — per-turn token + cost accounting computed from model usage (zero external deps), surfaced as a small badge in the trace. Prompt caching on the static system+tools prefix to cut real token cost.
- **Explainability on demand** — "why is this illegal?" answered in prose from the structured response, never raw JSON.
- **A golden-case set (4–6)** as the measurable behavior reference: fixed utterances → expected tool sequence → expected verdict outcome, replayed against the deterministic mock. Feeds the QA plan, a regression check, and the browser test.

## Deliberate scope — designed, not built (v1)

Naming what I'm *consciously* deferring is part of the plan. Each has a defined seam so it can be added without rework — the decision is scope, not capability.

- **Cross-session memory (Mem0).** Within a session, `TradeState` *is* the memory and it is authoritative; a fuzzy retrieval layer beside a deterministic state machine risks a second, non-authoritative source of state — against the whole "closed boundaries" thesis. Deferred behind a `MemoryProvider` seam; real value (user preferences/aliases across sessions) is future scope.
- **Durable trade storage / verdict cache (Supabase).** Validation is a *free* API and the expensive tokens are spent *upstream* of any cache key, so a cache saves latency, not cost — not worth a DB in a single-session prototype. Deferred behind a `VerdictCache` seam.
- **Model routing (cheap model for narration).** The `LLMClient` seam *allows* per-task routing, but v1 ships single-model: a second model is a second behavior surface the golden cases would have to police, for negligible prototype savings. One-line config change when it's worth it.
- **Langfuse.** Built-in cost accounting covers v1; Langfuse is the env-gated observability upgrade for aggregation at real volume.
- **3+ team trades, sign-and-trade, manual exception/TPE selection, salary overrides, auth/multi-user, persistence beyond in-memory session, mobile polish, and any CBA logic of my own** (explicitly out per brief).

---

## Interaction model & UX principles

- **Conversation is primary; the GUI is a read-only mirror.** The frontend holds no truth of its own — it renders server state — so it structurally cannot desync.
- **Every turn is legible.** After each turn the user sees what changed, why, and the resulting verdict.
- **Money and violations surface proactively** in chat on every verdict — never hidden behind a click.
- **Summarize by default, expand on demand.** Headline verdict + compact per-team money card inline; full CBA citations collapsed until asked for.
- **Errors are first-class and distinct.** `HTTP 200 {isValid:false}` (salary/apron matching) and `HTTP 400 {error}` (hard rules — Stepien, stretch, schema) get two different, plain-language messages. Neither is ever a silent failure.
- **No JSON is ever shown to the user.**

## Output presentation — concrete examples

*(Players and numbers below are illustrative; bball-GM data is synthetic.)*

**Legal trade.**
> **User:** "Boston sends Jaylen Brown to New York for Julius Randle and their 2027 first."

> **Assistant:** ✅ **Legal trade.** Here's the money:
> - **Boston** — out **$49.3M**, in **$33.1M** → **−$16.2M**, new total **$198.4M** *(below luxury tax)*
> - **New York** — out **$33.1M**, in **$49.3M** → **+$16.2M**, new total **$210.6M** *(Over First Apron)*
>
> New York absorbs the incoming salary under the first-apron 100% match. Want the CBA citations?

**Refine → illegal.**
> **User:** "Actually, route Boston's 2027 first to New York instead of the second-rounder."

> **Assistant:** ⛔ **That tips New York over.** With the swap, New York fails salary matching: sending **$57.1M**, receiving **$50.1M** — as a first-apron team they're capped at **100% of outgoing**, leaving them **$7.0M short**.
> **Rule applied:** Traded Player Exception, first-apron standard TPE *(CBA Art. VII §6(j))*.
> **Fixes:** add ~$7M of incoming salary to New York, or move a smaller contract out. Want me to try one?

The illegal verdict states the *failing team*, the *rule applied* (`allowances`), the *shortfall* (`violations`), and a *next action* — in prose, grounded in the structured response.

## Explainability & traceability

Two distinct trails, deliberately separated:

- **User-facing (traceability, graded):** every turn emits an ordered event trail — utterance → each tool call with args → state diff → verdict. Rendered as a collapsible "what changed" strip. This is the audit surface.
- **User-facing (explainability, graded):** the model narrates verdicts from structured fields; "why illegal?" cites failing team, rule applied, violation, and citation in plain language.
- **Developer-facing (cost, my addition):** per-turn model, token counts, cache savings, and USD — emitted into the same stream and shown as a small badge. This is *not* the rubric's traceability; it's a cost-awareness signal on top.

## Harness & tools (decision level — schema in `ai-plan.md`)

- A single **harness** owns the system prompt, message history, `TradeState`, and a **LangGraph state machine** (≤5 nodes) that runs a turn: interpret → execute tools → (validate) → respond, looping until resolved.
- **Phase gates tool availability** (`EMPTY → TEAMS_SET → HAS_ASSETS`), so the model can only call tools valid for the current state. Closed boundaries, enforced — not merely prompted.
- **Tools are the only mutators:** `set_teams`, `add_player`, `add_pick`, `route_pick`, `remove_player`, `remove_pick`, `request_verdict`. `add_*` writes both sides atomically so routing is never half-applied. Each tool's args are a **pydantic model**; validation failure is a recoverable structured error, not a crash.
- **NLU runs through the loop** — no hardcoded parsing, no single mega-prompt returning JSON. This is the primary thing under evaluation.
- **Catalog preloaded** (`/teams`, `/players`, `/draft-picks`) at session start; name→ID resolution is local, so the only per-turn network call is `request_verdict`.

## Sync model

One source of truth: server-side `TradeState` inside the graph. Chat and GUI both render from it. The turn streams `tool_call → state_diff → verdict → assistant → cost` events; the frontend applies them to chat, the GUI mirror, and the trace strip from the same stream.

---

## Acceptance criteria (testable, mapped to the brief's rubric)

- [ ] Natural language becomes trade state through a **tool-calling agentic loop** — no regex parsing, no single-JSON-return prompt.
- [ ] Tool availability is **closed per state** via the LangGraph machine; `request_verdict` is unreachable before preconditions hold.
- [ ] Every tool boundary is **pydantic-validated**; invalid args recover gracefully; verdict response validated against schema.
- [ ] A user can build a two-team trade with **players + picks by conversation alone**; the mouse is optional.
- [ ] **"Route the pick to X instead"** updates state and re-validates mid-conversation.
- [ ] The **GUI reflects state after every turn** — no desync (single source of truth).
- [ ] The **verdict appears in both chat** (prose + compact card) **and GUI** (per-team cards).
- [ ] **Illegal trades show the violation reason in chat** — never a silent failure or raw JSON.
- [ ] **"Why is this illegal?"** yields a prose explanation grounded in `violations` / `allowances` / `appliedRules`.
- [ ] A **per-turn trace** (what changed) is visible; a **per-turn cost badge** is shown.
- [ ] **Prompt caching** applied to the static system+tools prefix.
- [ ] **Golden cases (4–6)** pass against the deterministic mock provider.
- [ ] Deployed at a **public URL on Render free tier**.
- [ ] **Bonus:** real bball-GM API used, mock fallback proven.
- [ ] **Bonus:** one Playwright happy-path test (derived from a golden case).
- [ ] `docs/human-plan.md`, `docs/ai-plan.md`, `docs/end-of-session.md`, `docs/qa-plan.md`, `README.md` all committed.

## Assumptions & risks (detail in `ai-plan.md`)

- **API reachability/shape** — validated by a first-task spike; de-risked by the `VerdictProvider` fallback.
- **Name-resolution ambiguity** — mitigated by the preloaded catalog and model disambiguation.
- **Graph over-engineering** — hard cap at ≤5 nodes; if the graph grows or fights the framework, drop to a hand-rolled FSM (the brief permits it and it's more transparent at this size).
- **Render free-tier cold start** (~30–60s first hit) — documented; not a correctness issue.

## Definition of done

A reviewer opens the URL, types a two-team trade in plain English, watches the GUI fill in, gets a verdict in **both** chat and panel, asks **"why,"** gets a plain-language answer, refines with **"route the pick to New York instead,"** sees it re-validate and flip to illegal with the reason shown — **without ever touching the trade-builder controls.** The trace strip shows what changed and what the turn cost. The mouse stayed optional.

## Handoff to AI Plan

`docs/ai-plan.md` turns this contract into the implementation I approve: the LangGraph node/edge design and phase gates, pydantic tool contracts, `TradeState` model, `VerdictProvider` real/mock, prompt caching + cost accounting, golden-case runner, file layout, deploy config, and the deferred seams. I own the goal and quality bar above; the AI proposes the how and I approve or correct it.
