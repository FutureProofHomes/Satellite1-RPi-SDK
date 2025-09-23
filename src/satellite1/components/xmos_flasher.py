from __future__ import annotations
import subprocess
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Optional GPIO backends: prefer RPi.GPIO, fallback to sysfs if unavailable
try:
    import RPi.GPIO as GPIO  # type: ignore
    _HAVE_RPI_GPIO = True
except Exception:
    _HAVE_RPI_GPIO = False

from satellite1.command_spec import command, arg


@dataclass(slots=True)
class FlashromConfig:
    # flashrom programmer settings
    spi_dev: str = "/dev/spidev0.0"         # linux spidev node
    spispeed_khz: int = 12000               # flashrom expects kHz (e.g. 12000 = 12 MHz)
    chip: str | None = None                 # optional, e.g. "mx25l25635e"

    # routing GPIO (enable “direct SPI to flash” path on the HAT)
    gpio_direct_pin: int | None = None      # BCM pin number; None to skip GPIO handling
    gpio_active_high: bool = True           # True -> set pin HIGH to enable, else LOW
    gpio_settle_ms: int = 50                # delay after toggling, ms

    # running flashrom
    sudo: bool = True
    extra_args: list[str] = field(default_factory=list)  # additional flashrom args


class FlashromError(RuntimeError):
    pass


class Flashrom:
    def __init__(self, cfg: FlashromConfig):
        self.cfg = cfg
        if shutil.which("flashrom") is None:
            raise FlashromError("flashrom not found in PATH. Install the 'flashrom' package.")

    # ---------------- GPIO routing ----------------
    def _gpio_enable_direct(self) -> None:
        if self.cfg.gpio_direct_pin is None:
            return
        if _HAVE_RPI_GPIO:
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self.cfg.gpio_direct_pin, GPIO.OUT, initial=GPIO.LOW if not self.cfg.gpio_active_high else GPIO.HIGH)
            # Ensure exact level
            GPIO.output(self.cfg.gpio_direct_pin, GPIO.HIGH if self.cfg.gpio_active_high else GPIO.LOW)
        else:
            # sysfs fallback (works on Pi OS, though deprecated)
            pin = self.cfg.gpio_direct_pin
            gpio = Path("/sys/class/gpio")
            export = gpio / "export"
            unexport = gpio / "unexport"
            gp = gpio / f"gpio{pin}"
            try:
                if not gp.exists():
                    export.write_text(str(pin))
                (gp / "direction").write_text("out")
                (gp / "value").write_text("1" if self.cfg.gpio_active_high else "0")
            except PermissionError as e:
                raise FlashromError(f"Need root to control /sys/class/gpio (pin {pin}): {e}") from e
        time.sleep(self.cfg.gpio_settle_ms / 1000.0)

    def _gpio_disable_direct(self) -> None:
        if self.cfg.gpio_direct_pin is None:
            return
        if _HAVE_RPI_GPIO:
            try:
                GPIO.output(self.cfg.gpio_direct_pin, GPIO.LOW if self.cfg.gpio_active_high else GPIO.HIGH)
            finally:
                # Be conservative: don’t GPIO.cleanup() globally to avoid disturbing other users
                pass
        else:
            pin = self.cfg.gpio_direct_pin
            gp = Path("/sys/class/gpio") / f"gpio{pin}"
            try:
                if gp.exists():
                    (gp / "value").write_text("0" if self.cfg.gpio_active_high else "1")
            except Exception:
                pass
        time.sleep(self.cfg.gpio_settle_ms / 1000.0)

    # ---------------- flashrom helpers ----------------
    def _prog_arg(self) -> str:
        # linux_spi:dev=/dev/spidev0.0,spispeed=12000
        return f"linux_spi:dev={self.cfg.spi_dev},spispeed={self.cfg.spispeed_khz}"

    def _run(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        cmd = []
        if self.cfg.sudo:
            cmd += ["sudo", "-n"]
        cmd += ["flashrom", "-p", self._prog_arg()]
        if self.cfg.chip:
            cmd += ["-c", self.cfg.chip]
        cmd += list(self.cfg.extra_args)
        cmd += list(args)

        cp = subprocess.run(cmd, text=True, capture_output=True)
        if check and cp.returncode != 0:
            raise FlashromError(f"flashrom failed ({cp.returncode}):\nSTDOUT:\n{cp.stdout}\nSTDERR:\n{cp.stderr}")
        return cp

    # Public operations
    @command(help="Probe SPI flash")
    def probe(self) -> dict[str, Any]:
        """Identify the flash and return output."""
        self._gpio_enable_direct()
        try:
            cp = self._run("-L")  # list supported (quick PATH test)
            cp2 = self._run("-p", self._prog_arg(), "-R", check=False)  # not all builds have -R (probe-only)
            # If -R is unknown, just run a harmless read-ID by doing '-r /dev/null' on tiny size? We'll skip.
            return {"ok": cp2.returncode == 0, "stdout": cp2.stdout, "stderr": cp2.stderr}
        finally:
            self._gpio_disable_direct()

    @command(help="Read flash image")
    @arg("-o", "--out", required=True, help="Output file")
    def read(self, out_file: str | Path) -> Path:
        """Read flash content to file."""
        out = Path(out_file)
        self._gpio_enable_direct()
        try:
            cp = self._run("-r", str(out))
            return out
        finally:
            self._gpio_disable_direct()

    @command(help="Write flash image")
    @arg("-i", "--img", required=True, help="Image file")
    @arg("--verify", default=True, help="Verify image after writing")
    @arg("--backup-to", default=None, help="Backup output file")
    def write(self, image: str | Path, verify: bool = True, backup_before: Path | None = None) -> dict[str, Any]:
        """
        Write image to flash. By default flashrom verifies;
        Optionally read a backup before writing.
        """
        img = Path(image)
        if not img.is_file():
            raise FileNotFoundError(img)

        self._gpio_enable_direct()
        try:
            backup_path: Path | None = None
            if backup_before is not None:
                backup_path = Path(backup_before)
                self._run("-r", str(backup_path))

            args = ["-w", str(img)]
            if not verify:
                args.insert(0, "--noverify")
            cp = self._run(*args, check=True)
            return {"ok": True, "stdout": cp.stdout, "stderr": cp.stderr, "backup": str(backup_path) if backup_path else None}
        finally:
            self._gpio_disable_direct()
