"""Sensors for the GoodVibes integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import GoodVibesRuntimeData
from .const import DOMAIN


def _state(value: Any, fallback: str | None = None) -> str | None:
    """Return a Home Assistant state-safe value."""

    if value is None or value == "":
        return fallback
    text = str(value)
    return text if len(text) <= 255 else f"{text[:252]}..."


@dataclass(frozen=True, kw_only=True)
class GoodVibesSensorDescription(SensorEntityDescription):
    """Sensor description with value and attribute callbacks."""

    value_fn: Callable[[GoodVibesRuntimeData], Any]
    attrs_fn: Callable[[GoodVibesRuntimeData], dict[str, Any]] | None = None


SENSOR_DESCRIPTIONS: tuple[GoodVibesSensorDescription, ...] = (
    GoodVibesSensorDescription(
        key="daemon_status",
        translation_key="daemon_status",
        icon="mdi:server",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: _state(data.status, "unknown"),
        attrs_fn=lambda data: {
            "daemon_url": data.client.daemon_url,
            "event_type": data.event_type,
            "health": data.health,
            "daemon": data.daemon_status,
            "homeassistant": data.homeassistant_status,
        },
    ),
    GoodVibesSensorDescription(
        key="last_reply",
        translation_key="last_reply",
        icon="mdi:message-reply-text",
        value_fn=lambda data: _state(data.last_reply, "none"),
        attrs_fn=lambda data: {
            "last_event_at": data.last_event_at,
            "payload": data.last_payload,
        },
    ),
    GoodVibesSensorDescription(
        key="active_session_id",
        translation_key="active_session_id",
        icon="mdi:chat-processing",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: _state(data.active_session_id, "none"),
        attrs_fn=lambda data: {"active_session_id": data.active_session_id},
    ),
    GoodVibesSensorDescription(
        key="active_message_id",
        translation_key="active_message_id",
        icon="mdi:message-processing",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: _state(data.active_message_id, "none"),
        attrs_fn=lambda data: {"active_message_id": data.active_message_id},
    ),
    GoodVibesSensorDescription(
        key="active_agent_id",
        translation_key="active_agent_id",
        icon="mdi:robot",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: _state(data.active_agent_id, "none"),
        attrs_fn=lambda data: {"active_agent_id": data.active_agent_id},
    ),
    GoodVibesSensorDescription(
        key="last_error",
        translation_key="last_error",
        icon="mdi:alert-circle",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: _state(data.last_error, "none"),
        attrs_fn=lambda data: {"last_error": data.last_error},
    ),
    GoodVibesSensorDescription(
        key="tool_catalog_status",
        translation_key="tool_catalog_status",
        icon="mdi:tools",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: _tool_state(data),
        attrs_fn=lambda data: {
            "tool_count": len(data.tool_catalog.get("tools", [])),
            "agent_tool_count": len(data.tool_catalog.get("agent_tools", [])),
            "tools": [
                tool.get("name") or tool.get("id")
                for tool in data.tool_catalog.get("tools", [])
                if isinstance(tool, dict)
            ],
            "agent_tools": [
                tool.get("name") or tool.get("id")
                for tool in data.tool_catalog.get("agent_tools", [])
                if isinstance(tool, dict)
            ],
        },
    ),
)


def _tool_state(data: GoodVibesRuntimeData) -> str:
    """Return a compact state for the tool catalog sensor."""

    tool_count = len(data.tool_catalog.get("tools", []))
    agent_tool_count = len(data.tool_catalog.get("agent_tools", []))
    if not data.tool_catalog:
        return "unknown"
    return f"{tool_count} tools, {agent_tool_count} agent tools"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up GoodVibes sensors."""

    runtime = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        GoodVibesSensor(runtime, description) for description in SENSOR_DESCRIPTIONS
    )


class GoodVibesSensor(SensorEntity):
    """Representation of a GoodVibes sensor."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    entity_description: GoodVibesSensorDescription

    def __init__(
        self,
        runtime: GoodVibesRuntimeData,
        description: GoodVibesSensorDescription,
    ) -> None:
        """Initialize the sensor."""

        self._runtime = runtime
        self.entity_description = description
        base_unique_id = runtime.entry.unique_id or runtime.entry.entry_id
        self._attr_unique_id = f"{base_unique_id}_{description.key}"

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device registry metadata."""

        return {
            "identifiers": {(DOMAIN, self._runtime.device_identifier)},
            "manufacturer": "GoodVibes",
            "model": self._runtime.device_model,
            "name": self._runtime.device_name,
            "sw_version": self._runtime.sw_version,
        }

    @property
    def native_value(self) -> Any:
        """Return the sensor value."""

        return self.entity_description.value_fn(self._runtime)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return sensor attributes."""

        if self.entity_description.attrs_fn is None:
            return None
        return self.entity_description.attrs_fn(self._runtime)

    async def async_added_to_hass(self) -> None:
        """Subscribe to runtime updates."""

        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, self._runtime.signal, self.async_write_ha_state
            )
        )
