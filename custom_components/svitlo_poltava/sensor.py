"""Sensors for the Svitlo Poltava schedule."""

from __future__ import annotations

from typing import Any, Optional

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import DOMAIN, REGION
from .entity import PoltavaEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            SvitloStatus(coordinator),
            NextOutage(coordinator),
            OutageHoursToday(coordinator),
        ]
    )


def _queue(coordinator) -> str:
    return coordinator.queue


class SvitloStatus(PoltavaEntity, SensorEntity):
    """The current half-hour state plus the whole schedule in attributes."""

    _attr_translation_key = "svitlo_status"
    _attr_icon = "mdi:transmission-tower"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"svitlo_poltava_status_{_queue(coordinator)}"

    @property
    def native_value(self) -> str:
        data = self.coordinator.data
        if not data or not self.coordinator.last_update_success:
            return "No data"
        return {
            "on": "Grid ON",
            "off": "Grid OFF",
            "possible": "Possible",
        }.get(data.get("now_status"), "No data")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data or {}
        return {
            "region": REGION,
            "queue": self.coordinator.queue,
            "now_status": data.get("now_status"),
            "today_48half": data.get("today_48half", []),
            "tomorrow_48half": data.get("tomorrow_48half", []),
            "next_change_at": data.get("next_change_at"),
            "today_outage_hours": data.get("today_outage_hours"),
            "tomorrow_outage_hours": data.get("tomorrow_outage_hours"),
            "updated": data.get("updated"),
        }


class NextOutage(PoltavaEntity, SensorEntity):
    """The next planned outage, as a timestamp."""

    _attr_translation_key = "svitlo_next_outage"
    _attr_icon = "mdi:clock-alert"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"svitlo_poltava_next_off_{_queue(coordinator)}"

    @property
    def native_value(self):
        data = self.coordinator.data or {}
        raw = data.get("next_planned_off_at")
        return dt_util.parse_datetime(raw) if raw else None


class OutageHoursToday(PoltavaEntity, SensorEntity):
    """Planned outage hours for today."""

    _attr_translation_key = "svitlo_outage_today"
    _attr_icon = "mdi:clock-alert-outline"
    _attr_native_unit_of_measurement = UnitOfTime.HOURS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"svitlo_poltava_outage_today_{_queue(coordinator)}"

    @property
    def native_value(self) -> Optional[float]:
        data = self.coordinator.data or {}
        return data.get("today_outage_hours")
