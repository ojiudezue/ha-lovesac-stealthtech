"""Unit tests for the pure protocol layer.

Fixtures are constructed from libstealthtech docs/protocol-mapping.md and the
homebridge-lovesac-stealthtech reference implementation.
"""
import pytest

from lovesac_stealthtech import protocol as p


# --- Frame encoding: every command -----------------------------------------
@pytest.mark.parametrize(
    ("frame", "char", "data"),
    [
        (p.encode_volume(18), p.CHAR_EQ_CONTROL, b"\xaa\x03\x02\x01\x12"),
        (p.encode_bass(10), p.CHAR_EQ_CONTROL, b"\xaa\x03\x01\x01\x0a"),
        (p.encode_treble(20), p.CHAR_EQ_CONTROL, b"\xaa\x03\x00\x01\x14"),
        (p.encode_center_volume(30), p.CHAR_EQ_CONTROL, b"\xaa\x03\x03\x01\x1e"),
        (p.encode_rear_volume(15), p.CHAR_EQ_CONTROL, b"\xaa\x03\x0a\x01\x0f"),
        (p.encode_mute(True), p.CHAR_EQ_CONTROL, b"\xaa\x03\x09\x01\x01"),
        (p.encode_mute(False), p.CHAR_EQ_CONTROL, b"\xaa\x03\x09\x01\x00"),
        (p.encode_quiet_mode(True), p.CHAR_EQ_CONTROL, b"\xaa\x03\x04\x01\x01"),
        (p.encode_balance(50), p.CHAR_AUDIO_PATH, b"\xaa\x04\x00\x01\x32"),
        (p.encode_power(True), p.CHAR_AUDIO_PATH, b"\xaa\x04\x01\x01\x01"),
        (p.encode_power(False), p.CHAR_AUDIO_PATH, b"\xaa\x04\x01\x01\x00"),
        # Preset uses Format B with the asymmetric WRITE enum values.
        (p.encode_preset(p.PresetWrite.MOVIES), p.CHAR_EQ_CONTROL, b"\xaa\x03\x07\x00"),
        (p.encode_preset(p.PresetWrite.MUSIC), p.CHAR_EQ_CONTROL, b"\xaa\x03\x08\x00"),
        (p.encode_preset(p.PresetWrite.TV), p.CHAR_EQ_CONTROL, b"\xaa\x03\x05\x00"),
        (p.encode_preset(p.PresetWrite.NEWS), p.CHAR_EQ_CONTROL, b"\xaa\x03\x06\x00"),
        (p.encode_preset(p.PresetWrite.MANUAL), p.CHAR_EQ_CONTROL, b"\xaa\x03\x09\x00"),
        (p.encode_source(p.Source.HDMI_ARC), p.CHAR_SOURCE, b"\xaa\x07\x00\x00"),
        (p.encode_source(p.Source.OPTICAL), p.CHAR_SOURCE, b"\xaa\x07\x03\x00"),
        # State dump: AA 01 01 00; version request: AA 01 01 01.
        (p.encode_state_request(), p.CHAR_DEVICE_INFO, b"\xaa\x01\x01\x00"),
        (p.encode_version_request(), p.CHAR_DEVICE_INFO, b"\xaa\x01\x01\x01"),
        (p.encode_play_pause(), p.CHAR_PLAYER_CONTROL, b"\xaa\x05\x00\x01\x01"),
        (p.encode_skip(0), p.CHAR_PLAYER_CONTROL, b"\xaa\x05\x01\x01\x00"),
        (p.encode_skip(1), p.CHAR_PLAYER_CONTROL, b"\xaa\x05\x01\x01\x01"),
    ],
)
def test_encode(frame, char, data):
    assert frame.char_uuid == char
    assert frame.data == data


def test_encode_clamps():
    assert p.encode_volume(99).data[-1] == 36
    assert p.encode_volume(-5).data[-1] == 0
    assert p.encode_bass(21).data[-1] == 20
    assert p.encode_balance(200).data[-1] == 100


def test_char_uuids():
    assert p.SERVICE_UUID == "65786365-6c70-6f69-6e74-2e636f6d0000"
    assert p.CHAR_UPSTREAM.endswith("0001")
    assert p.CHAR_OTA.endswith("000a")


# --- Notification parsing: every status code --------------------------------
def notif(code: int, value: int) -> bytes:
    """Build a status notification: CC 05 AA <code> <value>."""
    return bytes([0xCC, 0x05, 0xAA, code, value])


@pytest.mark.parametrize(
    ("code", "value"),
    [(c, 1) for c in range(0x01, 0x10)],
)
def test_parse_all_status_codes(code, value):
    parsed = p.parse_notification(notif(code, value))
    assert isinstance(parsed, p.StatusNotification)
    assert parsed.code == code
    assert parsed.value == value


def test_parse_rejects_unknown_codes_and_short_frames():
    assert p.parse_notification(notif(0x10, 1)) is None
    assert p.parse_notification(notif(0x00, 1)) is None
    assert p.parse_notification(b"\xcc\x05") is None
    assert p.parse_notification(b"") is None


