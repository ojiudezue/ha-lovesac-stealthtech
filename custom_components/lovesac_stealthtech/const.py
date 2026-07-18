"""Constants for the Lovesac StealthTech integration."""

DOMAIN = "lovesac_stealthtech"

CONF_POLL_INTERVAL = "poll_interval"
CONF_IDLE_TIMEOUT = "idle_timeout"

# Local enum-label overrides (v0.3 D4): operator-supplied names for the raw
# layout / arm-type / covering sensor values while the shipped tables are
# still being crowd-sourced. Precedence: shipped table > operator override >
# raw int. Empty string = unset.
CONF_MY_COUCH_SHAPE = "my_couch_shape"
CONF_MY_ARM_STYLE = "my_arm_style"
CONF_MY_FABRIC = "my_fabric"

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
