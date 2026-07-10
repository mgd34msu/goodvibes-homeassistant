"""Daemon contract-version and capability checks for the GoodVibes client.

This integration is a thin client over a set of stable daemon HTTP routes. It
declares the minimum daemon version whose Home Assistant surface contract it is
written against (:data:`~.const.MIN_DAEMON_VERSION`) and the surface
capabilities it relies on (:data:`~.const.REQUIRED_DAEMON_CAPABILITIES`). At
connect it compares those against what the daemon advertises:

* ``GET /status`` returns the daemon software ``version`` (semver).
* ``GET /api/homeassistant/health`` returns a ``capabilities`` list of
  capability strings for the Home Assistant surface.

The functions here are pure so they can be unit tested without a running
daemon; the runtime turns a failing :class:`DaemonContractCheck` into a Home
Assistant repair issue (see ``data.py``).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any


def parse_version(value: Any) -> tuple[int, ...]:
    """Parse a semver-ish string into a comparable tuple of integers.

    Only the leading dotted numeric components are used; any pre-release or
    build suffix (``-rc.1``, ``+meta``) is ignored, and non-numeric components
    stop the parse. An unparseable value yields an empty tuple, which compares
    as the lowest possible version.
    """

    text = str(value or "").strip()
    if not text:
        return ()
    # Drop a leading "v" and any build/pre-release suffix.
    text = text.lstrip("vV").split("+", 1)[0].split("-", 1)[0]
    parts: list[int] = []
    for chunk in text.split("."):
        chunk = chunk.strip()
        if not chunk.isdigit():
            break
        parts.append(int(chunk))
    return tuple(parts)


def is_version_at_least(advertised: Any, minimum: Any) -> bool:
    """Return whether ``advertised`` is greater than or equal to ``minimum``.

    An unparseable advertised version is treated as "unknown" and allowed
    through (returns ``True``) rather than blocking on a version string the
    client simply does not understand; the capability check still guards the
    routes the integration actually calls.
    """

    advertised_parts = parse_version(advertised)
    if not advertised_parts:
        return True
    return advertised_parts >= parse_version(minimum)


def _advertised_capabilities(health: Mapping[str, Any] | None) -> set[str]:
    """Return the Home Assistant surface capability strings the daemon reports."""

    if not isinstance(health, Mapping):
        return set()
    raw = health.get("capabilities")
    if not isinstance(raw, (list, tuple, set)):
        return set()
    return {str(item) for item in raw if item}


@dataclass(frozen=True)
class DaemonContractCheck:
    """Outcome of comparing the daemon against the client's declared contract."""

    advertised_version: str | None
    minimum_version: str
    version_ok: bool
    missing_capabilities: tuple[str, ...] = field(default_factory=tuple)

    @property
    def capabilities_ok(self) -> bool:
        """Return whether every required capability was advertised."""

        return not self.missing_capabilities

    @property
    def ok(self) -> bool:
        """Return whether the daemon satisfies the declared contract."""

        return self.version_ok and self.capabilities_ok


def check_daemon_contract(
    status: Mapping[str, Any] | None,
    health: Mapping[str, Any] | None,
    *,
    minimum_version: str,
    required_capabilities: Sequence[str],
) -> DaemonContractCheck:
    """Compare a daemon's advertised version and capabilities to the contract.

    ``status`` is the ``GET /status`` body (for ``version``) and ``health`` is
    the ``GET /api/homeassistant/health`` body (for ``capabilities``). The
    version gate is skipped when the daemon advertises an unparseable version;
    the capability gate always applies because those are the routes this client
    depends on.
    """

    advertised_version = None
    if isinstance(status, Mapping):
        raw_version = status.get("version")
        if raw_version not in (None, ""):
            advertised_version = str(raw_version)

    version_ok = is_version_at_least(advertised_version, minimum_version)

    advertised = _advertised_capabilities(health)
    missing = tuple(
        capability
        for capability in required_capabilities
        if capability not in advertised
    )

    return DaemonContractCheck(
        advertised_version=advertised_version,
        minimum_version=minimum_version,
        version_ok=version_ok,
        missing_capabilities=missing,
    )
