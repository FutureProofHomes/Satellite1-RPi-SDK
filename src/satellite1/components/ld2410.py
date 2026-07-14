"""HLK-LD2410 24 GHz mmWave presence sensor (UART).

The LD2410 streams target-report frames over a serial UART (default
256000 baud). Each report gives the coarse target state (moving /
stationary / both) plus per-category distance and energy values.

The frame parser (:meth:`LD2410.parse_frame`) is pure and dependency
free so it can be unit-tested without hardware; the serial I/O is opened
lazily via ``pyserial`` only when reading from a real device.
"""

import time
from typing import NamedTuple, Optional

# Report frame framing bytes (see LD2410 serial protocol).
FRAME_HEADER = b"\xf4\xf3\xf2\xf1"
FRAME_TAIL = b"\xf8\xf7\xf6\xf5"

# Data-region markers.
DATA_TYPE_NORMAL = 0x02       # basic target mode
DATA_TYPE_ENGINEERING = 0x01  # engineering mode (extra gate energies)
HEAD_MARKER = 0xAA
TAIL_MARKER = 0x55

DEFAULT_PORT = "/dev/serial0"
DEFAULT_BAUDRATE = 256000

# Target-state values reported in byte 2 of the data region.
STATE_NONE = 0x00
STATE_MOVING = 0x01
STATE_STATIONARY = 0x02
STATE_BOTH = 0x03


class LD2410Report(NamedTuple):
    target_state: int
    moving_distance_cm: int
    moving_energy: int
    stationary_distance_cm: int
    stationary_energy: int
    detection_distance_cm: int

    @property
    def present(self) -> bool:
        """True when a moving and/or stationary target is detected."""
        return self.target_state != STATE_NONE


class LD2410:
    def __init__(self, port: str = DEFAULT_PORT, baudrate: int = DEFAULT_BAUDRATE):
        self.port = port
        self.baudrate = baudrate
        self._ser = None

    # ---- serial lifecycle -------------------------------------------------

    def open(self) -> None:
        if self._ser is not None:
            raise RuntimeError("Serial port is already open")
        import serial  # lazy: only needed on real hardware

        self._ser = serial.Serial(self.port, self.baudrate, timeout=1)

    def close(self) -> None:
        if self._ser is not None:
            self._ser.close()
            self._ser = None

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *exc):
        self.close()

    # ---- framing / parsing ------------------------------------------------

    @staticmethod
    def parse_frame(frame: bytes) -> LD2410Report:
        """Parse a complete report frame (header .. tail) into a report.

        Raises ValueError if the framing or markers do not validate.
        """
        if not frame.startswith(FRAME_HEADER) or not frame.endswith(FRAME_TAIL):
            raise ValueError("Frame header/tail mismatch")

        # Data length is a little-endian u16 covering the data region only.
        length = int.from_bytes(frame[4:6], "little")
        data = frame[6:6 + length]
        if len(data) != length:
            raise ValueError(f"Truncated data region: {len(data)} != {length}")

        # Normal mode carries 13 data bytes; engineering mode appends gate
        # energies we do not decode but whose leading fields are identical.
        if data[0] not in (DATA_TYPE_NORMAL, DATA_TYPE_ENGINEERING):
            raise ValueError(f"Unexpected data type 0x{data[0]:02X}")
        if data[1] != HEAD_MARKER:
            raise ValueError("Missing data head marker 0xAA")

        target_state = data[2]
        moving_distance = int.from_bytes(data[3:5], "little")
        moving_energy = data[5]
        stationary_distance = int.from_bytes(data[6:8], "little")
        stationary_energy = data[8]
        detection_distance = int.from_bytes(data[9:11], "little")

        return LD2410Report(
            target_state=target_state,
            moving_distance_cm=moving_distance,
            moving_energy=moving_energy,
            stationary_distance_cm=stationary_distance,
            stationary_energy=stationary_energy,
            detection_distance_cm=detection_distance,
        )

    def read(self, timeout: float = 2.0) -> Optional[LD2410Report]:
        """Read the next valid report frame, or None if none arrives in time."""
        if self._ser is None:
            raise RuntimeError("Serial port is not open")

        deadline = time.monotonic() + timeout
        buf = bytearray()
        while time.monotonic() < deadline:
            chunk = self._ser.read(64)
            if chunk:
                buf += chunk
            frame = self._extract_frame(buf)
            if frame is not None:
                return self.parse_frame(frame)
        return None

    @staticmethod
    def _extract_frame(buf: bytearray) -> Optional[bytes]:
        """Pop and return the first complete frame from *buf*, or None.

        Consumes any leading garbage up to the next header so the stream
        resynchronises after partial reads.
        """
        start = buf.find(FRAME_HEADER)
        if start < 0:
            # No header yet; retain only what might be a partial header.
            if len(buf) > 3:
                del buf[:-3]
            return None
        end = buf.find(FRAME_TAIL, start + len(FRAME_HEADER))
        if end < 0:
            del buf[:start]  # drop garbage before the header, wait for more
            return None
        end += len(FRAME_TAIL)
        frame = bytes(buf[start:end])
        del buf[:end]
        return frame


if __name__ == "__main__":
    with LD2410() as sensor:
        while True:
            report = sensor.read()
            if report is None:
                print("no frame")
                continue
            print(
                f"state={report.target_state} present={report.present} "
                f"moving={report.moving_distance_cm}cm/{report.moving_energy} "
                f"stationary={report.stationary_distance_cm}cm/{report.stationary_energy} "
                f"detection={report.detection_distance_cm}cm"
            )
            time.sleep(0.2)
