"""Switch platform for SEMS inverter control."""
from __future__ import annotations

import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SEMS switches from a config entry."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
    api = hass.data[DOMAIN][config_entry.entry_id]["api"]
    entities = []

    data = coordinator.data or {}

    for sn, inverter_data in data.items():
        if sn == "homeKit":
            continue

        device_info = DeviceInfo(
            identifiers={(DOMAIN, sn)},
            name=f"GoodWe Inverter {sn}",
            manufacturer="GoodWe",
        )

        entities.append(SemsInverterSwitch(coordinator, api, sn, device_info))

    async_add_entities(entities)


class SemsInverterSwitch(CoordinatorEntity, SwitchEntity):
    """Switch to control inverter on/off state."""

    _attr_icon = "mdi:solar-power"

    def __init__(self, coordinator, api, sn, device_info):
        """Initialize the switch."""
        super().__init__(coordinator)
        self._api = api
        self._sn = sn
        self._attr_unique_id = f"{sn}_power_switch"
        self._attr_name = "Inverter Power"
        self._attr_device_info = device_info

    @property
    def is_on(self):
        """Return true if inverter is generating."""
        data = self.coordinator.data.get(self._sn, {})
        status = data.get("status", 0)
        # Status 1 = generating, 0 = standby, -1 = fault
        return status == 1

    async def async_turn_on(self, **kwargs):
        """Turn on the inverter."""
        await self.hass.async_add_executor_job(
            self._api.control_inverter, self._sn, 1
        )
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs):
        """Turn off the inverter."""
        await self.hass.async_add_executor_job(
            self._api.control_inverter, self._sn, 0
        )
        await self.coordinator.async_request_refresh()
