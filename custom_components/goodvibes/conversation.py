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
    ConverseError,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_LLM_HASS_API
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, intent
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import GoodVibesRuntimeData
from .client import GoodVibesClientError
from .const import (
    CONF_PROMPT,
    DEFAULT_ASSIST_CONVERSATION_PREFIX,
    DEFAULT_CONVERSATION_TIMEOUT_MS,
    DEFAULT_DISPLAY_NAME,
    DOMAIN,
)
from .streaming import assistant_delta_stream, assistant_speech_from_result


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
        """Handle one Assist message, streaming the daemon response.

        The turn is streamed through the daemon ``/conversation/stream`` endpoint
        and fed to Home Assistant's ``ChatLog`` delta-stream API, so partial
        responses render as they arrive. The daemon currently emits one terminal
        frame, so today the full answer arrives as a single delta; incremental
        daemon deltas would stream here with no further change.
        """

        conversation_id = (
            user_input.conversation_id
            or f"{DEFAULT_ASSIST_CONVERSATION_PREFIX}-{uuid4()}"
        )
        message_id = f"ha-assist-{uuid4()}"
        try:
            instructions = await self._async_assemble_instructions(
                user_input, chat_log
            )
        except ConverseError as err:
            # A misconfigured LLM API id (e.g. one that was removed) surfaces as
            # a native conversation error rather than a daemon round-trip.
            return err.as_conversation_result()
        payload = self._build_payload(
            user_input, conversation_id, message_id, instructions
        )
        self._runtime.async_start_conversation_turn(message_id)

        final_holder: dict[str, Any] = {}
        speech_parts: list[str] = []

        async def _tracked_deltas():
            frames = self._runtime.client.conversation_stream(
                payload, timeout_ms=DEFAULT_CONVERSATION_TIMEOUT_MS
            )
            async for delta in assistant_delta_stream(frames, final_holder):
                if content := delta.get("content"):
                    speech_parts.append(content)
                yield delta

        try:
            async for _content in chat_log.async_add_delta_content_stream(
                self.entity_id, _tracked_deltas()
            ):
                pass
        except GoodVibesClientError as err:
            speech = f"GoodVibes is unavailable: {err}"
            self._runtime.async_apply_conversation_error(message_id, str(err))
            chat_log.async_add_assistant_content_without_tools(
                AssistantContent(agent_id=user_input.agent_id, content=speech)
            )
            result_conversation_id = conversation_id
        else:
            result = final_holder.get("result") or {}
            self._runtime.async_apply_conversation_response(result)
            speech = (
                "".join(speech_parts)
                or assistant_speech_from_result(result)
                or str(result.get("error") or "GoodVibes did not return a response.")
            )
            # If the stream yielded no content delta, the chat log has no
            # assistant message yet; add the resolved speech so the turn is
            # never empty.
            if not speech_parts:
                chat_log.async_add_assistant_content_without_tools(
                    AssistantContent(agent_id=user_input.agent_id, content=speech)
                )
            result_conversation_id = str(
                result.get("conversationId") or conversation_id
            )

        response = intent.IntentResponse(language=user_input.language)
        response.async_set_speech(speech)
        return ConversationResult(
            response=response,
            conversation_id=result_conversation_id,
            continue_conversation=False,
        )

    async def _async_assemble_instructions(
        self,
        user_input: ConversationInput,
        chat_log: ChatLog,
    ) -> str | None:
        """Assemble the turn's system prompt through Home Assistant's llm helper.

        This routes the config entry's chosen Assist LLM API and custom prompt
        through ``chat_log.async_provide_llm_data`` — the same helper a
        first-class conversation agent uses. When an LLM API is selected, the
        prompt Home Assistant assembles lists only the entities exposed to
        assistants (``async_should_expose``), so the instructions handed to the
        daemon honor the same boundary as the Home Graph snapshot.

        The assembled prompt is returned so it can travel to the daemon as the
        turn's instructions. It is forwarded only when the user has configured
        the LLM API or a custom prompt; an unconfigured agent returns ``None`` so
        the daemon keeps its own default behavior.
        """

        options = self._runtime.entry.options
        llm_api = options.get(CONF_LLM_HASS_API)
        prompt = options.get(CONF_PROMPT)
        await chat_log.async_provide_llm_data(
            user_input.as_llm_context(DOMAIN),
            llm_api,
            prompt,
            user_input.extra_system_prompt,
        )
        if not (llm_api or prompt):
            return None
        for content in chat_log.content:
            if getattr(content, "role", None) == "system" and content.content:
                return content.content
        return None

    def _build_payload(
        self,
        user_input: ConversationInput,
        conversation_id: str,
        message_id: str,
        instructions: str | None = None,
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
        if instructions:
            # The Home Assistant llm helper already folds any per-turn
            # extra_system_prompt into the assembled instructions.
            context_payload["instructions"] = instructions
        elif user_input.extra_system_prompt:
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
