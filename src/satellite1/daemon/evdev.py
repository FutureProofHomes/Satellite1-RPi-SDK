"""Expose the Satellite1 HAT buttons as a Linux evdev input device.

The four HAT buttons are GPIO bits in the XMOS control status register,
read over SPI (see :mod:`satellite1.components.xmos_device_cntrl`). This
daemon polls that register, debounces the reads, and injects standard
key events through ``/dev/uinput`` so any consumer (Home Assistant,
desktop, ``evtest``) sees a normal keyboard-like device — no audio stack
coupling.

The status frame from the alpha XMOS firmware is intermittently garbled,
so reads are validated (``00 <port_a> 00 00`` with the button bits in the
low nibble) and a state must repeat for ``--confirm-samples`` polls before
it is trusted. This mirrors the hardening we needed in the field.

Button -> gpio_port_a bit (idle nibble = 0x07, buttons are active-LOW):
    bit 0 (0x01) "volume_up"   -> KEY_VOLUMEUP
    bit 2 (0x04) "volume_down" -> KEY_VOLUMEDOWN
    bit 1 (0x02) "action"      -> KEY_MUTE  (the manufacturer's "action"
                    button; defaulted to speaker mute — remap in the config)
    bit 3 (0x08) mic mute; owned by the XMOS in hardware (it toggles the
                    red mic LED and cuts the mic), so it is NOT emitted here.

The button -> key-code mapping is configurable: a ``[buttons]`` table in the
TOML config (default ``/etc/satellite1.conf``, override with ``--config``)
overrides the defaults, so the action button can be repurposed without a code
change. Set a button to ``""`` to disable it.

Run as a user with access to ``/dev/uinput`` and the ``spi`` group.
"""

import argparse
import logging
import time
import tomllib
from typing import Dict, List, NamedTuple, Optional

from ..components.xmos_device_cntrl import (
    DeviceCntrlConfig,
    MAIN_SERVICER,
    XMOSDeviceCntrl,
)

log = logging.getLogger("sat1-buttons")

DEFAULT_POLL_S = 0.03       # ~33 Hz
DEFAULT_DEBOUNCE_S = 0.25
DEFAULT_CONFIRM_SAMPLES = 2
DEFAULT_CONFIG_PATH = "/etc/satellite1.conf"
STATUS_REG_LEN = 4
IDLE_NIBBLE = 0x07         # bits 0-2 high (released), bit 3 low


class Button(NamedTuple):
    mask: int          # gpio_port_a bit
    active_high: bool
    key: str           # default evdev ecode name (overridable via config)

    def is_pressed(self, port_a: int) -> bool:
        bit_set = bool(port_a & self.mask)
        return bit_set if self.active_high else not bit_set


# Physical button -> (bit, polarity, default key). Names are the manufacturer's
# button designations; the key is only a default (see load_keymap). Mic (bit 3)
# is intentionally absent: the XMOS handles mic mute in hardware.
BUTTONS: Dict[str, Button] = {
    "volume_up": Button(0x01, False, "KEY_VOLUMEUP"),
    "volume_down": Button(0x04, False, "KEY_VOLUMEDOWN"),
    # The "action" button; defaulted to KEY_MUTE (speaker mute) for satellite use.
    "action": Button(0x02, False, "KEY_MUTE"),
}


def load_keymap(
    path: str = DEFAULT_CONFIG_PATH, buttons: Dict[str, Button] = BUTTONS
) -> Dict[str, str]:
    """Return ``{button_name: key_code}`` — the built-in defaults overridden by
    the ``[buttons]`` table in the TOML config at *path*.

    A button mapped to ``""`` is disabled (dropped). Unknown button names are
    warned about and ignored. A missing or unparseable file leaves the defaults.
    """
    keymap = {name: b.key for name, b in buttons.items()}
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except FileNotFoundError:
        return keymap
    except (OSError, tomllib.TOMLDecodeError) as exc:
        log.warning("button config %s ignored: %s", path, exc)
        return keymap

    overrides = data.get("buttons")
    if isinstance(overrides, dict):
        for name, code in overrides.items():
            if name not in keymap:
                log.warning(
                    "button config: unknown button %r (known: %s)",
                    name,
                    ", ".join(keymap),
                )
                continue
            keymap[name] = str(code)
    return {name: code for name, code in keymap.items() if code}


def decode_port_a(reg: bytes) -> Optional[int]:
    """Return the validated gpio_port_a byte, or None for a garbled read.

    A valid status frame is ``00 <port_a> 00 00`` with the button bits in
    the low nibble. Anything else (shifted/None/garbage frame) is rejected
    so a bad sample can neither invent nor hide a press.
    """
    if reg is None or len(reg) < STATUS_REG_LEN:
        return None
    if reg[0] != 0x00 or reg[2] != 0x00 or reg[3] != 0x00 or (reg[1] & 0xF0):
        return None
    return reg[1]


def read_buttons(port_a: Optional[int]) -> Optional[Dict[str, bool]]:
    """Map a validated port_a byte to a per-button pressed dict, or None."""
    if port_a is None:
        return None
    return {name: btn.is_pressed(port_a) for name, btn in BUTTONS.items()}


