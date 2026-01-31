"""Enhanced GoodWe SEMS integration for Home Assistant."""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_SCAN_INTERVAL, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONF_POWERSTATION_ID, DEFAULT_SCAN_INTERVAL, DOMAIN, PLATFORMS
from .sems_api import OutOfRetries, SemsApi

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the SEMS component."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up SEMS from a config entry."""
    username = entry.data[CONF_USERNAME]
    password = entry.data[CONF_PASSWORD]
    powerstation_id = entry.data.get(CONF_POWERSTATION_ID)
    scan_interval = entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)

    api = SemsApi(username, password)

    coordinator = SemsDataUpdateCoordinator(
        hass,
        api,
        powerstation_id,
        update_interval=timedelta(seconds=scan_interval),
    )

    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = {
        "api": api,
        "coordinator": coordinator,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


class SemsDataUpdateCoordinator(DataUpdateCoordinator):
    """Enhanced data coordinator fetching from multiple SEMS endpoints."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: SemsApi,
        powerstation_id: str | None,
        update_interval: timedelta,
    ):
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=update_interval,
        )
        self.api = api
        self.powerstation_id = powerstation_id

    async def _async_update_data(self):
        """Fetch data from SEMS API."""
        try:
            # Get powerstation ID if not configured
            if not self.powerstation_id:
                stations = await self.hass.async_add_executor_job(
                    self.api.get_powerstation_ids
                )
                if stations:
                    self.powerstation_id = stations[0].get("id")
                else:
                    raise UpdateFailed("No power stations found")

            # Fetch all data from enhanced API
            all_data = await self.hass.async_add_executor_job(
                self.api.get_all_data, self.powerstation_id
            )

            result = {}

            # Process inverter data
            inverter_points = all_data.get("inverter_points", [])

            for inverter in inverter_points:
                sn = inverter.get("sn", inverter.get("name"))
                if not sn:
                    continue

                inverter_data = {
                    "sn": sn,
                    "status": inverter.get("status"),
                    "out_pac": inverter.get("out_pac", 0),
                    "in_pac": inverter.get("in_pac", 0),
                    "eday": inverter.get("eday", 0),
                    "emonth": inverter.get("emonth", 0),
                    "etotal": inverter.get("etotal", 0),
                    "soc": inverter.get("soc"),
                    "vbattery1": inverter.get("vbattery1"),
                    "ibattery1": inverter.get("ibattery1"),
                    "last_refresh": inverter.get("last_refresh_time"),
                }

                # Extract dict values (detailed sensor readings from left/right sections)
                inv_dict = inverter.get("dict", {})
                for section in ["left", "right"]:
                    for item in inv_dict.get(section, []):
                        key = item.get("key", "")
                        value = item.get("value")
                        if key and value is not None:
                            # Store both original and lowercase keys for flexible access
                            inverter_data[key] = value
                            inverter_data[key.lower()] = value

                _LOGGER.debug("SEMS: Inverter %s loaded with %d data points", sn, len(inverter_data))
                result[sn] = inverter_data

            # Add homeKit data with powerflow, KPIs, and warnings
            homekit_data = {}

            # Powerflow data
            powerflow = all_data.get("powerflow")
            if powerflow:
                homekit_data["powerflow"] = powerflow

            # Plant detail KPIs
            plant_detail = all_data.get("plant_detail")
            if plant_detail:
                kpi = plant_detail.get("kpi")
                if kpi:
                    homekit_data["kpi"] = kpi
                info = plant_detail.get("info")
                if info:
                    homekit_data["info"] = info

            # Warnings
            warnings = all_data.get("warnings")
            if warnings:
                homekit_data["warnings"] = warnings

            # Weather
            weather = all_data.get("weather")
            if weather:
                homekit_data["weather"] = weather

            result["homeKit"] = homekit_data

            _LOGGER.debug("SEMS data update complete: %s inverters", len(result) - 1)
            return result

        except OutOfRetries as err:
            raise UpdateFailed(f"Authentication failed: {err}") from err
        except Exception as err:
            _LOGGER.exception("Error fetching SEMS data")
            raise UpdateFailed(f"Error fetching data: {err}") from err
