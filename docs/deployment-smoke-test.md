# Deployment smoke test — 2026-08-09

**Live URL:** https://gambit-hapi-onboarding.onrender.com/
**Deploy method:** Render "Public Git Repository" (not the `render.yaml` Blueprint flow — see `README.md`'s Deployment section for why), branch `yonatan_project`, commit `6bc71db`.
**Provider mode:** `PROVIDER=api` — real `bball-GM` validation, real Anthropic calls. No mocking anywhere in this run.

This is the first live check of the actual deployed instance, run immediately after the first successful Render build. Everything below was checked against the real public URL, not localhost.

## Pre-deploy issue (fixed before this run)

The first build attempt failed: Render defaulted to Python 3.14.3 (its current newest default), which has no prebuilt wheel for `pydantic-core==2.23.4`, so pip fell back to a source build via Rust/maturin — which then failed because Render's build filesystem is read-only for the cargo cache. Fixed by pinning `3.13.5` (the exact version already proven locally) via a `.python-version` file. See commit `6bc71db`. This smoke test is the first run against the build that succeeded after that fix.

## Results

| # | Check | Method | Result | Status |
|---|-------|--------|--------|--------|
| 1 | Health check | `GET /api/health` | `200`, `{"status":"ok"}` | ✅ Pass |
| 2 | Security headers present | Response headers on `/api/health` | `x-content-type-options: nosniff`, `x-frame-options: DENY`, `referrer-policy: no-referrer` all present | ✅ Pass |
| 3 | SPA served at root | `GET /` | `200`, `content-type: text/html` — built frontend served from the same origin as the API, as designed | ✅ Pass |
| 4 | Teams catalog loads | `GET /api/teams` | `200`, real 30-team list (Celtics, Knicks, etc. with correct ids/names) | ✅ Pass |
| 5 | Team-scoped assets (closed-list picker data) | `GET /api/teams/2/assets` | `200`, real Celtics roster (players + salaries) | ✅ Pass |
| 6 | Empty message rejected | `POST /api/chat` with `message: ""` | `422` | ✅ Pass |
| 7 | Oversized message rejected | `POST /api/chat` with a 4001-char message | `422` | ✅ Pass |
| 8 | Full real trade turn (API level) | `POST /api/chat`: *"Set up a trade between the Boston Celtics and the New York Knicks: Boston sends Neemias Queta to New York for Andre Drummond. Then get me a verdict."* | Correct tool sequence (`set_teams` → `add_player` ×2 → `request_verdict`), real bball-GM verdict (`source: "api"`, not mock) — **Legal trade**, correct salary figures for both teams, real CBA citations, coherent prose narration, stream ended cleanly on `done` | ✅ Pass |
| 9 | Same trade, real browser | Playwright against the live URL, same utterance typed into the actual composer | Verdict card renders in chat (legal, correct figures, CBA citations collapsible) **and** the GUI trade panel independently shows the same two teams/assets — reached via two different event types (`verdict` vs `state_diff`), confirming they didn't just coincidentally agree | ✅ Pass |
| 10 | Branding renders | Same browser session | Header shows the Gambit mark + "Gambit Trade Machine" title; landing page (on a fresh session) shows the full logo lockup, description, and team picker | ✅ Pass (visually confirmed via screenshot) |

**Real cost observed for check #9's full turn:** 13 events, **$0.0414** — consistent with local testing, confirms cost accounting works identically in production.

## Known gap, not tested here

- Cold start behavior (first request after 15 minutes idle) — this run happened to hit an already-warm instance (health check returned in 0.47s). Per Render's free-tier docs, the first request after idle should take roughly a minute; not independently re-verified against a genuinely cold instance in this pass.
- Cross-browser/mobile on the *deployed* URL specifically — covered locally (see `docs/qa-plan.md`'s manual checklist, checks 11–12) but not re-run against production in this pass.

## Conclusion

All 10 checks pass against the live, publicly reachable URL, using the real Anthropic API and the real bball-GM validation API — no mocking. The core deliverable (`chat → state → GUI mirror → verdict in both places`, reachable by a stranger without cloning anything) is confirmed working end-to-end in production.
