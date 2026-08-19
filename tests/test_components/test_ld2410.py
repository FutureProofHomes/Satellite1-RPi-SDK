import pytest

from satellite1.components.ld2410 import (
    FRAME_HEADER,
    FRAME_TAIL,
    LD2410,
    STATE_BOTH,
    STATE_NONE,
)

# A well-formed normal-mode report frame:
#   data type 0x02, head 0xAA, state 0x03 (both),
#   moving 50cm/energy 42, stationary 60cm/energy 55, detection 61cm,
#   tail marker 0x55, check 0x00.
_DATA = bytes(
    [0x02, 0xAA, 0x03, 0x32, 0x00, 0x2A, 0x3C, 0x00, 0x37, 0x3D, 0x00, 0x55, 0x00]
)
GOOD_FRAME = FRAME_HEADER + len(_DATA).to_bytes(2, "little") + _DATA + FRAME_TAIL


def test_parse_frame_decodes_fields():
    report = LD2410.parse_frame(GOOD_FRAME)
    assert report.target_state == STATE_BOTH
    assert report.moving_distance_cm == 50
    assert report.moving_energy == 42
    assert report.stationary_distance_cm == 60
    assert report.stationary_energy == 55
    assert report.detection_distance_cm == 61
    assert report.present is True


def test_present_false_when_no_target():
    data = bytearray(_DATA)
    data[2] = STATE_NONE
    frame = FRAME_HEADER + len(data).to_bytes(2, "little") + bytes(data) + FRAME_TAIL
    assert LD2410.parse_frame(frame).present is False


def test_parse_frame_rejects_bad_framing():
    with pytest.raises(ValueError):
        LD2410.parse_frame(b"\x00\x00" + GOOD_FRAME[2:])


def test_parse_frame_rejects_bad_data_type():
    data = bytearray(_DATA)
    data[0] = 0x99
    frame = FRAME_HEADER + len(data).to_bytes(2, "little") + bytes(data) + FRAME_TAIL
    with pytest.raises(ValueError):
        LD2410.parse_frame(frame)


def test_extract_frame_resyncs_past_garbage():
    buf = bytearray(b"\x11\x22\x33" + GOOD_FRAME + b"\xaa\xbb")
    frame = LD2410._extract_frame(buf)
    assert frame == GOOD_FRAME
    # Leading garbage and the frame are consumed; trailing bytes remain.
    assert bytes(buf) == b"\xaa\xbb"


def test_extract_frame_waits_for_complete_tail():
    buf = bytearray(GOOD_FRAME[:-1])  # missing last tail byte
    assert LD2410._extract_frame(buf) is None


class _FakeSerial:
    """Minimal pyserial stand-in that yields queued byte chunks."""

    def __init__(self, *chunks):
        self._chunks = list(chunks)

    def read(self, _n):
        return self._chunks.pop(0) if self._chunks else b""

    def close(self):
        pass


def test_read_returns_parsed_report():
    sensor = LD2410()
    # Deliver the frame split across two reads to exercise buffering.
    sensor._ser = _FakeSerial(GOOD_FRAME[:5], GOOD_FRAME[5:])
    report = sensor.read()
    assert report is not None
    assert report.moving_distance_cm == 50


def test_read_returns_none_on_timeout():
    sensor = LD2410()
    sensor._ser = _FakeSerial()  # never yields data
    assert sensor.read(timeout=0.05) is None


def test_read_requires_open_port():
    with pytest.raises(RuntimeError):
        LD2410().read()
