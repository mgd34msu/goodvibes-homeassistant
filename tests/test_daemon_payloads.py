"""Stage 2: pin the unified daemon payload builders.

These tests lock the single payload contract shared by the Home Assistant
services (snake_case input) and the sidebar panel (camelCase input). The point
of the unification is that both conventions produce the *same* daemon payload,
so most tests assert snake_case and camelCase inputs are equal.
"""

from __future__ import annotations

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.goodvibes import daemon_payloads as dp


class _FakeRuntime:
    """Minimal runtime exposing what the shared builders touch."""

    def __init__(
        self,
        *,
        enabled: bool = True,
        installation: str = "inst-1",
        ksid: str = "ks-1",
    ) -> None:
        self.home_graph_enabled = enabled
        self._installation = installation
        self._ksid = ksid

    def home_graph_base_payload(self, data: dict | None = None) -> dict:
        data = data or {}
        installation = str(data.get("installation_id") or self._installation)
        ksid = str(data.get("knowledge_space_id") or self._ksid)
        payload: dict = {"installationId": installation}
        if ksid:
            payload["knowledgeSpaceId"] = ksid
        return payload


# --- pure helpers -----------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [(True, True), ("yes", True), ("1", True), ("on", True), ("false", False),
     ("", False), (0, False), ("no", False)],
)
def test_truthy(value, expected):
    assert dp.truthy(value) is expected


def test_string_list_dedupes_and_splits():
    assert dp.string_list("a, b, a") == ["a", "b"]
    assert dp.string_list(["a", "b", "a"]) == ["a", "b"]
    assert dp.string_list('["x","y"]') == ["x", "y"]
    assert dp.string_list("") == []


def test_parse_tags_variants():
    assert dp.parse_tags("a, b") == ["a", "b"]
    assert dp.parse_tags('["a","b"]') == ["a", "b"]
    assert dp.parse_tags(["a", "b"]) == ["a", "b"]
    assert dp.parse_tags("") is None


def test_first_value_prefers_snake_then_camel():
    assert dp.first_value({"a_b": "x", "aB": "y"}, "a_b", "aB") == "x"
    assert dp.first_value({"aB": "y"}, "a_b", "aB") == "y"
    assert dp.first_value({"a_b": ""}, "a_b", default="d") == "d"


def test_required_text_and_object_raise():
    with pytest.raises(HomeAssistantError):
        dp.required_text({}, "query")
    with pytest.raises(HomeAssistantError):
        dp.required_object({"data": "not-a-dict"}, "data")
    assert dp.required_object({"data": {"k": 1}}, "data") == {"k": 1}


# --- base + target ----------------------------------------------------------


def test_base_payload_snake_and_camel_match():
    runtime = _FakeRuntime()
    snake = dp.base_payload(runtime, {"installation_id": "i9", "knowledge_space_id": "k9"})
    camel = dp.base_payload(runtime, {"installationId": "i9", "knowledgeSpaceId": "k9"})
    assert snake == camel == {"installationId": "i9", "knowledgeSpaceId": "k9"}


def test_target_payload_snake_and_camel_match():
    snake = dp.target_payload(
        {"target_kind": "device", "target_id": "d1", "relation": "documents"}
    )
    camel = dp.target_payload(
        {"targetKind": "device", "targetId": "d1", "relation": "documents"}
    )
    assert snake == camel == {"kind": "device", "id": "d1", "relation": "documents"}


def test_target_payload_accepts_explicit_object_and_title():
    explicit = dp.target_payload({"target": {"kind": "area", "id": "a1"}})
    assert explicit == {"kind": "area", "id": "a1"}
    with_title = dp.target_payload(
        {"target_kind": "device", "target_id": "d1", "title": "Boiler"}
    )
    assert with_title["title"] == "Boiler"


def test_target_payload_requires_kind_and_id_together():
    assert dp.target_payload({}) is None
    with pytest.raises(HomeAssistantError):
        dp.target_payload({"target_kind": "device"})


