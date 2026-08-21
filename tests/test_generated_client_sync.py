"""Sync checks for the vendored generated operator client.

``custom_components/goodvibes/generated_client.py`` is a byte-for-byte copy of
the SDK's generated Python artifact (see the file's own header). This repo does
not run the SDK's code generator, so there are two independent guards here:

* the recorded SHA-256 in ``tests/generated_client.sha256`` is checked on every
  run, everywhere. This is the guard that works in CI, which has no SDK
  checkout: a hand-edit of the vendored file changes its hash and fails the
  build. An earlier version of this module compared against a sibling SDK
  checkout and skipped when one was absent, which is always the case in CI, so
  hand-edits to the vendored copy could ship undetected.
* when a sibling ``goodvibes-sdk`` checkout happens to be present (the local
  development layout), the vendored copy is additionally byte-compared against
  the SDK's artifact. That catches the other direction: a vendored copy that is
  internally consistent with its recorded hash but stale relative to upstream.
"""

from __future__ import annotations

import hashlib
import pathlib

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

VENDORED_RELATIVE_PATH = "custom_components/goodvibes/generated_client.py"
VENDORED_PATH = REPO_ROOT / VENDORED_RELATIVE_PATH

# Written in `sha256sum` output format so the same file can be checked from a
# shell with `sha256sum -c tests/generated_client.sha256`, which is what
# .github/workflows/sdk-drift.yml does.
RECORDED_HASH_PATH = pathlib.Path(__file__).resolve().parent / "generated_client.sha256"

# The SDK repo is expected to be a sibling checkout of this repo (both under the
# same parent directory), matching the local development layout. This one is a
# convenience path, not a hard dependency -- the hash check above does not
# depend on it.
SDK_ARTIFACT_PATH = (
    REPO_ROOT.parent
    / "goodvibes-sdk"
    / "packages"
    / "contracts"
    / "artifacts"
    / "python"
    / "homeassistant_operator_client.py"
)

_REFRESH_HINT = (
    "If you meant to update the vendored client, re-copy the SDK's generated "
    "artifact over it and refresh the recorded hash with:\n"
    f"  sha256sum {VENDORED_RELATIVE_PATH} > tests/generated_client.sha256\n"
    "Never edit either file by hand."
)


def _read_recorded_hash() -> str:
    """Return the SHA-256 recorded for the vendored client.

    Parses `sha256sum` output format, ignoring the blank and ``#`` comment lines
    that `sha256sum -c` also ignores.
    """

    for line in RECORDED_HASH_PATH.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        digest, _, path = stripped.partition("  ")
        if path.strip() == VENDORED_RELATIVE_PATH:
            return digest.strip().lower()

    raise AssertionError(
        f"{RECORDED_HASH_PATH} records no hash for {VENDORED_RELATIVE_PATH}."
    )


def test_vendored_generated_client_matches_recorded_hash():
    """The vendored copy must match the hash committed alongside it.

    This assertion never skips: it is the only drift guard that runs in CI.
    """

    actual = hashlib.sha256(VENDORED_PATH.read_bytes()).hexdigest()
    expected = _read_recorded_hash()

    assert actual == expected, (
        f"{VENDORED_RELATIVE_PATH} does not match the hash recorded in "
        f"{RECORDED_HASH_PATH.name}.\n"
        f"  recorded: {expected}\n"
        f"  actual:   {actual}\n"
        "The vendored client is a byte-for-byte copy of the SDK's generated "
        "artifact, so this means it was edited in place or replaced.\n"
        f"{_REFRESH_HINT}"
    )


def test_vendored_generated_client_matches_sdk_artifact():
    """The vendored copy must stay byte-identical to the SDK's generated artifact.

    Belt and braces for development machines. Skipping when no sibling SDK
    checkout exists is safe here only because the recorded-hash test above
    always runs.
    """

    if not SDK_ARTIFACT_PATH.exists():
        pytest.skip(
            f"No SDK checkout at {SDK_ARTIFACT_PATH}: this repo does not vendor "
            "the SDK, so the upstream comparison only runs when a sibling "
            "goodvibes-sdk checkout is present. The recorded-hash check in this "
            "module covers CI."
        )

    vendored = VENDORED_PATH.read_bytes()
    upstream = SDK_ARTIFACT_PATH.read_bytes()
    assert vendored == upstream, (
        f"{VENDORED_RELATIVE_PATH} has drifted from the SDK artifact at "
        f"{SDK_ARTIFACT_PATH}. Re-copy the SDK's generated file over the "
        "vendored copy (regenerate it in the SDK repo first with "
        "`bun run refresh:contracts` if needed) rather than hand-editing "
        "either file."
    )


def test_recorded_hash_matches_sdk_artifact():
    """The recorded hash must describe upstream, not a drifted vendored copy.

    Without this, re-recording the hash of an already-drifted file would make
    both other tests pass while the integration ships a client the SDK never
    generated.
    """

    if not SDK_ARTIFACT_PATH.exists():
        pytest.skip(f"No SDK checkout at {SDK_ARTIFACT_PATH}.")

    upstream_hash = hashlib.sha256(SDK_ARTIFACT_PATH.read_bytes()).hexdigest()
    assert upstream_hash == _read_recorded_hash(), (
        f"The hash recorded in {RECORDED_HASH_PATH.name} does not match the SDK "
        f"artifact at {SDK_ARTIFACT_PATH}. The recorded hash must be taken from "
        "a vendored copy that is byte-identical to upstream."
    )
