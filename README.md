# GoodWe SEMS Enhanced - Home Assistant Integration

Enhanced version of the [goodwe-sems-home-assistant](https://github.com/TimSoethout/goodwe-sems-home-assistant) integration with additional sensors and endpoints discovered through API analysis.

## New Features

This enhanced version adds the following capabilities:

### Power Flow Sensors
Real-time power flow data showing:
- **Solar Production** - Current PV output (watts)
- **House Load** - Current consumption (watts)
- **Grid Power** - Import/export power (watts)
- **Battery Power** - Charge/discharge power (watts)
- **Grid Status** - Importing/Exporting/Idle
- **Solar Status** - Generating/Idle
- **Battery Status** - Charging/Discharging/Idle

### Detailed Inverter Sensors
Per-inverter detailed metrics:
- **PV String Voltages** (PV1, PV2, PV3) - Individual string DC voltage
- **PV String Currents** (PV1, PV2, PV3) - Individual string DC current
- **AC Voltage** - Grid voltage
- **AC Current** - Output current
- **AC Frequency** - Grid frequency (Hz)
- **Temperature** - Inverter internal temperature
- **WiFi Signal (RSSI)** - Connection signal strength
- **Battery SOC** - State of charge percentage
- **Battery Voltage/Current** - Battery metrics

### KPI Sensors
Aggregated statistics:
- **Monthly Generation** (kWh)
- **Total Generation** (kWh)
- **Today Income** (currency)
- **Total Income** (currency)

### Warning Sensor
- **Active Warnings** - Count of current warnings with details in attributes

## New API Endpoints Used

| Endpoint | Purpose |
|----------|---------|
| `/api/v2/PowerStation/GetPowerflow` | Real-time power flow |
| `/api/v3/PowerStation/GetInverterAllPoint` | Detailed inverter metrics |
| `/api/v3/PowerStation/GetPlantDetailByPowerstationId` | Plant KPIs |
| `/api/warning/PowerstationWarningsQuery` | Active warnings |
| `/api/v3/PowerStation/GetWeather` | Location weather |
| `/api/PowerStationMonitor/GetInverterPacByDay` | 5-min interval history |
| `/api/v2/Charts/GetChartByPlant` | Chart data |

## Installation

### HACS (Recommended)
1. Add this repository as a custom repository in HACS
2. Install "GoodWe SEMS Enhanced"
3. Restart Home Assistant
4. Add integration via UI

### Manual Installation
1. Copy the `custom_components/sems` folder to your Home Assistant `custom_components` directory
2. Restart Home Assistant
3. Go to Settings > Integrations > Add Integration
4. Search for "GoodWe SEMS Enhanced"
5. Enter your SEMS portal credentials

## Configuration

| Option | Required | Default | Description |
|--------|----------|---------|-------------|
| Username | Yes | - | SEMS portal email/username |
| Password | Yes | - | SEMS portal password |
| Power Station ID | No | Auto-detect | Specific station ID |
| Scan Interval | No | 60 | Update interval in seconds |

## Example Automations

### Energy Dashboard
All energy sensors support long-term statistics and can be added to the Energy Dashboard.

### Grid Export Alert
```yaml
automation:
  - alias: "Solar Exporting to Grid"
    trigger:
      - platform: state
        entity_id: sensor.powerflow_grid_status
        to: "Exporting"
    action:
      - service: notify.mobile_app
        data:
          message: "Solar is now exporting {{ states('sensor.powerflow_grid') }}W to grid"
```

### Low Battery Warning
```yaml
automation:
  - alias: "Battery Low Warning"
    trigger:
      - platform: numeric_state
        entity_id: sensor.powerflow_soc
        below: 20
    action:
      - service: notify.mobile_app
        data:
          message: "Solar battery at {{ states('sensor.powerflow_soc') }}%"
```

## Credits

- Original integration: [TimSoethout/goodwe-sems-home-assistant](https://github.com/TimSoethout/goodwe-sems-home-assistant)
- API analysis and enhancements: HAR file analysis of semsportal.com

## License

MIT License - See original repository for details.
