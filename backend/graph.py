"""The LangGraph state machine -- the graded core (ai-plan.md §4).

    interpret --(tool calls)--> execute_tools --(more building)--> interpret
       |                              |
       |(no tool calls: this text     |(request_verdict succeeded)
       | IS the turn's answer)        v
       v                          validate --> respond --> END
      END                       (narrates the verdict/hard_error
                                  into prose -- the one thing
                                  interpret never saw)

Four nodes, matching ai-plan.md's node list exactly, with two deliberate
implementation choices beyond the literal diagram (both noted in
docs/end-of-session.md):

1. interpret ends the turn directly when it returns no tool calls, instead
   of routing through respond. Its own text (a disambiguation question, a
   "why illegal" answer from prior context, general conversation) already
   IS the turn's answer -- routing it through a second LLM call in respond
   would be a redundant call for no benefit. respond exists specifically
   to narrate *structured* data (a Verdict or hard-error) that interpret
   never had access to, since that data doesn't exist until after
   validate runs.
2. request_verdict is still routed through execute_tools (as a no-op
   mutator with a defense-in-depth phase check) rather than
   short-circuiting directly from interpret, so a turn that mixes
   building calls and request_verdict in one LLM response (multi-intent
   is fine per ai-plan.md §4) still applies the building calls before
   checking whether a verdict was requested.

NOT YET LIVE-TESTED against a real model (no ANTHROPIC_API_KEY this
session) -- see llm.py and backend/tests/test_graph.py, which exercises
this graph with a fake LLM client.
"""

import json
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph

from .catalog import Catalog
from .contracts import Verdict
from .llm import LLMClient
from .providers import HardRuleViolation, ProviderUnavailable, VerdictProvider
from .state import TradeState
from .tools import execute_tool, tools_for_phase

SYSTEM_PROMPT = """You are the trade-building assistant for a two-team NBA \
trade machine. Conversation is the only way the user builds a trade -- \
there is no other input method.

Rules you must never break:
- Only use the tools you are given for the current phase; do not claim to \
do things you have no tool for.
- Never assert a trade is legal or illegal without calling request_verdict \
and getting a verdict back.
- Never invent salary, cap, or rule numbers. Only cite figures that appear \
in a tool result or the verdict.
- If a tool returns an error, explain it to the user or ask a clarifying \
question -- do not retry the exact same call unless you have new \
information (e.g. a corrected name from the user)."""

RESPOND_SYSTEM_PROMPT = """You narrate trade state, verdicts, and errors \
in plain prose for a chat UI. Never show JSON or code blocks. Ground every \
number and rule citation in the structured data you're given -- never \
invent one. Money and violations must be surfaced proactively, not hidden \
behind a follow-up question."""


def _append(existing: list, new: list) -> list:
    return existing + new


class GraphState(TypedDict):
    messages: Annotated[list[dict], _append]
    events: Annotated[list[dict], _append]
    trade: TradeState
    catalog: Catalog
    provider: VerdictProvider
    mock_provider: VerdictProvider | None
    llm: LLMClient
    pending_tool_uses: list
    verdict_requested: bool
    verdict: Verdict | None
    hard_error: dict | None


def _tool_result(tool_use_id: str, result: dict) -> dict:
    return {"type": "tool_result", "tool_use_id": tool_use_id, "content": json.dumps(result)}


async def interpret(state: GraphState) -> dict:
    trade: TradeState = state["trade"]
    tools = tools_for_phase(trade.phase())
    response = await state["llm"].create(
        task="interpret", system=SYSTEM_PROMPT, messages=state["messages"], tools=tools,
    )
    tool_uses = [b for b in response.content if b.type == "tool_use"]
    events = [{"event": "tool_call", "data": {"name": b.name, "args": b.input}} for b in tool_uses]
    if not tool_uses:
        # Final intent with no tool call (disambiguation question, answering
        # "why illegal" from prior context, general conversation) -- this
        # text already IS the turn's answer. Ending here instead of routing
        # through respond avoids a second, redundant LLM call: respond
        # exists to narrate *structured* data (a verdict/hard_error) that
        # interpret never saw, not to re-narrate text interpret already
        # produced. See docs/end-of-session.md for this deviation from the
        # ai-plan.md §4 diagram.
        text = "".join(b.text for b in response.content if b.type == "text")
        events.append({"event": "assistant", "data": {"text": text}})
    return {
        "messages": [{"role": "assistant", "content": response.content}],
        "pending_tool_uses": tool_uses,
        "events": events,
    }


