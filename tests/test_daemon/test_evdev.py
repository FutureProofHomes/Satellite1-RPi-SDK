from satellite1.daemon.evdev import (
    BUTTONS,
    EdgeDetector,
    decode_port_a,
    load_keymap,
    read_buttons,
)

# gpio_port_a is active-LOW: idle nibble 0x07 = all released.
IDLE = 0x07
VOL_UP_PRESSED = IDLE & ~0x01     # bit 0 low
VOL_DOWN_PRESSED = IDLE & ~0x04   # bit 2 low
MUTE_PRESSED = IDLE & ~0x02       # bit 1 low


def frame(port_a):
    return bytes([0x00, port_a, 0x00, 0x00])


# ---- decode_port_a -------------------------------------------------------

def test_decode_valid_frame():
    assert decode_port_a(frame(IDLE)) == IDLE


def test_decode_rejects_high_nibble_set():
    assert decode_port_a(bytes([0x00, 0x17, 0x00, 0x00])) is None


def test_decode_rejects_nonzero_padding():
    assert decode_port_a(bytes([0x00, IDLE, 0x01, 0x00])) is None
    assert decode_port_a(bytes([0x01, IDLE, 0x00, 0x00])) is None


def test_decode_rejects_short_or_none():
    assert decode_port_a(b"\x00\x07\x00") is None
    assert decode_port_a(None) is None


# ---- read_buttons --------------------------------------------------------

def test_read_buttons_idle_all_released():
    assert read_buttons(IDLE) == {n: False for n in BUTTONS}


def test_read_buttons_single_press():
    r = read_buttons(VOL_UP_PRESSED)
    assert r["volume_up"] is True
    assert r["volume_down"] is False
    assert r["action"] is False


def test_read_buttons_none_passthrough():
    assert read_buttons(None) is None


# ---- EdgeDetector --------------------------------------------------------

def _idle():
    return read_buttons(IDLE)


def test_press_fires_after_confirm_and_idle():
    d = EdgeDetector(confirm_samples=2, debounce_s=0.0)
    t = 1.0
    # Establish a confirmed idle baseline.
    assert d.update(_idle(), t) == []
    assert d.update(_idle(), t) == []
    # Now press volume_up, confirmed over two polls.
    press = read_buttons(VOL_UP_PRESSED)
    assert d.update(press, t) == []          # first sighting, not yet confirmed
    assert d.update(press, t) == ["volume_up"]


def test_unconfirmed_flaky_read_does_not_fire():
    d = EdgeDetector(confirm_samples=2, debounce_s=0.0)
    d.update(_idle(), 0.0)
    d.update(_idle(), 0.0)
    # A single flaky press followed by idle never reaches confirm_samples.
    assert d.update(read_buttons(VOL_UP_PRESSED), 0.0) == []
    assert d.update(_idle(), 0.0) == []
    assert d.update(_idle(), 0.0) == []


def test_no_fire_before_first_idle_seen():
    d = EdgeDetector(confirm_samples=1, debounce_s=0.0)
    # First confirmed state is already a press: startup transient must not fire.
    assert d.update(read_buttons(VOL_UP_PRESSED), 0.0) == []


def test_debounce_blocks_rapid_repeat():
    d = EdgeDetector(confirm_samples=1, debounce_s=0.25)
    d.update(_idle(), 1.0)
    assert d.update(read_buttons(MUTE_PRESSED), 1.5) == ["action"]
    # Release then re-press within the debounce window -> suppressed.
    d.update(_idle(), 1.6)
    assert d.update(read_buttons(MUTE_PRESSED), 1.7) == []
    # Outside the window it fires again.
    d.update(_idle(), 1.8)
    assert d.update(read_buttons(MUTE_PRESSED), 2.0) == ["action"]


def test_none_reading_is_ignored():
    d = EdgeDetector(confirm_samples=1, debounce_s=0.0)
    d.update(_idle(), 1.0)
    assert d.update(None, 1.0) == []
    assert d.update(read_buttons(VOL_DOWN_PRESSED), 1.0) == ["volume_down"]


# ---- load_keymap ---------------------------------------------------------

def _write(tmp_path, text):
    p = tmp_path / "satellite1.conf"
    p.write_text(text)
    return str(p)


def test_keymap_defaults_when_no_file(tmp_path):
    km = load_keymap(str(tmp_path / "missing.conf"))
    assert km == {"volume_up": "KEY_VOLUMEUP", "volume_down": "KEY_VOLUMEDOWN", "action": "KEY_MUTE"}


def test_keymap_action_defaults_to_mute():
    # The manufacturer "action" button keeps the speaker-mute function by default.
    assert load_keymap("/nonexistent")["action"] == "KEY_MUTE"


def test_keymap_override_repurposes_a_button(tmp_path):
    cfg = _write(tmp_path, '[buttons]\naction = "KEY_PLAYPAUSE"\n')
    assert load_keymap(cfg)["action"] == "KEY_PLAYPAUSE"
    # Untouched buttons keep their defaults.
    assert load_keymap(cfg)["volume_up"] == "KEY_VOLUMEUP"


def test_keymap_empty_string_disables(tmp_path):
    cfg = _write(tmp_path, '[buttons]\naction = ""\n')
    assert "action" not in load_keymap(cfg)


def test_keymap_unknown_button_ignored(tmp_path):
    cfg = _write(tmp_path, '[buttons]\nnope = "KEY_A"\naction = "KEY_STOP"\n')
    km = load_keymap(cfg)
    assert "nope" not in km
    assert km["action"] == "KEY_STOP"


def test_keymap_bad_toml_falls_back_to_defaults(tmp_path):
    cfg = _write(tmp_path, "this is not = valid = toml [[[")
    assert load_keymap(cfg)["action"] == "KEY_MUTE"
