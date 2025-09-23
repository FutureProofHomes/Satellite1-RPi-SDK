import types
import builtins
import pytest

# Import the module under test as "mod"
import importlib
import sys


MODULE_NAME = "satellite1.components.xmos_device_cntrl"  # change if your filename differs


def load_module_with_stubbed_spidev():
    # Create a stub spidev module
    spidev_stub = types.SimpleNamespace()

    class SpiDevStub:
        def __init__(self):
            self.opened = False
            self.args = None
            self.max_speed_hz = None
            self.mode = None
            self.bits_per_word = None
            self._queue = []  # push responses here

        def open(self, bus, dev):
            self.opened = True
            self.args = (bus, dev)

        def xfer2(self, tx):
            if self._queue:
                return list(self._queue.pop(0))
            # default echo-ish: return header + zeros
            return [0, 0, 0] + [0] * (len(tx) - 3)

        def close(self):
            self.opened = False

        def queue(self, *responses):
            # push sequences to be returned on next xfer2 calls
            self._queue.extend(responses)

    spidev_stub.SpiDev = SpiDevStub

    # Inject stub into sys.modules BEFORE import
    sys.modules["spidev"] = spidev_stub

    if MODULE_NAME in sys.modules:
        del sys.modules[MODULE_NAME]
    return importlib.import_module(MODULE_NAME), spidev_stub


def test_open_close_sets_spi_and_config():
    mod, spidev_stub = load_module_with_stubbed_spidev()
    dev = mod.XMOSDeviceCntrl(mod.DeviceCntrlConfig(bus=1, dev=2, max_speed_hz=1_000_000, mode=1, bits_per_word=8))
    assert dev._spi is None
    dev.open()
    assert dev._spi is not None
    assert dev._spi.args == (1, 2)
    assert dev._spi.max_speed_hz == 1_000_000
    assert dev._spi.mode == 1
    assert dev._spi.bits_per_word == 8
    dev.close()
    assert dev._spi is None


def test_payload_slice_bug_is_fixed():
    mod, spidev_stub = load_module_with_stubbed_spidev()
    dev = mod.XMOSDeviceCntrl()
    dev.open()
    # Queue a single non-ignored response (not RET_IGNORED_IN_DEVICE)
    dev._spi.queue([0x01, 0x00, 0x00, 0, 0, 0, 0])
    ok, data = dev.transfer(0x10, 0x00, b"\xAA\xBB\xCC", 0)
    assert ok and data is None  # write path
    dev.close()


def test_ignored_then_accepts():
    mod, spidev_stub = load_module_with_stubbed_spidev()
    dev = mod.XMOSDeviceCntrl()
    dev.open()
    # First two rx: ignored, then accepted
    dev._spi.queue(
        [mod.CntrlProto.RET_IGNORED_IN_DEVICE, 0, 0, 0],  # attempt 1
        [mod.CntrlProto.RET_IGNORED_IN_DEVICE, 0, 0, 0],  # attempt 2
        [0x02, 0x00, 0x00, 0],  # accepted
    )
    ok, _ = dev.transfer(0x00, 0x00, b"", 0)
    assert ok is True
    dev.close()


def test_all_ignored_fails():
    mod, spidev_stub = load_module_with_stubbed_spidev()
    dev = mod.XMOSDeviceCntrl()
    dev.open()
    dev._spi.queue(
        [mod.CntrlProto.RET_IGNORED_IN_DEVICE, 0, 0],
        [mod.CntrlProto.RET_IGNORED_IN_DEVICE, 0, 0],
        [mod.CntrlProto.RET_IGNORED_IN_DEVICE, 0, 0],
    )
    ok, data = dev.transfer(0x00, 0x00, b"", 0)
    assert ok is False and data is None
    dev.close()


def test_no_response_header_sums_to_zero_is_failure():
    mod, spidev_stub = load_module_with_stubbed_spidev()
    dev = mod.XMOSDeviceCntrl()
    dev.open()
    dev._spi.queue([0, 0, 0] + [0] * 10)
    ok, data = dev.transfer(0x01, 0x00, b"", 0)
    assert ok is False and data is None
    dev.close()


def test_status_register_update_when_control_resource_id():
    mod, spidev_stub = load_module_with_stubbed_spidev()
    dev = mod.XMOSDeviceCntrl(mod.DeviceCntrlConfig(status_reg_len=4))
    dev.open()
    # CNTRL_RES_ID with some status bytes
    dev._spi.queue([mod.CntrlProto.CNTRL_RES_ID, 0x00, 0x11, 0x22, 0x33, 0x44])
    ok, _ = dev.transfer(0x10, 0x00, b"\x01", 0)
    assert ok
    # Only the first 4 bytes should be captured into status buffer
    assert bytes(dev.dc_status_register_)[:4] == b"\x11\x22\x33\x44"
    dev.close()


def test_read_command_second_phase_returns_payload():
    mod, spidev_stub = load_module_with_stubbed_spidev()
    dev = mod.XMOSDeviceCntrl()
    dev.open()
    # Phase 1 accepted
    dev._spi.queue([0x02, 0x00, 0x00])
    # Phase 2: payload available, data in rx2[1:1+len]
    payload = b"\xDE\xAD\xBE\xEF\x01"
    rx2 = [mod.CntrlProto.RET_PAYLOAD_AVAILABLE] + list(payload) + [0, 0]
    dev._spi.queue(rx2)
    ok, data = dev.transfer(0xF0, 0x58 | mod.CntrlProto.CMD_READ_BIT, None, read_payload_len=len(payload))
    assert ok and data == payload
    dev.close()


def test_command_struct_validation():
    from math import inf
    mod, _ = load_module_with_stubbed_spidev()
    with pytest.raises(ValueError):
        mod.DeviceCntrlCMD(-1, 0, 0)
    with pytest.raises(ValueError):
        mod.DeviceCntrlCMD(0, 256, 0)
    with pytest.raises(ValueError):
        mod.DeviceCntrlCMD(0, 0, mod.MAX_SPI_TRANSFER_LEN)  # too big


def test_status_dataclass_from_bytes():
    mod, _ = load_module_with_stubbed_spidev()
    sr = mod.DeviceCntrlStatusRegister.from_bytes(b"\x01\x02\x03\x04")
    assert (sr.device_status, sr.gpio_port_a, sr.gpio_port_b) == (1, 2, 3)
