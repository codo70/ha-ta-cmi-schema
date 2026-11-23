"""Constants for the Technische Alternative C.M.I. Schema integration."""

DOMAIN = "ta_cmi_schema"

CONF_SCAN_INTERVAL = "scan_interval"
CONF_PAGES = "pages"
CONF_SENSORS = "create_sensors"

DEFAULT_USERNAME = "admin"
DEFAULT_SCAN_INTERVAL = 60  # seconds
MIN_SCAN_INTERVAL = 15
MAX_PAGES = 200
MAX_MISSING_PAGES = 3

STORAGE_VERSION = 1
# bump whenever discovery (names, detected types) changes, so cached schemas
# of older versions are re-read automatically after an update
DISCOVERY_VERSION = 4

PLATFORMS = ["number", "select", "time", "switch", "sensor", "binary_sensor", "button"]

SERVICE_WRITE_VALUE = "write_value"
SERVICE_REDISCOVER = "rediscover"
ATTR_SHORT_ADDRESS = "short_address"
ATTR_VALUE = "value"
ATTR_ENTRY_ID = "config_entry_id"
