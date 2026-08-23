"""Constants for the Shelly Modbus integration."""

DOMAIN = "shelly_modbus"

MANUFACTURER = "Shelly"

# Modbus-TCP defaults.  Shelly devices always serve on port 502 and ignore the
# unit id, but both stay configurable for use behind gateways.
DEFAULT_PORT = 502
DEFAULT_UNIT_ID = 1
DEFAULT_TIMEOUT = 5
DEFAULT_MESSAGE_WAIT_MS = 20

# Shelly firmware rejects reads larger than 80 registers in a single request
# (verified on Pro 3EM and 3EM-63 Gen3 firmware 2.0.0).
MAX_BLOCK_SIZE = 80

# Shelly publishes its values as input registers using the classic "3xxxx"
# notation.  The wire address is the documented address minus this offset.
INPUT_REGISTER_OFFSET = 30000

# Configuration keys.
CONF_MODEL = "model"
CONF_PROFILE = "profile"
CONF_UNIT_ID = "unit_id"

# Polling categories.  Each register definition declares which category it
# belongs to; the interval per category is configurable in the options flow.
SCAN_INTERVAL_HIGH = "high"
SCAN_INTERVAL_LOW = "low"
SCAN_INTERVAL_STATIC = "static"

CONF_SCAN_INTERVAL_HIGH = "scan_interval_high"
CONF_SCAN_INTERVAL_LOW = "scan_interval_low"

# Fast-changing measurements (power, voltage, current) vs. slow ones
# (energy counters, error flags).  Static values are read once at startup.
DEFAULT_SCAN_INTERVALS = {
    SCAN_INTERVAL_HIGH: 10,
    SCAN_INTERVAL_LOW: 60,
}

SCAN_INTERVAL_LIMITS = {
    SCAN_INTERVAL_HIGH: (1, 3600),
    SCAN_INTERVAL_LOW: (5, 86400),
}

# Platforms this integration forwards config entries to.
PLATFORMS = ["sensor", "binary_sensor", "switch"]
