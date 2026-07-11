"""Tests for the daemon contract-version and capability checks."""

from __future__ import annotations

from custom_components.goodvibes.const import (
    MIN_DAEMON_VERSION,
    REQUIRED_DAEMON_CAPABILITIES,
)
from custom_components.goodvibes.generated_client import CONTRACT_VERSION
from custom_components.goodvibes.version_check import (
    check_daemon_contract,
    is_version_at_least,
    parse_version,
)


def test_contract_version_is_at_least_min_daemon_version():
    """The generated contract's version must not fall below the declared floor.

    MIN_DAEMON_VERSION is hand-maintained (see const.py) because it covers
    hand-written surfaces the generated client does not, but it still must
    describe a daemon no newer than the one the mechanical REST subset was
    generated against — otherwise the floor would claim compatibility with a
    contract version this client was never checked against.
    """

    assert is_version_at_least(CONTRACT_VERSION, MIN_DAEMON_VERSION)


def test_parse_version_ignores_prefix_and_suffix():
    assert parse_version("v1.6.1") == (1, 6, 1)
    assert parse_version("1.6.1-rc.2") == (1, 6, 1)
    assert parse_version("1.6.1+build.9") == (1, 6, 1)
    assert parse_version("") == ()
    assert parse_version("nightly") == ()


def test_is_version_at_least_compares_numerically():
    assert is_version_at_least("1.6.1", "1.3.0")
    assert is_version_at_least("1.3.0", "1.3.0")
    assert not is_version_at_least("1.2.9", "1.3.0")
    # An unparseable advertised version is not blocked on version alone.
    assert is_version_at_least("nightly", "1.3.0")


def _health(caps):
    return {"ok": True, "capabilities": list(caps)}


def test_contract_ok_when_version_and_capabilities_satisfied():
    check = check_daemon_contract(
        {"version": "1.6.1"},
        _health(REQUIRED_DAEMON_CAPABILITIES),
        minimum_version=MIN_DAEMON_VERSION,
        required_capabilities=REQUIRED_DAEMON_CAPABILITIES,
    )
    assert check.ok
    assert check.version_ok
    assert check.capabilities_ok
    assert check.missing_capabilities == ()


def test_contract_flags_old_version():
    check = check_daemon_contract(
        {"version": "1.2.0"},
        _health(REQUIRED_DAEMON_CAPABILITIES),
        minimum_version=MIN_DAEMON_VERSION,
        required_capabilities=REQUIRED_DAEMON_CAPABILITIES,
    )
    assert not check.ok
    assert not check.version_ok
    assert check.capabilities_ok
    assert check.advertised_version == "1.2.0"


def test_contract_flags_missing_capabilities():
    check = check_daemon_contract(
        {"version": "1.6.1"},
        _health(["conversation-stream"]),
        minimum_version=MIN_DAEMON_VERSION,
        required_capabilities=REQUIRED_DAEMON_CAPABILITIES,
    )
    assert not check.ok
    assert check.version_ok
    assert not check.capabilities_ok
    assert "conversation-cancel" in check.missing_capabilities


def test_contract_handles_absent_bodies():
    check = check_daemon_contract(
        {},
        {},
        minimum_version=MIN_DAEMON_VERSION,
        required_capabilities=REQUIRED_DAEMON_CAPABILITIES,
    )
    # No version advertised -> version gate is skipped; no capabilities -> flagged.
    assert check.version_ok
    assert not check.capabilities_ok
    assert check.advertised_version is None
