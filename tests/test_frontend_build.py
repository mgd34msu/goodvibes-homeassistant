"""Guards for the built sidebar panel assets.

The panel assets are authored in ``frontend/src`` and built into the served
directory by ``frontend/build.mjs``. These tests do not run the JavaScript build
(that is CI's job via ``npm run check``); they assert the committed served
artifacts exist, are non-empty, carry the build banner stamped with the current
integration version, and were not replaced by an empty or truncated file.
"""

from __future__ import annotations

from pathlib import Path

from custom_components.goodvibes.const import INTEGRATION_VERSION

FRONTEND_DIR = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "goodvibes"
    / "frontend"
)
SRC_DIR = Path(__file__).resolve().parents[1] / "frontend" / "src"

BUILT_ASSETS = ["goodvibes-home-panel.js", "goodvibes-icons.js"]


def test_source_modules_are_checked_in():
    """Each built asset has an authored source it is built from."""

    for name in BUILT_ASSETS:
        source = SRC_DIR / name
        assert source.is_file(), f"missing panel source {source}"
        assert source.stat().st_size > 0


def test_built_assets_carry_versioned_banner():
    """Each served artifact is present and stamped with the build banner."""

    for name in BUILT_ASSETS:
        served = FRONTEND_DIR / name
        assert served.is_file(), f"missing built asset {served}"
        text = served.read_text(encoding="utf-8")
        assert text.strip(), f"{name} is empty"
        assert "GoodVibes Home Assistant" in text
        assert f"v{INTEGRATION_VERSION}" in text.splitlines()[0]
        # The banner names the build script so the artifact is clearly generated.
        assert "frontend/build.mjs" in text


def test_panel_defines_its_custom_element():
    """The built panel still registers the custom element it must define."""

    text = (FRONTEND_DIR / "goodvibes-home-panel.js").read_text(encoding="utf-8")
    assert 'customElements.define("goodvibes-home-panel"' in text
