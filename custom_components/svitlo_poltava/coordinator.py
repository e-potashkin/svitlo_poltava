"""Fetch and parse the Poltavaoblenergo schedule for queue 3.1."""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, time, timedelta
from typing import Any, Callable, Optional

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import DOMAIN, POE_GPV_URL, QUEUE
from .poe_gpv import STATE_OFF, STATE_ON, STATE_POSSIBLE, parse_poe_page

_LOGGER = logging.getLogger(__name__)

TZ_KYIV = dt_util.get_time_zone("Europe/Kyiv")
CACHE_SECONDS = 120


class SvitloPoltavaCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """One queue: fetch the operator page, build the 48-slot day."""

    def __init__(self, hass: HomeAssistant, scan_interval: int) -> None:
        self.queue = QUEUE
        self._history_today: list[list[str]] = []
        self._history_tomorrow: list[list[str]] = []
        self._unsub_precise: Optional[Callable[[], None]] = None
        self._days: Optional[dict[date, dict[str, list[str]]]] = None
        self._fetched: Optional[datetime] = None
        self._fetch_lock = asyncio.Lock()

        super().__init__(
            hass=hass,
            logger=_LOGGER,
            name=f"{DOMAIN}_{QUEUE}",
            update_interval=timedelta(seconds=scan_interval),
        )

    async def _async_update_data(self) -> dict[str, Any]:
        page = await self._fetch_page()
        try:
            data = self._build(page)
        except Exception as err:  # noqa: BLE001 - report, keep the last data
            raise UpdateFailed(f"Schedule parse error: {err}") from err
        self._schedule_precise_refresh(data)
        return data

    async def _fetch_page(self) -> dict[str, Any]:
        now = dt_util.utcnow()
        if (
            self._days is not None
            and self._fetched
            and (now - self._fetched).total_seconds() < CACHE_SECONDS
        ):
            return {"days": self._days}

        async with self._fetch_lock:
            now = dt_util.utcnow()
            if (
                self._days is not None
                and self._fetched
                and (now - self._fetched).total_seconds() < CACHE_SECONDS
            ):
                return {"days": self._days}

            session = async_get_clientsession(self.hass)
            try:
                async with session.get(
                    POE_GPV_URL,
                    headers={"User-Agent": "Mozilla/5.0 (compatible; svitlo_poltava)"},
                    timeout=30,
                ) as response:
                    if response.status != 200:
                        _LOGGER.warning("HTTP %s for %s", response.status, POE_GPV_URL)
                        return {"days": self._days or {}}
                    html = await response.text()
            except Exception as err:  # noqa: BLE001 - keep the cached page
                _LOGGER.warning("Cannot read %s: %s", POE_GPV_URL, err)
                return {"days": self._days or {}}

            days = parse_poe_page(html)
            if days:
                self._days = days
                self._fetched = now
                _LOGGER.info(
                    "Schedule: %d day(s) %s, %d queue(s)",
                    len(days),
                    ", ".join(sorted(day.isoformat() for day in days)),
                    len(next(iter(days.values()))),
                )
            else:
                _LOGGER.warning("The operator page carries no schedule; kept the cache")
            return {"days": self._days or {}}

    def _build(self, page: dict[str, Any]) -> dict[str, Any]:
        """Build one queue from the operator page, and from nothing else.

        The page carries three states per half hour: on, off and possible. A
        possible window is a warning, not an outage, so "next outage" is the
        earliest of the two and `next_outage_kind` says which one it is.
        """
        now = dt_util.now(TZ_KYIV)
        today = now.date()
        days = (page or {}).get("days") or {}
        today_states = (days.get(today) or {}).get(self.queue)
        tomorrow = today + timedelta(days=1)
        tomorrow_states = (days.get(tomorrow) or {}).get(self.queue)
        updated = dt_util.utcnow().replace(microsecond=0).isoformat()
        page_days = sorted(day.isoformat() for day in days)

        if not today_states:
            return {
                "queue": self.queue,
                "date": today.isoformat(),
                "now_status": "nosched",
                "now_halfhour_index": None,
                "next_change_at": None,
                "today_48half": [],
                "tomorrow_48half": [],
                "tomorrow_date": None,
                "updated": updated,
                "source": POE_GPV_URL,
                "next_on_at": None,
                "next_off_at": None,
                "next_planned_off_at": None,
                "next_possible_at": None,
                "next_outage_kind": None,
                "today_outage_hours": None,
                "tomorrow_outage_hours": None,
                "possible_hours_today": None,
                "longest_outage_hours": None,
                "history_today_48half": [],
                "history_tomorrow_48half": [],
                "is_emergency": False,
                "page_days": page_days,
            }

        today_half = list(today_states)
        tomorrow_half = list(tomorrow_states) if tomorrow_states else []
        tomorrow_iso = tomorrow.isoformat() if tomorrow_half else None
        idx = now.hour * 2 + (1 if now.minute >= 30 else 0)
        cur = today_half[idx]

        next_on_at = self._find_next_at(
            [STATE_ON], today, today_half, idx, tomorrow_iso, tomorrow_half
        )
        next_off_at = self._find_next_at(
            [STATE_OFF], today, today_half, idx, tomorrow_iso, tomorrow_half
        )
        next_possible_at = self._find_next_at(
            [STATE_POSSIBLE], today, today_half, idx, tomorrow_iso, tomorrow_half
        )

        upcoming = [
            (stamp, kind)
            for stamp, kind in ((next_off_at, STATE_OFF), (next_possible_at, STATE_POSSIBLE))
            if stamp
        ]
        next_planned_off_at, next_outage_kind = (
            min(upcoming, key=lambda item: item[0]) if upcoming else (None, None)
        )

        if cur in (STATE_OFF, STATE_POSSIBLE):
            next_change_iso = next_on_at
        else:
            next_change_iso = min((stamp for stamp, _ in upcoming), default=None)

        next_change_hhmm = None
        if next_change_iso:
            change = dt_util.parse_datetime(next_change_iso)
            if change:
                next_change_hhmm = self._localize_kyiv(change).strftime("%H:%M")

        def longest_off(series: list[str]) -> float:
            best = current = 0
            for state in series:
                if state == STATE_OFF:
                    current += 1
                    best = max(best, current)
                else:
                    current = 0
            return best * 0.5

        data = {
            "queue": self.queue,
            "date": today.isoformat(),
            "now_status": cur,
            "now_halfhour_index": idx,
            "next_change_at": next_change_hhmm,
            "today_48half": today_half,
            "tomorrow_48half": tomorrow_half,
            "tomorrow_date": tomorrow_iso,
            "updated": updated,
            "source": POE_GPV_URL,
            "next_on_at": next_on_at,
            "next_off_at": next_off_at,
            "next_planned_off_at": next_planned_off_at,
            "next_possible_at": next_possible_at,
            "next_outage_kind": next_outage_kind,
            "today_outage_hours": today_half.count(STATE_OFF) * 0.5,
            "tomorrow_outage_hours": (tomorrow_half.count(STATE_OFF) * 0.5) if tomorrow_half else None,
            "possible_hours_today": today_half.count(STATE_POSSIBLE) * 0.5,
            "longest_outage_hours": longest_off(today_half + tomorrow_half),
            "history_today_48half": self._history_today,
            "history_tomorrow_48half": self._history_tomorrow,
            "is_emergency": False,
            "page_days": page_days,
        }

        if self.data and self.data.get("date") == data["date"]:
            old_today = self.data.get("today_48half") or []
            if old_today and old_today != today_half:
                if not self._history_today or old_today != self._history_today[0]:
                    self._history_today.insert(0, old_today)
                    self._history_today = self._history_today[:3]
                    data["history_today_48half"] = self._history_today
            old_tomorrow = self.data.get("tomorrow_48half") or []
            if tomorrow_half and old_tomorrow and old_tomorrow != tomorrow_half:
                if not self._history_tomorrow or old_tomorrow != self._history_tomorrow[0]:
                    self._history_tomorrow.insert(0, old_tomorrow)
                    self._history_tomorrow = self._history_tomorrow[:3]
                    data["history_tomorrow_48half"] = self._history_tomorrow
        elif self.data and self.data.get("date") and self.data["date"] != data["date"]:
            _LOGGER.debug("Day rollover %s -> %s", self.data["date"], data["date"])
            self._history_today = []
            self._history_tomorrow = []

        return data

    def _schedule_precise_refresh(self, data: dict[str, Any]) -> None:
        """Wake up exactly when the status changes, not on the next poll."""
        if data.get("now_status") == "nosched":
            if self._unsub_precise:
                self._unsub_precise()
                self._unsub_precise = None
            return

        if self._unsub_precise:
            self._unsub_precise()
            self._unsub_precise = None

        next_change_hhmm = data.get("next_change_at")
        base_date_iso = data.get("date")
        if not next_change_hhmm or not base_date_iso:
            return

        try:
            hh, mm = [int(part) for part in next_change_hhmm.split(":")]
            base_day = datetime.fromisoformat(base_date_iso).date()
            local_naive = datetime.combine(
                base_day, time(hour=hh, minute=mm, second=0, microsecond=0)
            )
            candidate_kyiv = self._localize_kyiv(local_naive)
            now_kyiv = dt_util.now(TZ_KYIV)
            if candidate_kyiv <= now_kyiv:
                candidate_kyiv += timedelta(days=1)
            candidate_utc = dt_util.as_utc(candidate_kyiv)

            @callback
            def _tick(_now) -> None:
                self.hass.async_create_task(self.async_request_refresh())

            self._unsub_precise = async_track_point_in_utc_time(
                self.hass, _tick, candidate_utc
            )
        except Exception as err:  # noqa: BLE001 - the next poll is the fallback
            _LOGGER.debug("Cannot arm the precise refresh: %s", err)

    @staticmethod
    def _find_next_at(
        target_states: list[str],
        base_date: date,
        today_half: list[str],
        idx: int,
        tomorrow_date_iso: Optional[str],
        tomorrow_half: Optional[list[str]],
    ) -> Optional[str]:
        if not today_half:
            return None
        today_tail = today_half[idx + 1 :]
        seq = list(today_tail)
        has_tomorrow = bool(tomorrow_date_iso and tomorrow_half)
        if has_tomorrow:
            seq.extend(tomorrow_half or [])

        pos = next((i for i, state in enumerate(seq) if state in target_states), None)
        if pos is None:
            return None

        if pos < len(today_tail):
            base_local_midnight = datetime.combine(
                base_date, datetime.min.time(), tzinfo=TZ_KYIV
            )
            minutes_from_base = (idx + 1 + pos) * 30
            next_local = base_local_midnight + timedelta(minutes=minutes_from_base)
        else:
            if not has_tomorrow:
                return None
            tomorrow_date = datetime.fromisoformat(tomorrow_date_iso).date()
            base_local_midnight = datetime.combine(
                tomorrow_date, datetime.min.time(), tzinfo=TZ_KYIV
            )
            minutes_into_tomorrow = (pos - len(today_tail)) * 30
            next_local = base_local_midnight + timedelta(minutes=minutes_into_tomorrow)

        return dt_util.as_utc(next_local).isoformat()

    @staticmethod
    def _localize_kyiv(value: datetime) -> datetime:
        if value.tzinfo is not None:
            return value.astimezone(TZ_KYIV)
        return value.replace(tzinfo=TZ_KYIV)
