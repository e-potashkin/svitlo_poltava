"""Read the Poltavaoblenergo page and build the 48-slot schedule."""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, time, timedelta
from typing import Any, Optional

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import DOMAIN, POE_GPV_URL
from .poe_gpv import STATE_OFF, STATE_ON, STATE_POSSIBLE, parse_poe_page

_LOGGER = logging.getLogger(__name__)

KYIV = dt_util.get_time_zone("Europe/Kyiv")
PAGE_TTL = 120


class SvitloPoltavaCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Own the current schedule for one queue."""

    def __init__(self, hass: HomeAssistant, queue: str, scan_interval: int) -> None:
        self.queue = queue
        self._days: Optional[dict[date, dict[str, list[str]]]] = None
        self._fetched: Optional[datetime] = None
        self._fetch_lock = asyncio.Lock()
        self._timer = None

        super().__init__(
            hass=hass,
            logger=_LOGGER,
            name=f"{DOMAIN}_{queue}",
            update_interval=timedelta(seconds=scan_interval),
        )

    async def _async_update_data(self) -> dict[str, Any]:
        page = await self._read_page()
        try:
            data = self._build(page)
        except Exception as err:  # noqa: BLE001 - keep the last good data
            raise UpdateFailed(f"Cannot build the schedule: {err}") from err
        self._arm_timer(data)
        return data

    async def _read_page(self) -> dict[str, Any]:
        now = dt_util.utcnow()
        if self._fresh(now):
            return {"days": self._days or {}}

        async with self._fetch_lock:
            now = dt_util.utcnow()
            if self._fresh(now):
                return {"days": self._days or {}}

            session = async_get_clientsession(self.hass)
            try:
                async with session.get(
                    POE_GPV_URL,
                    headers={"User-Agent": "Mozilla/5.0 (compatible; svitlo_poltava)"},
                    timeout=30,
                ) as response:
                    if response.status != 200:
                        _LOGGER.warning("Operator page: HTTP %s", response.status)
                        return {"days": self._days or {}}
                    html = await response.text()
            except Exception as err:  # noqa: BLE001 - keep the cached page
                _LOGGER.warning("Operator page: %s", err)
                return {"days": self._days or {}}

            days = parse_poe_page(html)
            if days:
                self._days = days
                self._fetched = now
                _LOGGER.info(
                    "Operator page: %d day(s), %d queue(s)",
                    len(days),
                    len(next(iter(days.values()))),
                )
            else:
                _LOGGER.warning("Operator page has no schedule")
            return {"days": self._days or {}}

    def _fresh(self, now: datetime) -> bool:
        return bool(
            self._days is not None
            and self._fetched
            and (now - self._fetched).total_seconds() < PAGE_TTL
        )

    def _build(self, page: dict[str, Any]) -> dict[str, Any]:
        """Turn the page into one queue's day, today and tomorrow."""
        now = dt_util.now(KYIV)
        today = now.date()
        days = page.get("days") or {}
        today_slots = (days.get(today) or {}).get(self.queue)
        if not today_slots:
            return self._empty(today)

        tomorrow = today + timedelta(days=1)
        tomorrow_slots = (days.get(tomorrow) or {}).get(self.queue) or []
        tomorrow_iso = tomorrow.isoformat() if tomorrow_slots else None

        slot = now.hour * 2 + (1 if now.minute >= 30 else 0)
        current = today_slots[slot]

        next_on = self._next_slot([STATE_ON], today, today_slots, slot, tomorrow_iso, tomorrow_slots)
        next_off = self._next_slot([STATE_OFF], today, today_slots, slot, tomorrow_iso, tomorrow_slots)
        next_possible = self._next_slot(
            [STATE_POSSIBLE], today, today_slots, slot, tomorrow_iso, tomorrow_slots
        )

        upcoming = [
            (stamp, kind)
            for stamp, kind in ((next_off, STATE_OFF), (next_possible, STATE_POSSIBLE))
            if stamp
        ]
        # An outage block is the run of "off" and "possible" half hours together:
        # the operator plans 12:00-14:00 off and 14:00-14:30 possible, and the
        # card draws that as one block that can run until 14:30. The next
        # planned outage is the next such BLOCK, never the "possible" tail of
        # the block that is already running (Eugene, 2026-10-23 12:27: "не
        # зрозумів чому next_outage = 14:00 якщо наступне в 18:00").
        planned_off = self._next_slot(
            [STATE_OFF, STATE_POSSIBLE], today, today_slots, slot, tomorrow_iso, tomorrow_slots
        )
        change = next_on if current in (STATE_OFF, STATE_POSSIBLE) else min(
            (stamp for stamp, _ in upcoming), default=None
        )

        return {
            "queue": self.queue,
            "date": today.isoformat(),
            "now_status": current,
            "next_change_at": self._hhmm(change),
            "today_48half": list(today_slots),
            "tomorrow_48half": list(tomorrow_slots),
            "tomorrow_date": tomorrow_iso,
            "updated": dt_util.utcnow().replace(microsecond=0).isoformat(),
            "next_planned_off_at": planned_off,
            "today_outage_hours": today_slots.count(STATE_OFF) * 0.5,
            "tomorrow_outage_hours": (
                tomorrow_slots.count(STATE_OFF) * 0.5 if tomorrow_slots else None
            ),
        }

    def _empty(self, today: date) -> dict[str, Any]:
        return {
            "queue": self.queue,
            "date": today.isoformat(),
            "now_status": "nosched",
            "next_change_at": None,
            "today_48half": [],
            "tomorrow_48half": [],
            "tomorrow_date": None,
            "updated": dt_util.utcnow().replace(microsecond=0).isoformat(),
            "next_planned_off_at": None,
            "today_outage_hours": None,
            "tomorrow_outage_hours": None,
        }

    def _next_slot(
        self,
        targets: list[str],
        today: date,
        today_slots: list[str],
        slot: int,
        tomorrow_iso: Optional[str],
        tomorrow_slots: list[str],
    ) -> Optional[str]:
        """First slot after now that OPENS a run of the target states.

        A planned outage is a run of consecutive half-hour slots and the
        operator page stores every slot on its own. Looking for the next slot
        that merely holds the target state pointed inside the outage that was
        already running: at 12:05, inside a 12:00-14:00 cut, the next planned
        outage read 12:30 (the second half-hour of the same cut), so the
        countdown to the next outage counted down during the outage itself.
        A slot opens a run only when the slot before it holds no target state
        either, so a list of targets groups them: with ("off", "possible") a
        "possible" tail stays inside the block that is already running.
        """
        tomorrow = list(tomorrow_slots) if tomorrow_iso and tomorrow_slots else []
        stamps = [self._stamp(today, offset) for offset in range(len(today_slots))]
        if tomorrow:
            day = date.fromisoformat(tomorrow_iso)
            stamps += [self._stamp(day, offset) for offset in range(len(tomorrow))]
        all_slots = list(today_slots) + tomorrow
        for offset in range(slot + 1, len(all_slots)):
            if all_slots[offset] in targets and all_slots[offset - 1] not in targets:
                return stamps[offset]
        return None

    @staticmethod
    def _stamp(day: date, slot: int) -> str:
        moment = datetime.combine(
            day,
            time(hour=slot // 2, minute=30 if slot % 2 else 0),
            tzinfo=KYIV,
        )
        return dt_util.as_utc(moment).isoformat()

    def _hhmm(self, iso: Optional[str]) -> Optional[str]:
        if not iso:
            return None
        moment = dt_util.parse_datetime(iso)
        if not moment:
            return None
        return self._kyiv(moment).strftime("%H:%M")

    def _arm_timer(self, data: dict[str, Any]) -> None:
        """Refresh exactly at the next status change."""
        if self._timer:
            self._timer()
            self._timer = None

        if data.get("now_status") == "nosched":
            return

        hhmm = data.get("next_change_at")
        day = data.get("date")
        if not hhmm or not day:
            return

        try:
            hour, minute = (int(part) for part in hhmm.split(":"))
            moment = datetime.combine(
                date.fromisoformat(day), time(hour=hour, minute=minute), tzinfo=KYIV
            )
            if moment <= dt_util.now(KYIV):
                moment += timedelta(days=1)
            self._timer = async_track_point_in_utc_time(
                self.hass, self._refresh, dt_util.as_utc(moment)
            )
        except (ValueError, TypeError) as err:
            _LOGGER.debug("Cannot arm the change timer: %s", err)

    @callback
    def _refresh(self, _now) -> None:
        self.hass.async_create_task(self.async_request_refresh())

    @staticmethod
    def _kyiv(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=KYIV)
        return value.astimezone(KYIV)
