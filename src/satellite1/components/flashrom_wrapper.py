from __future__ import annotations
import os, shlex, shutil, subprocess, logging, re, tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

log = logging.getLogger(__name__)

_DETECT_RE = re.compile(r'^Found .* flash chip "([^"]+)" \((\d+)\s+kB,\s*([^)]+)\)', re.M)
_MULTI_RE = re.compile(r"^Multiple flash chip definitions match the detected chip", re.M)

class FlashromError(RuntimeError):
    def __init__(self, message: str, *, returncode: int | None = None, stdout: str = "", stderr: str = "") -> None:
        super().__init__(message)
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr

@dataclass
class ChipInfo:
    name: str
    size_kb: int
    interface: str

@dataclass
class DetectResult:
    candidates: List[ChipInfo] = field(default_factory=list)
    multiple: bool = False

    @property
    def primary(self) -> Optional[ChipInfo]:
        return self.candidates[0] if self.candidates else None

class Flashrom:
    """
    Thin wrapper for flashrom (Linux SPI).
    """
    def __init__(
        self,
        *,
        programmer: str = "linux_spi",
        dev: str = "/dev/spidev0.0",
        spispeed_khz: int = 1000,
        chip: str | None = None,
        flashrom_bin: str = "flashrom",
        use_sudo: bool | None = None,
        timeout: int = 120,
    ) -> None:
        self.programmer = programmer
        self.dev = dev
        self.spispeed_khz = int(spispeed_khz)
        self.chip = chip
        self.flashrom_bin = flashrom_bin
        self.timeout = timeout
        if use_sudo is None:
            try:
                use_sudo = os.geteuid() != 0
            except Exception:
                use_sudo = True
        self.use_sudo = use_sudo
        if shutil.which(self.flashrom_bin) is None:
            log.warning("flashrom binary '%s' not found on PATH", self.flashrom_bin)

    # ---------- core helpers ----------
    def _prog_arg(self) -> str:
        if self.programmer == "linux_spi":
            return f"linux_spi:dev={self.dev},spispeed={self.spispeed_khz}"
        return self.programmer

    def _base_cmd(self, *, chip_override: str | None = None) -> list[str]:
        cmd: list[str] = []
        if self.use_sudo:
            cmd += ["sudo", "-n"]
        cmd += [self.flashrom_bin, "-p", self._prog_arg()]
        chosen = chip_override or self.chip
        if chosen:
            cmd += ["-c", chosen]
        return cmd

    def _run(self, extra: list[str], *, chip_override: str | None = None) -> subprocess.CompletedProcess[str]:
        cmd = self._base_cmd(chip_override=chip_override) + extra
        log.debug("flashrom cmd: %s", " ".join(shlex.quote(c) for c in cmd))
        try:
            cp = subprocess.run(
                cmd, check=False, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=self.timeout,
            )
        except subprocess.TimeoutExpired as e:
            raise FlashromError(f"flashrom timed out after {self.timeout}s", stdout=e.stdout or "", stderr=e.stderr or "")
        log.debug("flashrom rc=%s\nstdout:\n%s\nstderr:\n%s", cp.returncode, cp.stdout, cp.stderr)
        return cp

    # ---------- detection ----------
    def detect(self, chip: str | None = None) -> DetectResult:
        """Run detection and parse candidate chips. Pass `chip` to force a specific definition for this call."""
        cp = self._run([], chip_override=chip)
        if cp.returncode != 0:
            raise FlashromError("flashrom detect failed", returncode=cp.returncode, stdout=cp.stdout, stderr=cp.stderr)

        candidates: list[ChipInfo] = []
        for m in _DETECT_RE.finditer(cp.stdout + "\n" + cp.stderr):
            name, size_kb, iface = m.group(1, 2, 3)
            candidates.append(ChipInfo(name=name, size_kb=int(size_kb), interface=iface.strip()))
        multiple = _MULTI_RE.search(cp.stdout + "\n" + cp.stderr) is not None
        return DetectResult(candidates=candidates, multiple=multiple)

    def confirm_chip(self, chip: str | None = None) -> bool:
        """Boolean probe when you already know the chip (forces -c)."""
        chosen = chip or self.chip
        if not chosen:
            raise ValueError("No chip specified; pass chip= or set self.chip first.")
        cp = self._run([], chip_override=chosen)
        ok = (cp.returncode == 0)
        if not ok:
            log.warning("Chip confirmation failed for %s (rc=%s)", chosen, cp.returncode)
        return ok

    def ensure_chip(self, chip: str | None = None) -> None:
        """Like confirm_chip(), but raises on failure."""
        chosen = chip or self.chip
        if not chosen:
            raise ValueError("No chip specified; pass chip= or set self.chip first.")
        cp = self._run([], chip_override=chosen)
        if cp.returncode != 0:
            raise FlashromError(
                f"flashrom did not confirm chip '{chosen}'",
                returncode=cp.returncode, stdout=cp.stdout, stderr=cp.stderr
            )

    def get_chip_size_bytes(self, *, chip: str | None = None) -> int:
        """
        Detect and return the first candidate's size in bytes.
        If you already know the exact chip, pass it (or set self.chip) to avoid multi-match issues.
        """
        res = self.detect(chip or self.chip)
        if not res.candidates:
            raise FlashromError("No flash chip detected")
        size_b = res.candidates[0].size_kb * 1024
        log.debug("Detected chip size: %d bytes (%s)", size_b, res.candidates[0].name)
        return size_b

    # ---------- raw operations ----------
    def read(self, out_file: Path | str, *, verify: bool = False, chip: str | None = None) -> Path:
        out_file = Path(out_file)
        cp = self._run(["-r", str(out_file)], chip_override=chip)
        if cp.returncode != 0:
            raise FlashromError("flashrom read failed", returncode=cp.returncode, stdout=cp.stdout, stderr=cp.stderr)
        if verify:
            self._verify_file(out_file, chip=chip)
        return out_file

    def erase(self, *, chip: str | None = None) -> None:
        cp = self._run(["-E"], chip_override=chip)
        if cp.returncode != 0:
            raise FlashromError("flashrom erase failed", returncode=cp.returncode, stdout=cp.stdout, stderr=cp.stderr)

    def write(self, image: Path | str, *, verify: bool = True, chip: str | None = None) -> None:
        image = Path(image)
        cp = self._run(["-w", str(image)] + (["-v"] if verify else []), chip_override=chip)
        if cp.returncode != 0:
            raise FlashromError("flashrom write failed", returncode=cp.returncode, stdout=cp.stdout, stderr=cp.stderr)

    def verify(self, image: Path | str, *, chip: str | None = None) -> None:
        self._verify_file(Path(image), chip=chip)

    def _verify_file(self, image: Path, *, chip: str | None = None) -> None:
        cp = self._run(["-v", str(image)], chip_override=chip)
        if cp.returncode != 0:
            raise FlashromError("flashrom verify failed", returncode=cp.returncode, stdout=cp.stdout, stderr=cp.stderr)

    # ---------- higher-level write for small images ----------
    def write_image(
        self,
        image: Path | str,
        *,
        strategy: str = "pad",                # "pad" or "region"
        verify: bool = True,
        chip: str | None = None,              # override for this call
        chip_size_bytes: int | None = None,   # only needed for "pad" if you don't want detect()
        erase_before: bool = False,           # useful with "region" if you want rest blank
        keep_padded: bool = False,            # keep padded file on disk (pad strategy)
        padded_out: Path | None = None,       # explicit output path for padded file
    ) -> None:
        """
        Write an image smaller than the flash size using one of two strategies:

        - strategy="pad": pad the image with 0xFF to the full chip size, then write/verify.
                          If chip_size_bytes is None, we detect the size (honoring `chip` or self.chip).
        - strategy="region": create a flashrom layout for [0 .. len(image)-1] and write only that region.
                             Verify only that region; optionally erase the whole chip first.

        Raises FlashromError on failure.
        """
        image = Path(image)
        if not image.exists():
            raise FileNotFoundError(image)

        if strategy not in ("pad", "region"):
            raise ValueError("strategy must be 'pad' or 'region'")

        if strategy == "pad":
            size_b = chip_size_bytes or self.get_chip_size_bytes(chip=chip or self.chip)
            img_size = image.stat().st_size
            if img_size > size_b:
                raise ValueError(f"Image ({img_size} B) larger than chip ({size_b} B)")

            # Create padded file (either at padded_out or a temp next to image)
            if padded_out is None:
                padded_out = image.with_suffix(image.suffix + ".padded.bin")
            self._pad_file(image, padded_out, size_b)
            try:
                self.write(padded_out, verify=verify, chip=chip)
            finally:
                if not keep_padded and padded_out and padded_out.exists():
                    try:
                        padded_out.unlink()
                    except Exception:
                        pass
            return

        # strategy == "region"
        img_size = image.stat().st_size
        if img_size == 0:
            raise ValueError("Image size is 0 bytes")
        if erase_before:
            self.erase(chip=chip)

        # Build one-region layout file and write only that region
        start = 0
        end = img_size - 1
        layout_line = f"{start:08x}:{end:08x} factory\n"
        with tempfile.NamedTemporaryFile("w", delete=False, prefix="flashrom_layout_", suffix=".txt") as tf:
            tf.write(layout_line)
            layout_path = Path(tf.name)

        try:
            args = ["-l", str(layout_path), "--include", "factory", "-w", str(image)]
            if verify:
                args.append("-v")
            cp = self._run(args, chip_override=chip)
            if cp.returncode != 0:
                raise FlashromError("flashrom regioned write failed", returncode=cp.returncode, stdout=cp.stdout, stderr=cp.stderr)
        finally:
            try:
                layout_path.unlink(missing_ok=True)  # py3.8+: wrap in try if older
            except Exception:
                pass

    # ---------- convenience ctor ----------
    @classmethod
    def for_rpi_w25q64jv(cls, *, spispeed_khz: int = 1000, dev: str = "/dev/spidev0.0", **kw) -> "Flashrom":
        """Config for Winbond W25Q64JV on Raspberry Pi SPI0/CE0."""
        return cls(dev=dev, spispeed_khz=spispeed_khz, chip="W25Q64JV-.Q", **kw)

    # ---------- small util ----------
    @staticmethod
    def _pad_file(src: Path, dst: Path, size_bytes: int) -> None:
        data = src.read_bytes()
        if len(data) > size_bytes:
            raise ValueError("Source image larger than target size")
        pad = b"\xFF" * (size_bytes - len(data))
        dst.write_bytes(data + pad)
        log.debug("Padded %s (%d B) -> %s (%d B)", src, len(data), dst, size_bytes)
