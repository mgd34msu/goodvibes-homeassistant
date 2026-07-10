"""Home Graph snapshot helpers for the GoodVibes integration."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from enum import Enum
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import (
    area_registry as ar,
    device_registry as dr,
    entity_registry as er,
)
from homeassistant.util import dt as dt_util

try:
    from homeassistant.loader import async_get_integration
except ImportError:
    async_get_integration = None

try:
    from homeassistant.const import __version__ as HA_VERSION
except ImportError:
    HA_VERSION = "unknown"

try:
    from homeassistant.helpers import label_registry as lr
except ImportError:
    lr = None

try:
    from homeassistant.components.homeassistant.exposed_entities import (
        async_should_expose,
    )
except ImportError:
    async_should_expose = None

# The Home Graph snapshot honors the same "expose to assistants" boundary that
# Home Assistant's built-in Assist/conversation agents use. That boundary is
# keyed per assistant; the conversation assistant key is "conversation".
EXPOSED_ASSISTANT = "conversation"

HELPER_DOMAINS = {
    "counter",
    "input_boolean",
    "input_button",
    "input_datetime",
    "input_number",
    "input_select",
    "input_text",
    "number",
    "schedule",
    "timer",
}

DEFAULT_PAGE_AUTOMATION_MAX_RUN_MS = 120000

DEFAULT_PAGE_AUTOMATION = {
    "enabled": True,
    "devicePassports": True,
    "roomPages": True,
    "maxRunMs": DEFAULT_PAGE_AUTOMATION_MAX_RUN_MS,
}


def derive_installation_id(hass: HomeAssistant, entry: ConfigEntry | None = None) -> str:
    """Return a stable Home Assistant installation id for Home Graph."""

    config_uuid = getattr(hass.config, "uuid", None)
    if config_uuid:
        return str(config_uuid)
    if entry is not None:
        return entry.entry_id
    location_name = getattr(hass.config, "location_name", None)
    if location_name:
        return _slug(str(location_name))
    return "homeassistant"


def default_knowledge_space_id(installation_id: str) -> str:
    """Return the default Home Graph knowledge space id."""

    return f"homeassistant:{installation_id}"


def build_home_graph_base_payload(
    installation_id: str,
    knowledge_space_id: str | None = None,
) -> dict[str, Any]:
    """Build common Home Graph payload fields."""

    payload = {"installationId": installation_id}
    if knowledge_space_id:
        payload["knowledgeSpaceId"] = knowledge_space_id
    return payload


async def async_build_home_graph_snapshot(
    hass: HomeAssistant,
    entry: ConfigEntry,
    installation_id: str,
    knowledge_space_id: str | None = None,
    include_unexposed: bool = False,
    resolve_provenance: Callable[[Any], dict[str, Any] | None] | None = None,
) -> dict[str, Any]:
    """Build the Home Assistant context snapshot sent to the daemon.

    By default only entities the user has exposed to assistants are included, so
    the snapshot respects the same boundary Home Assistant's own voice and
    conversation agents honor. Pass ``include_unexposed=True`` to carry the whole
    registry regardless of exposure. Devices and areas are pruned to those that
    still own at least one included entity.

    When ``resolve_provenance`` is supplied it is called with each entity state's
    Home Assistant :class:`~homeassistant.core.Context` and returns the causal
    provenance for that state (which automation/script/user/integration caused
    it, chained where Home Assistant supplies parent contexts). That provenance
    travels on each entity so the registered/synced graph — and therefore the
    daemon's grounding ``ask`` path — can answer cause questions. Older daemons
    ignore the extra field.
    """

    entity_registry = er.async_get(hass)
    device_registry = dr.async_get(hass)
    area_registry = ar.async_get(hass)

    included_registry_entities = [
        entity
        for entity in _registry_items(entity_registry, "entities")
        if _should_include_entity(
            hass, str(getattr(entity, "entity_id", "")), include_unexposed
        )
    ]
    entities = [
        _entity_snapshot(hass, entity, resolve_provenance)
        for entity in included_registry_entities
    ]

    included_device_ids = {
        device_id
        for entity in included_registry_entities
        if (device_id := getattr(entity, "device_id", None))
    }
    included_devices = [
        device
        for device in _registry_items(device_registry, "devices")
        if getattr(device, "id", None) in included_device_ids
    ]

    # An area is kept when at least one included entity resolves to it, either
    # directly (entity area) or through the area of an included device.
    included_area_ids = {
        area_id
        for entity in included_registry_entities
        if (area_id := getattr(entity, "area_id", None))
    }
    for device in included_devices:
        if area_id := getattr(device, "area_id", None):
            included_area_ids.add(area_id)
    included_areas = [
        area
        for area in _registry_items(area_registry, "areas")
        if getattr(area, "id", None) in included_area_ids
    ]

    snapshot: dict[str, Any] = {
        **build_home_graph_base_payload(installation_id, knowledge_space_id),
        "title": getattr(hass.config, "location_name", None) or "Home Assistant",
        "pageAutomation": dict(DEFAULT_PAGE_AUTOMATION),
        "entities": entities,
        "devices": [_device_snapshot(device) for device in included_devices],
        "areas": [_area_snapshot(area) for area in included_areas],
        "automations": _domain_snapshots(entities, "automation"),
        "scripts": _domain_snapshots(entities, "script"),
        "scenes": _domain_snapshots(entities, "scene"),
        "labels": _label_snapshots(hass),
        "integrations": await _integration_snapshots(hass),
        "metadata": {
            "source": "homeassistant",
            "integration": "goodvibes",
            "configEntryId": entry.entry_id,
            "homeAssistantVersion": HA_VERSION,
            "generatedAt": dt_util.utcnow().isoformat(),
            "helperDomains": sorted(HELPER_DOMAINS),
            "helpers": [
                entity
                for entity in entities
                if str(entity.get("domain")) in HELPER_DOMAINS
            ],
        },
    }
    return snapshot


def _should_include_entity(
    hass: HomeAssistant,
    entity_id: str,
    include_unexposed: bool,
) -> bool:
    """Return whether a registry entity belongs in the snapshot.

    With ``include_unexposed`` the whole registry is kept. Otherwise the entity
    is included only when Home Assistant reports it as exposed to assistants. If
    the exposed-entities helper is unavailable (older cores), the snapshot falls
    back to including everything rather than hiding the entire home.
    """

    if not entity_id:
        return False
    if include_unexposed or async_should_expose is None:
        return True
    return bool(async_should_expose(hass, EXPOSED_ASSISTANT, entity_id))


def _entity_snapshot(
    hass: HomeAssistant,
    entity: Any,
    resolve_provenance: Callable[[Any], dict[str, Any] | None] | None = None,
) -> dict[str, Any]:
    entity_id = str(getattr(entity, "entity_id", ""))
    domain = entity_id.split(".", 1)[0] if "." in entity_id else None
    platform = getattr(entity, "platform", None)
    state = hass.states.get(entity_id) if entity_id else None
    provenance = None
    if resolve_provenance is not None and state is not None:
        # Attribute this state's cause from its Home Assistant context chain.
        provenance = resolve_provenance(getattr(state, "context", None))
    return _clean_dict(
        {
            "entityId": entity_id,
            "domain": domain,
            "uniqueId": getattr(entity, "unique_id", None),
            "platform": platform,
            "integrationId": platform,
            "deviceId": getattr(entity, "device_id", None),
            "areaId": getattr(entity, "area_id", None),
            "name": getattr(entity, "name", None),
            "originalName": getattr(entity, "original_name", None),
            "translationKey": getattr(entity, "translation_key", None),
            "entityCategory": _jsonable(getattr(entity, "entity_category", None)),
            "disabledBy": _jsonable(getattr(entity, "disabled_by", None)),
            "hiddenBy": _jsonable(getattr(entity, "hidden_by", None)),
            "labels": _jsonable(getattr(entity, "labels", None)),
            "aliases": _jsonable(getattr(entity, "aliases", None)),
            "state": state.state if state else None,
            "lastChanged": _state_timestamp(state, "last_changed"),
            "lastUpdated": _state_timestamp(state, "last_updated"),
            "attributes": _state_attributes(state),
            "provenance": provenance,
            "metadata": {
                "source": "entity_registry",
                "domain": domain,
                "platform": platform,
                "uniqueId": getattr(entity, "unique_id", None),
                "translationKey": getattr(entity, "translation_key", None),
                "entityCategory": _jsonable(getattr(entity, "entity_category", None)),
                "disabledBy": _jsonable(getattr(entity, "disabled_by", None)),
                "hiddenBy": _jsonable(getattr(entity, "hidden_by", None)),
                # Mirror the attributed cause so a graph indexer that reads only
                # metadata still carries "what caused this state".
                "cause": (provenance or {}).get("cause"),
            },
        }
    )


def _device_snapshot(device: Any) -> dict[str, Any]:
    return _clean_dict(
        {
            "id": getattr(device, "id", None),
            "name": getattr(device, "name", None),
            "nameByUser": getattr(device, "name_by_user", None),
            "areaId": getattr(device, "area_id", None),
            "manufacturer": getattr(device, "manufacturer", None),
            "model": getattr(device, "model", None),
            "modelId": getattr(device, "model_id", None),
            "swVersion": getattr(device, "sw_version", None),
            "hwVersion": getattr(device, "hw_version", None),
            "serialNumber": getattr(device, "serial_number", None),
            "configurationUrl": getattr(device, "configuration_url", None),
            "entryType": _jsonable(getattr(device, "entry_type", None)),
            "disabledBy": _jsonable(getattr(device, "disabled_by", None)),
            "viaDeviceId": getattr(device, "via_device_id", None),
            "configEntries": _jsonable(getattr(device, "config_entries", None)),
            "identifiers": _jsonable(getattr(device, "identifiers", None)),
            "connections": _jsonable(getattr(device, "connections", None)),
            "labels": _jsonable(getattr(device, "labels", None)),
            "metadata": {
                "source": "device_registry",
                "nameByUser": getattr(device, "name_by_user", None),
                "modelId": getattr(device, "model_id", None),
                "swVersion": getattr(device, "sw_version", None),
                "hwVersion": getattr(device, "hw_version", None),
                "serialNumber": getattr(device, "serial_number", None),
                "configurationUrl": getattr(device, "configuration_url", None),
                "entryType": _jsonable(getattr(device, "entry_type", None)),
                "disabledBy": _jsonable(getattr(device, "disabled_by", None)),
                "viaDeviceId": getattr(device, "via_device_id", None),
                "configEntries": _jsonable(getattr(device, "config_entries", None)),
                "identifiers": _jsonable(getattr(device, "identifiers", None)),
                "connections": _jsonable(getattr(device, "connections", None)),
            },
        }
    )


def _area_snapshot(area: Any) -> dict[str, Any]:
    return _clean_dict(
        {
            "id": getattr(area, "id", None),
            "name": getattr(area, "name", None),
            "aliases": _jsonable(getattr(area, "aliases", None)),
            "labels": _jsonable(getattr(area, "labels", None)),
            "picture": getattr(area, "picture", None),
            "metadata": {
                "source": "area_registry",
                "picture": getattr(area, "picture", None),
            },
        }
    )


def _label_snapshots(hass: HomeAssistant) -> list[dict[str, Any]]:
    if lr is None:
        return []
    label_registry = lr.async_get(hass)
    return [
        _clean_dict(
            {
                "id": getattr(label, "label_id", None) or getattr(label, "id", None),
                "name": getattr(label, "name", None),
                "description": getattr(label, "description", None),
                "icon": getattr(label, "icon", None),
                "color": getattr(label, "color", None),
                "metadata": {
                    "source": "label_registry",
                    "icon": getattr(label, "icon", None),
                    "color": getattr(label, "color", None),
                },
            }
        )
        for label in _registry_items(label_registry, "labels")
    ]


async def _integration_snapshots(hass: HomeAssistant) -> list[dict[str, Any]]:
    entries_by_domain: dict[str, list[dict[str, Any]]] = {}
    for config_entry in hass.config_entries.async_entries():
        domain = str(config_entry.domain)
        entries_by_domain.setdefault(domain, []).append(
            _clean_dict(
                {
                    "entryId": config_entry.entry_id,
                    "title": config_entry.title,
                    "uniqueId": config_entry.unique_id,
                    "source": getattr(config_entry, "source", None),
                    "disabledBy": _jsonable(
                        getattr(config_entry, "disabled_by", None)
                    ),
                    "state": _jsonable(getattr(config_entry, "state", None)),
                }
            )
        )
    snapshots = []
    for domain, entries in sorted(entries_by_domain.items()):
        integration_metadata = await _async_integration_metadata(hass, domain)
        snapshots.append(
            _clean_dict(
                {
                    "id": domain,
                    "integrationId": domain,
                    "domain": domain,
                    "title": entries[0].get("title") if len(entries) == 1 else domain,
                    "documentationUrl": integration_metadata.get("documentationUrl"),
                    "documentationUrls": integration_metadata.get(
                        "documentationUrls"
                    ),
                    "sourceUrls": integration_metadata.get("sourceUrls"),
                    "issueTrackerUrl": integration_metadata.get("issueTrackerUrl"),
                    "suggestedSources": integration_metadata.get("suggestedSources"),
                    "metadata": {
                        "source": "config_entries",
                        "entryCount": len(entries),
                        "entries": entries,
                        **integration_metadata,
                    },
                }
            )
        )
    return snapshots


async def _async_integration_metadata(
    hass: HomeAssistant,
    domain: str,
) -> dict[str, Any]:
    """Return documentation/source metadata for a Home Assistant integration."""

    documentation_urls = [f"https://www.home-assistant.io/integrations/{domain}/"]
    source_urls: list[str] = []
    issue_tracker_url: str | None = None
    raw: dict[str, Any] = {}
    integration = None

    if async_get_integration is not None:
        try:
            integration = await async_get_integration(hass, domain)
        except Exception:
            integration = None

    if integration is not None:
        manifest = getattr(integration, "manifest", None)
        if isinstance(manifest, dict):
            raw.update(manifest)
        for key in (
            "name",
            "documentation",
            "issue_tracker",
            "iot_class",
            "integration_type",
            "quality_scale",
            "requirements",
            "dependencies",
            "after_dependencies",
            "codeowners",
            "config_flow",
        ):
            value = getattr(integration, key, None)
            if value not in (None, ""):
                raw.setdefault(key, value)

        if documentation := _first_text(
            raw.get("documentation"),
            getattr(integration, "documentation", None),
        ):
            documentation_urls.append(documentation)
        if issue_tracker_url := _first_text(
            raw.get("issue_tracker"),
            getattr(integration, "issue_tracker", None),
        ):
            pass
        if source_url := _first_text(
            raw.get("source_url"),
            raw.get("source"),
            getattr(integration, "source_url", None),
        ):
            source_urls.append(source_url)

        file_path = str(getattr(integration, "file_path", "") or "")
        if file_path and "custom_components" not in file_path:
            source_urls.append(
                f"https://github.com/home-assistant/core/tree/dev/homeassistant/components/{domain}"
            )

    documentation_urls = _unique_texts(documentation_urls)
    source_urls = _unique_texts(source_urls)
    suggested_sources = [
        _source_candidate(
            url,
            f"{domain} Home Assistant documentation",
            "documentation",
        )
        for url in documentation_urls
    ]
    suggested_sources.extend(
        _source_candidate(url, f"{domain} source", "source")
        for url in source_urls
    )
    if issue_tracker_url:
        suggested_sources.append(
            _source_candidate(
                issue_tracker_url,
                f"{domain} issue tracker",
                "issue_tracker",
            )
        )

    return _clean_dict(
        {
            "name": raw.get("name"),
            "documentationUrl": documentation_urls[0] if documentation_urls else None,
            "documentationUrls": documentation_urls,
            "sourceUrls": source_urls,
            "issueTrackerUrl": issue_tracker_url,
            "suggestedSources": suggested_sources,
            "manifest": _jsonable(raw) if raw else None,
        }
    )


def _source_candidate(url: str, title: str, kind: str) -> dict[str, Any]:
    """Return a daemon-friendly source suggestion for an integration."""

    return {
        "url": url,
        "title": title,
        "kind": kind,
        "relation": "source_for",
    }


def _first_text(*values: Any) -> str | None:
    """Return the first non-empty string-like value."""

    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _unique_texts(values: Iterable[Any]) -> list[str]:
    """Return unique non-empty strings in input order."""

    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if not isinstance(value, str):
            continue
        text = value.strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _domain_snapshots(entities: list[dict[str, Any]], domain: str) -> list[dict[str, Any]]:
    return [entity for entity in entities if entity.get("domain") == domain]


def _state_timestamp(state: Any, attr: str) -> str | None:
    """Return an entity state timestamp (last_changed/last_updated) as ISO text.

    These per-entity timestamps travel with the snapshot so any answer built from
    a snapshotted state can cite when that state was observed, not just its value.
    The snapshot-level observation time is recorded separately as
    ``metadata.generatedAt``.
    """

    if state is None:
        return None
    value = getattr(state, attr, None)
    if value is None:
        return None
    isoformat = getattr(value, "isoformat", None)
    if callable(isoformat):
        return str(isoformat())
    return str(value)


def _state_attributes(state: Any) -> dict[str, Any]:
    if state is None:
        return {}
    keys = {
        "device_class",
        "entity_picture",
        "friendly_name",
        "icon",
        "supported_features",
        "unit_of_measurement",
    }
    return {
        key: _jsonable(value)
        for key, value in state.attributes.items()
        if key in keys or key.startswith("assumed_")
    }


def _registry_items(registry: Any, attr: str) -> Iterable[Any]:
    listing_method = getattr(registry, f"async_list_{attr}", None)
    if callable(listing_method):
        return listing_method()
    values = getattr(registry, attr, None)
    if values is None:
        return []
    if hasattr(values, "values"):
        return values.values()
    return values


def _clean_dict(value: dict[str, Any]) -> dict[str, Any]:
    return {
        key: cleaned
        for key, raw in value.items()
        if (cleaned := _jsonable(raw)) not in (None, {}, [])
    }


def _jsonable(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {
            str(key): converted
            for key, raw in value.items()
            if (converted := _jsonable(raw)) is not None
        }
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_jsonable(item) for item in sorted(value, key=str)]
    return str(value)


def _slug(value: str) -> str:
    lowered = value.strip().lower()
    return "".join(char if char.isalnum() else "-" for char in lowered).strip("-")
