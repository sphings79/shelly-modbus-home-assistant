"""The Shelly Modbus integration.

Reads Shelly Gen2+ devices over their built-in Modbus-TCP server, without the
cloud and without the HTTP/RPC API.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError

from .const import DOMAIN, PLATFORMS
from .coordinator import ShellyModbusCoordinator
from .registers import preload


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a Shelly device from a config entry."""
    # The register maps come from YAML on disk; read them in an executor so the
    # event loop is never blocked. Everything afterwards hits the cache.
    await hass.async_add_executor_job(preload)

    coordinator = ShellyModbusCoordinator(hass, entry)

    if not coordinator.definitions:
        # Retrying cannot conjure up a register map; this needs the user.
        raise ConfigEntryError(
            f"No register definitions for model '{entry.data.get('model')}'; "
            "remove and re-add the device"
        )

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    try:
        # Connect before the first refresh so failures surface as a retry rather
        # than as a pile of unavailable entities.
        await coordinator.async_init()
        await coordinator.async_config_entry_first_refresh()
    except Exception:
        # The first refresh raises ConfigEntryNotReady when the device does not
        # answer. Without this the coordinator would stay in hass.data with the
        # socket async_init opened, leaking one of each per setup retry.
        await coordinator.async_close()
        hass.data[DOMAIN].pop(entry.entry_id, None)
        raise

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(async_update_options))

    return True


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when its options change.

    Home Assistant expects an update listener to schedule a reload rather than
    reconfigure in place, and applying options by hand would not cover the ones
    that change how entities are constructed anyway.
    """
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        coordinator: ShellyModbusCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_close()

    return unload_ok
