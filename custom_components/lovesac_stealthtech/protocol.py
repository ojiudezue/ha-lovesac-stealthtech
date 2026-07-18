"""Pure protocol layer for the Lovesac StealthTech BLE hub.

No bleak / Home Assistant imports — fully unit-testable.

Every constant in this module cites its source:
- [HB]  homebridge-lovesac-stealthtech (MIT, ohmantics):
        src/settings.ts, src/protocol/constants.ts, commands.ts, responses.ts
- [LST] libstealthtech (MIT, jackspirou): docs/protocol-mapping.md
Where the two disagree, [LST] is treated as authoritative and the discrepancy
is noted in a PROTOCOL-UNCERTAIN comment. As of fetch date 2026-07-17 the two
sources agree on every constant below.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum

# --- GATT UUIDs -------------------------------------------------------------
# Service UUID encodes "excelpoint.com" in ASCII. [HB settings.ts / LST]
SERVICE_UUID = "65786365-6c70-6f69-6e74-2e636f6d0000"


def _char(suffix: str) -> str:
    return f"65786365-6c70-6f69-6e74-2e636f6d{suffix}"


# Characteristic UUIDs: base UUID with last 2 bytes varying. [HB settings.ts / LST]
CHAR_UPSTREAM = _char("0001")        # Notify: device -> host status
CHAR_DEVICE_INFO = _char("0002")     # Write: request state dump / version
CHAR_EQ_CONTROL = _char("0003")      # Write: volume/bass/treble/center/rear/mute/quiet/preset
CHAR_AUDIO_PATH = _char("0004")      # Write: balance, power
CHAR_PLAYER_CONTROL = _char("0005")  # Write: BT media play/pause/skip
CHAR_SYSTEM_LAYOUT = _char("0006")   # Write: configuration shape
CHAR_SOURCE = _char("0007")          # Write: input source
CHAR_COVERING = _char("0008")        # Write: fabric type
CHAR_USER_SETTING = _char("0009")    # Write: user preferences
CHAR_OTA = _char("000a")             # Write: OTA firmware update

# --- Ranges ----------------------------------------------------------------
# All from [LST protocol-mapping.md Command Encoding Table], matching the
# clamps in [HB commands.ts].
VOLUME_MAX = 36
BASS_MAX = 20
TREBLE_MAX = 20
CENTER_VOLUME_MAX = 30
REAR_VOLUME_MAX = 30
BALANCE_MAX = 100  # 50 = center


# --- Enums -----------------------------------------------------------------
class StatusCode(IntEnum):
    """UpStream notification status codes. [HB constants.ts / LST]"""

    VOLUME = 0x01
    CENTER_VOLUME = 0x02
    TREBLE = 0x03
    BASS = 0x04
    MUTE = 0x05
    QUIET_MODE = 0x06
    BALANCE = 0x07
    LAYOUT = 0x08
    SOURCE = 0x09
    POWER = 0x0A  # INVERTED on read: 0=ON, 1=OFF [LST / HB responses.ts]
    PRESET = 0x0B
    COVERING = 0x0C
    ARM_TYPE = 0x0D
    SUBWOOFER = 0x0E  # 1=connected
    REAR_VOLUME = 0x0F


class PresetWrite(IntEnum):
    """Preset values WRITTEN to the device. Asymmetric with read values.
    [HB constants.ts / LST 'Preset / Sound Mode Values']"""

    TV = 5
    NEWS = 6
    MOVIES = 7
    MUSIC = 8
    MANUAL = 9  # write-only; no corresponding read value


class PresetRead(IntEnum):
    """Preset values READ from notifications. [HB constants.ts / LST]"""

    MOVIES = 0
    MUSIC = 1
    TV = 2
    NEWS = 3


class Source(IntEnum):
    """Input source; same value read and write. [HB constants.ts / LST]"""

    HDMI_ARC = 0
    BLUETOOTH = 1
    AUX = 2
    OPTICAL = 3


PRESET_READ_TO_WRITE: dict[PresetRead, PresetWrite] = {
    PresetRead.MOVIES: PresetWrite.MOVIES,
    PresetRead.MUSIC: PresetWrite.MUSIC,
    PresetRead.TV: PresetWrite.TV,
    PresetRead.NEWS: PresetWrite.NEWS,
}
PRESET_WRITE_TO_READ = {w: r for r, w in PRESET_READ_TO_WRITE.items()}

PRESET_NAMES: dict[PresetRead, str] = {
    PresetRead.MOVIES: "Movies",
    PresetRead.MUSIC: "Music",
    PresetRead.TV: "TV",
    PresetRead.NEWS: "News",
}
PRESET_NAME_TO_WRITE: dict[str, PresetWrite] = {
    "Movies": PresetWrite.MOVIES,
    "Music": PresetWrite.MUSIC,
    "TV": PresetWrite.TV,
    "News": PresetWrite.NEWS,
}

SOURCE_NAMES: dict[Source, str] = {
    Source.HDMI_ARC: "HDMI-ARC",
    Source.BLUETOOTH: "Bluetooth",
    Source.AUX: "AUX",
    Source.OPTICAL: "Optical",
}
SOURCE_NAME_TO_VALUE = {name: src for src, name in SOURCE_NAMES.items()}

# --- Empirical enum-binding project (layout / arm type / covering) ----------
# The firmware names layouts Straight / L-shape / U-shape / Pit (per
# libstealthtech firmware-analysis.md), but no public binding exists between
# those names and the raw byte values reported on the LAYOUT / ARM_TYPE /
# COVERING status codes. These maps start EMPTY on purpose: entries get added
# as users report app-config vs raw-value pairs on the issue tracker
# (https://github.com/ojiudezue/ha-lovesac-stealthtech/issues). The raw
# sensors render the mapped name when a value is present here, else the raw
# int, and always expose the raw int as a `raw_value` attribute.
LAYOUT_NAMES: dict[int, str] = {}
ARM_TYPE_NAMES: dict[int, str] = {}
COVERING_NAMES: dict[int, str] = {}


# --- Frame encoding ---------------------------------------------------------
@dataclass(frozen=True)
class Frame:
    """A write destined for a specific characteristic (write-without-response)."""

    char_uuid: str
    data: bytes


def _format_a(cmd: int, sub: int, value: int) -> bytes:
    """Format A (5 bytes): AA <cmd> <sub> 01 <value>. [LST 'Packet Formats']"""
    return bytes([0xAA, cmd, sub, 0x01, value & 0xFF])


def _format_b(cmd: int, value: int) -> bytes:
    """Format B (4 bytes): AA <cmd> <value> 00. [LST 'Packet Formats']"""
    return bytes([0xAA, cmd, value & 0xFF, 0x00])


def _clamp(value: int, max_value: int) -> int:
    return max(0, min(max_value, int(value)))


def encode_volume(level: int) -> Frame:
    return Frame(CHAR_EQ_CONTROL, _format_a(0x03, 0x02, _clamp(level, VOLUME_MAX)))


def encode_bass(level: int) -> Frame:
    return Frame(CHAR_EQ_CONTROL, _format_a(0x03, 0x01, _clamp(level, BASS_MAX)))


def encode_treble(level: int) -> Frame:
    return Frame(CHAR_EQ_CONTROL, _format_a(0x03, 0x00, _clamp(level, TREBLE_MAX)))


def encode_center_volume(level: int) -> Frame:
    return Frame(CHAR_EQ_CONTROL, _format_a(0x03, 0x03, _clamp(level, CENTER_VOLUME_MAX)))


def encode_rear_volume(level: int) -> Frame:
    return Frame(CHAR_EQ_CONTROL, _format_a(0x03, 0x0A, _clamp(level, REAR_VOLUME_MAX)))


def encode_mute(muted: bool) -> Frame:
    return Frame(CHAR_EQ_CONTROL, _format_a(0x03, 0x09, 1 if muted else 0))


def encode_quiet_mode(on: bool) -> Frame:
    return Frame(CHAR_EQ_CONTROL, _format_a(0x03, 0x04, 1 if on else 0))


def encode_balance(balance: int) -> Frame:
    return Frame(CHAR_AUDIO_PATH, _format_a(0x04, 0x00, _clamp(balance, BALANCE_MAX)))


def encode_power(on: bool) -> Frame:
    # NOTE: WRITE power is NOT inverted (1=on); only the READ side inverts.
    # [HB commands.ts setPower vs responses.ts Power case]
    return Frame(CHAR_AUDIO_PATH, _format_a(0x04, 0x01, 1 if on else 0))


def encode_preset(preset: PresetWrite) -> Frame:
    # Preset uses Format B on EqControl, with the asymmetric WRITE enum.
    return Frame(CHAR_EQ_CONTROL, _format_b(0x03, int(preset)))


def encode_source(source: Source) -> Frame:
    return Frame(CHAR_SOURCE, _format_b(0x07, int(source)))


def encode_state_request() -> Frame:
    """Request full state dump: AA 01 01 00. [LST 'Get State' / HB requestDeviceInfo]"""
    return Frame(CHAR_DEVICE_INFO, _format_b(0x01, 0x01))


def encode_version_request() -> Frame:
    """Request firmware versions: AA 01 01 01 (trailing 01 distinguishes from
    the state request). [HB requestVersionInfo / LST 'Get Version']"""
    return Frame(CHAR_DEVICE_INFO, bytes([0xAA, 0x01, 0x01, 0x01]))


# PROTOCOL-UNCERTAIN: neither source documents the <value> semantics for
# PlayerControl. [HB commands.ts] exposes setPlayPause(value)/setSkip(value)
# with no fixed value; [LST] lists the value column as "—". We use value=1 for
# play/pause toggle and value 0=next / 1=previous for skip AS A GUESS.
# Verify against hardware before trusting BT transport controls.
def encode_play_pause(value: int = 1) -> Frame:
    return Frame(CHAR_PLAYER_CONTROL, _format_a(0x05, 0x00, value))


def encode_skip(value: int) -> Frame:
    return Frame(CHAR_PLAYER_CONTROL, _format_a(0x05, 0x01, value))


# --- State -----------------------------------------------------------------
@dataclass
class StealthTechState:
    """Mirror of the hub's reported state. None = not yet reported."""

    power: bool | None = None
    volume: int | None = None
    mute: bool | None = None
    quiet_mode: bool | None = None
    bass: int | None = None
    treble: int | None = None
    center_volume: int | None = None
    rear_volume: int | None = None
    balance: int | None = None
    source: Source | None = None
    preset: PresetRead | None = None
    subwoofer_connected: bool | None = None
    layout: int | None = None
    covering: int | None = None
    arm_type: int | None = None
    versions: dict[str, str] = field(default_factory=dict)


