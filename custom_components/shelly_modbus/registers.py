"""
Loading and expansion of the YAML register definitions.

``registers/components.yaml`` describes each Shelly component type once, with
offsets relative to the component's base address.  ``registers/models.yaml``
lists which component instances a given device model publishes.  Expanding one
against the other yields the flat list of entity definitions the coordinator
and the platforms work with.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from .const import MAX_BLOCK_SIZE, SCAN_INTERVAL_HIGH, SCAN_INTERVAL_STATIC
from .helpers.modbus_client import register_count

_LOGGER = logging.getLogger(__name__)

_REGISTER_DIR = Path(__file__).parent / "registers"

# Component types whose fields are power-meter readings.  When a model declares
# `metering: false` for an instance, these are skipped.
_METERING_EXEMPT_FIELDS = {"output", "state"}


def _load_yaml(path: Path) -> dict:
    """Read one YAML file, returning an empty dict when it is missing."""
    try:
        with path.open("r", encoding="utf-8") as handle:
            return yaml.safe_load(handle) or {}
    except FileNotFoundError:
        _LOGGER.error("Register definition file not found: %s", path)
        return {}
    except yaml.YAMLError as err:
        _LOGGER.error("Could not parse %s: %s", path, err)
        return {}


def load_components() -> dict[str, Any]:
    """Return the component register maps."""
    return _load_yaml(_REGISTER_DIR / "components.yaml")


def load_models() -> dict[str, Any]:
    """Return the model database keyed by Shelly model code."""
    return _load_yaml(_REGISTER_DIR / "models.yaml").get("models", {})


def model_options() -> dict[str, str]:
    """Return ``{model_code: display name}`` for the config flow selector."""
    return {code: spec.get("name", code) for code, spec in load_models().items()}


def profiles_for_model(model: str) -> list[str]:
    """Return the profile names a model supports."""
    spec = load_models().get(model)
    if not spec:
        return []
    return list(spec.get("profiles", {}))


def _instance_label(component: dict, comp_type: str, comp_id: int) -> str | None:
    """Build the per-instance name prefix, e.g. "Channel 2"."""
    template = component.get("instance_label")
    if not template:
        return None
    return template.format(id=comp_id, id_1=comp_id + 1)


def component_blocks(comp_type: str, comp_id: int) -> dict[str, int] | None:
    """Return the address window a component instance occupies.

    Used to probe whether the instance exists on the device.
    """
    components = load_components()
    component = components.get(comp_type)
    if not component or "base" not in component:
        return None
    base = component["base"] + comp_id * component.get("stride", 0)
    return {"base": base}


def expand_definitions(model: str, profile: str | None = None) -> list[dict[str, Any]]:
    """Expand a model into flat entity definitions.

    Each returned definition carries everything an entity needs: its unique
    ``key``, the wire ``address``, how to decode it, and its presentation
    metadata.
    """
    components = load_components()
    models = load_models()

    spec = models.get(model)
    if not spec:
        _LOGGER.error("Unknown Shelly model '%s'", model)
        return []

    profiles = spec.get("profiles", {})
    if profile not in profiles:
        profile = spec.get("default_profile") or next(iter(profiles), None)
    instances = profiles.get(profile, {}).get("components", [])

    definitions: list[dict[str, Any]] = []

    # Device-level identity registers are present on every model.
    definitions.extend(_expand_instance(components, {"type": "device", "id": 0}))

    for instance in instances:
        definitions.extend(_expand_instance(components, instance))

    return definitions


def _expand_instance(
    components: dict[str, Any], instance: dict[str, Any]
) -> list[dict[str, Any]]:
    """Expand one component instance into its entity definitions."""
    comp_type = instance.get("type")
    comp_id = int(instance.get("id", 0))
    has_metering = instance.get("metering", True)

    component = components.get(comp_type)
    if not component:
        _LOGGER.warning("No register map for component type '%s'", comp_type)
        return []

    stride = component.get("stride", 0)
    base = component.get("base")
    label = _instance_label(component, comp_type, comp_id)

    # Coils and discrete inputs use their own base/stride.
    coil_base = component.get("coil_base")
    coil_stride = component.get("coil_stride", 0)
    discrete_base = component.get("discrete_base")
    discrete_stride = component.get("discrete_stride", 0)

    definitions: list[dict[str, Any]] = []

    for field_key, field in (component.get("fields") or {}).items():
        if not has_metering and field_key not in _METERING_EXEMPT_FIELDS:
            continue

        data_type = field.get("data_type", "uint16")

        # Build a key that stays unique across component instances.
        if comp_type == "device":
            key = field_key
        else:
            key = f"{comp_type}_{comp_id}_{field_key}"

        # Entity names are translated by Home Assistant.  The translation key
        # is per component type and field, so all instances of a component
        # share one string; the instance number is passed as a placeholder.
        translation_key = (
            field_key if comp_type == "device" else f"{comp_type}_{field_key}"
        )

        definition: dict[str, Any] = {
            "key": key,
            "field": field_key,
            "translation_key": translation_key,
            "translation_placeholders": {"idx": str(comp_id + 1)} if label else None,
            "component": comp_type,
            "component_id": comp_id,
            "instance_label": label,
            "data_type": data_type,
            "name": field.get("name", field_key.replace("_", " ").title()),
            "platform": field.get("platform", "sensor"),
            "unit": field.get("unit"),
            "scale": field.get("scale"),
            "device_class": field.get("device_class"),
            "state_class": field.get("state_class"),
            "icon": field.get("icon"),
            "category": field.get("category"),
            "precision": field.get("precision"),
            "enabled_by_default": field.get("enabled_by_default", True),
            "scan_interval": field.get("scan_interval", SCAN_INTERVAL_HIGH),
        }

        if data_type == "discrete":
            if discrete_base is None:
                continue
            definition["address"] = discrete_base + comp_id * discrete_stride
            definition["access"] = "discrete_input"
        elif field.get("platform") == "switch":
            # The readable state lives in an input register, the writable
            # output in a coil.
            if base is None:
                continue
            definition["address"] = base + comp_id * stride + field.get("offset", 0)
            definition["count"] = register_count(data_type, field.get("count"))
            definition["access"] = "input_register"
            if coil_base is not None:
                definition["coil_address"] = coil_base + comp_id * coil_stride
        else:
            if base is None:
                continue
            definition["address"] = base + comp_id * stride + field.get("offset", 0)
            definition["count"] = register_count(data_type, field.get("count"))
            definition["access"] = "input_register"

        definitions.append(definition)

    return definitions


def entity_name(definition: dict[str, Any]) -> str:
    """Return the display name, prefixed with the instance label if any."""
    label = definition.get("instance_label")
    name = definition.get("name", definition["key"])
    return f"{label} {name}" if label else name


def is_static(definition: dict[str, Any]) -> bool:
    """Return True for values that never change while the device runs."""
    return definition.get("scan_interval") == SCAN_INTERVAL_STATIC


# Registers this far apart are still read in one request; bridging a small gap
# costs less than a second round trip.
MAX_BLOCK_GAP = 8


def build_blocks(definitions: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Group register definitions into contiguous read blocks.

    Blocks never span component instances, because the address space between
    them is unmapped and the device answers with an exception response.  Each
    block also stays within the device's maximum request size.
    """
    by_component: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for definition in definitions:
        if definition.get("access") != "input_register":
            continue
        group = (definition["component"], definition["component_id"])
        by_component.setdefault(group, []).append(definition)

    blocks: list[list[dict[str, Any]]] = []
    for group_definitions in by_component.values():
        group_definitions.sort(key=lambda d: d["address"])
        current: list[dict[str, Any]] = []

        for definition in group_definitions:
            if not current:
                current = [definition]
                continue

            start = current[0]["address"]
            end = definition["address"] + definition.get("count", 1)
            previous_end = max(d["address"] + d.get("count", 1) for d in current)

            if (
                end - start <= MAX_BLOCK_SIZE
                and definition["address"] - previous_end <= MAX_BLOCK_GAP
            ):
                current.append(definition)
            else:
                blocks.append(current)
                current = [definition]

        if current:
            blocks.append(current)

    return blocks
