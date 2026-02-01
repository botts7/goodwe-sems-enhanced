"""Config flow for sems integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_SCAN_INTERVAL, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError

from .const import (
    CONF_ALWAYS_POLL_POWERFLOW,
    CONF_MIDNIGHT_SKIP,
    CONF_NIGHT_INTERVAL,
    CONF_NIGHT_MODE,
    CONF_STALE_THRESHOLD,
    CONF_STATION_ID,
    DEFAULT_NIGHT_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_STALE_THRESHOLD,
    DOMAIN,
    SEMS_CONFIG_SCHEMA,
)
from .sems_api import SemsApi

_LOGGER = logging.getLogger(__name__)


def mask_password(user_input: dict[str, Any]) -> dict[str, Any]:
    """Mask password in user input for logging."""
    masked_input = user_input.copy()
    if CONF_PASSWORD in masked_input:
        masked_input[CONF_PASSWORD] = "<masked>"
    return masked_input


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect.

    Data has the keys from STEP_USER_DATA_SCHEMA with values provided by the user.
    """

    _LOGGER.debug(
        "SEMS - Start validation config flow user input, with input data: %s",
        mask_password(data),
    )
    api = SemsApi(hass, data[CONF_USERNAME], data[CONF_PASSWORD])

    authenticated = await hass.async_add_executor_job(api.test_authentication)
    # If you cannot connect:
    # throw CannotConnect
    # If the authentication is wrong:
    # InvalidAuth
    if not authenticated:
        raise InvalidAuth

    # If optional station ID is not provided, query the SEMS API for the first found
    if CONF_STATION_ID not in data:
        _LOGGER.debug(
            "SEMS - No station ID provided, query SEMS API, using first found"
        )
        powerStationId = await hass.async_add_executor_job(api.getPowerStationIds)
        _LOGGER.debug("SEMS - Found power station IDs: %s", powerStationId)

        data[CONF_STATION_ID] = powerStationId

    # Return info that you want to store in the config entry.
    _LOGGER.debug("SEMS - validate_input Returning data: %s", mask_password(data))
    return data


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for sems."""

    _LOGGER.debug("SEMS - new config flow")

    VERSION = 1
    # CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> OptionsFlowHandler:
        """Get the options flow for this handler."""
        return OptionsFlowHandler(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Handle the initial step."""
        if user_input is None:
            return self.async_show_form(step_id="user", data_schema=SEMS_CONFIG_SCHEMA)

        errors = {}

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
            _LOGGER.debug(
                "Creating config entry for %s with data: %s",
                info[CONF_STATION_ID],
                mask_password(info),
            )
            return self.async_create_entry(
                title=f"Inverter {info[CONF_STATION_ID]}", data=info
            )

        return self.async_show_form(
            step_id="user", data_schema=SEMS_CONFIG_SCHEMA, errors=errors
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for SEMS."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Manage the options."""
        if user_input is not None:
            # Update config entry with new options
            new_data = {**self.config_entry.data, **user_input}
            self.hass.config_entries.async_update_entry(
                self.config_entry, data=new_data
            )
            return self.async_create_entry(title="", data=user_input)

        # Get current values from config entry data
        current_data = self.config_entry.data

        options_schema = vol.Schema(
            {
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    default=current_data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): vol.All(vol.Coerce(int), vol.Range(min=30, max=600)),
                vol.Optional(
                    CONF_NIGHT_MODE,
                    default=current_data.get(CONF_NIGHT_MODE, True),
                ): bool,
                vol.Optional(
                    CONF_NIGHT_INTERVAL,
                    default=current_data.get(CONF_NIGHT_INTERVAL, DEFAULT_NIGHT_INTERVAL),
                ): vol.All(vol.Coerce(int), vol.Range(min=60, max=3600)),
                vol.Optional(
                    CONF_ALWAYS_POLL_POWERFLOW,
                    default=current_data.get(CONF_ALWAYS_POLL_POWERFLOW, True),
                ): bool,
                vol.Optional(
                    CONF_MIDNIGHT_SKIP,
                    default=current_data.get(CONF_MIDNIGHT_SKIP, True),
                ): bool,
                vol.Optional(
                    CONF_STALE_THRESHOLD,
                    default=current_data.get(CONF_STALE_THRESHOLD, DEFAULT_STALE_THRESHOLD),
                ): vol.All(vol.Coerce(int), vol.Range(min=60, max=3600)),
            }
        )

        return self.async_show_form(step_id="init", data_schema=options_schema)
