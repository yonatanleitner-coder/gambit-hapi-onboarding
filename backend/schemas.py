"""SSE event envelope validation (ai-plan.md §8).

A lightweight safety net at the transport boundary -- catches a misnamed
or malformed event before it hits the wire. It does not re-validate each
event's own payload shape; those already validate at their source
(Verdict is pydantic, cost_event() is a pure builder, tool results are
plain dicts checked by their own callers).
"""

from typing import Literal

from pydantic import BaseModel


class SSEEvent(BaseModel):
    event: Literal["tool_call", "state_diff", "verdict", "assistant", "cost", "error", "done"]
    data: dict