# --- Notification parsing ---------------------------------------------------
@dataclass(frozen=True)
class StatusNotification:
    code: StatusCode
    value: int


@dataclass(frozen=True)
class VersionNotification:
    component: str  # "mcu" | "dsp" | "eq"
    major: int
    minor: int

    @property
    def version(self) -> str:
        # [LST]: "CC 06 AA 01 03 01 01 47 = MCU version 1.71" — minor is
        # rendered as decimal of the raw byte (0x47 = 71).
        return f"{self.major}.{self.minor}"


_VERSION_COMPONENTS = {0x01: "mcu", 0x02: "dsp", 0x03: "eq"}


def parse_notification(
    data: bytes,
) -> StatusNotification | VersionNotification | None:
    """Parse an UpStream notification.

    Status frames: CC 05/06 AA ... <code> <value> — last 2 bytes are always
    code+value. [LST 'Status Notifications']
    Version frames: CC 05/06 AA 01 03 <type> <major> <minor> — these MIMIC
    status frames (e.g. MCU v1.71 ends 01 47, which would parse as Volume=71),
    so they must be filtered FIRST. [HB responses.ts / LST 'Version Notifications']
    """
    if len(data) < 4:
        return None

    # Version-frame detection: payload AA 01 03 after the CC xx header.
    if len(data) >= 5 and data[2] == 0xAA and data[3] == 0x01 and data[4] == 0x03:
        if len(data) >= 8:
            component = _VERSION_COMPONENTS.get(data[5])
            if component is not None:
                return VersionNotification(component, data[6], data[7])
        return None  # malformed / unknown version frame: never a status

    code = data[-2]
    value = data[-1]
    if not (StatusCode.VOLUME <= code <= StatusCode.REAR_VOLUME):
        return None
    return StatusNotification(StatusCode(code), value)


