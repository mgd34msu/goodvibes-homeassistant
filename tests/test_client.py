"""Tests for the GoodVibes daemon client: requests, headers, and error types."""

from __future__ import annotations

from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import aiohttp
import pytest

from custom_components.goodvibes.client import (
    GoodVibesClient,
    GoodVibesClientError,
    GoodVibesDaemonError,
    GoodVibesSurfaceMissingError,
    GoodVibesUnauthorizedError,
    GoodVibesUnavailableError,
    _query_path,
)

DAEMON = "http://127.0.0.1:3421"


def _client(hass, token: str | None = "tok-abc") -> GoodVibesClient:
    return GoodVibesClient(hass, DAEMON, token, "secret-xyz")


async def test_native_call_sends_bearer_header(hass, aioclient_mock):
    """A daemon-native GET carries the bearer token, not the webhook secret."""

    aioclient_mock.get(
        f"{DAEMON}/status", json={"status": "running", "version": "1.2.0"}
    )
    result = await _client(hass).status()

    assert result == {"status": "running", "version": "1.2.0"}
    _method, _url, _data, headers = aioclient_mock.mock_calls[0]
    assert headers["Authorization"] == "Bearer tok-abc"
    assert "x-goodvibes-homeassistant-secret" not in headers


async def test_webhook_uses_secret_header_not_bearer(hass, aioclient_mock):
    """The webhook path uses the shared secret and suppresses the bearer."""

    aioclient_mock.post(f"{DAEMON}/webhook/homeassistant", json={"ok": True})
    await _client(hass).prompt({"type": "prompt", "message": "hi"})

    _method, _url, _data, headers = aioclient_mock.mock_calls[0]
    assert headers["x-goodvibes-homeassistant-secret"] == "secret-xyz"
    assert "Authorization" not in headers


@pytest.mark.parametrize(
    ("status", "exc_type"),
    [
        (401, GoodVibesUnauthorizedError),
        (403, GoodVibesUnauthorizedError),
        (404, GoodVibesSurfaceMissingError),
        (500, GoodVibesDaemonError),
        (502, GoodVibesDaemonError),
    ],
)
async def test_http_error_status_maps_to_typed_exception(
    hass, aioclient_mock, status, exc_type
):
    """Each HTTP error status raises the matching typed exception with status."""

    aioclient_mock.get(f"{DAEMON}/status", status=status, text="boom")
    with pytest.raises(exc_type) as err:
        await _client(hass).status()
    assert err.value.status == status


async def test_unknown_channel_action_body_maps_to_surface_missing(
    hass, aioclient_mock
):
    """An 'unknown channel action' body is classified as a missing surface."""

    aioclient_mock.post(
        f"{DAEMON}/api/channels/actions/homeassistant/homeassistant-manifest",
        status=400,
        text="Unknown channel action",
    )
    with pytest.raises(GoodVibesSurfaceMissingError):
        await _client(hass).manifest()


async def test_connection_error_maps_to_unavailable(hass, aioclient_mock):
    """A connection failure surfaces as an 'unavailable' error."""

    aioclient_mock.get(f"{DAEMON}/status", exc=aiohttp.ClientError())
    with pytest.raises(GoodVibesUnavailableError):
        await _client(hass).status()


async def test_timeout_maps_to_unavailable(hass, aioclient_mock):
    """A request timeout surfaces as an 'unavailable' error."""

    aioclient_mock.get(f"{DAEMON}/status", exc=TimeoutError())
    with pytest.raises(GoodVibesUnavailableError):
        await _client(hass).status()


def test_typed_errors_share_the_base_class():
    """Every typed error is a GoodVibesClientError so broad catches still work."""

    for cls in (
        GoodVibesUnauthorizedError,
        GoodVibesSurfaceMissingError,
        GoodVibesUnavailableError,
        GoodVibesDaemonError,
    ):
        assert issubclass(cls, GoodVibesClientError)


async def test_upload_reads_file_off_the_event_loop(hass, aioclient_mock, tmp_path):
    """The upload read-back opens/closes the file through an executor thread."""

    upload = tmp_path / "note.txt"
    upload.write_bytes(b"hello world")
    aioclient_mock.post(
        f"{DAEMON}/api/homeassistant/home-graph/ingest/artifact", json={"ok": True}
    )

    with patch.object(
        hass, "async_add_executor_job", wraps=hass.async_add_executor_job
    ) as spy:
        result = await _client(hass).home_graph_upload_artifact(
            {"installationId": "inst"},
            str(upload),
            filename="note.txt",
            content_type="text/plain",
        )

    assert result == {"ok": True}
    assert spy.called
    executor_funcs = [call.args[0].__name__ for call in spy.call_args_list]
    # The blocking open() and close() ran on an executor thread, never the loop.
    assert "_open_binary" in executor_funcs
    assert "close" in executor_funcs


def test_query_path_filters_empty_and_non_scalar_values():
    """Only non-empty scalar params become query string entries."""

    path = _query_path(
        "/x",
        {
            "a": "1",
            "blank": "",
            "none": None,
            "empty_list": [],
            "obj": {"k": 1},
            "num": 2,
            "flag": True,
        },
    )
    qs = parse_qs(urlparse(path).query)
    assert qs["a"] == ["1"]
    assert qs["num"] == ["2"]
    assert qs["flag"] == ["True"]
    for dropped in ("blank", "none", "empty_list", "obj"):
        assert dropped not in qs


def test_query_path_with_no_usable_params_returns_bare_path():
    """A payload with nothing usable leaves the path unchanged."""

    assert _query_path("/x", {"blank": "", "none": None}) == "/x"


async def test_conversation_stream_parses_sse_frames(hass, aioclient_mock):
    """The streaming endpoint is consumed as ordered SSE frames."""

    body = (
        "event: delta\n"
        'data: {"delta": "Lights "}\n'
        "\n"
        "event: final\n"
        'data: {"status": "completed", "assistant": {"speechText": "Lights on."}}\n'
        "\n"
    )
    aioclient_mock.post(
        f"{DAEMON}/api/homeassistant/conversation/stream",
        text=body,
        headers={"Content-Type": "text/event-stream"},
    )

    frames = [
        frame
        async for frame in _client(hass).conversation_stream({"message": "hi"})
    ]

    assert frames[0] == {"event": "delta", "data": {"delta": "Lights "}}
    assert frames[1]["event"] == "final"
    assert frames[1]["data"]["assistant"]["speechText"] == "Lights on."
    # The stream carries the bearer token, since it is a daemon-native route.
    _method, _url, _data, headers = aioclient_mock.mock_calls[0]
    assert headers["Authorization"] == "Bearer tok-abc"


async def test_conversation_stream_error_status_raises_typed(hass, aioclient_mock):
    """A non-200 stream response raises the matching typed client error."""

    aioclient_mock.post(
        f"{DAEMON}/api/homeassistant/conversation/stream",
        status=404,
        text="not found",
    )
    with pytest.raises(GoodVibesSurfaceMissingError):
        async for _frame in _client(hass).conversation_stream({"message": "hi"}):
            pass
