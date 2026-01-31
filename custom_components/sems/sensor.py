"""Enhanced SEMS sensors with powerflow, inverter details, and warnings."""
from __future__ import annotations

import logging
import re
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


def parse_power_value(value_str):
    """Parse power string like '128W' or '1.5kW' to watts."""
    if not value_str:
        return 0
    match = re.match(r"([-\d.]+)\s*(kW|W)?", str(value_str), re.IGNORECASE)
    if match:
        num = float(match.group(1))
        unit = (match.group(2) or "W").lower()
        if unit == "kw":
            return num * 1000
        return num
    return 0


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SEMS sensors from a config entry."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
    entities = []

    data = coordinator.data or {}

    # Process each inverter
    for sn, inverter_data in data.items():
        if sn == "homeKit":
            continue

        device_info = DeviceInfo(
            identifiers={(DOMAIN, sn)},
            name=f"GoodWe Inverter {sn}",
            manufacturer="GoodWe",
            model=inverter_data.get("model_type", "Unknown"),
            sw_version=inverter_data.get("firmware", ""),
        )

        # Basic power sensor
        entities.append(SemsPowerSensor(coordinator, sn, device_info))

        # Statistics sensors
        entities.append(SemsEnergySensor(coordinator, sn, "eday", "Today", device_info))
        entities.append(SemsEnergySensor(coordinator, sn, "emonth", "This Month", device_info))
        entities.append(SemsEnergySensor(coordinator, sn, "etotal", "Total", device_info))

        # Inverter detail sensors (from GetInverterAllPoint)
        entities.append(SemsTemperatureSensor(coordinator, sn, device_info))
        entities.append(SemsFrequencySensor(coordinator, sn, device_info))
        entities.append(SemsVoltageSensor(coordinator, sn, "ac", "AC Voltage", device_info))
        entities.append(SemsCurrentSensor(coordinator, sn, "ac", "AC Current", device_info))
        entities.append(SemsRSSISensor(coordinator, sn, device_info))

        # Per-string DC sensors (PV1, PV2, PV3)
        for i in range(1, 4):
            entities.append(SemsDCStringSensor(coordinator, sn, i, "voltage", device_info))
            entities.append(SemsDCStringSensor(coordinator, sn, i, "current", device_info))

        # Battery sensors (if available)
        entities.append(SemsBatterySOCSensor(coordinator, sn, device_info))
        entities.append(SemsBatteryVoltageSensor(coordinator, sn, device_info))
        entities.append(SemsBatteryCurrentSensor(coordinator, sn, device_info))

        # Diagnostic sensor to see all data keys
        entities.append(SemsDiagnosticSensor(coordinator, sn))

    # Powerflow sensors (plant-level)
    if "powerflow" in data.get("homeKit", {}):
        powerflow = data["homeKit"]["powerflow"]
        plant_device = DeviceInfo(
            identifiers={(DOMAIN, "powerflow")},
            name="Solar Power Flow",
            manufacturer="GoodWe",
            model="Power Flow Monitor",
        )
        entities.append(SemsPowerflowSensor(coordinator, "pv", "Solar Production", plant_device))
        entities.append(SemsPowerflowSensor(coordinator, "load", "House Load", plant_device))
        entities.append(SemsPowerflowSensor(coordinator, "grid", "Grid Power", plant_device))
        entities.append(SemsPowerflowSensor(coordinator, "bettery", "Battery Power", plant_device))
        entities.append(SemsPowerflowSOCSensor(coordinator, plant_device))
        entities.append(SemsPowerflowStatusSensor(coordinator, "grid", "Grid Status", plant_device))
        entities.append(SemsPowerflowStatusSensor(coordinator, "pv", "Solar Status", plant_device))
        entities.append(SemsPowerflowStatusSensor(coordinator, "bettery", "Battery Status", plant_device))

    # KPI sensors
    if "kpi" in data.get("homeKit", {}):
        kpi_device = DeviceInfo(
            identifiers={(DOMAIN, "kpi")},
            name="Solar KPIs",
            manufacturer="GoodWe",
            model="Statistics",
        )
        entities.append(SemsKPISensor(coordinator, "month_generation", "Monthly Generation", UnitOfEnergy.KILO_WATT_HOUR, kpi_device))
        entities.append(SemsKPISensor(coordinator, "total_power", "Total Generation", UnitOfEnergy.KILO_WATT_HOUR, kpi_device))
        entities.append(SemsKPISensor(coordinator, "day_income", "Today Income", "AUD", kpi_device))
        entities.append(SemsKPISensor(coordinator, "total_income", "Total Income", "AUD", kpi_device))

    # Warning sensor
    entities.append(SemsWarningSensor(coordinator))

    async_add_entities(entities)