class EdgeDetector:
    """Turn a stream of (possibly flaky) button readings into press edges.

    A reading must repeat for ``confirm_samples`` polls before it is
    trusted; a released->pressed transition then fires, gated by an
    all-released reading (so a startup transient cannot fire) and a
    per-button debounce window. Pure and time-injected for testing.
    """

    def __init__(
        self,
        buttons=BUTTONS,
        confirm_samples: int = DEFAULT_CONFIRM_SAMPLES,
        debounce_s: float = DEFAULT_DEBOUNCE_S,
    ):
        self._names = list(buttons)
        self._confirm_samples = confirm_samples
        self._debounce_s = debounce_s
        self._prev: Optional[Dict[str, bool]] = None
        self._candidate: Optional[Dict[str, bool]] = None
        self._candidate_count = 0
        self._seen_idle = False
        self._last_fire = {name: 0.0 for name in self._names}

    def update(self, reading: Optional[Dict[str, bool]], now: float) -> List[str]:
        """Feed one reading; return button names that fired a press."""
        if reading is None:  # garbage/None read — ignore
            return []

        if reading == self._candidate:
            self._candidate_count += 1
        else:
            self._candidate, self._candidate_count = reading, 1
        if self._candidate_count < self._confirm_samples:
            return []

        # 'reading' is now a confirmed, stable state.
        if not any(reading.values()):
            self._seen_idle = True

        fired: List[str] = []
        if self._prev is not None and self._seen_idle:
            for name in self._names:
                if (
                    reading[name]
                    and not self._prev[name]
                    and (now - self._last_fire[name]) > self._debounce_s
                ):
                    self._last_fire[name] = now
                    fired.append(name)
        self._prev = reading
        return fired


class _UInputKeyboard:
    """Thin wrapper around python-evdev's UInput for a set of key codes."""

    def __init__(self, keys: List[str]):
        from evdev import UInput, ecodes  # lazy: only on real hardware

        self._ecodes = ecodes
        self._codes: Dict[str, int] = {}
        for key in dict.fromkeys(keys):  # de-dupe, preserve order
            code = ecodes.ecodes.get(key)
            if code is None:
                log.warning("unknown key code %r — ignoring", key)
                continue
            self._codes[key] = code
        if not self._codes:
            raise ValueError("no valid key codes to register")
        self._ui = UInput(
            {ecodes.EV_KEY: list(self._codes.values())}, name="satellite1-buttons"
        )

    def tap(self, key: str) -> None:
        code = self._codes.get(key)
        if code is None:
            return
        self._ui.write(self._ecodes.EV_KEY, code, 1)  # press
        self._ui.write(self._ecodes.EV_KEY, code, 0)  # release
        self._ui.syn()

    def close(self) -> None:
        self._ui.close()


def _parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--config",
        default=DEFAULT_CONFIG_PATH,
        help="TOML file with a [buttons] table (default: %(default)s)",
    )
    parser.add_argument("--spi-bus", type=int, default=0)
    parser.add_argument("--spi-dev", type=int, default=0)
    parser.add_argument("--spi-speed-hz", type=int, default=8_000_000)
    parser.add_argument("--poll-seconds", type=float, default=DEFAULT_POLL_S)
    parser.add_argument("--debounce-seconds", type=float, default=DEFAULT_DEBOUNCE_S)
    parser.add_argument("--confirm-samples", type=int, default=DEFAULT_CONFIRM_SAMPLES)
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser.parse_args(argv)


def main(argv=None) -> None:
    args = _parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    keymap = load_keymap(args.config)
    keyboard = _UInputKeyboard(list(keymap.values()))
    detector = EdgeDetector(
        confirm_samples=args.confirm_samples,
        debounce_s=args.debounce_seconds,
    )

    cfg = DeviceCntrlConfig(
        bus=args.spi_bus,
        dev=args.spi_dev,
        max_speed_hz=args.spi_speed_hz,
        mode=3,
        bits_per_word=8,
        status_reg_len=STATUS_REG_LEN,
    )
    dc = XMOSDeviceCntrl(cfg)
    dc.open()

    # Warm up so a startup transient never fires.
    for _ in range(15):
        try:
            dc.send_cmd(MAIN_SERVICER.CMD_NO_OP)
        except Exception:  # noqa: BLE001
            pass
        time.sleep(args.poll_seconds)

    log.info(
        "satellite1 button daemon started (%s)",
        ", ".join(f"{n}->{k}" for n, k in keymap.items()),
    )
    try:
        while True:
            try:
                dc.send_cmd(MAIN_SERVICER.CMD_NO_OP)
            except Exception as e:  # noqa: BLE001
                log.warning("SPI read error: %s", e)
                time.sleep(0.2)
                continue

            reading = read_buttons(decode_port_a(bytes(dc.dc_status_register_)))
            for name in detector.update(reading, time.monotonic()):
                key = keymap.get(name)
                if key is None:
                    continue  # button disabled in config
                log.info("button: %s -> %s", name, key)
                keyboard.tap(key)
            time.sleep(args.poll_seconds)
    finally:
        keyboard.close()
        dc.close()


if __name__ == "__main__":
    main()
