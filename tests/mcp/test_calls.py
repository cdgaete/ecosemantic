from __future__ import annotations

import uuid

from ecosemantic.mcp.calls import InProgress, about, begin, current, end, note
from ecosemantic.mcp.context import ServerContext


def test_outside_a_call_there_is_none_and_nothing_is_kept() -> None:
    note("an answer")
    about(uuid.uuid4())
    assert current() is None


def test_a_tool_hands_the_call_in_progress_its_answer_and_its_system(
    context: ServerContext,
) -> None:
    system = uuid.uuid4()
    call = InProgress(context=context, agent="electricity", client="claude-code", origin="agent")
    token = begin(call)
    try:
        note("an answer")
        about(system)
        assert current() is call
    finally:
        end(token)
    assert (call.answer, call.product_system_id) == ("an answer", system)
    assert current() is None
