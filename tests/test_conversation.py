"""Tests for the conversation agent's native llm-helper integration.

The conversation entity keeps the model call on the daemon, but it routes the
config entry's chosen Assist LLM API and custom prompt through Home Assistant's
``chat_log.async_provide_llm_data`` helper and forwards the assembled system
prompt to the daemon as the turn's instructions. These tests cover that wiring
and the conversation options flow, without reaching a real daemon.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from homeassistant.components.conversation import ConversationInput
from homeassistant.const import CONF_LLM_HASS_API
from homeassistant.core import Context
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.goodvibes import conversation as conv
from custom_components.goodvibes.const import CONF_PROMPT, DOMAIN

DAEMON = "http://127.0.0.1:3421"


def _entity(
    hass,
    options: dict | None = None,
    *,
    home_graph_enabled: bool = True,
    installation_id: str = "test-installation",
    knowledge_space_id: str = "homeassistant:test-installation",
):
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=DAEMON,
        data={"daemon_url": DAEMON},
        options=options or {},
    )
    entry.add_to_hass(hass)
    runtime = SimpleNamespace(
        entry=entry,
        home_graph_enabled=home_graph_enabled,
        installation_id=installation_id,
        effective_knowledge_space_id=knowledge_space_id,
    )
    # Mirrors GoodVibesRuntimeData.home_graph_base_payload: the same
    # installation/knowledge-space identifier the integration registers the
    # Home Graph under (see data.py) is what a conversation turn should send
    # back as its grounding reference.
    runtime.home_graph_base_payload = lambda data=None: {
        "installationId": runtime.installation_id,
        "knowledgeSpaceId": runtime.effective_knowledge_space_id,
    }
    entity = conv.GoodVibesConversationEntity(runtime)
    entity.hass = hass
    return entity


def _user_input(extra_system_prompt: str | None = None) -> ConversationInput:
    return ConversationInput(
        text="turn on the light",
        context=Context(),
        conversation_id=None,
        device_id=None,
        satellite_id=None,
        language="en",
        agent_id="goodvibes",
        extra_system_prompt=extra_system_prompt,
    )


class _FakeChatLog:
    """Records the llm data it was given and exposes an assembled system prompt."""

    def __init__(self, assembled: str) -> None:
        self._assembled = assembled
        self.content: list = []
        self.provided: tuple | None = None

    async def async_provide_llm_data(self, llm_context, api, prompt, extra):
        self.provided = (api, prompt, extra)
        # The real helper sets content[0] to the assembled system prompt.
        self.content = [SimpleNamespace(role="system", content=self._assembled)]


async def test_instructions_none_when_no_options_configured(hass):
    """An unconfigured agent forwards no assembled instructions."""

    entity = _entity(hass, options={})
    chat_log = _FakeChatLog("SYSTEM PROMPT")

    instructions = await entity._async_assemble_instructions(_user_input(), chat_log)

    # The helper still runs (native path), but nothing is forwarded so the
    # daemon keeps its own default behavior.
    assert chat_log.provided is not None
    assert instructions is None


async def test_custom_prompt_is_assembled_and_forwarded(hass):
    """A configured custom prompt produces forwarded instructions."""

    entity = _entity(hass, options={CONF_PROMPT: "Be terse."})
    chat_log = _FakeChatLog("Be terse.\nCurrent time ...")

    instructions = await entity._async_assemble_instructions(_user_input(), chat_log)

    assert chat_log.provided[1] == "Be terse."
    assert instructions == "Be terse.\nCurrent time ..."


async def test_selected_llm_api_forwards_instructions(hass):
    """Selecting an Assist LLM API forwards the assembled prompt too."""

    entity = _entity(hass, options={CONF_LLM_HASS_API: ["assist"]})
    chat_log = _FakeChatLog("You can control the house ...")

    instructions = await entity._async_assemble_instructions(_user_input(), chat_log)

    assert chat_log.provided[0] == ["assist"]
    assert instructions == "You can control the house ..."


def test_build_payload_uses_instructions_when_present(hass):
    """Assembled instructions ride in the daemon payload context."""

    entity = _entity(hass)
    payload = entity._build_payload(
        _user_input(), "conv-1", "msg-1", instructions="ASSEMBLED"
    )
    assert payload["context"]["instructions"] == "ASSEMBLED"
    assert "extraSystemPrompt" not in payload["context"]


def test_build_payload_falls_back_to_extra_system_prompt(hass):
    """Without assembled instructions the per-turn extra prompt is preserved."""

    entity = _entity(hass)
    payload = entity._build_payload(
        _user_input(extra_system_prompt="one-off note"),
        "conv-1",
        "msg-1",
        instructions=None,
    )
    assert payload["context"]["extraSystemPrompt"] == "one-off note"
    assert "instructions" not in payload["context"]


def test_build_payload_carries_grounding_reference(hass):
    """The turn references the same graph the integration registers/re-syncs.

    ``home_graph_watch.py`` keeps the daemon-registered Home Graph fresh under
    ``installation_id``/``effective_knowledge_space_id``; this is the identifier
    a conversation turn must send back so the daemon can ground the turn in
    that same registered graph.
    """

    entity = _entity(
        hass,
        installation_id="my-house",
        knowledge_space_id="homeassistant:my-house",
    )
    payload = entity._build_payload(_user_input(), "conv-1", "msg-1")

    assert payload["grounding"] == {
        "installationId": "my-house",
        "knowledgeSpaceId": "homeassistant:my-house",
    }


def test_build_payload_omits_grounding_when_home_graph_disabled(hass):
    """No grounding reference is sent for a graph that was never registered."""

    entity = _entity(hass, home_graph_enabled=False)
    payload = entity._build_payload(_user_input(), "conv-1", "msg-1")

    assert "grounding" not in payload


async def test_options_flow_saves_custom_prompt(hass):
    """The options flow stores a custom prompt on the config entry."""

    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=DAEMON, data={"daemon_url": DAEMON}
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == "form"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_PROMPT: "Speak plainly."}
    )
    assert result["type"] == "create_entry"
    assert entry.options[CONF_PROMPT] == "Speak plainly."


async def test_options_flow_empty_prompt_stores_nothing(hass):
    """Submitting an empty prompt leaves no custom prompt behind."""

    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=DAEMON, data={"daemon_url": DAEMON}
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_PROMPT: "   "}
    )
    assert result["type"] == "create_entry"
    assert CONF_PROMPT not in entry.options


async def test_options_flow_saves_perception_triggers(hass):
    """The options flow persists perception enablement, entities, and prompt."""

    from custom_components.goodvibes.const import (
        CONF_PERCEPTION_ENABLED,
        CONF_PERCEPTION_ENTITIES,
        CONF_PERCEPTION_PROMPT,
    )

    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=DAEMON, data={"daemon_url": DAEMON}
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_PERCEPTION_ENABLED: True,
            CONF_PERCEPTION_ENTITIES: ["binary_sensor.front_door"],
            CONF_PERCEPTION_PROMPT: "Note who is at the door.",
        },
    )
    assert result["type"] == "create_entry"
    assert entry.options[CONF_PERCEPTION_ENABLED] is True
    assert entry.options[CONF_PERCEPTION_ENTITIES] == ["binary_sensor.front_door"]
    assert entry.options[CONF_PERCEPTION_PROMPT] == "Note who is at the door."


async def test_options_flow_saves_habit_mining(hass):
    """The options flow persists habit-mining enablement and clamped retention."""

    from custom_components.goodvibes.const import (
        CONF_HABIT_MINING_ENABLED,
        CONF_HABIT_RETENTION_DAYS,
    )

    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=DAEMON, data={"daemon_url": DAEMON}
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_HABIT_MINING_ENABLED: True, CONF_HABIT_RETENTION_DAYS: 30},
    )
    assert result["type"] == "create_entry"
    assert entry.options[CONF_HABIT_MINING_ENABLED] is True
    # Retention is stored as an int within the honest bounds.
    assert entry.options[CONF_HABIT_RETENTION_DAYS] == 30


async def test_options_flow_habit_mining_defaults_off(hass):
    """Habit mining stays disabled when the options form is submitted untouched."""

    from custom_components.goodvibes.const import CONF_HABIT_MINING_ENABLED

    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=DAEMON, data={"daemon_url": DAEMON}
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_PROMPT: "Speak plainly."}
    )
    assert result["type"] == "create_entry"
    assert entry.options[CONF_HABIT_MINING_ENABLED] is False


async def test_options_flow_perception_defaults_off(hass):
    """Perception stays disabled when the options form is submitted untouched."""

    from custom_components.goodvibes.const import CONF_PERCEPTION_ENABLED

    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=DAEMON, data={"daemon_url": DAEMON}
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_PROMPT: "Speak plainly."}
    )
    assert result["type"] == "create_entry"
    assert entry.options[CONF_PERCEPTION_ENABLED] is False
