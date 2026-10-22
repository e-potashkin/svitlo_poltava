"""Svitlo Poltava: the Poltavaoblenergo outage schedule for queue 3.1."""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CARD_STATIC_PATH,
    CARD_URL,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    PLATFORMS,
    VERSION,
)
from .coordinator import SvitloPoltavaCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Register the bundled card and its static path."""
    www = Path(__file__).parent / "www"
    if not www.exists():
        return True

    await hass.http.async_register_static_paths(
        [StaticPathConfig(CARD_STATIC_PATH, str(www), False)]
    )
    # Load the card as a frontend module on every page. This is more reliable
    # than writing a Lovelace resource: the resource store is not always loaded
    # when a custom integration starts, and a HACS install would otherwise need
    # a manual step.
    add_extra_js_url(hass, f"{CARD_URL}?v={VERSION}")
    _LOGGER.debug("Card module registered: %s", CARD_URL)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up one queue entry."""
    interval = int(
        entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    )
    coordinator = SvitloPoltavaCoordinator(hass, interval)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload the platforms and drop the coordinator."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return unloaded


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload when the scan interval changes."""
    await hass.config_entries.async_reload(entry.entry_id)
