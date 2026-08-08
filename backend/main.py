"""FastAPI app (ai-plan.md §10): POST /api/chat (SSE), GET /api/health,
plus the built SPA at "/" (ai-plan.md §11 -- one Render service serves
both, so /trades/validate stays server-side, no CORS, no key in the
browser).
"""

from contextlib import asynccontextmanager
from pathlib import Path

import anthropic
import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .catalog import Catalog
from .config import PROVIDER
from .harness import SessionStore, handle_chat
from .llm import LLMClient
from .providers import BballGmProvider, MockProvider

# A single chat turn costs real Anthropic tokens -- an unbounded message
# body is a cheap cost-amplification and context-stuffing vector (A06:
# insecure design). 4000 chars is generous for a trade-building utterance
# and cheap to raise later if a real user ever hits it.
MAX_MESSAGE_LENGTH = 4000

# frontend/dist only exists after `npm run build` (task 11's deploy build
# step runs this; local API-only dev never needs to) -- mounting
# conditionally means `uvicorn backend.main:app` still works standalone
# against the Vite dev server (task 8's workflow) without a prior build.
FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http_client = httpx.AsyncClient()
    app.state.catalog = await Catalog.load(app.state.http_client)
    app.state.llm = LLMClient(anthropic.AsyncAnthropic())
    app.state.mock_provider = MockProvider(app.state.catalog)
    app.state.provider = (
        BballGmProvider(app.state.http_client) if PROVIDER == "api" else app.state.mock_provider
    )
    app.state.sessions = SessionStore()
    yield
    await app.state.http_client.aclose()


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],  # Vite dev server (task 8)
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    """Baseline hardening headers (A02: security misconfiguration). Cheap,
    no new dependency, and safe defaults for an app with no inline scripts,
    no third-party frames, and a single deploy origin serving both the API
    and the built SPA."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/teams")
async def list_teams(request: Request):
    """Catalog only reaches the frontend through SSE payloads, which carry
    team ids but not names (state_diff's snapshot is id-only -- see
    tools.py's _snapshot). Without this, the trade panel would have to
    show raw integers instead of "Boston Celtics"."""
    catalog: Catalog = request.app.state.catalog
    return [
        {"id": t.id, "name": t.name, "city": t.city, "abbreviation": t.abbreviation, "fullName": t.full_name}
        for t in catalog.teams.values()
    ]


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=200)
    message: str = Field(min_length=1, max_length=MAX_MESSAGE_LENGTH)


@app.post("/api/chat")
async def chat(req: ChatRequest, request: Request):
    state = request.app.state
    session = state.sessions.get_or_create(req.session_id)
    stream = handle_chat(
        session=session,
        user_text=req.message,
        catalog=state.catalog,
        provider=state.provider,
        llm=state.llm,
        mock_provider=state.mock_provider,
    )
    return StreamingResponse(stream, media_type="text/event-stream")


# Mounted last and at "/" -- FastAPI matches the /api/* routes above first
# for those exact paths, so this only ever serves the SPA's static assets
# and index.html (html=True serves index.html for "/" and any unmatched
# path, which is fine here: the app has no client-side router to conflict
# with, see frontend/src/App.tsx).
if FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="spa")
