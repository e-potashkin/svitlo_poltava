"""Config flow for Svitlo Poltava: choose the queue, one entry."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import selector

from .const import (
    CONF_QUEUE,
    CONF_SCAN_INTERVAL,
    DEFAULT_QUEUE,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    POE_GPV_URL,
)
from .poe_gpv import parse_poe_page

_LOGGER = logging.getLogger(__name__)


def _queue_key(queue: str) -> tuple[int, ...]:
    """Sort 1.1, 1.2, 2.1 ... 10.1 numerically."""
    try:
        return tuple(int(part) for part in queue.split("."))
    except ValueError:
        return (99, 99)


async def _async_queues(hass) -> list[str]:
    """Read the queue list from the operator page."""
    session = async_get_clientsession(hass)
    async with session.get(
        POE_GPV_URL,
        headers={"User-Agent": "Mozilla/5.0 (compatible; svitlo_poltava)"},
        timeout=30,
    ) as response:
        if response.status != 200:
            raise RuntimeError(f"HTTP {response.status}")
        html = await response.text()

    days = parse_poe_page(html)
    queues = {queue for day in days.values() for queue in day}
    if not queues:
        raise RuntimeError("The page carries no schedule")
    return sorted(queues, key=_queue_key)


def _queue_schema(queues: list[str], current: str) -> vol.Schema:
    if queues:
        default = current if current in queues else (DEFAULT_QUEUE if DEFAULT_QUEUE in queues else queues[0])
        return vol.Schema(
            {
                vol.Required(CONF_QUEUE, default=default): selector(
                    {"select": {"options": queues, "mode": "dropdown"}}
                )
            }
        )
    # The page is down: let the user type the queue. The coordinator will
    # report the failure if the value is wrong.
    return vol.Schema({vol.Required(CONF_QUEUE, default=current): str})


class SvitloPoltavaConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """One entry for one queue."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(entry: config_entries.ConfigEntry):
        return SvitloPoltavaOptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        load_error = None
        try:
            queues = await _async_queues(self.hass)
        except Exception as err:  # noqa: BLE001 - show the form, let the user retry
            _LOGGER.warning("Cannot read the queue list: %s", err)
            queues = []
            load_error = "cannot_connect"

        errors: dict[str, str] = {}
        if user_input is not None:
            queue = str(user_input[CONF_QUEUE]).strip()
            if queues and queue not in queues:
                errors["base"] = "invalid_queue"
            if not errors:
                await self.async_set_unique_id(f"poltava_{queue}")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"Poltava — Queue {queue}",
                    data={CONF_QUEUE: queue},
                )

        if load_error and not errors:
            errors["base"] = load_error

        return self.async_show_form(
            step_id="user",
            data_schema=_queue_schema(queues, DEFAULT_QUEUE),
            errors=errors,
        )


class SvitloPoltavaOptionsFlow(config_entries.OptionsFlow):
    """Change the queue and the poll interval."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        current_queue = self.config_entry.data.get(CONF_QUEUE, DEFAULT_QUEUE)
        current_interval = int(
            self.config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        )

        load_error = None
        try:
            queues = await _async_queues(self.hass)
        except Exception as err:  # noqa: BLE001 - keep the current queue usable
            _LOGGER.warning("Cannot read the queue list: %s", err)
            queues = [current_queue]
            load_error = "cannot_connect"

        errors: dict[str, str] = {}
        if user_input is not None:
            queue = str(user_input[CONF_QUEUE]).strip()
            interval = int(user_input[CONF_SCAN_INTERVAL])
            if queues and queue not in queues:
                errors["base"] = "invalid_queue"
            if not errors:
                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    data={**self.config_entry.data, CONF_QUEUE: queue},
                    title=f"Poltava — Queue {queue}",
                    options={CONF_SCAN_INTERVAL: interval},
                )
                return self.async_create_entry(title="", data={})

        if queues:
            queue_field = vol.Required(CONF_QUEUE, default=current_queue)
            queue_schema = selector({"select": {"options": queues, "mode": "dropdown"}})
        else:
            queue_field = vol.Required(CONF_QUEUE, default=current_queue)
            queue_schema = str

        if load_error and not errors:
            errors["base"] = load_error

        schema = vol.Schema(
            {
                queue_field: queue_schema,
                vol.Optional(CONF_SCAN_INTERVAL, default=current_interval): vol.All(
                    int, vol.Range(min=60, max=600)
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