def test_version_frame_mimic_is_not_a_status():
    # CC 06 AA 01 03 01 01 47 = MCU v1.71 (from LST docs). Its last two bytes
    # (01 47) would otherwise parse as Volume=71 - out of range but only by
    # luck; the frame must be classified as a version frame, not a status.
    raw = bytes([0xCC, 0x06, 0xAA, 0x01, 0x03, 0x01, 0x01, 0x47])
    parsed = p.parse_notification(raw)
    assert isinstance(parsed, p.VersionNotification)
    assert parsed.component == "mcu"
    assert parsed.version == "1.71"


def test_truncated_version_frame_returns_none_not_status():
    # AA 01 03 header but too short for component/major/minor.
    assert p.parse_notification(bytes([0xCC, 0x06, 0xAA, 0x01, 0x03])) is None


# --- apply_status ------------------------------------------------------------
def apply(code, value, state=None):
    state = state or p.StealthTechState()
    changed = p.apply_status(state, p.StatusNotification(p.StatusCode(code), value))
    return state, changed


def test_apply_each_field():
    s, c = apply(p.StatusCode.VOLUME, 12)
    assert c and s.volume == 12
    s, c = apply(p.StatusCode.CENTER_VOLUME, 7)
    assert c and s.center_volume == 7
    s, c = apply(p.StatusCode.TREBLE, 3)
    assert c and s.treble == 3
    s, c = apply(p.StatusCode.BASS, 4)
    assert c and s.bass == 4
    s, c = apply(p.StatusCode.MUTE, 1)
    assert c and s.mute is True
    s, c = apply(p.StatusCode.QUIET_MODE, 0)
    assert c and s.quiet_mode is False
    s, c = apply(p.StatusCode.BALANCE, 50)
    assert c and s.balance == 50
    s, c = apply(p.StatusCode.SOURCE, 1)
    assert c and s.source == p.Source.BLUETOOTH
    s, c = apply(p.StatusCode.SUBWOOFER, 1)
    assert c and s.subwoofer_connected is True
    s, c = apply(p.StatusCode.REAR_VOLUME, 30)
    assert c and s.rear_volume == 30
    s, c = apply(p.StatusCode.LAYOUT, 0x42)
    assert c and s.layout == 0x42
    s, c = apply(p.StatusCode.COVERING, 2)
    assert c and s.covering == 2
    s, c = apply(p.StatusCode.ARM_TYPE, 1)
    assert c and s.arm_type == 1


def test_power_read_is_inverted():
    s, _ = apply(p.StatusCode.POWER, 0)
    assert s.power is True  # 0 = ON per LST docs
    s, _ = apply(p.StatusCode.POWER, 1)
    assert s.power is False


def test_preset_read_enum_is_asymmetric_with_write():
    s, _ = apply(p.StatusCode.PRESET, 0)
    assert s.preset == p.PresetRead.MOVIES
    # Round trip through the mapping produces the WRITE value 7, not 0.
    assert p.PRESET_READ_TO_WRITE[s.preset] == p.PresetWrite.MOVIES == 7
    for read_val, write_val in [(0, 7), (1, 8), (2, 5), (3, 6)]:
        assert p.PRESET_READ_TO_WRITE[p.PresetRead(read_val)] == write_val


def test_apply_out_of_range_ignored():
    s, c = apply(p.StatusCode.VOLUME, 37)
    assert not c and s.volume is None
    s, c = apply(p.StatusCode.PRESET, 5)  # write-enum value arriving on read
    assert not c and s.preset is None


def test_apply_no_change_returns_false():
    s = p.StealthTechState(volume=10)
    _, changed = apply(p.StatusCode.VOLUME, 10, s)
    assert changed is False


# --- Full state dump from a captured-bytes-style fixture ---------------------
STATE_DUMP = [
    notif(0x0A, 0x00),  # power ON (inverted)
    notif(0x01, 18),    # volume
    notif(0x05, 0),     # unmuted
    notif(0x06, 1),     # quiet mode on
    notif(0x04, 10),    # bass
    notif(0x03, 12),    # treble
    notif(0x02, 15),    # center
    notif(0x0F, 20),    # rear
    notif(0x07, 50),    # balance centered
    notif(0x09, 0),     # HDMI-ARC
    notif(0x0B, 2),     # preset TV (read value)
    notif(0x0E, 1),     # subwoofer connected
    notif(0x08, 3),     # layout
    notif(0x0C, 1),     # covering
    notif(0x0D, 2),     # arm type
    bytes([0xCC, 0x06, 0xAA, 0x01, 0x03, 0x01, 0x01, 0x47]),  # MCU 1.71
]


def test_state_dump_parse():
    state = p.StealthTechState()
    for raw in STATE_DUMP:
        parsed = p.parse_notification(raw)
        if isinstance(parsed, p.StatusNotification):
            p.apply_status(state, parsed)
        elif isinstance(parsed, p.VersionNotification):
            state.versions[parsed.component] = parsed.version
    assert state.power is True
    assert state.volume == 18
    assert state.mute is False
    assert state.quiet_mode is True
    assert state.bass == 10
    assert state.treble == 12
    assert state.center_volume == 15
    assert state.rear_volume == 20
    assert state.balance == 50
    assert state.source == p.Source.HDMI_ARC
    assert state.preset == p.PresetRead.TV
    assert state.subwoofer_connected is True
    assert state.versions == {"mcu": "1.71"}
