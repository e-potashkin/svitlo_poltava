"""Calendar of the planned outage windows."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any, Optional

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import DOMAIN, REGION
from .entity import PoltavaEntity

KYIV = dt_util.get_time_zone("Europe/Kyiv")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([OutageCalendar(coordinator)])


class OutageCalendar(PoltavaEntity, CalendarEntity):
    """Every "off" run becomes one event."""

    _attr_translation_key = "svitlo_calendar"
    _attr_icon = "mdi:calendar-clock"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"svitlo_poltava_calendar_{coordinator.queue}"
        self._event: Optional[CalendarEvent] = None

    @property
    def event(self) -> Optional[CalendarEvent]:
        return self._event

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._rebuild()

    @callback
    def _handle_coordinator_update(self) -> None:
        self._rebuild()
        super()._handle_coordinator_update()

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        return self._between(start_date, end_date)

    def _rebuild(self) -> None:
        now = dt_util.utcnow()
        events = self._between(now - timedelta(days=1), now + timedelta(days=2))
        current = next((event for event in events if event.start <= now < event.end), None)
        upcoming = next((event for event in events if event.start > now), None)
        self._event = current or upcoming

    def _between(self, start: datetime, end: datetime) -> list[CalendarEvent]:
        events: list[CalendarEvent] = []
        for day, series in self._days():
            events.extend(self._events_for(day, series))
        return [event for event in events if event.start < end and event.end > start]

    def _days(self) -> list[tuple[date, list[str]]]:
        data = self.coordinator.data or {}
        days: list[tuple[date, list[str]]] = []
        today_iso = data.get("date")
        today = data.get("today_48half") or []
        tomorrow_iso = data.get("tomorrow_date")
        tomorrow = data.get("tomorrow_48half") or []

        if today_iso and today:
            days.append((date.fromisoformat(today_iso), today))
        if tomorrow_iso and tomorrow:
            days.append((date.fromisoformat(tomorrow_iso), tomorrow))

        # One outage can cross midnight: join the two adjacent days.
        if len(days) == 2 and (days[1][0] - days[0][0]).days == 1:
            return [(days[0][0], days[0][1] + days[1][1])]
        return days

    def _events_for(self, day: date, series: list[str]) -> list[CalendarEvent]:
        events: list[CalendarEvent] = []
        start: Optional[int] = None
        for slot, state in enumerate(series):
            if state == "off" and start is None:
                start = slot
            elif state != "off" and start is not None:
                events.append(self._make_event(day, start, slot))
                start = None
        if start is not None:
            events.append(self._make_event(day, start, len(series)))
        return events

    def _make_event(self, day: date, start: int, end: int) -> CalendarEvent:
        def moment(slot: int) -> datetime:
            return datetime.combine(
                day + timedelta(days=slot // 48),
                time(hour=(slot % 48) // 2, minute=30 if slot % 2 else 0),
                tzinfo=KYIV,
            )

        start_local = moment(start)
        end_local = moment(end)
        return CalendarEvent(
            summary=f"Svitlo Poltava {self.coordinator.queue}: ❌ Відключення",
            start=dt_util.as_utc(start_local),
            end=dt_util.as_utc(end_local),
            description=f"Немає світла {start_local:%H:%M}–{end_local:%H:%M}",
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data or {}
        now = dt_util.now(KYIV)
        slot = now.hour * 2 + (1 if now.minute >= 30 else 0)
        today = data.get("today_48half") or []
        return {
            "region": REGION,
            "queue": self.coordinator.queue,
            "now_status": today[slot] if slot < len(today) else None,
            "today_48half": today,
            "tomorrow_48half": data.get("tomorrow_48half", []),
            "next_change_at": data.get("next_change_at"),
            "today_outage_hours": data.get("today_outage_hours"),
            "tomorrow_outage_hours": data.get("tomorrow_outage_hours"),
            "updated": data.get("updated"),
        }
