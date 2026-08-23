"""Switch platform for the Shelly Modbus integration.

Relay outputs are readable as an input register and writable as a coil.
Only devices that actually expose a Switch component over Modbus (Gen4
switches and the Pro Output Addon) create entities here.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import ShellyModbusCoordinator
from .entity import ShellyModbusEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Create a switch for every writable relay output."""
    coordinator: ShellyModbusCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        ShellyModbusSwitch(coordinator, definition)
        for definition in coordinator.definitions
        if definition.get("platform") == "switch" and "coil_address" in definition
    ]

    _LOGGER.debug("Adding %d Shelly Modbus switches", len(entities))
    async_add_entities(entities)


class ShellyModbusSwitch(ShellyModbusEntity, SwitchEntity):
    """A relay output driven through its Modbus coil."""

    def __init__(
        self, coordinator: ShellyModbusCoordinator, definition: dict[str, Any]
    ) -> None:
        super().__init__(coordinator, definition)
        try:
            self._attr_device_class = SwitchDeviceClass(definition["device_class"])
        except (KeyError, ValueError):
            self._attr_device_class = None

    @property
    def is_on(self) -> bool | None:
        """Return the current output state."""
        value = self.native_value_raw
        return None if value is None else bool(value)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the output on."""
        await self.coordinator.async_set_coil(self.key, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the output off."""
        await self.coordinator.async_set_coil(self.key, False)
