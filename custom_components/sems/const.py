"""Constants for the SEMS Enhanced integration."""

DOMAIN = "sems_enhanced"

PLATFORMS = ["sensor", "switch"]

CONF_POWERSTATION_ID = "powerstation_id"
CONF_API_SERVER = "api_server"

DEFAULT_SCAN_INTERVAL = 60
MIN_SCAN_INTERVAL = 30
MAX_SCAN_INTERVAL = 300

# API server options - the login endpoint redirects to regional server
API_SERVERS = {
    "auto": "Auto-detect (recommended)",
    "global": "Global (semsportal.com)",
    "eu": "Europe (eu.semsportal.com)",
    "us": "USA (us.semsportal.com)",
    "au": "Australia (au.semsportal.com)",
    "cn": "China (semsportal.com.cn)",
}

DEFAULT_API_SERVER = "auto"