_STATUS_RANGES: dict[StatusCode, int] = {
    StatusCode.VOLUME: VOLUME_MAX,
    StatusCode.CENTER_VOLUME: CENTER_VOLUME_MAX,
    StatusCode.TREBLE: TREBLE_MAX,
    StatusCode.BASS: BASS_MAX,
    StatusCode.MUTE: 1,
    StatusCode.QUIET_MODE: 1,
    StatusCode.BALANCE: BALANCE_MAX,
    StatusCode.SOURCE: 3,
    StatusCode.POWER: 1,
    StatusCode.PRESET: 3,
    StatusCode.SUBWOOFER: 1,
    StatusCode.REAR_VOLUME: REAR_VOLUME_MAX,
    # LAYOUT / COVERING / ARM_TYPE: raw bytes, no documented range.
}


def apply_status(state: StealthTechState, notif: StatusNotification) -> bool:
    """Apply a status notification to state. Returns True if state changed.

    Out-of-range values are ignored (firmware-bug guard, per [HB responses.ts]).
    """
    code, value = notif.code, notif.value
    limit = _STATUS_RANGES.get(code)
    if limit is not None and not (0 <= value <= limit):
        return False

    if code == StatusCode.VOLUME:
        return _set(state, "volume", value)
    if code == StatusCode.CENTER_VOLUME:
        return _set(state, "center_volume", value)
    if code == StatusCode.TREBLE:
        return _set(state, "treble", value)
    if code == StatusCode.BASS:
        return _set(state, "bass", value)
    if code == StatusCode.MUTE:
        return _set(state, "mute", value == 1)
    if code == StatusCode.QUIET_MODE:
        return _set(state, "quiet_mode", value == 1)
    if code == StatusCode.BALANCE:
        return _set(state, "balance", value)
    if code == StatusCode.SOURCE:
        return _set(state, "source", Source(value))
    if code == StatusCode.POWER:
        # INVERTED: 0 = ON, 1 = OFF. [LST / HB responses.ts]
        return _set(state, "power", value == 0)
    if code == StatusCode.PRESET:
        return _set(state, "preset", PresetRead(value))
    if code == StatusCode.SUBWOOFER:
        return _set(state, "subwoofer_connected", value == 1)
    if code == StatusCode.REAR_VOLUME:
        return _set(state, "rear_volume", value)
    if code == StatusCode.LAYOUT:
        return _set(state, "layout", value)
    if code == StatusCode.COVERING:
        return _set(state, "covering", value)
    if code == StatusCode.ARM_TYPE:
        return _set(state, "arm_type", value)
    return False


def _set(state: StealthTechState, attr: str, value: object) -> bool:
    if getattr(state, attr) == value:
        return False
    setattr(state, attr, value)
    return True
