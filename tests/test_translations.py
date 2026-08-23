"""Every entity must have an English and a German name."""

import json
from pathlib import Path

import pytest
from shelly_modbus.registers import expand_definitions, load_models

TRANSLATIONS = (
    Path(__file__).resolve().parent.parent
    / "custom_components"
    / "shelly_modbus"
    / "translations"
)
LANGUAGES = ["en", "de"]


def load(language):
    return json.loads((TRANSLATIONS / f"{language}.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("language", LANGUAGES)
def test_every_definition_has_a_name(language):
    translations = load(language)["entity"]
    missing = set()

    for model in load_models():
        for profile in load_models()[model]["profiles"]:
            for definition in expand_definitions(model, profile):
                platform = definition.get("platform", "sensor")
                key = definition["translation_key"]
                if key not in translations.get(platform, {}):
                    missing.add(f"{platform}.{key}")

    assert not missing, f"missing {language} names: {sorted(missing)}"


def test_languages_have_identical_keys():
    english, german = (load(language)["entity"] for language in LANGUAGES)
    assert english.keys() == german.keys()
    for platform in english:
        assert english[platform].keys() == german[platform].keys()


@pytest.mark.parametrize("language", LANGUAGES)
def test_placeholders_are_consistent(language):
    """A name using {idx} must use it in every language."""
    english, other = load("en")["entity"], load(language)["entity"]
    for platform, items in english.items():
        for key, value in items.items():
            expected = "{idx}" in value["name"]
            actual = "{idx}" in other[platform][key]["name"]
            assert expected == actual, f"{platform}.{key} placeholder mismatch"


@pytest.mark.parametrize("language", LANGUAGES)
def test_config_and_options_steps_exist(language):
    data = load(language)
    assert data["config"]["step"]["user"]["data"]["host"]
    assert data["config"]["step"]["model"]["data"]["model"]
    assert data["options"]["step"]["init"]["data"]["scan_interval_high"]
    assert data["options"]["step"]["init"]["data"]["scan_interval_low"]


@pytest.mark.parametrize("language", LANGUAGES)
def test_german_names_are_not_just_english(language):
    """Guard against the German file being a copy of the English one."""
    if language == "en":
        return
    english, german = load("en")["entity"], load("de")["entity"]
    identical = sum(
        1
        for platform in english
        for key in english[platform]
        if english[platform][key]["name"] == german[platform][key]["name"]
    )
    total = sum(len(items) for items in english.values())
    assert identical / total < 0.2, "German translations look untranslated"
