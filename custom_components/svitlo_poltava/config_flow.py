"""Config flow for Svitlo Poltava: one queue, one entry."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback

from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN


class SvitloPoltavaConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """One entry for queue 3.1. The region and queue are fixed."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(entry: config_entries.ConfigEntry):
        return SvitloPoltavaOptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if user_input is not None:
            return self.async_create_entry(title="Poltava — Queue 3.1", data={})

        return self.async_show_form(step_id="user", data_schema=vol.Schema({}))


class SvitloPoltavaOptionsFlow(config_entries.OptionsFlow):
    """One option: how often to read the operator page."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            return self.async_create_entry(
                title="",
                data={CONF_SCAN_INTERVAL: user_input[CONF_SCAN_INTERVAL]},
            )

        current = int(
            self.config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        )
        schema = vol.Schema(
            {
                vol.Optional(CONF_SCAN_INTERVAL, default=current): vol.All(
                    int, vol.Range(min=60, max=600)
                )
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