def route_after_interpret(state: GraphState) -> str:
    return "execute_tools" if state["pending_tool_uses"] else "done"


async def execute_tools(state: GraphState) -> dict:
    trade, catalog = state["trade"], state["catalog"]
    tool_results, diff_events = [], []
    verdict_requested = False

    for block in state["pending_tool_uses"]:
        result = execute_tool(block.name, block.input, trade, catalog)
        if block.name == "request_verdict" and "error" not in result:
            verdict_requested = True
        elif "error" not in result:
            diff_events.append({"event": "state_diff", "data": result})
        tool_results.append(_tool_result(block.id, result))

    return {
        "messages": [{"role": "user", "content": tool_results}],
        "events": diff_events,
        "verdict_requested": verdict_requested,
    }


def route_after_execute_tools(state: GraphState) -> str:
    return "validate" if state["verdict_requested"] else "interpret"


async def validate(state: GraphState) -> dict:
    trade, provider = state["trade"], state["provider"]
    req = trade.to_validate_request()
    try:
        verdict = await provider.validate(req)
    except HardRuleViolation as exc:
        return {
            "verdict": None,
            "hard_error": exc.api_error.model_dump(),
            "events": [{"event": "error", "data": {"kind": "api_400", "message": exc.api_error.error}}],
        }
    except ProviderUnavailable as exc:
        mock = state.get("mock_provider")
        if mock is None:
            return {
                "verdict": None,
                "hard_error": {"error": str(exc)},
                "events": [{"event": "error", "data": {"kind": "provider_down", "message": str(exc)}}],
            }
        verdict = await mock.validate(req)

    return {
        "verdict": verdict,
        "hard_error": None,
        "events": [{"event": "verdict", "data": verdict.model_dump()}],
    }


async def respond(state: GraphState) -> dict:
    verdict, hard_error = state.get("verdict"), state.get("hard_error")
    if verdict is not None:
        instruction = f"Narrate this verdict for the user. Verdict JSON: {verdict.model_dump_json()}"
    elif hard_error is not None:
        instruction = (
            "The trade engine rejected this with a hard rule violation "
            f"(Stepien rule, stretch provision, or malformed request). Explain in plain "
            f"language, don't show raw JSON. Raw error: {hard_error['error']}"
        )
    else:
        instruction = "Continue the conversation based on the tool results above."

    messages = state["messages"] + [{"role": "user", "content": instruction}]
    response = await state["llm"].create(task="respond", system=RESPOND_SYSTEM_PROMPT, messages=messages)
    text = "".join(b.text for b in response.content if b.type == "text")
    return {
        "messages": [{"role": "assistant", "content": response.content}],
        "events": [{"event": "assistant", "data": {"text": text}}],
    }


def build_graph():
    graph = StateGraph(GraphState)
    graph.add_node("interpret", interpret)
    graph.add_node("execute_tools", execute_tools)
    graph.add_node("validate", validate)
    graph.add_node("respond", respond)

    graph.add_edge(START, "interpret")
    graph.add_conditional_edges("interpret", route_after_interpret, {
        "execute_tools": "execute_tools", "done": END,
    })
    graph.add_conditional_edges("execute_tools", route_after_execute_tools, {
        "validate": "validate", "interpret": "interpret",
    })
    graph.add_edge("validate", "respond")
    graph.add_edge("respond", END)

    return graph.compile()


async def run_turn(
    *,
    trade: TradeState,
    catalog: Catalog,
    provider: VerdictProvider,
    llm: LLMClient,
    messages: list[dict],
    mock_provider: VerdictProvider | None = None,
    recursion_limit: int = 15,
) -> dict:
    """Run one turn to completion. Guard: recursion_limit caps a runaway
    interpret<->execute_tools loop (ai-plan.md §4)."""
    graph = build_graph()
    initial: GraphState = {
        "messages": messages,
        "events": [],
        "trade": trade,
        "catalog": catalog,
        "provider": provider,
        "mock_provider": mock_provider,
        "llm": llm,
        "pending_tool_uses": [],
        "verdict_requested": False,
        "verdict": None,
        "hard_error": None,
    }
    return await graph.ainvoke(initial, config={"recursion_limit": recursion_limit})
