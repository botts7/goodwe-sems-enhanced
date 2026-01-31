"""Config flow for SEMS integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_SCAN_INTERVAL, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import selector

from .const import (
    API_SERVERS,
    CONF_API_SERVER,
    CONF_POWERSTATION_ID,
    DEFAULT_API_SERVER,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)
from .sems_api import SemsApi

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Optional(CONF_POWERSTATION_ID): str,
        vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(
            vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL)
        ),
        vol.Optional(CONF_API_SERVER, default=DEFAULT_API_SERVER): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[{"value": k, "label": v} for k, v in API_SERVERS.items()],
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        ),
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect."""
    _LOGGER.info("SEMS Enhanced: Starting validation for %s", data[CONF_USERNAME])

    api = SemsApi(data[CONF_USERNAME], data[CONF_PASSWORD])

    _LOGGER.info("SEMS Enhanced: Attempting login...")
    login_success = await hass.async_add_executor_job(api.login)
    _LOGGER.info("SEMS Enhanced: Login result: %s", login_success)

    if not login_success:
        _LOGGER.error("SEMS Enhanced: Login failed!")
        raise InvalidAuth

    # Get powerstation ID if not provided
    powerstation_id = data.get(CONF_POWERSTATION_ID)
    if not powerstation_id:
        _LOGGER.info("SEMS Enhanced: Fetching power stations...")
        stations = await hass.async_add_executor_job(api.get_powerstation_ids)
        _LOGGER.info("SEMS Enhanced: Got stations: %s", stations)

        if stations:
            powerstation_id = stations[0].get("id")
            station_name = stations[0].get("stationname", "SEMS")
            _LOGGER.info("SEMS Enhanced: Using station %s (%s)", station_name, powerstation_id)
        else:
            _LOGGER.error("SEMS Enhanced: No power stations found!")
            raise CannotConnect("No power stations found")
    else:
        station_name = "SEMS"
        _LOGGER.info("SEMS Enhanced: Using provided station ID: %s", powerstation_id)

    return {"title": station_name, "powerstation_id": powerstation_id}


class ConfigFlow(config_entries.ConfigFlow, domain="sems_enhanced"):
    """Handle a config flow for SEMS."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                # Store the powerstation_id we discovered
                user_input[CONF_POWERSTATION_ID] = info["powerstation_id"]
                return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return SemsOptionsFlow()


class SemsOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for SEMS."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        # Get current values from config entry
        current_scan = self.config_entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        current_server = self.config_entry.data.get(CONF_API_SERVER, DEFAULT_API_SERVER)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_SCAN_INTERVAL,
                        default=self.config_entry.options.get(CONF_SCAN_INTERVAL, current_scan),
                    ): vol.All(
                        vol.Coerce(int),
                        vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL),
                    ),
                    vol.Optional(
                        CONF_API_SERVER,
                        default=self.config_entry.options.get(CONF_API_SERVER, current_server),
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[{"value": k, "label": v} for k, v in API_SERVERS.items()],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            ),
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""
