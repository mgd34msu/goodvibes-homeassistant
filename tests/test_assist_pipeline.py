"""Tests for the conversation entity's Assist-pipeline / Wyoming behavior.

A Wyoming voice satellite feeds Home Assistant's Assist pipeline, which routes
the transcribed turn to the selected conversation agent. The GoodVibes
conversation entity is that agent. These tests cover the pipeline-facing
behavior: the entity is a selectable conversation agent, and a turn carrying the
device and satellite a Wyoming satellite supplies is handled end to end and
carries that context to the daemon.

Full-duplex talk-mode and wake-word handling belong to Home Assistant and
Wyoming, not this integration; see docs/voice-assist.md.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from homeassistant.components.conversation import (
    ConversationEntity,
    ConversationEntityFeature,
    ConversationInput,
    ConversationResult,
)
from homeassistant.core import Context
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.goodvibes import conversation as conv
from custom_components.goodvibes.const import DOMAIN

DAEMON = "http://127.0.0.1:3421"


def _runtime(hass, capture: dict):
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=DAEMON, data={"daemon_url": DAEMON}, options={}
    )
    entry.add_to_hass(hass)

    async def _conversation_stream(payload, timeout_ms=0):
        capture["payload"] = payload
        capture["timeout_ms"] = timeout_ms
        yield {
            "event": "final",
            "data": {
                "status": "completed",
                "conversationId": payload["conversationId"],
                "assistant": {"speechText": "Lights are on."},
            },
        }

    runtime = SimpleNamespace(
        entry=entry,
        home_graph_enabled=True,
        installation_id="inst-1",
        effective_knowledge_space_id="homeassistant:inst-1",
        client=SimpleNamespace(conversation_stream=_conversation_stream),
        async_start_conversation_turn=MagicMock(),
        async_apply_conversation_response=MagicMock(),
        async_apply_conversation_error=MagicMock(),
    )
    runtime.home_graph_base_payload = lambda data=None: {
        "installationId": runtime.installation_id,
        "knowledgeSpaceId": runtime.effective_knowledge_space_id,
    }
    return runtime


class _FakeChatLog:
    """Minimal ChatLog that drives the delta stream like the real one."""

    def __init__(self) -> None:
        self.content: list = []
        self.added: list = []

    async def async_provide_llm_data(self, *_args) -> None:
        self.content = []

    async def async_add_delta_content_stream(self, _agent_id, stream):
        async for delta in stream:
            yield delta

    def async_add_assistant_content_without_tools(self, content) -> None:
        self.added.append(content)


def _entity(hass, capture: dict):
    entity = conv.GoodVibesConversationEntity(_runtime(hass, capture))
    entity.hass = hass
    entity.entity_id = "conversation.goodvibes"
    return entity


def _wyoming_input() -> ConversationInput:
    """A turn shaped like one a Wyoming satellite feeds into the pipeline."""

    return ConversationInput(
        text="are the lights on",
        context=Context(),
        conversation_id=None,
        device_id="wyoming-satellite-device",
        satellite_id="assist_satellite.living_room",
        language="en",
        agent_id="conversation.goodvibes",
        extra_system_prompt=None,
    )


def test_entity_is_a_selectable_conversation_agent(hass):
    """It is a ConversationEntity that can control Home Assistant, any language."""

    entity = _entity(hass, {})
    assert isinstance(entity, ConversationEntity)
    assert entity.supported_languages == "*"
    assert entity.supported_features & ConversationEntityFeature.CONTROL


def test_build_payload_carries_wyoming_device_and_satellite(hass):
    """A satellite-fed turn carries its device and satellite to the daemon."""

    entity = _entity(hass, {})
    user_input = _wyoming_input()
    payload = entity._build_payload(user_input, "conv-1", "msg-1")

    assert payload["deviceId"] == "wyoming-satellite-device"
    assert payload["context"]["deviceId"] == "wyoming-satellite-device"
    assert payload["context"]["satelliteId"] == "assist_satellite.living_room"
    assert payload["context"]["language"] == "en"


async def test_pipeline_turn_is_handled_end_to_end(hass):
    """A Wyoming-shaped turn streams through and returns a spoken result."""

    capture: dict = {}
    entity = _entity(hass, capture)
    chat_log = _FakeChatLog()

    result = await entity._async_handle_message(_wyoming_input(), chat_log)

    assert isinstance(result, ConversationResult)
    assert result.response.speech["plain"]["speech"] == "Lights are on."
    # The daemon turn was fed the satellite context from the pipeline.
    assert capture["payload"]["context"]["satelliteId"] == (
        "assist_satellite.living_room"
    )
    entity._runtime.async_start_conversation_turn.assert_called_once()
    entity._runtime.async_apply_conversation_response.assert_called_once()
