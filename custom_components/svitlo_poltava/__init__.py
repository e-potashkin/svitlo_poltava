"""Svitlo Poltava: the Poltavaoblenergo outage schedule for the chosen queue."""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .const import (
    CARD_STATIC_PATH,
    CARD_URL,
    CONF_QUEUE,
    CONF_SCAN_INTERVAL,
    DEFAULT_QUEUE,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    PLATFORMS,
    VERSION,
)
from .coordinator import SvitloPoltavaCoordinator

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


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
    """Set up the selected queue."""
    queue = entry.data.get(CONF_QUEUE, DEFAULT_QUEUE)
    await _async_cleanup(hass, entry, queue)

    interval = int(
        entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    )
    coordinator = SvitloPoltavaCoordinator(hass, queue, interval)
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
    """Reload when the queue or the scan interval changes."""
    await hass.config_entries.async_reload(entry.entry_id)


async def _async_cleanup(hass: HomeAssistant, entry: ConfigEntry, queue: str) -> None:
    """Remove entities and the device that belong to a previous queue.

    Keep only the five entities this version creates. This removes the old
    queue's entities and the sensors that earlier versions created.
    """
    expected = {
        f"svitlo_poltava_{kind}_{queue}"
        for kind in ("status", "power", "next_off", "outage_today", "calendar")
    }
    entity_reg = er.async_get(hass)
    for entity in er.async_entries_for_config_entry(entity_reg, entry.entry_id):
        if entity.unique_id not in expected:
            entity_reg.async_remove(entity.entity_id)

    device_reg = dr.async_get(hass)
    for device in dr.async_entries_for_config_entry(device_reg, entry.entry_id):
        if (DOMAIN, queue) not in device.identifiers:
            device_reg.async_remove_device(device.id)
