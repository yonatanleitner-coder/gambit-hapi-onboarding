import pytest
from pydantic import ValidationError

from backend.schemas import SSEEvent


def test_accepts_every_documented_event_name():
    for name in ["tool_call", "state_diff", "verdict", "assistant", "cost", "error", "done"]:
        SSEEvent(event=name, data={})


def test_rejects_unknown_event_name():
    with pytest.raises(ValidationError):
        SSEEvent(event="not_a_real_event", data={})


def test_rejects_non_dict_data():
    with pytest.raises(ValidationError):
        SSEEvent(event="assistant", data="not a dict")
