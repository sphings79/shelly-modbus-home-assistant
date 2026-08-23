"""Sensor platform for the Shelly Modbus integration."""

from __future__ import annotations

import logging
import time
from typing import Any

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import ShellyModbusCoordinator
from .entity import ShellyModbusEntity

_LOGGER = logging.getLogger(__name__)

# Readings further apart than this are treated as a dropout rather than a slow
# poll, so a stalled connection cannot be integrated into a large fake total.
MAX_INTEGRATION_GAP = 900  # seconds


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

    entities: list[SensorEntity] = []
    for definition in coordinator.definitions:
        if definition.get("platform", "sensor") != "sensor":
            continue
        if definition.get("access") == "integrated":
            entities.append(ShellyModbusEnergySensor(coordinator, definition))
        else:
            entities.append(ShellyModbusSensor(coordinator, definition))

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


class ShellyModbusEnergySensor(ShellyModbusEntity, RestoreSensor):
    """An energy counter integrated from one of the netted power sensors.

    Shelly's own energy registers are accumulated per phase and never netted
    across them, so they cannot serve a grid meter that bills the net flow.
    The netted power is correct, so integrating it over time gives the energy a
    netting meter would record.

    Integration is trapezoidal between consecutive readings, matching Home
    Assistant's own Riemann sum helper. The total survives restarts through
    RestoreSensor. It cannot be backdated: the counter starts at zero when the
    integration is first set up, because the netted history was never recorded
    anywhere.
    """

    def __init__(
        self, coordinator: ShellyModbusCoordinator, definition: dict[str, Any]
    ) -> None:
        super().__init__(coordinator, definition)

        self._source: str = definition["source"]
        self._attr_native_unit_of_measurement = definition.get("unit")
        self._attr_device_class = _as_enum(
            SensorDeviceClass, definition.get("device_class")
        )
        self._attr_state_class = _as_enum(
            SensorStateClass, definition.get("state_class")
        )
        if (precision := definition.get("precision")) is not None:
            self._attr_suggested_display_precision = precision

        self._total: float = 0.0
        self._last_power: float | None = None
        self._last_timestamp: float | None = None

    async def async_added_to_hass(self) -> None:
        """Restore the counter so a restart does not reset it to zero."""
        await super().async_added_to_hass()

        if (last := await self.async_get_last_sensor_data()) is not None:
            try:
                self._total = float(last.native_value)
            except (TypeError, ValueError):
                # An unknown/unavailable previous state is not a usable total.
                self._total = 0.0

        # Deliberately not seeding the previous reading: the time Home Assistant
        # was down was never measured, so nothing may be integrated across it.

    @property
    def available(self) -> bool:
        """Available once a total exists, even if a single read just failed.

        The counter keeps its value through a dropout rather than going
        unavailable, which would show up as a gap in the energy dashboard.
        """
        return self.coordinator.last_update_success

    @property
    def native_value(self) -> float:
        """Return the accumulated energy in kWh."""
        return round(self._total, 6)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Integrate the power reading that just arrived."""
        power = None
        if self.coordinator.data:
            power = self.coordinator.data.get(self._source)

        now = time.monotonic()

        if power is None:
            # Break the chain: integrating across a gap would invent energy.
            self._last_power = None
            self._last_timestamp = None
            super()._handle_coordinator_update()
            return

        if self._last_power is not None and self._last_timestamp is not None:
            elapsed = now - self._last_timestamp
            if 0 < elapsed <= MAX_INTEGRATION_GAP:
                # Trapezoidal rule, W*s converted to kWh.
                average = (power + self._last_power) / 2
                self._total += average * elapsed / 3_600_000

        self._last_power = power
        self._last_timestamp = now

        super()._handle_coordinator_update()
