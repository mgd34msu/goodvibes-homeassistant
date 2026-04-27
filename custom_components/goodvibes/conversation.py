"""Conversation agent support for the GoodVibes integration."""

from __future__ import annotations

from typing import Any, Literal
from uuid import uuid4

from homeassistant.components.conversation import (
    AssistantContent,
    ChatLog,
    ConversationEntity,
    ConversationEntityFeature,
    ConversationInput,
    ConversationResult,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, intent
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import GoodVibesRuntimeData
from .client import GoodVibesClientError
from .const import (
    DEFAULT_ASSIST_CONVERSATION_PREFIX,
    DEFAULT_CONVERSATION_TIMEOUT_MS,
    DEFAULT_DISPLAY_NAME,
    DOMAIN,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the GoodVibes conversation entity."""

    runtime = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([GoodVibesConversationEntity(runtime)])


class GoodVibesConversationEntity(ConversationEntity):
    """Home Assistant Assist conversation agent backed by GoodVibes."""

    _attr_has_entity_name = True
    _attr_name = "GoodVibes"
    _attr_should_poll = False
    _attr_supported_features = ConversationEntityFeature.CONTROL

    def __init__(self, runtime: GoodVibesRuntimeData) -> None:
        """Initialize the conversation entity."""

        self._runtime = runtime
        base_unique_id = runtime.entry.unique_id or runtime.entry.entry_id
        self._attr_unique_id = f"{base_unique_id}_conversation"

    @property
    def supported_languages(self) -> list[str] | Literal["*"]:
        """Return supported languages."""

        return "*"

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

    async def _async_handle_message(
        self,
        user_input: ConversationInput,
        chat_log: ChatLog,
    ) -> ConversationResult:
        """Handle one Assist message through the daemon conversation endpoint."""

        conversation_id = (
            user_input.conversation_id
            or f"{DEFAULT_ASSIST_CONVERSATION_PREFIX}-{uuid4()}"
        )
        message_id = f"ha-assist-{uuid4()}"
        payload = self._build_payload(user_input, conversation_id, message_id)
        self._runtime.async_start_conversation_turn(message_id)

        try:
            result = await self._runtime.client.conversation(
                payload,
                timeout_ms=DEFAULT_CONVERSATION_TIMEOUT_MS,
            )
        except GoodVibesClientError as err:
            speech = f"GoodVibes is unavailable: {err}"
            result_conversation_id = conversation_id
            self._runtime.async_apply_conversation_error(message_id, str(err))
        else:
            self._runtime.async_apply_conversation_response(result)
            assistant = result.get("assistant")
            if isinstance(assistant, dict):
                speech = str(
                    assistant.get("speechText")
                    or assistant.get("text")
                    or result.get("error")
                    or "GoodVibes did not return a response."
                )
            else:
                speech = str(
                    result.get("error") or "GoodVibes did not return a response."
                )
            result_conversation_id = str(
                result.get("conversationId") or conversation_id
            )

        chat_log.async_add_assistant_content_without_tools(
            AssistantContent(agent_id=user_input.agent_id, content=speech)
        )
        response = intent.IntentResponse(language=user_input.language)
        response.async_set_speech(speech)
        return ConversationResult(
            response=response,
            conversation_id=result_conversation_id,
            continue_conversation=False,
        )

    def _build_payload(
        self,
        user_input: ConversationInput,
        conversation_id: str,
        message_id: str,
    ) -> dict[str, Any]:
        """Build the daemon conversation request payload."""

        context_payload: dict[str, Any] = {"language": user_input.language}
        if user_input.device_id:
            context_payload["deviceId"] = user_input.device_id
            device = dr.async_get(self.hass).async_get(user_input.device_id)
            if device and device.area_id:
                context_payload["areaId"] = device.area_id
        if user_input.satellite_id:
            context_payload["satelliteId"] = user_input.satellite_id
        if user_input.context.id:
            context_payload["haContextId"] = user_input.context.id
        if user_input.extra_system_prompt:
            context_payload["extraSystemPrompt"] = user_input.extra_system_prompt

        payload: dict[str, Any] = {
            "message": user_input.text,
            "conversationId": conversation_id,
            "messageId": message_id,
            "displayName": DEFAULT_DISPLAY_NAME,
            "context": context_payload,
            "timeoutMs": DEFAULT_CONVERSATION_TIMEOUT_MS,
        }
        if user_input.context.user_id:
            payload["userId"] = user_input.context.user_id
        if user_input.device_id:
            payload["deviceId"] = user_input.device_id
        return payload
