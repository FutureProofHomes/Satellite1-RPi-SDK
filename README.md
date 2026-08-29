# satellite1-rpi — Python SDK

Python library and CLI tools for controlling the Satellite1 Raspberry Pi HAT.

> **⚠️ Early-stage development:**
> This is early-stage experimental software. No official support is provided yet. 
> For issues and feature requests, open an issue on the GitHub repository: https://github.com/futureproofhomes/Satellite1-RPi/issues

## Overview

The `satellite1-rpi` distribution provides:

- Python SDK for interacting with the Satellite1 hardware (DAC, XMOS, USB-C PD)
- Command-line interface (`sat1`) for hardware control
- `satellite1d` systemd daemon for hardware ownership and startup

## Installation

### Prerequisites

Install the SDK package:

```bash
sudo dpkg -i satellite1-rpi-sdk_<version>_arm64.deb
```

This creates:

- Python virtual environment at `/opt/satellite1/venv`
- CLI binaries (`sat1`, `sat1-dac`, `sat1-speaker`, `sat1-lineout`, and
  `sat1-xmos`) and `satellite1d` in `/usr/bin/`
- `satellite1d.service` to own hardware and initialize DACs when XMOS is ready

No reboot required.

The CLI connects through a group-owned daemon socket. Add an interactive user
to `satellite1`, then log out and back in before using `sat1`:

```bash
sudo usermod -aG satellite1 "$USER"
```

XMOS firmware operations run through the daemon's SPI access and do not need
`sudo`. Firmware images must be readable by the `satellite1d` service user.

### 4. Verify installation

Test the CLI:

```bash
sat1 pd                # Show USB-C power contract status
sat1 dac volume        # Show active DAC volume
sat1 xmos read-firmware  # Show XMOS firmware version
```

## Build Process

The package is built using Docker to ensure a consistent build environment.

### Dependencies

- Docker
- `make`
- Git

### Build steps

```bash
# Build the Docker image (shared Deb-builder)
make docker-image

# Build local .deb and wheel packages (inside Docker)
make deb
```

Local output is placed in `out/local/`. Its Debian version is marked as a
lower-sorting local build and its wheel uses a PEP 440 development version.

Inspect the active package versions with:

```bash
make print-config
```

### Clean build artifacts

```bash
make clean
```

### Development workflow

Enter an interactive shell inside the build container:

```bash
make shell
```

## Versioning

The first entry in `debian/changelog` is the authoritative public release
version and release notes. Debian versions use this format:

```text
<python-version>-<package-revision>
```

Examples:

- `0.2.0-1`: first package release for SDK version `0.2.0`
- `0.2.0-2`: packaging-only correction for SDK version `0.2.0`
- `0.3.0-1`: first package release for SDK version `0.3.0`

The bundled Python wheel always uses the Debian upstream component, so the
wheel in `0.2.0-2` is version `0.2.0`. Increment the Python version for SDK
API or behavior changes, and the package revision for packaging, dependency,
or installation changes.

Local builds do not modify `debian/changelog` and are never releases. They
derive versions such as:

```text
Debian: 0.2.0-1~local.20260827T120000Z.gabcdef123456
Wheel:  0.2.0.dev20260827120000+gabcdef123456
```

The Debian local version sorts below the corresponding public package, while
the wheel version remains valid PEP 440.

## Releases

CI builds local artifacts on pushes to `develop` and manual runs. These are
available as workflow artifacts only: they never create tags or GitHub
releases.

To prepare a public release, manually run **Prepare SDK release** from the
current `develop` tip. The workflow:

- Reads the public version and release notes from `debian/changelog`.
- Builds and validates the public `.deb` and its bundled Python wheel.
- Creates the annotated `v<debian-version>` tag, for example `v0.2.0-1`.
- Creates a draft GitHub Release with both artifacts attached.

Review and edit the draft release before publishing it.

### Public Release Checklist

1. Update `debian/changelog` with the next public version and release notes.
2. Build and inspect the package from a clean tree with `make deb BUILD_KIND=public`.
3. Commit and merge the release changes to `develop`.
4. Run the **Prepare SDK release** workflow from the current `develop` tip.
5. Review the draft GitHub Release and publish it.

### Local development (SDK)

