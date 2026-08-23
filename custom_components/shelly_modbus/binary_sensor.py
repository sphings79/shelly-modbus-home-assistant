"""Binary sensor platform for the Shelly Modbus integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ShellyModbusCoordinator
from .entity import ShellyModbusEntity

_LOGGER = logging.getLogger(__name__)


def _as_device_class(value: str | None) -> BinarySensorDeviceClass | None:
    """Convert a YAML string into a binary sensor device class."""
    if value is None:
        return None
    try:
        return BinarySensorDeviceClass(value)
    except ValueError:
        _LOGGER.warning("Unknown binary sensor device class '%s'", value)
        return None


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Create binary sensors plus the connection diagnostic entity."""
    coordinator: ShellyModbusCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[BinarySensorEntity] = [
        ShellyModbusBinarySensor(coordinator, definition)
        for definition in coordinator.definitions
        if definition.get("platform") == "binary_sensor"
    ]
    entities.append(ShellyModbusConnectionSensor(coordinator))

    _LOGGER.debug("Adding %d Shelly Modbus binary sensors", len(entities))
    async_add_entities(entities)


class ShellyModbusBinarySensor(ShellyModbusEntity, BinarySensorEntity):
    """A boolean register, typically an error flag or an input state."""

    def __init__(
        self, coordinator: ShellyModbusCoordinator, definition: dict[str, Any]
    ) -> None:
        super().__init__(coordinator, definition)
        self._attr_device_class = _as_device_class(definition.get("device_class"))

    @property
    def is_on(self) -> bool | None:
        """Return the current state."""
        value = self.native_value_raw
        return None if value is None else bool(value)


class ShellyModbusConnectionSensor(
    CoordinatorEntity[ShellyModbusCoordinator], BinarySensorEntity
):
    """Reports whether the Modbus connection to the device is alive."""

    _attr_has_entity_name = True
    _attr_name = "Modbus Connection"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: ShellyModbusCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_modbus_connection"

    @property
    def available(self) -> bool:
        """Always available, so a lost connection is visible rather than hidden."""
        return True

    @property
    def is_on(self) -> bool:
        """True while the last update succeeded."""
        return self.coordinator.last_update_success

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Connection diagnostics."""
        return self.coordinator.connection_attributes()

    @property
    def device_info(self) -> dict[str, Any]:
        """Attach to the same device."""
        return self.coordinator.device_info
