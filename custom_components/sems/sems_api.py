"""Enhanced SEMS API client with additional endpoints."""
import json
import logging
import requests

_LOGGER = logging.getLogger(__name__)


class OutOfRetries(Exception):
    """Raised when max retries exceeded."""
    pass


class SemsApi:
    """Enhanced SEMS API client."""

    def __init__(self, username, password):
        """Initialize the API client."""
        self.username = username
        self.password = password
        self.token = None
        self.api_base = None
        self.retry_limit = 3
        self.retry_count = 0
        self._session = requests.Session()

    def login(self):
        """Authenticate with SEMS portal and obtain token."""
        url = "https://www.semsportal.com/api/v2/Common/CrossLogin"
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "token": '{"version":"","client":"web","language":"en"}'
        }
        payload = {"account": self.username, "pwd": self.password}

        _LOGGER.debug("SEMS: Attempting login for user %s", self.username)

        try:
            response = self._session.post(url, headers=headers, json=payload, timeout=30, verify=True)
            data = response.json()

            if data.get("code") == 0 or data.get("code") == "0":
                self.token = data.get("data", {})
                self.api_base = data.get("api")
                self.retry_count = 0
                _LOGGER.debug("SEMS: Login successful, API base: %s", self.api_base)
                return True
            else:
                _LOGGER.error("SEMS: Login failed - code=%s, msg=%s", data.get("code"), data.get("msg"))
                return False
        except requests.exceptions.SSLError as e:
            _LOGGER.error("SEMS: SSL Error: %s", e)
            return False
        except requests.exceptions.ConnectionError as e:
            _LOGGER.error("SEMS: Connection Error: %s", e)
            return False
        except requests.exceptions.Timeout as e:
            _LOGGER.error("SEMS: Timeout Error: %s", e)
            return False
        except json.JSONDecodeError as e:
            _LOGGER.error("SEMS: JSON decode error: %s", e)
            return False
        except Exception as e:
            _LOGGER.error("SEMS: Unexpected error during login: %s (%s)", e, type(e).__name__)
            return False

    def _make_request(self, endpoint, payload=None):
        """Make authenticated API request."""
        if not self.token:
            _LOGGER.debug("SEMS: No token, attempting login first")
            if not self.login():
                _LOGGER.error("SEMS: Login failed, cannot make request")
                return None

        url = f"{self.api_base}{endpoint}" if self.api_base else f"https://www.semsportal.com/api{endpoint}"
        _LOGGER.debug("SEMS: Making request to %s", url)

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "token": json.dumps(self.token) if isinstance(self.token, dict) else self.token
        }

        try:
            response = self._session.post(url, headers=headers, json=payload or {}, timeout=30)
            data = response.json()

            if data.get("code") in ["100001", "100002"]:
                _LOGGER.warning("SEMS: Token expired, re-authenticating")
                self.token = None
                self.retry_count += 1
                if self.retry_count >= self.retry_limit:
                    raise OutOfRetries("Max retries exceeded")
                return self._make_request(endpoint, payload)

            return data
        except Exception as e:
            _LOGGER.error("SEMS: Request error: %s", e)
            return None

    def _make_form_request(self, endpoint, payload=None):
        """Make authenticated API request with form data."""
        if not self.token:
            if not self.login():
                return None

        url = f"{self.api_base}{endpoint}" if self.api_base else f"https://www.semsportal.com/api{endpoint}"

        headers = {
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Accept": "application/json",
            "token": json.dumps(self.token) if isinstance(self.token, dict) else self.token
        }

        try:
            response = self._session.post(url, headers=headers, data=payload or {}, timeout=30)
            return response.json()
        except Exception as e:
            _LOGGER.error("SEMS: Form request error: %s", e)
            return None

    def get_powerstation_ids(self):
        """Get list of power station IDs for the user."""
        data = self._make_request("/PowerStation/GetPowerStationIdByOwner")

        if data and (data.get("code") == 0 or data.get("code") == "0"):
            result = data.get("data")

            if isinstance(result, str):
                _LOGGER.debug("SEMS: Single station ID: %s", result)
                return [{"id": result, "stationname": "SEMS Station"}]
            elif isinstance(result, list):
                _LOGGER.debug("SEMS: Found %d stations", len(result))
                return result
            else:
                _LOGGER.debug("SEMS: Unexpected data type: %s", type(result))
            return []

        _LOGGER.error("SEMS: Failed to get power stations")
        return []

    def get_plant_detail(self, powerstation_id):
        """Get detailed plant information."""
        payload = {"powerStationId": powerstation_id}
        return self._make_form_request("/v3/PowerStation/GetPlantDetailByPowerstationId", payload)

    def get_powerflow(self, powerstation_id):
        """Get real-time power flow data."""
        payload = {"PowerStationId": powerstation_id}
        return self._make_form_request("/v2/PowerStation/GetPowerflow", payload)

    def get_inverter_all_points(self, powerstation_id):
        """Get detailed inverter data points."""
        payload = {"powerStationId": powerstation_id}
        return self._make_form_request("/v3/PowerStation/GetInverterAllPoint", payload)

    def get_warnings(self, powerstation_id):
        """Get active warnings and alerts."""
        payload = {"pw_id": powerstation_id}
        return self._make_form_request("/warning/PowerstationWarningsQuery", payload)

    def get_inverter_pac_by_day(self, inverter_sn, date):
        """Get 5-minute interval power data."""
        payload = {"id": inverter_sn, "date": date}
        return self._make_request("/PowerStationMonitor/GetInverterPacByDay", payload)

    def get_weather(self, powerstation_id):
        """Get weather data."""
        payload = {"powerStationId": powerstation_id}
        return self._make_form_request("/v3/PowerStation/GetWeather", payload)

    def control_inverter(self, inverter_sn, status):
        """Control inverter status."""
        payload = {
            "InverterSN": inverter_sn,
            "InverterStatusSettingMark": "1",
            "InverterStatus": str(status)
        }
        return self._make_request("/PowerStation/SaveRemoteControlInverter", payload)

    def get_all_data(self, powerstation_id):
        """Fetch all available data for a power station."""
        result = {
            "powerstation_id": powerstation_id,
            "plant_detail": None,
            "powerflow": None,
            "inverter_points": None,
            "warnings": None,
            "weather": None
        }

        plant_data = self.get_plant_detail(powerstation_id)
        if plant_data and (plant_data.get("code") == 0 or plant_data.get("code") == "0"):
            result["plant_detail"] = plant_data.get("data")

        powerflow_data = self.get_powerflow(powerstation_id)
        if powerflow_data and (powerflow_data.get("code") == 0 or powerflow_data.get("code") == "0"):
            result["powerflow"] = powerflow_data.get("data", {}).get("powerflow")

        inverter_data = self.get_inverter_all_points(powerstation_id)
        if inverter_data and (inverter_data.get("code") == 0 or inverter_data.get("code") == "0"):
            result["inverter_points"] = inverter_data.get("data", {}).get("inverterPoints", [])

        warnings_data = self.get_warnings(powerstation_id)
        if warnings_data and not warnings_data.get("hasError"):
            result["warnings"] = warnings_data.get("data", {}).get("list", [])

        weather_data = self.get_weather(powerstation_id)
        if weather_data and (weather_data.get("code") == 0 or weather_data.get("code") == "0"):
            result["weather"] = weather_data.get("data")

        return result