class SemsPowerSensor(CoordinatorEntity, SensorEntity):
    """Sensor for current power output."""

    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfPower.WATT

    def __init__(self, coordinator, sn, device_info):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._sn = sn
        self._attr_unique_id = f"{sn}_power"
        self._attr_name = "Power"
        self._attr_device_info = device_info

    @property
    def native_value(self):
        """Return the current power."""
        data = self.coordinator.data.get(self._sn, {})
        return data.get("pac", data.get("out_pac", 0))


class SemsEnergySensor(CoordinatorEntity, SensorEntity):
    """Sensor for energy generation statistics."""

    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR

    def __init__(self, coordinator, sn, key, name, device_info):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._sn = sn
        self._key = key
        self._attr_unique_id = f"{sn}_{key}"
        self._attr_name = f"Energy {name}"
        self._attr_device_info = device_info

    @property
    def native_value(self):
        """Return the energy value."""
        data = self.coordinator.data.get(self._sn, {})
        return data.get(self._key, 0)


class SemsTemperatureSensor(CoordinatorEntity, SensorEntity):
    """Sensor for inverter temperature."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    def __init__(self, coordinator, sn, device_info):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._sn = sn
        self._attr_unique_id = f"{sn}_temperature"
        self._attr_name = "Temperature"
        self._attr_device_info = device_info

    @property
    def native_value(self):
        """Return the temperature."""
        data = self.coordinator.data.get(self._sn, {})
        temp = data.get("tempperature", data.get("innerTemp", data.get("innertemp")))
        if temp:
            try:
                return float(str(temp).replace("°C", "").replace("℃", "").strip())
            except (ValueError, TypeError):
                pass
        return None


class SemsFrequencySensor(CoordinatorEntity, SensorEntity):
    """Sensor for AC frequency."""

    _attr_device_class = SensorDeviceClass.FREQUENCY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfFrequency.HERTZ

    def __init__(self, coordinator, sn, device_info):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._sn = sn
        self._attr_unique_id = f"{sn}_frequency"
        self._attr_name = "AC Frequency"
        self._attr_device_info = device_info

    @property
    def native_value(self):
        """Return the frequency."""
        data = self.coordinator.data.get(self._sn, {})
        freq = data.get("fac1", data.get("acFrequency", data.get("acfrequency")))
        if freq:
            try:
                return float(str(freq).replace("Hz", "").strip())
            except (ValueError, TypeError):
                pass
        return None


class SemsVoltageSensor(CoordinatorEntity, SensorEntity):
    """Sensor for voltage."""

    _attr_device_class = SensorDeviceClass.VOLTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT

    def __init__(self, coordinator, sn, voltage_type, name, device_info):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._sn = sn
        self._type = voltage_type
        self._attr_unique_id = f"{sn}_{voltage_type}_voltage"
        self._attr_name = name
        self._attr_device_info = device_info

    @property
    def native_value(self):
        """Return the voltage."""
        data = self.coordinator.data.get(self._sn, {})
        _LOGGER.debug("SEMS Voltage: sn=%s, data_keys=%s", self._sn, list(data.keys())[:10])
        if self._type == "ac":
            volt = data.get("vac1") or data.get("acVacVol") or data.get("acvacvol")
            _LOGGER.debug("SEMS Voltage: volt=%s", volt)
            if volt:
                try:
                    return float(str(volt).replace("V", "").strip())
                except (ValueError, TypeError):
                    pass
        return None


class SemsCurrentSensor(CoordinatorEntity, SensorEntity):
    """Sensor for current."""

    _attr_device_class = SensorDeviceClass.CURRENT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE

    def __init__(self, coordinator, sn, current_type, name, device_info):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._sn = sn
        self._type = current_type
        self._attr_unique_id = f"{sn}_{current_type}_current"
        self._attr_name = name
        self._attr_device_info = device_info

    @property
    def native_value(self):
        """Return the current."""
        data = self.coordinator.data.get(self._sn, {})
        if self._type == "ac":
            curr = data.get("iac1", data.get("acCurrent", data.get("accurrent")))
            if curr:
                try:
                    return float(str(curr).replace("A", "").strip())
                except (ValueError, TypeError):
                    pass
        return None


class SemsDCStringSensor(CoordinatorEntity, SensorEntity):
    """Sensor for DC string voltage/current."""

    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, sn, string_num, value_type, device_info):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._sn = sn
        self._string = string_num
        self._value_type = value_type
        self._attr_unique_id = f"{sn}_pv{string_num}_{value_type}"
        self._attr_name = f"PV{string_num} {value_type.title()}"
        self._attr_device_info = device_info

        if value_type == "voltage":
            self._attr_device_class = SensorDeviceClass.VOLTAGE
            self._attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT
        else:
            self._attr_device_class = SensorDeviceClass.CURRENT
            self._attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE

    @property
    def native_value(self):
        """Return the DC string value."""
        data = self.coordinator.data.get(self._sn, {})

        # Try dcVandC format first (e.g., "243.4/0.2") - both cases
        for dc_key in [f"dcVandC{self._string}", f"dcvandc{self._string}"]:
            dc_val = data.get(dc_key)
            if dc_val and "/" in str(dc_val):
                parts = str(dc_val).split("/")
                try:
                    if self._value_type == "voltage":
                        return float(parts[0])
                    else:
                        return float(parts[1])
                except (ValueError, IndexError):
                    pass

        # Try direct keys (vpv1, ipv1, etc.)
        if self._value_type == "voltage":
            key = f"vpv{self._string}"
        else:
            key = f"ipv{self._string}"

        val = data.get(key, data.get(key.lower()))
        if val:
            try:
                return float(val)
            except (ValueError, TypeError):
                pass

        return None


class SemsRSSISensor(CoordinatorEntity, SensorEntity):
    """Sensor for WiFi signal strength."""

    _attr_device_class = SensorDeviceClass.SIGNAL_STRENGTH
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "dBm"

    def __init__(self, coordinator, sn, device_info):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._sn = sn
        self._attr_unique_id = f"{sn}_rssi"
        self._attr_name = "WiFi Signal"
        self._attr_device_info = device_info

    @property
    def native_value(self):
        """Return the RSSI."""
        data = self.coordinator.data.get(self._sn, {})
        rssi = data.get("rssi", data.get("RSSI"))
        if rssi:
            try:
                val = float(rssi)
                # RSSI is typically negative, but SEMS reports it as positive percentage-like
                # Convert to approximate dBm if it's a high positive value
                if val > 0 and val <= 100:
                    return val  # Return as signal quality percentage
                return val
            except (ValueError, TypeError):
                pass
        return None


class SemsBatterySOCSensor(CoordinatorEntity, SensorEntity):
    """Sensor for battery state of charge."""

    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE

    def __init__(self, coordinator, sn, device_info):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._sn = sn
        self._attr_unique_id = f"{sn}_battery_soc"
        self._attr_name = "Battery SOC"
        self._attr_device_info = device_info

    @property
    def native_value(self):
        """Return the SOC."""
        data = self.coordinator.data.get(self._sn, {})
        soc = data.get("soc")
        if soc:
            try:
                return float(str(soc).replace("%", "").strip())
            except (ValueError, TypeError):
                pass
        return None


class SemsBatteryVoltageSensor(CoordinatorEntity, SensorEntity):
    """Sensor for battery voltage."""

    _attr_device_class = SensorDeviceClass.VOLTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT

    def __init__(self, coordinator, sn, device_info):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._sn = sn
        self._attr_unique_id = f"{sn}_battery_voltage"
        self._attr_name = "Battery Voltage"
        self._attr_device_info = device_info

    @property
    def native_value(self):
        """Return the battery voltage."""
        data = self.coordinator.data.get(self._sn, {})
        return data.get("vbattery1")


class SemsBatteryCurrentSensor(CoordinatorEntity, SensorEntity):
    """Sensor for battery current."""

    _attr_device_class = SensorDeviceClass.CURRENT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE

    def __init__(self, coordinator, sn, device_info):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._sn = sn
        self._attr_unique_id = f"{sn}_battery_current"
        self._attr_name = "Battery Current"
        self._attr_device_info = device_info

    @property
    def native_value(self):
        """Return the battery current."""
        data = self.coordinator.data.get(self._sn, {})
        return data.get("ibattery1")


class SemsPowerflowSensor(CoordinatorEntity, SensorEntity):
    """Sensor for power flow values."""

    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfPower.WATT

    def __init__(self, coordinator, key, name, device_info):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._key = key
        self._attr_unique_id = f"powerflow_{key}"
        self._attr_name = name
        self._attr_device_info = device_info

    @property
    def native_value(self):
        """Return the power flow value."""
        homekit = self.coordinator.data.get("homeKit", {})
        powerflow = homekit.get("powerflow", {})
        value = powerflow.get(self._key)
        return parse_power_value(value)


class SemsPowerflowSOCSensor(CoordinatorEntity, SensorEntity):
    """Sensor for powerflow battery SOC."""

    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE

    def __init__(self, coordinator, device_info):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = "powerflow_soc"
        self._attr_name = "System Battery SOC"
        self._attr_device_info = device_info

    @property
    def native_value(self):
        """Return the SOC."""
        homekit = self.coordinator.data.get("homeKit", {})
        powerflow = homekit.get("powerflow", {})
        soc = powerflow.get("soc", 0)
        if isinstance(soc, str):
            return float(soc.replace("%", "").strip())
        return soc


class SemsPowerflowStatusSensor(CoordinatorEntity, SensorEntity):
    """Sensor for power flow status (direction)."""

    def __init__(self, coordinator, key, name, device_info):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._key = key
        self._attr_unique_id = f"powerflow_{key}_status"
        self._attr_name = name
        self._attr_device_info = device_info

    @property
    def native_value(self):
        """Return the status."""
        homekit = self.coordinator.data.get("homeKit", {})
        powerflow = homekit.get("powerflow", {})
        status = powerflow.get(f"{self._key}Status", 0)

        # Map status codes to human-readable values
        if self._key == "grid":
            if status == -1:
                return "Importing"
            elif status == 1:
                return "Exporting"
            return "Idle"
        elif self._key == "pv":
            if status == -1:
                return "Generating"
            return "Idle"
        elif self._key == "bettery":
            if status == -1:
                return "Charging"
            elif status == 1:
                return "Discharging"
            return "Idle"
        return str(status)


class SemsKPISensor(CoordinatorEntity, SensorEntity):
    """Sensor for KPI values."""

    _attr_state_class = SensorStateClass.TOTAL

    def __init__(self, coordinator, key, name, unit, device_info):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._key = key
        self._attr_unique_id = f"kpi_{key}"
        self._attr_name = name
        self._attr_native_unit_of_measurement = unit
        self._attr_device_info = device_info

        if "income" in key.lower():
            self._attr_device_class = SensorDeviceClass.MONETARY
        else:
            self._attr_device_class = SensorDeviceClass.ENERGY

    @property
    def native_value(self):
        """Return the KPI value."""
        homekit = self.coordinator.data.get("homeKit", {})
        kpi = homekit.get("kpi", {})
        return kpi.get(self._key)


class SemsWarningSensor(CoordinatorEntity, SensorEntity):
    """Sensor for active warnings count."""

    _attr_icon = "mdi:alert"

    def __init__(self, coordinator):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = "sems_warnings"
        self._attr_name = "Active Warnings"

    @property
    def native_value(self):
        """Return the warning count."""
        homekit = self.coordinator.data.get("homeKit", {})
        warnings = homekit.get("warnings", [])
        count = 0
        for inverter in warnings:
            count += len(inverter.get("warning", []))
        return count

    @property
    def extra_state_attributes(self):
        """Return warning details."""
        homekit = self.coordinator.data.get("homeKit", {})
        warnings = homekit.get("warnings", [])
        details = []
        for inverter in warnings:
            for warning in inverter.get("warning", []):
                details.append({
                    "inverter": inverter.get("sn"),
                    "message": warning
                })
        return {"warnings": details} if details else {}


class SemsDiagnosticSensor(CoordinatorEntity, SensorEntity):
    """Diagnostic sensor showing available data keys."""

    _attr_icon = "mdi:bug"

    def __init__(self, coordinator, sn):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._sn = sn
        self._attr_unique_id = f"{sn}_diagnostic"
        self._attr_name = "Data Diagnostic"

    @property
    def native_value(self):
        """Return count of data keys."""
        data = self.coordinator.data.get(self._sn, {})
        return len(data.keys())

    @property
    def extra_state_attributes(self):
        """Return all data keys and sample values."""
        data = self.coordinator.data.get(self._sn, {})
        attrs = {"all_keys": list(data.keys())}
        # Add first 20 key-value pairs
        for i, (k, v) in enumerate(data.items()):
            if i >= 20:
                break
            attrs[k] = str(v)[:50]  # Truncate long values
        return attrs
