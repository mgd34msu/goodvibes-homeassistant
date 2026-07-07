"""Stage 4: the conversation SSE-to-delta transform.

Proves the previously-dead ``/conversation/stream`` endpoint is now consumed and
converted into Home Assistant assistant-content deltas: a single terminal frame
becomes one full-text delta today, and incremental ``delta`` frames would stream
through in order.
"""

from __future__ import annotations

import pytest

from custom_components.goodvibes.client import GoodVibesClientError
from custom_components.goodvibes.streaming import (
    assistant_delta_stream,
    assistant_speech_from_result,
)


async def _frames(items):
    for item in items:
        yield item


async def _collect(items):
    holder: dict = {}
    deltas = [d async for d in assistant_delta_stream(_frames(items), holder)]
    return deltas, holder


async def test_single_final_frame_becomes_one_full_delta():
    """The daemon's single terminal frame yields role + full-text content."""

    final = {
        "status": "completed",
        "conversationId": "c1",
        "assistant": {"speechText": "Lights are on."},
    }
    deltas, holder = await _collect([{"event": "final", "data": final}])

    assert deltas == [
        {"role": "assistant"},
        {"content": "Lights are on."},
    ]
    assert holder["result"] is final


async def test_incremental_delta_frames_stream_in_order():
    """Successive delta frames stream as content deltas; final is not re-emitted."""

    items = [
        {"event": "delta", "data": {"delta": "Lights "}},
        {"event": "delta", "data": {"delta": "are on."}},
        {"event": "final", "data": {"assistant": {"speechText": "Lights are on."}}},
    ]
    deltas, holder = await _collect(items)

    assert deltas == [
        {"role": "assistant"},
        {"content": "Lights "},
        {"content": "are on."},
    ]
    # The full text streamed via deltas; the final frame only carries the result.
    assert holder["result"]["assistant"]["speechText"] == "Lights are on."


async def test_error_frame_raises_client_error():
    """An error frame raises so the entity can surface an honest failure."""

    with pytest.raises(GoodVibesClientError, match="daemon exploded"):
        await _collect([{"event": "error", "data": {"error": "daemon exploded"}}])


async def test_speech_extraction_prefers_speech_text():
    assert assistant_speech_from_result(
        {"assistant": {"speechText": "hi", "text": "ignored"}}
    ) == "hi"
    assert assistant_speech_from_result({"text": "fallback"}) == "fallback"
    assert assistant_speech_from_result({}) == ""
