"""Diagnostics for Svitlo Poltava."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, POE_GPV_URL


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return the current schedule and where it came from."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    return {
        "entry": entry.as_dict(),
        "source": POE_GPV_URL,
        "queue": coordinator.queue,
        "coordinator_data": coordinator.data,
    }
