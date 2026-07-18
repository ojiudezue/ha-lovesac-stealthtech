"""Constants for the Lovesac StealthTech integration."""

DOMAIN = "lovesac_stealthtech"

CONF_POLL_INTERVAL = "poll_interval"
CONF_IDLE_TIMEOUT = "idle_timeout"

DEFAULT_POLL_INTERVAL = 90  # seconds (matches homebridge plugin default)
DEFAULT_IDLE_TIMEOUT = 5.0  # seconds of notification silence before disconnect

# Consecutive connect/poll failures before marking unavailable.
# Mirrors UNREACHABLE_THRESHOLD=6 in homebridge-lovesac-stealthtech settings.ts.
MAX_CONSECUTIVE_FAILURES = 6

UNAVAILABLE_MESSAGE = (
    "Cannot connect to the StealthTech hub after {failures} attempts. "
    "The hub accepts only ONE BLE connection at a time - if the Lovesac "
    "mobile app is open on a phone nearby, it is likely holding the "
    "connection slot. Close the app and the integration will recover."
)