# --- home_graph / artifact / link / review ----------------------------------


def test_home_graph_payload_snake_and_camel_match():
    runtime = _FakeRuntime()
    snake = dp.home_graph_payload(
        runtime,
        {"target_kind": "device", "target_id": "d1", "metadata": {"a": 1}},
    )
    camel = dp.home_graph_payload(
        runtime,
        {"targetKind": "device", "targetId": "d1", "metadata": '{"a": 1}'},
    )
    assert snake == camel
    assert snake["target"] == {"kind": "device", "id": "d1"}
    assert snake["metadata"] == {"a": 1}


def test_home_graph_payload_requires_enabled():
    with pytest.raises(HomeAssistantError):
        dp.home_graph_payload(_FakeRuntime(enabled=False), {})


def test_artifact_payload_requires_a_source():
    runtime = _FakeRuntime()
    assert "uri" in dp.artifact_payload(runtime, {"url": "http://x/y.pdf"})
    assert "path" in dp.artifact_payload(runtime, {"path": "/tmp/a.pdf"})
    with pytest.raises(HomeAssistantError):
        dp.artifact_payload(runtime, {})


def test_link_payload_snake_and_camel_match():
    runtime = _FakeRuntime()
    snake = dp.link_payload(
        runtime,
        {"source_id": "s1", "target_kind": "device", "target_id": "d1"},
    )
    camel = dp.link_payload(
        runtime,
        {"sourceId": "s1", "targetKind": "device", "targetId": "d1"},
    )
    assert snake == camel
    assert snake["sourceId"] == "s1"
    assert snake["target"] == {"kind": "device", "id": "d1"}


def test_link_payload_requires_source_or_node_and_target():
    runtime = _FakeRuntime()
    with pytest.raises(HomeAssistantError):
        dp.link_payload(runtime, {"target_kind": "device", "target_id": "d1"})
    with pytest.raises(HomeAssistantError):
        dp.link_payload(runtime, {"source_id": "s1"})


def test_review_payload_action_and_id_aliases():
    runtime = _FakeRuntime()
    by_action = dp.review_payload(runtime, {"action": "reject", "issue_id": "i1"})
    by_decision = dp.review_payload(runtime, {"decision": "reject", "issueId": "i1"})
    assert by_action == by_decision
    assert by_action["action"] == "reject"
    assert by_action["issueId"] == "i1"
    with pytest.raises(HomeAssistantError):
        dp.review_payload(runtime, {"action": "reject"})  # no id


# --- map (the field-list convergence point) ---------------------------------


def test_map_payload_snake_and_camel_lists_match():
    runtime = _FakeRuntime()
    snake = dp.map_payload(
        runtime,
        {
            "limit": "5",
            "query": "lights",
            "min_confidence": "0.4",
            "include_sources": "true",
            "node_kinds": "device, area",
            "entity_ids": "light.a, light.b",
        },
    )
    camel = dp.map_payload(
        runtime,
        {
            "limit": 5,
            "query": "lights",
            "minConfidence": 0.4,
            "includeSources": True,
            "nodeKinds": ["device", "area"],
            "ha": {"entityIds": ["light.a", "light.b"]},
        },
    )
    assert snake == camel
    assert snake["limit"] == 5
    assert snake["minConfidence"] == 0.4
    assert snake["includeSources"] is True
    assert snake["nodeKinds"] == ["device", "area"]
    assert snake["ha"] == {"entityIds": ["light.a", "light.b"]}


# --- prompt (webhook contract) ----------------------------------------------


def test_prompt_payload_shape():
    payload = dp.prompt_payload(
        {"message": "hi", "device_id": "d1", "tools": ["t1"]},
        message_key="message",
        body_type="prompt",
    )
    assert payload["type"] == "prompt"
    assert payload["message"] == "hi"
    assert payload["deviceId"] == "d1"
    assert payload["tools"] == ["t1"]
    assert payload["conversationId"] == "home"