```bash
cd satellite1-rpi
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

For daemon and CLI development, install the development extra:

```bash
pip install -e ".[dev]"
```

### Running tests

```bash
cd satellite1-rpi
pytest
```

### Code style

Format with `black`:

```bash
cd satellite1-rpi
black src/
```

## CLI Usage

The `sat1` command provides unified control over Satellite1 hardware subsystems.

### Global options

```bash
sat1 [-h] [--socket SOCKET] [-v] {dac,xmos,led,pd} ...
```


| Option            | Description                                                |
| ------------------- | ------------------------------------------------------------ |
| `-h`, `--help`    | Show help message                                          |
| `--socket FILE`   | Daemon Unix socket (default: `/run/satellite1/satellite1d.sock`) |
| `-v`, `--verbose` | Increase verbosity                                         |

### Subcommands


| Subcommand | Description                              |
| ------------ | ------------------------------------------ |
| `dac`      | Audio DAC controls (volume, mute, amp level) |
| `xmos`     | XMOS firmware and interface management   |
| `led`      | XMOS LED ring controls                   |
| `pd`       | USB-C Power Delivery status              |

### DAC Commands

```bash
sat1 dac {volume|set-volume|mute|unmute|amp-level|set-amp-level|plugged-in} [options]
```


| Command      | Description                         |
| -------------- | ------------------------------------- |
| `volume`     | Read current output volume          |
| `set-volume` | Set volume (0.0 – 1.0)             |
| `mute`       | Mute line-out or speaker            |
| `unmute`     | Unmute output                       |
| `amp-level` | Read speaker amp level              |
| `set-amp-level` | Set speaker amp level           |
| `plugged-in` | Detect if headphones are plugged in |

#### DAC Selection

Use `--dac` to target a specific output:

```bash
sat1 dac --dac line-out volume    # Line-out RCA
sat1 dac --dac speaker volume     # Built-in speaker
sat1 dac --dac auto volume        # Auto-detect (default)
```

### XMOS Commands

```bash
sat1 xmos {read-firmware|read-status|reset|flash-firmware}
```


| Command            | Description                       |
| -------------------- | ----------------------------------- |
| `read-firmware`    | Read firmware version string      |
| `read-status`      | Read XMOS status register         |
| `reset`            | Toggle XMOS reset line            |
| `flash-firmware`   | Flash new XMOS firmware           |

### Power Delivery

```bash
sat1 pd
```

Shows the current USB-C Power Delivery contract: voltage, current, maximum power, and contract type (PD, USB, etc.).

### LED Ring

The optional XMOS backend drives the complete 24-pixel LED ring. Frames are
accepted into a latest-frame-wins queue, so callers should send complete frames
without waiting for physical transmission.

```bash
sat1 led set-color 0 32 128
sat1 led clear
```

## Configuration

`satellite1d` reads machine configuration from `/etc/satellite1.conf` by default
(TOML format). The CLI sends requests to the daemon socket and does not load
hardware configuration. Missing configuration sections use their model defaults.

Restart the daemon after changing the machine configuration:

```bash
sudo systemctl restart satellite1d
```

Override with:

```bash
satellite1d --config /path/to/custom.conf
```

### GPIO Controller

The direct XMOS reset and action-button lines use `/dev/gpiochip0` by default.
If the Raspberry Pi header GPIO controller has a different path on the target
kernel, configure it explicitly:

```toml
[gpio]
chip = "/dev/gpiochip4"
```

### Buttons

HAT buttons can optionally be exposed as a standard Linux input device. This
is disabled by default: uncomment one or more mappings in
`[buttons.evdev]` to enable it.

```toml
[buttons.evdev]
volume_up = "KEY_VOLUMEUP"
volume_down = "KEY_VOLUMEDOWN"
action = "KEY_MUTE"
mic_mute = "KEY_MICMUTE"
```

Mappings use Linux `KEY_*` names. An empty value disables one button. The
daemon validates mappings at startup and fails clearly on an unknown key name.
It debounces the XMOS status samples and emits button-press events through a
virtual `Satellite1 Buttons` input device. The mic-mute button is still owned
by XMOS firmware; its optional event only reports that physical press.

Use `evtest` to inspect the device after enabling mappings. The daemon needs
no extra process or root privileges: the package grants its `satellite1`
service group access to `/dev/uinput`.

### Volume Buttons

Enable the optional volume-button workflow to adjust the active output by a
fixed step. It selects line-out when a jack is plugged in and speaker otherwise.

```toml
[workflows.volume-buttons]
enabled = true
step = 0.05
led_enabled = true
led_color = [0, 90, 255]
led_muted_color = [255, 0, 0]
led_timeout = 1.5
```

When enabled, each volume-button press temporarily displays a 24-pixel volume
bar. Zero volume displays a red first pixel. The notification suppresses normal
LED frames until `led_timeout` expires, then restores the latest normal frame.

### LED Ring

Enable the XMOS-controlled LED ring:

```toml
[led_ring]
enabled = true
backend = "xmos"
```

The native WS281x backend is not included in this release.

## Python API

The public Python API connects to `satellite1d` through its local Unix socket.
It does not access hardware directly, so applications can safely use it while
the daemon owns the HAT.

```python
from satellite1 import AsyncSatellite1Client

async with AsyncSatellite1Client() as satellite:
    await satellite.dac.set_volume(0.5, dac="speaker")
    contract = await satellite.power.get_contract()
    firmware = await satellite.xmos.get_firmware()
    await satellite.led.render_frame([(0, 32, 128)] * 24)
```

The client provides `health()`, `satellite.power.get_contract()`, DAC controls,
and XMOS firmware, status, reset, and flashing operations. It requires the same
socket access as the `sat1` command: add the application user to the
`satellite1` group.

### Direct hardware access

Direct hardware modules now live under `satellite1_hw`. They are for daemon
development and maintenance only; do not use them while `satellite1d` is
running.

```python
from satellite1_hw.sat1_hat import XMOS
```

This is a breaking import rename: replace existing `satellite1.*` direct
hardware imports with `satellite1_hw.*`.

See the `src/` directory for the full API.

## Systemd Service

The `satellite1d.service` owns hardware and runs continuously. View logs with:

```bash
sudo journalctl -u satellite1d -f
```

## License

See the top-level LICENSE file.

## Repository

https://github.com/futureproofhomes/Satellite1-RPi/tree/main/satellite1-rpi
