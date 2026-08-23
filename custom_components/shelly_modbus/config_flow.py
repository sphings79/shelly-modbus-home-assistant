"""Config and options flow for the Shelly Modbus integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

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
    SCAN_INTERVAL_HIGH,
    SCAN_INTERVAL_LIMITS,
    SCAN_INTERVAL_LOW,
)
from .helpers.modbus_client import ShellyModbusClient, decode_registers
from .registers import load_components, load_models

_LOGGER = logging.getLogger(__name__)

# Profiles are told apart by which component block answers.
_PROFILE_PROBES = {
    "triphase": ("em", 0),
    "monophase": ("em1", 0),
    "default": None,
}


async def async_identify_device(
    host: str, port: int, unit_id: int
) -> dict[str, Any] | None:
    """Read a device's identity over Modbus.

    Returns the MAC, the reported model code, and which component blocks
    answer, or ``None`` when the device cannot be reached.
    """
    client = ShellyModbusClient(host=host, port=port, unit_id=unit_id)

    try:
        if not await client.async_connect():
            return None

        mac_regs = await client.async_read_input_registers(0, 6)
        if mac_regs is None:
            return None

        model_regs = await client.async_read_input_registers(6, 10)

        info: dict[str, Any] = {
            "mac": decode_registers(mac_regs, "char"),
            "model": decode_registers(model_regs, "char") if model_regs else None,
            "components": [],
        }

        # Probe each component base address to see what this device publishes.
        components = load_components()
        for comp_type in ("em", "emdata", "em1", "em1data", "switch"):
            component = components.get(comp_type, {})
            base = component.get("base")
            if base is None:
                continue
            if await client.async_probe(base, 2):
                info["components"].append(comp_type)

        return info
    finally:
        await client.async_close()


def _detect_profile(model_spec: dict[str, Any], components: list[str]) -> str | None:
    """Pick the profile whose components the device actually answers for."""
    profiles = model_spec.get("profiles", {})

    for profile in profiles:
        probe = _PROFILE_PROBES.get(profile)
        if probe is None:
            continue
        comp_type, _ = probe
        if comp_type in components:
            return profile

    return model_spec.get("default_profile") or next(iter(profiles), None)


class ShellyModbusConfigFlow(ConfigFlow, domain=DOMAIN):
    """Guides the user through adding a device."""

    VERSION = 1

    def __init__(self) -> None:
        self._host: str | None = None
        self._port: int = DEFAULT_PORT
        self._unit_id: int = DEFAULT_UNIT_ID
        self._info: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the address, then identify the device."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._host = user_input["host"].strip()
            self._port = int(user_input.get("port", DEFAULT_PORT))
            self._unit_id = int(user_input.get(CONF_UNIT_ID, DEFAULT_UNIT_ID))

            info = await async_identify_device(self._host, self._port, self._unit_id)

            if info is None:
                errors["base"] = "cannot_connect"
            elif not info["components"]:
                errors["base"] = "no_components"
            else:
                self._info = info
                if mac := info.get("mac"):
                    await self.async_set_unique_id(mac.lower())
                    self._abort_if_unique_id_configured(updates={"host": self._host})
                return await self.async_step_model()

        schema = vol.Schema(
            {
                vol.Required("host", default=(user_input or {}).get("host", "")): str,
                vol.Optional("port", default=self._port): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=65535)
                ),
                vol.Optional(CONF_UNIT_ID, default=self._unit_id): vol.All(
                    vol.Coerce(int), vol.Range(min=0, max=247)
                ),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_model(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm the detected model, or let the user pick another one."""
        models = load_models()
        detected_model = self._info.get("model")

        if user_input is not None:
            model = user_input[CONF_MODEL]
            profile = user_input.get(CONF_PROFILE) or models.get(model, {}).get(
                "default_profile"
            )
            name = models.get(model, {}).get("name", model)

            return self.async_create_entry(
                title=name,
                data={
                    "host": self._host,
                    "port": self._port,
                    CONF_UNIT_ID: self._unit_id,
                    CONF_MODEL: model,
                    CONF_PROFILE: profile,
                },
                options={
                    CONF_SCAN_INTERVAL_HIGH: DEFAULT_SCAN_INTERVALS[SCAN_INTERVAL_HIGH],
                    CONF_SCAN_INTERVAL_LOW: DEFAULT_SCAN_INTERVALS[SCAN_INTERVAL_LOW],
                },
            )

        # Pre-select what the device reported, falling back to the first model
        # whose components match what answered.
        default_model = detected_model if detected_model in models else None
        if default_model is None:
            for code, spec in models.items():
                if _detect_profile(spec, self._info["components"]):
                    default_model = code
                    break
        default_model = default_model or next(iter(models))

        default_profile = _detect_profile(
            models[default_model], self._info["components"]
        )

        model_options = [
            {"value": code, "label": f"{spec.get('name', code)} ({code})"}
            for code, spec in models.items()
        ]
        profile_options = sorted(
            {
                profile
                for spec in models.values()
                for profile in spec.get("profiles", {})
            }
        )

        schema = vol.Schema(
            {
                vol.Required(CONF_MODEL, default=default_model): SelectSelector(
                    SelectSelectorConfig(
                        options=model_options, mode=SelectSelectorMode.DROPDOWN
                    )
                ),
                vol.Optional(
                    CONF_PROFILE, default=default_profile or "default"
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=profile_options, mode=SelectSelectorMode.DROPDOWN
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="model",
            data_schema=schema,
            description_placeholders={
                "detected": detected_model or "unknown",
            },
        )

    async def async_step_zeroconf(self, discovery_info) -> ConfigFlowResult:
        """Handle a Shelly announced over mDNS."""
        host = discovery_info.host
        properties = getattr(discovery_info, "properties", {}) or {}

        # The mDNS name carries the MAC, which is the unique id.
        name = getattr(discovery_info, "name", "") or ""
        mac = properties.get("mac") or name.split("-")[-1].split(".")[0]
        if mac:
            await self.async_set_unique_id(mac.lower())
            self._abort_if_unique_id_configured(updates={"host": host})

        self._host = host
        self._port = DEFAULT_PORT
        self._unit_id = DEFAULT_UNIT_ID

        info = await async_identify_device(host, self._port, self._unit_id)
        if info is None or not info["components"]:
            # Modbus is off, or this model does not implement it at all.
            return self.async_abort(reason="cannot_connect")

        self._info = info
        model = info.get("model")
        self.context["title_placeholders"] = {
            "name": load_models().get(model, {}).get("name", model or host)
        }
        return await self.async_step_model()

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow."""
        return ShellyModbusOptionsFlow()


class ShellyModbusOptionsFlow(OptionsFlow):
    """Lets the user tune the polling intervals per category."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show and store the interval options."""
        if user_input is not None:
            return self.async_create_entry(
                data={
                    CONF_SCAN_INTERVAL_HIGH: int(user_input[CONF_SCAN_INTERVAL_HIGH]),
                    CONF_SCAN_INTERVAL_LOW: int(user_input[CONF_SCAN_INTERVAL_LOW]),
                }
            )

        options = self.config_entry.options
        high_min, high_max = SCAN_INTERVAL_LIMITS[SCAN_INTERVAL_HIGH]
        low_min, low_max = SCAN_INTERVAL_LIMITS[SCAN_INTERVAL_LOW]

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_INTERVAL_HIGH,
                    default=options.get(
                        CONF_SCAN_INTERVAL_HIGH,
                        DEFAULT_SCAN_INTERVALS[SCAN_INTERVAL_HIGH],
                    ),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=high_min,
                        max=high_max,
                        step=1,
                        unit_of_measurement="s",
                        mode=NumberSelectorMode.BOX,
                    )
                ),
                vol.Required(
                    CONF_SCAN_INTERVAL_LOW,
                    default=options.get(
                        CONF_SCAN_INTERVAL_LOW,
                        DEFAULT_SCAN_INTERVALS[SCAN_INTERVAL_LOW],
                    ),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=low_min,
                        max=low_max,
                        step=1,
                        unit_of_measurement="s",
                        mode=NumberSelectorMode.BOX,
                    )
                ),
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)
