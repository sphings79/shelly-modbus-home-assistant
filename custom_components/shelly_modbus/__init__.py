"""The Shelly Modbus integration.

Reads Shelly Gen2+ devices over their built-in Modbus-TCP server, without the
cloud and without the HTTP/RPC API.
"""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, PLATFORMS
from .coordinator import ShellyModbusCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a Shelly device from a config entry."""
    coordinator = ShellyModbusCoordinator(hass, entry)

    if not coordinator.definitions:
        _LOGGER.error(
            "No register definitions for model '%s'; remove and re-add the device",
            entry.data.get("model"),
        )
        return False

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    # Connect before the first refresh so failures surface as a retry rather
    # than as a pile of unavailable entities.
    await coordinator.async_init()
    await coordinator.async_config_entry_first_refresh()

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(async_update_options))

    return True


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Apply changed options without tearing the entry down."""
    coordinator: ShellyModbusCoordinator | None = hass.data.get(DOMAIN, {}).get(
        entry.entry_id
    )
    if coordinator is None:
        return

    if coordinator.update_options(entry):
        await coordinator.async_request_refresh()


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        coordinator: ShellyModbusCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_close()

    return unload_ok
