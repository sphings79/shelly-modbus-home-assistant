"""Repository-level sanity checks."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMPONENT = ROOT / "custom_components" / "shelly_modbus"


def test_manifest_is_complete():
    manifest = json.loads((COMPONENT / "manifest.json").read_text())
    for key in (
        "domain",
        "name",
        "version",
        "documentation",
        "requirements",
        "codeowners",
        "iot_class",
    ):
        assert manifest.get(key), f"manifest is missing {key}"
    assert manifest["domain"] == "shelly_modbus"
    assert manifest["config_flow"] is True
    assert manifest["iot_class"] == "local_polling"


def test_manifest_keys_are_sorted():
    """hassfest requires: domain, name, then the rest alphabetically."""
    manifest = json.loads((COMPONENT / "manifest.json").read_text())
    keys = list(manifest)
    assert keys[:2] == ["domain", "name"]
    assert keys[2:] == sorted(keys[2:])


def test_brand_assets_exist():
    """HACS rejects an integration without brand assets or a brands entry."""
    brand = COMPONENT / "brand"
    for name in ("icon.png", "logo.png"):
        assert (brand / name).is_file(), f"missing brand asset {name}"


def test_hacs_manifest_exists():
    hacs = json.loads((ROOT / "hacs.json").read_text())
    assert hacs["name"]
    assert hacs["homeassistant"]


def test_every_platform_module_exists():
    from shelly_modbus.const import PLATFORMS

    for platform in PLATFORMS:
        assert (COMPONENT / f"{platform}.py").is_file()
