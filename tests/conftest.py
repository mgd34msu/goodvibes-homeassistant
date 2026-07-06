"""Shared fixtures for the GoodVibes integration test suite.

The suite uses pytest-homeassistant-custom-component, which supplies the async
`hass` fixture (a lightweight in-process Home Assistant, not a real running
instance) and the `aioclient_mock` fixture that intercepts the shared aiohttp
client session so no request ever leaves the test process.
"""

from __future__ import annotations

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Load the goodvibes custom integration in every test."""

    yield
