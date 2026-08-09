# Gambit Trade Machine — Chat-first NBA Trades

Conversation is the primary way to build, refine, and validate a two-team, multi-asset NBA trade. Natural language flows through a bounded **LangGraph tool-calling harness** — never a regex parser, never a single mega-prompt returning JSON — and a GUI panel mirrors the resulting trade state live, in sync with chat.

**Live demo:** https://gambit-hapi-onboarding.onrender.com/

Built as a HAPI Flow onboarding exercise ([`gambit-onboarding-task.md`](./gambit-onboarding-task.md)). Full design reasoning lives in [`docs/human-plan.md`](./docs/human-plan.md) (the contract) and [`docs/ai-plan.md`](./docs/ai-plan.md) (the implementation plan); session-by-session decisions and known gaps are tracked in [`docs/end-of-session.md`](./docs/end-of-session.md).

---

## What it does

- Describe a trade in plain English — teams, players, draft picks, routing — and the assistant builds it turn by turn.
- Don't know exact names? Pick teams and assets from closed-list dropdowns instead of typing; either way, only the tool-calling loop ever touches trade state.
- Ask for a verdict: real salary-cap validation against [bball-GM](http://bball-gm.com)'s live API, with a deterministic mock fallback if it's ever unreachable (badged `source: mock`, never silently passed off as real).
- Illegal trades show the violation, the rule, and a plain-language explanation — in **both** chat and the GUI — never raw JSON, never a silent failure.
- A per-turn trace ("what changed") and a per-turn token/cost badge make every turn auditable.

## Architecture

```
 user message
      │
      ▼
┌─────────────┐  tool calls   ┌───────────────┐
│  interpret  │──────────────▶│ execute_tools │
│ (LLM + only │◀── loop while │  (pydantic-   │
│  the tools  │    building   │   validated)  │
│  valid for  │               └───────┬───────┘
│  the phase) │                       │ request_verdict
└──────┬──────┘                       ▼
       │ no tool call            ┌──────────┐
       │ (final answer)          │ validate │──▶ real bball-GM API,
       ▼                         │(Provider)│    mock fallback
      END                        └────┬─────┘
                                       ▼
                                  ┌──────────┐
                                  │ respond  │──▶ narrates the verdict
                                  │(narrate+ │    in prose, never JSON
                                  │  cost)   │
                                  └────┬─────┘
                                       ▼
                                      END
```

- **Phase-gated tools** (`EMPTY → TEAMS_SET → HAS_ASSETS`) — the model can only see `request_verdict` once two teams and at least one asset exist. Closed boundaries, enforced by the graph, not just prompted.
- **Every tool's arguments and the verdict response are pydantic-validated.** A bad or ambiguous name comes back as a structured, recoverable error the model can react to — never an exception, never a crash.
- **One event stream, three surfaces.** A turn emits `tool_call → state_diff → verdict → assistant → cost` over SSE; chat, the GUI mirror, and the trace/cost strip all render from the same stream, so they cannot desync.

## Stack

| Layer | Choice |
|---|---|
| Harness core | LangGraph state machine, 4 nodes (`interpret → execute_tools → validate → respond`) |
| Backend | Python / FastAPI |
| Model | Claude (Anthropic native tool use), single-model v1 behind an `LLMClient` seam |
| Contracts | Pydantic — every tool arg + the verdict response |
| Frontend | React + Vite (TypeScript) |
| Transport | Server-Sent Events (hand-rolled — `EventSource` can't POST) |
| Validation | Real `bball-gm.com/api/trades/validate`, deterministic mock fallback |
| Cost | Anthropic prompt caching + built-in per-turn token/USD accounting (zero extra deps) |

## Repo layout

```
backend/          FastAPI app, LangGraph harness, tools, providers, catalog, cost accounting
frontend/         React + Vite chat UI, GUI mirror, verdict card, trace/cost strip
golden/           Golden-case eval (fixed utterances -> expected tool sequence + verdict)
tests/            Playwright happy-path browser test
docs/             human-plan, ai-plan, qa-plan, end-of-session (the full design/decision trail)
render.yaml       Render Blueprint spec (see Deployment below for how this repo is actually deployed)
```

## Running locally

Requires Python 3.13 (pinned in `.python-version` — a newer default on some platforms has no prebuilt wheel for one of the pydantic dependencies yet) and Node 20+.

```bash
# clone and enter
git clone https://github.com/yonatanleitner-coder/gambit-hapi-onboarding.git
cd gambit-hapi-onboarding

# backend
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt      # .venv/bin/pip on macOS/Linux
cp .env.example .env                               # fill in a real ANTHROPIC_API_KEY
.venv/Scripts/python -m uvicorn backend.main:app --reload   # http://localhost:8000

# frontend (separate terminal)
cd frontend
npm install
npm run dev                                         # http://localhost:5173, proxies /api to :8000
```

Open `http://localhost:5173`. `PROVIDER=mock` in `.env` swaps the real bball-GM validation call for a deterministic local approximation (no network, no CBA-accuracy risk) — useful for offline work or the test suite below.

## Testing

```bash
# backend unit + integration suite (no API key needed; LLM calls use a scripted fake client)
.venv/Scripts/python -m pytest backend/tests -q

# golden-case eval -- real Anthropic calls, deterministic mock CBA math (needs ANTHROPIC_API_KEY)
.venv/Scripts/python -m pytest backend/tests/test_golden.py -q

# Playwright happy-path browser test (root-level, separate from the frontend app's own deps)
npm install                       # at repo root, once
npx playwright install chromium   # once
npx playwright test               # boots both dev servers itself
```

See [`docs/qa-plan.md`](./docs/qa-plan.md) for the full manual + automated QA checklist.

## Deployment

One Render web service serves both `/api/*` and the built frontend from the same origin (`backend/main.py` mounts `frontend/dist` once built) — no CORS, no API key ever reaching the browser.

**This repo is deployed via Render's "Public Git Repository" option**, not the `render.yaml` Blueprint flow the file otherwise documents — this repo's GitHub identity restricts third-party OAuth app authorization, so Render can't be granted the usual GitHub App access. Deploying from a public HTTPS URL sidesteps that entirely (`render.yaml` stays in the repo as the canonical settings reference; the values below are the same ones, just entered by hand):

1. Render dashboard → **New +** → **Web Service** → **Public Git Repository** → `https://github.com/yonatanleitner-coder/gambit-hapi-onboarding`, branch `yonatan_project`.
2. Build command: `pip install -r requirements.txt && cd frontend && npm ci && npm run build`
3. Start command: `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
4. Env vars: `ANTHROPIC_API_KEY` (secret), `PROVIDER=api`, `BBALL_GM_BASE=https://bball-gm.com/api`

One consequence of this path: no auto-deploy on push. New commits need a manual **Deploy latest commit** click in the Render dashboard. Free-tier services also spin down after 15 minutes idle — expect ~1 minute cold start on the first request after a quiet period.

The live URL above has passed a full smoke test against the real Anthropic + bball-GM APIs (health, security headers, catalog endpoints, input validation, and an end-to-end trade verified in both a raw API call and a real browser) — see [`docs/deployment-smoke-test.md`](./docs/deployment-smoke-test.md) for the complete results.

## Design notes & honesty about scope

This is Prototyper-stage work — it proves the harness + tool-boundary pattern, not a production trade engine. Deliberately deferred (each behind a named seam so it can be added later without rework): cross-session memory, durable trade/verdict storage, model routing beyond a single model, 3+ team trades, sign-and-trade, and any hand-rolled CBA logic (legality is delegated entirely to bball-GM's real API by design). Full reasoning for every cut is in [`docs/human-plan.md`](./docs/human-plan.md); what was actually built, what broke, and what's still open is in [`docs/end-of-session.md`](./docs/end-of-session.md).
