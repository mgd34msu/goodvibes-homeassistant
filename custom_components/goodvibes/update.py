"""Update entity for the GoodVibes integration."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path, PurePosixPath
from typing import Any
from zipfile import ZipFile

from aiohttp import ClientError
from awesomeversion import AwesomeVersion
from homeassistant.components import persistent_notification
from homeassistant.components.update import UpdateEntity, UpdateEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import GoodVibesRuntimeData
from .const import (
    DOMAIN,
    INTEGRATION_VERSION,
    UPDATE_RELEASES_API_URL,
    UPDATE_RELEASES_URL,
    UPDATE_REPOSITORY,
)

PLACEHOLDER_OWNER = "OWNER/"
GITHUB_HEADERS = {
    "Accept": "application/vnd.github+json",
    "User-Agent": "goodvibes-homeassistant",
}


@dataclass(slots=True)
class ReleaseInfo:
    """Cached GitHub release metadata."""

    version: str
    html_url: str
    body: str
    zipball_url: str
    asset_url: str | None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the GoodVibes update entity."""

    runtime = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([GoodVibesIntegrationUpdate(runtime)])


class GoodVibesIntegrationUpdate(UpdateEntity):
    """Expose GitHub release updates for the custom integration."""

    _attr_has_entity_name = True
    _attr_translation_key = "integration_update"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_supported_features = (
        UpdateEntityFeature.INSTALL | UpdateEntityFeature.RELEASE_NOTES
    )
    _attr_title = "GoodVibes Home Assistant integration"

    def __init__(self, runtime: GoodVibesRuntimeData) -> None:
        """Initialize the update entity."""

        self._runtime = runtime
        base_unique_id = runtime.entry.unique_id or runtime.entry.entry_id
        self._attr_unique_id = f"{base_unique_id}_integration_update"
        self._release: ReleaseInfo | None = None
        self._latest_version = INTEGRATION_VERSION
        self._release_summary: str | None = None
        self._release_url = UPDATE_RELEASES_URL
        self._in_progress = False
        self._last_error: str | None = None

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
    def installed_version(self) -> str:
        """Return the installed integration version."""

        return INTEGRATION_VERSION

    @property
    def latest_version(self) -> str:
        """Return the latest integration version."""

        return self._latest_version

    @property
    def release_url(self) -> str | None:
        """Return the release URL."""

        return self._release_url

    @property
    def release_summary(self) -> str | None:
        """Return a short release summary."""

        return self._release_summary

    @property
    def in_progress(self) -> bool:
        """Return whether install is running."""

        return self._in_progress

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return update metadata."""

        return {
            "repository": UPDATE_REPOSITORY,
            "release_api_url": UPDATE_RELEASES_API_URL,
            "placeholder_repository": _repository_is_placeholder(),
            "last_error": self._last_error,
        }

    async def async_update(self) -> None:
        """Fetch the latest GitHub release metadata."""

        if _repository_is_placeholder():
            self._release = None
            self._latest_version = INTEGRATION_VERSION
            self._release_summary = (
                "Set UPDATE_REPOSITORY in custom_components/goodvibes/const.py "
                "after publishing the GitHub repository."
            )
            self._release_url = UPDATE_RELEASES_URL
            self._last_error = None
            return

        session = async_get_clientsession(self.hass)
        try:
            async with asyncio.timeout(15):
                response = await session.get(
                    UPDATE_RELEASES_API_URL,
                    headers=GITHUB_HEADERS,
                )
                async with response:
                    if response.status >= 400:
                        raise HomeAssistantError(
                            f"GitHub release lookup failed: HTTP {response.status}"
                        )
                    payload = await response.json()
        except (TimeoutError, ClientError, HomeAssistantError) as err:
            self._last_error = str(err)
            return

        release = _release_from_payload(payload)
        if release is None:
            self._last_error = "GitHub release response did not include a usable tag."
            return

        self._release = release
        self._latest_version = release.version
        self._release_summary = _summary_from_body(release.body)
        self._release_url = release.html_url
        self._last_error = None

    async def async_install(
        self,
        version: str | None,
        backup: bool,
        **kwargs: Any,
    ) -> None:
        """Install the latest release from GitHub."""

        if _repository_is_placeholder():
            raise HomeAssistantError(
                "Set UPDATE_REPOSITORY in custom_components/goodvibes/const.py "
                "before installing updates from Home Assistant."
            )

        if self._release is None:
            await self.async_update()
        if self._release is None:
            raise HomeAssistantError(self._last_error or "No release metadata is available.")

        if version and _normalize_version(version) != self._release.version:
            raise HomeAssistantError(
                "Installing a specific GoodVibes integration version is not supported yet."
            )

        self._in_progress = True
        self.async_write_ha_state()
        try:
            data = await self._download_release_zip(self._release)
            await self.hass.async_add_executor_job(
                _install_release_zip,
                data,
                Path(self.hass.config.path("custom_components", DOMAIN)),
            )
            persistent_notification.async_create(
                self.hass,
                (
                    "GoodVibes Home Assistant integration files were updated. "
                    "Restart Home Assistant to load the new version."
                ),
                title="GoodVibes update installed",
                notification_id="goodvibes_update_installed",
            )
        finally:
            self._in_progress = False
            self.async_write_ha_state()

    async def async_release_notes(self) -> str | None:
        """Return full release notes."""

        if self._release is None:
            await self.async_update()
        return self._release.body if self._release else self._release_summary

    def version_is_newer(self, latest_version: str, installed_version: str) -> bool:
        """Return True when the latest version is newer than installed."""

        return AwesomeVersion(latest_version) > AwesomeVersion(installed_version)

    async def _download_release_zip(self, release: ReleaseInfo) -> bytes:
        """Download the release zipball or custom release asset."""

        url = release.asset_url or release.zipball_url
        session = async_get_clientsession(self.hass)
        try:
            async with asyncio.timeout(60):
                response = await session.get(url, headers=GITHUB_HEADERS)
                async with response:
                    if response.status >= 400:
                        raise HomeAssistantError(
                            f"GitHub release download failed: HTTP {response.status}"
                        )
                    return await response.read()
        except (TimeoutError, ClientError) as err:
            raise HomeAssistantError(f"GitHub release download failed: {err}") from err


def _repository_is_placeholder() -> bool:
    """Return whether the GitHub repository still needs to be configured."""

    return UPDATE_REPOSITORY.startswith(PLACEHOLDER_OWNER)


def _release_from_payload(payload: Any) -> ReleaseInfo | None:
    """Build release metadata from the GitHub API payload."""

    if not isinstance(payload, dict):
        return None
    tag = payload.get("tag_name") or payload.get("name")
    zipball_url = payload.get("zipball_url")
    html_url = payload.get("html_url") or UPDATE_RELEASES_URL
    if not isinstance(tag, str) or not tag:
        return None
    if not isinstance(zipball_url, str) or not zipball_url:
        return None
    return ReleaseInfo(
        version=_normalize_version(tag),
        html_url=str(html_url),
        body=str(payload.get("body") or ""),
        zipball_url=zipball_url,
        asset_url=_release_asset_url(payload.get("assets")),
    )


def _release_asset_url(assets: Any) -> str | None:
    """Prefer an explicit release zip asset when one is available."""

    if not isinstance(assets, list):
        return None
    zip_assets = [
        asset
        for asset in assets
        if isinstance(asset, dict)
        and isinstance(asset.get("browser_download_url"), str)
        and str(asset.get("name") or "").lower().endswith(".zip")
    ]
    if not zip_assets:
        return None
    preferred = next(
        (
            asset
            for asset in zip_assets
            if "goodvibes" in str(asset.get("name") or "").lower()
        ),
        zip_assets[0],
    )
    return str(preferred["browser_download_url"])


def _summary_from_body(body: str) -> str | None:
    """Return a Home Assistant-safe release summary."""

    for line in body.splitlines():
        text = line.strip(" -#\t")
        if text:
            return text[:255]
    return None


def _normalize_version(version: str) -> str:
    """Normalize release tag versions."""

    return version.strip().removeprefix("v")


def _install_release_zip(data: bytes, target_dir: Path) -> None:
    """Install integration files from a GitHub release zip."""

    target_dir.mkdir(parents=True, exist_ok=True)
    files = _integration_files_from_zip(data)
    if not files:
        raise HomeAssistantError(
            "The release archive did not contain custom_components/goodvibes files."
        )
    for relative_path, content in files:
        destination = target_dir / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)


def _integration_files_from_zip(data: bytes) -> list[tuple[Path, bytes]]:
    """Return safe integration file paths from a release archive."""

    files: list[tuple[Path, bytes]] = []
    with ZipFile(BytesIO(data)) as archive:
        names = [name for name in archive.namelist() if not name.endswith("/")]
        prefix = _integration_prefix(names)
        if prefix is None:
            return []
        for name in names:
            if not name.startswith(prefix):
                continue
            relative = PurePosixPath(name[len(prefix) :])
            if not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
                continue
            if "__pycache__" in relative.parts:
                continue
            files.append((Path(*relative.parts), archive.read(name)))
    return files


def _integration_prefix(names: list[str]) -> str | None:
    """Find the path prefix that contains this integration in a zipball."""

    candidates = [
        "custom_components/goodvibes/",
        "goodvibes/",
    ]
    for name in names:
        for marker in candidates:
            index = name.find(marker)
            if index >= 0:
                return name[: index + len(marker)]
    return None
