"""Sync check for the vendored generated operator client.

``custom_components/goodvibes/generated_client.py`` is a byte-for-byte copy of
the SDK's generated Python artifact (see the file's own header). This repo
does not run the SDK's code generator, so drift can only be caught by
diffing the vendored copy against the SDK checkout when one happens to be
present on the machine running the tests (e.g. a sibling checkout during
local development). CI for this repo does not have an SDK checkout, so the
comparison is skipped there rather than failing.
"""

from __future__ import annotations

import pathlib

import pytest

VENDORED_PATH = (
    pathlib.Path(__file__).resolve().parents[1]
    / "custom_components"
    / "goodvibes"
    / "generated_client.py"
)

# The SDK repo is expected to be a sibling checkout of this repo (both under
# the same parent directory), matching the local development layout. This is
# a convenience path, not a hard dependency: when it is absent (as in CI) the
# test skips with a clear reason instead of failing.
SDK_ARTIFACT_PATH = (
    pathlib.Path(__file__).resolve().parents[2]
    / "goodvibes-sdk"
    / "packages"
    / "contracts"
    / "artifacts"
    / "python"
    / "homeassistant_operator_client.py"
)


def test_vendored_generated_client_matches_sdk_artifact():
    """The vendored copy must stay byte-identical to the SDK's generated artifact."""

    if not SDK_ARTIFACT_PATH.exists():
        pytest.skip(
            "SDK checkout not found at "
            f"{SDK_ARTIFACT_PATH} — this repo does not vendor the SDK, so the "
            "sync check only runs when a sibling goodvibes-sdk checkout is "
            "present locally. CI for this repo has no SDK checkout."
        )

    vendored = VENDORED_PATH.read_bytes()
    upstream = SDK_ARTIFACT_PATH.read_bytes()
    assert vendored == upstream, (
        "custom_components/goodvibes/generated_client.py has drifted from the "
        f"SDK artifact at {SDK_ARTIFACT_PATH}. Re-copy the SDK's generated "
        "file over the vendored copy (regenerate it in the SDK repo first "
        "with `bun run refresh:contracts` if needed) rather than hand-editing "
        "either file."
    )
