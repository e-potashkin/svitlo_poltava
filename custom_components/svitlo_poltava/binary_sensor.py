"""Binary sensor for the planned power state."""

from __future__ import annotations

from typing import Optional

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import PoltavaEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([PowerPresent(coordinator)])


class PowerPresent(PoltavaEntity, BinarySensorEntity):
    """On when the plan says power, off during a planned outage.

    A "possible" window counts as on: it is a warning, not a cut.
    """

    _attr_translation_key = "svitlo_electricity_status"
    _attr_device_class = BinarySensorDeviceClass.POWER

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"svitlo_poltava_power_{coordinator.queue}"

    @property
    def is_on(self) -> Optional[bool]:
        data = self.coordinator.data
        if not data or not self.coordinator.last_update_success:
            return None
        status = data.get("now_status")
        if status == "off":
            return False
        if status in ("on", "possible"):
            return True
        return None
