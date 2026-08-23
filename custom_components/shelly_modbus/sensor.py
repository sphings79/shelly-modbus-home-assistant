"""Sensor platform for the Shelly Modbus integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import ShellyModbusCoordinator
from .entity import ShellyModbusEntity

_LOGGER = logging.getLogger(__name__)


def _as_enum(enum_cls, value):
    """Convert a YAML string into a Home Assistant enum member.

    An unrecognised value is dropped rather than raising, so one bad register
    definition cannot take down the whole platform.
    """
    if value is None:
        return None
    try:
        return enum_cls(value)
    except ValueError:
        _LOGGER.warning("Unknown %s '%s'", enum_cls.__name__, value)
        return None


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Create a sensor for every sensor-platform register definition."""
    coordinator: ShellyModbusCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        ShellyModbusSensor(coordinator, definition)
        for definition in coordinator.definitions
        if definition.get("platform", "sensor") == "sensor"
    ]

    _LOGGER.debug("Adding %d Shelly Modbus sensors", len(entities))
    async_add_entities(entities)


class ShellyModbusSensor(ShellyModbusEntity, SensorEntity):
    """A single measured or informational value."""

    def __init__(
        self, coordinator: ShellyModbusCoordinator, definition: dict[str, Any]
    ) -> None:
        super().__init__(coordinator, definition)

        self._attr_native_unit_of_measurement = definition.get("unit")
        self._attr_device_class = _as_enum(
            SensorDeviceClass, definition.get("device_class")
        )
        self._attr_state_class = _as_enum(
            SensorStateClass, definition.get("state_class")
        )

        if (precision := definition.get("precision")) is not None:
            self._attr_suggested_display_precision = precision

    @property
    def native_value(self) -> Any:
        """Return the current value."""
        return self.native_value_raw
