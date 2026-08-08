"""FastAPI app (ai-plan.md §10): POST /api/chat (SSE), GET /api/health.

Serving the built SPA is task 8/11's job -- frontend/dist doesn't exist
yet, so no StaticFiles mount here (it would fail at startup against a
missing directory anyway).
"""

from contextlib import asynccontextmanager

import anthropic
import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .catalog import Catalog
from .config import PROVIDER
from .harness import SessionStore, handle_chat
from .llm import LLMClient
from .providers import BballGmProvider, MockProvider


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
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health():
    return {"status": "ok"}


class ChatRequest(BaseModel):
    session_id: str
    message: str


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
