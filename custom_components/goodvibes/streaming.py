"""Turn daemon conversation SSE frames into Home Assistant streaming deltas.

The Assist conversation entity feeds Home Assistant's
``ChatLog.async_add_delta_content_stream`` an async iterator of
``AssistantContentDeltaDict`` dicts. This module converts the daemon's
``/conversation/stream`` Server-Sent Events into that delta shape.

Kept free of any ``homeassistant.components.conversation`` import (the delta is
just a plain dict) so the conversion logic is unit-testable without the full
conversation component and its intent dependencies.

As of SDK 1.3.0 the daemon streams incremental ``event: delta`` frames shaped
``{"ok": true, "delta": "...", "text": "<accumulated so far>", "turnId": "...",
"conversationId": "...", "messageId": "..."}`` as the model produces text,
followed by the unchanged terminal ``final``/``error`` frame. This module reads
the ``delta`` field (the incremental chunk, not the running ``text``
accumulation) from each frame and yields it as a content delta in order. A
daemon that predates streaming and only emits the terminal frame still works
unchanged: the whole answer is emitted as one delta.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from .client import GoodVibesClientError


def assistant_speech_from_result(result: Any) -> str:
    """Extract the assistant speech text from a daemon conversation result."""

    if not isinstance(result, dict):
        return str(result or "")
    assistant = result.get("assistant")
    if isinstance(assistant, dict):
        text = (
            assistant.get("speechText")
            or assistant.get("text")
            or assistant.get("message")
        )
        if text:
            return str(text)
    return str(result.get("speechText") or result.get("text") or "")


def _frame_error_text(data: Any) -> str:
    """Return an honest error message from an ``error`` SSE frame."""

    if isinstance(data, dict):
        return str(
            data.get("error") or data.get("message") or "GoodVibes conversation failed"
        )
    return str(data or "GoodVibes conversation failed")


def _delta_text(data: Any) -> str:
    """Return the incremental text carried by a ``delta`` SSE frame."""

    if isinstance(data, str):
        return data
    if isinstance(data, dict):
        for key in ("delta", "text", "content"):
            value = data.get(key)
            if isinstance(value, str) and value:
                return value
        return assistant_speech_from_result(data)
    return ""


async def assistant_delta_stream(
    frames: AsyncIterator[dict[str, Any]],
    final_holder: dict[str, Any],
) -> AsyncIterator[dict[str, Any]]:
    """Yield Home Assistant assistant-content deltas from daemon SSE frames.

    ``final_holder`` is populated with the final result dict under ``"result"``
    (and ``"error"`` if the daemon reported one) so the caller can apply runtime
    state after the stream drains. Raises :class:`GoodVibesClientError` on an
    ``error`` frame so the conversation entity can surface an honest failure.
    """

    started = False
    async for frame in frames:
        name = frame.get("event")
        data = frame.get("data")
        if name == "delta":
            text = _delta_text(data)
            if text:
                if not started:
                    started = True
                    yield {"role": "assistant"}
                yield {"content": text}
        elif name == "final":
            final_holder["result"] = data if isinstance(data, dict) else {}
            text = assistant_speech_from_result(data)
            # If no incremental delta preceded this frame, emit the whole answer
            # once. If deltas already streamed, the final frame just echoes the
            # accumulated text, so do not double-emit it.
            if text and not started:
                started = True
                yield {"role": "assistant"}
                yield {"content": text}
        elif name == "error":
            message = _frame_error_text(data)
            final_holder["error"] = message
            raise GoodVibesClientError(message)
    final_holder.setdefault("result", {})
