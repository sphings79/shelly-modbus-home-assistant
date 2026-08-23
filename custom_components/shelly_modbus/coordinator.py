"""Data coordinator for the Shelly Modbus integration."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_registry import async_get as async_get_entity_registry
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_MODEL,
    CONF_PROFILE,
    CONF_SCAN_INTERVAL_HIGH,
    CONF_SCAN_INTERVAL_LOW,
    CONF_UNIT_ID,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVALS,
    DEFAULT_UNIT_ID,
    DOMAIN,
    MANUFACTURER,
    SCAN_INTERVAL_HIGH,
    SCAN_INTERVAL_LOW,
    SCAN_INTERVAL_STATIC,
)
from .helpers.modbus_client import ShellyModbusClient, decode_registers
from .registers import build_blocks, expand_definitions, load_models

_LOGGER = logging.getLogger(__name__)


class ShellyModbusCoordinator(DataUpdateCoordinator):
    """Polls a Shelly device over Modbus and shares the decoded values."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.entry = entry
        self.host: str = entry.data["host"]
        self.port: int = entry.data.get("port", DEFAULT_PORT)
        self.model: str = entry.data.get(CONF_MODEL, "")
        self.profile: str | None = entry.data.get(CONF_PROFILE)

        options = dict(entry.options)
        self.scan_intervals = {
            SCAN_INTERVAL_HIGH: int(
                options.get(
                    CONF_SCAN_INTERVAL_HIGH, DEFAULT_SCAN_INTERVALS[SCAN_INTERVAL_HIGH]
                )
            ),
            SCAN_INTERVAL_LOW: int(
                options.get(
                    CONF_SCAN_INTERVAL_LOW, DEFAULT_SCAN_INTERVALS[SCAN_INTERVAL_LOW]
                )
            ),
        }

        self.client = ShellyModbusClient(
            host=self.host,
            port=self.port,
            unit_id=entry.data.get(CONF_UNIT_ID, DEFAULT_UNIT_ID),
            timeout=entry.data.get("timeout", 5),
        )

        self.definitions: list[dict[str, Any]] = expand_definitions(
            self.model, self.profile
        )
        self._definitions_by_key = {d["key"]: d for d in self.definitions}

        # Which entities each platform actually created, so disabled entities
        # are never polled.
        self._registered_keys: set[str] = set()
        self._last_read: dict[str, float] = {}
        self._static_done = False

        self._consecutive_failures = 0
        self._last_success: datetime | None = None

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} {self.host}",
            update_interval=timedelta(seconds=self.scan_intervals[SCAN_INTERVAL_HIGH]),
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def async_init(self) -> None:
        """Open the connection before the first refresh."""
        if not await self.client.async_connect():
            _LOGGER.warning(
                "Could not reach the Shelly Modbus server at %s:%s during setup",
                self.host,
                self.port,
            )

    async def async_close(self) -> None:
        """Close the connection when the entry unloads."""
        await self.client.async_close()

    def register_key(self, key: str) -> None:
        """Mark a definition as backing a live entity, so it gets polled."""
        self._registered_keys.add(key)

    def update_options(self, entry: ConfigEntry) -> bool:
        """Apply new option values. Returns True when the interval changed."""
        options = dict(entry.options)
        new_intervals = {
            SCAN_INTERVAL_HIGH: int(
                options.get(
                    CONF_SCAN_INTERVAL_HIGH, DEFAULT_SCAN_INTERVALS[SCAN_INTERVAL_HIGH]
                )
            ),
            SCAN_INTERVAL_LOW: int(
                options.get(
                    CONF_SCAN_INTERVAL_LOW, DEFAULT_SCAN_INTERVALS[SCAN_INTERVAL_LOW]
                )
            ),
        }
        changed = new_intervals != self.scan_intervals
        self.scan_intervals = new_intervals
        self.update_interval = timedelta(seconds=new_intervals[SCAN_INTERVAL_HIGH])
        return changed

    # ------------------------------------------------------------------
    # Device metadata
    # ------------------------------------------------------------------

    @property
    def model_name(self) -> str:
        """Human readable model name."""
        spec = load_models().get(self.model, {})
        return spec.get("name", self.model or "Shelly")

    @property
    def device_info(self) -> dict[str, Any]:
        """Device registry entry shared by every entity."""
        data = self.data or {}
        info: dict[str, Any] = {
            "identifiers": {(DOMAIN, self.entry.entry_id)},
            "manufacturer": MANUFACTURER,
            "model": self.model_name,
            "name": self.entry.title,
            "configuration_url": f"http://{self.host}",
        }
        if mac := data.get("mac"):
            # Format as a proper MAC so HA can link it to other integrations.
            formatted = ":".join(mac[i : i + 2] for i in range(0, len(mac), 2))
            info["connections"] = {("mac", formatted.lower())}
        return info

    @property
    def available(self) -> bool:
        """True while the device is answering."""
        return self._consecutive_failures == 0

    def connection_attributes(self) -> dict[str, Any]:
        """Diagnostic attributes for the connection entity."""
        return {
            "host": self.host,
            "port": self.port,
            "model": self.model,
            "profile": self.profile,
            "connected": self.client.is_connected,
            "consecutive_failures": self._consecutive_failures,
            "last_success": self._last_success.isoformat()
            if self._last_success
            else None,
        }

    # ------------------------------------------------------------------
    # Read planning
    # ------------------------------------------------------------------

    def _due_categories(self, now: float) -> set[str]:
        """Return which polling categories are due for a read."""
        due = {SCAN_INTERVAL_HIGH}

        last_low = self._last_read.get(SCAN_INTERVAL_LOW)
        if last_low is None or now - last_low >= self.scan_intervals[SCAN_INTERVAL_LOW]:
            due.add(SCAN_INTERVAL_LOW)

        if not self._static_done:
            due.add(SCAN_INTERVAL_STATIC)

        return due

    def _definitions_to_read(self, categories: set[str]) -> list[dict[str, Any]]:
        """Return the definitions to poll this cycle.

        Only registers backing an enabled entity are read, so disabling
        entities in Home Assistant genuinely reduces Modbus traffic.
        """
        entity_registry = async_get_entity_registry(self.hass)
        disabled = set()
        for entry in entity_registry.entities.values():
            if entry.config_entry_id == self.entry.entry_id and entry.disabled_by:
                # unique_id is "<entry_id>_<key>".
                prefix = f"{self.entry.entry_id}_"
                if entry.unique_id.startswith(prefix):
                    disabled.add(entry.unique_id[len(prefix) :])

        selected = []
        for definition in self.definitions:
            if definition["scan_interval"] not in categories:
                continue
            key = definition["key"]
            if key in disabled:
                continue
            # Before a platform has registered its entities, read everything so
            # the first refresh can populate them.
            if self._registered_keys and key not in self._registered_keys:
                continue
            selected.append(definition)
        return selected

    # ------------------------------------------------------------------
    # Polling
    # ------------------------------------------------------------------

    async def _async_update_data(self) -> dict[str, Any]:
        """Read every due register and return the decoded values."""
        loop_now = asyncio.get_running_loop().time()
        categories = self._due_categories(loop_now)
        definitions = self._definitions_to_read(categories)

        # Carry previous values forward so categories that are not due keep
        # their state instead of going unavailable.
        data: dict[str, Any] = dict(self.data or {})

        blocks = build_blocks(definitions)
        read_any = False
        failures = 0

        for block in blocks:
            start = block[0]["address"]
            end = max(d["address"] + d.get("count", 1) for d in block)
            registers = await self.client.async_read_input_registers(start, end - start)

            if registers is None:
                failures += 1
                continue

            read_any = True
            for definition in block:
                offset = definition["address"] - start
                chunk = registers[offset : offset + definition.get("count", 1)]
                data[definition["key"]] = self._decode(definition, chunk)

        # Coils and discrete inputs are single-bit reads.
        for definition in definitions:
            access = definition.get("access")
            if access == "discrete_input":
                value = await self.client.async_read_discrete_input(
                    definition["address"]
                )
                if value is None:
                    failures += 1
                else:
                    read_any = True
                    data[definition["key"]] = value

        if not read_any and definitions:
            self._consecutive_failures += 1
            raise UpdateFailed(
                f"No response from Shelly Modbus server at {self.host}:{self.port}"
            )

        self._consecutive_failures = 0 if not failures else self._consecutive_failures
        self._last_success = datetime.now(UTC)

        for category in categories:
            self._last_read[category] = loop_now
        if SCAN_INTERVAL_STATIC in categories and read_any:
            self._static_done = True

        return data

    def _decode(self, definition: dict[str, Any], registers: list[int]) -> Any:
        """Decode one field and apply its scale factor."""
        if not registers:
            return None
        try:
            value = decode_registers(registers, definition["data_type"])
        except ValueError as err:
            _LOGGER.warning("Cannot decode %s: %s", definition["key"], err)
            return None

        if value is None:
            return None

        if (
            definition["data_type"] == "uint32"
            and definition.get("device_class") == "timestamp"
        ):
            # Shelly reports Unix seconds; HA wants an aware datetime.
            if value <= 0:
                return None
            return datetime.fromtimestamp(value, tz=UTC)

        if (scale := definition.get("scale")) and isinstance(value, (int, float)):
            value = value * scale

        return value

    # ------------------------------------------------------------------
    # Writing
    # ------------------------------------------------------------------

    async def async_set_coil(self, key: str, value: bool) -> bool:
        """Switch a relay output and refresh its state."""
        definition = self._definitions_by_key.get(key)
        if not definition or "coil_address" not in definition:
            _LOGGER.error("No writable coil for '%s'", key)
            return False

        if not await self.client.async_write_coil(definition["coil_address"], value):
            _LOGGER.error("Failed writing coil for '%s'", key)
            return False

        # Reflect the new state immediately, then confirm on the next poll.
        if self.data is not None:
            self.data[key] = value
            self.async_update_listeners()

        await self.async_request_refresh()
        return True
