"""Tests for the panel upload reader: off-loop disk I/O and the size guard."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.goodvibes import frontend
from custom_components.goodvibes.frontend import (
    UploadTooLargeError,
    _read_multipart_upload,
)


class _FakePart:
    """A minimal stand-in for one aiohttp multipart body part."""

    def __init__(self, name, *, filename=None, headers=None, chunks=(), text=""):
        self.name = name
        self.filename = filename
        self.headers = headers or {}
        self._chunks = list(chunks)
        self._text = text

    async def read_chunk(self, _size):
        return self._chunks.pop(0) if self._chunks else b""

    async def text(self):
        return self._text


class _FakeReader:
    def __init__(self, parts):
        self._parts = list(parts)

    async def next(self):
        return self._parts.pop(0) if self._parts else None


class _FakeRequest:
    def __init__(self, parts, content_type="multipart/form-data; boundary=x"):
        self.content_type = content_type
        self._parts = parts

    async def multipart(self):
        return _FakeReader(self._parts)


async def test_upload_write_runs_on_executor_and_preserves_bytes(hass):
    """The temp file is created, written, and closed via executor threads."""

    part = _FakePart(
        "file",
        filename="doc.txt",
        headers={"Content-Type": "text/plain"},
        chunks=[b"abc", b"def"],
    )
    request = _FakeRequest([part])

    with patch.object(
        hass, "async_add_executor_job", wraps=hass.async_add_executor_job
    ) as spy:
        fields, file_info = await _read_multipart_upload(hass, request)

    try:
        assert file_info["filename"] == "doc.txt"
        assert file_info["size"] == 6
        assert Path(file_info["path"]).read_bytes() == b"abcdef"
        assert "uploadedAt" in fields

        executor_funcs = [call.args[0].__name__ for call in spy.call_args_list]
        # Every blocking disk operation went through the executor: temp-file
        # creation, the file open, each write, and the close.
        assert "_create_upload_tempfile" in executor_funcs
        assert "fdopen" in executor_funcs
        assert "write" in executor_funcs
        assert "close" in executor_funcs
    finally:
        os.unlink(file_info["path"])


async def test_upload_over_cap_is_refused_and_cleans_up(hass):
    """An upload past the cap raises a size error and leaves no temp file."""

    part = _FakePart(
        "file",
        filename="big.bin",
        headers={"Content-Type": "application/octet-stream"},
        chunks=[b"\0" * (600 * 1024), b"\0" * (600 * 1024)],
    )
    request = _FakeRequest([part])

    created_paths: list[str] = []
    real_create = frontend._create_upload_tempfile

    def _tracking_create():
        fd, path = real_create()
        created_paths.append(path)
        return fd, path

    with patch.object(frontend, "MAX_UPLOAD_BYTES", 1024 * 1024), patch.object(
        frontend, "_create_upload_tempfile", _tracking_create
    ):
        with pytest.raises(UploadTooLargeError, match="1 MiB limit"):
            await _read_multipart_upload(hass, request)

    # The refusal is honest about the limit and is a HomeAssistantError so the
    # view can turn it into an HTTP response.
    assert issubclass(UploadTooLargeError, HomeAssistantError)
    # The partially written temp file was removed on the error path.
    assert created_paths
    assert not any(os.path.exists(path) for path in created_paths)
