"""Shared entity base for the Shelly Modbus integration."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import ShellyModbusCoordinator
from .registers import entity_name

_ENTITY_CATEGORIES = {
    "diagnostic": EntityCategory.DIAGNOSTIC,
    "config": EntityCategory.CONFIG,
}


class ShellyModbusEntity(CoordinatorEntity[ShellyModbusCoordinator]):
    """Common wiring for every entity backed by a register definition."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: ShellyModbusCoordinator, definition: dict[str, Any]
    ) -> None:
        super().__init__(coordinator)
        self.definition = definition
        self.key: str = definition["key"]

        self._attr_unique_id = f"{coordinator.entry.entry_id}_{self.key}"
        self._attr_entity_registry_enabled_default = definition.get(
            "enabled_by_default", True
        )

        # Names come from translations/<lang>.json so entities show up in the
        # user's own language.  The instance number is substituted into the
        # translated string, which keeps words like "Channel"/"Kanal"
        # translatable too.
        self._attr_translation_key = definition.get("translation_key")
        if placeholders := definition.get("translation_placeholders"):
            self._attr_translation_placeholders = placeholders
        if not self._attr_translation_key:
            # Fall back to the English name from the register map.
            self._attr_name = entity_name(definition)

        if icon := definition.get("icon"):
            self._attr_icon = icon
        if category := definition.get("category"):
            self._attr_entity_category = _ENTITY_CATEGORIES.get(category)

        # Tell the coordinator this register backs a live entity so it gets
        # included in the polling plan.
        coordinator.register_key(self.key)

    @property
    def device_info(self) -> dict[str, Any]:
        """Attach every entity to the one device."""
        return self.coordinator.device_info

    @property
    def available(self) -> bool:
        """Available while the coordinator has a value for this register."""
        return (
            self.coordinator.last_update_success
            and self.coordinator.data is not None
            and self.coordinator.data.get(self.key) is not None
        )

    @property
    def native_value_raw(self) -> Any:
        """The decoded value straight from the coordinator."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get(self.key)
