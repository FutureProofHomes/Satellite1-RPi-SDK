# satellite1-rpi — Python SDK

Python library and CLI tools for controlling the Satellite1 Raspberry Pi HAT.

> **⚠️ Early-stage development:**
> This is early-stage experimental software. No official support is provided yet. 
> For issues and feature requests, open an issue on the GitHub repository: https://github.com/futureproofhomes/Satellite1-RPi/issues

## Overview

The `satellite1-rpi` package provides:

- Python API for interacting with the Satellite1 hardware (DAC, XMOS, USB-C PD)
- Command-line interface (`sat1`) for hardware control
- Systemd service for automatic DAC initialization at boot

## Installation

### Prerequisites

Install the SDK package:

```bash
sudo dpkg -i satellite1-rpi-sdk_0.1.5_arm64.deb
```

This creates:

- Python virtual environment at `/opt/satellite1/venv`
- CLI binaries (`sat1`, `sat1-dac`, `sat1-xmos`) in `/usr/bin/`
- `satellite1-init.service` to initialize DAC at boot

No reboot required.

### 4. Verify installation

Test the CLI:

```bash
sat1 pd                # Show USB-C power contract status
sat1 dac status        # Show DAC status
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

# Build the .deb package (inside Docker)
make deb
```

Output `.deb` and wheel files are placed in the `out/` directory.

### Clean build artifacts

```bash
make clean
```

### Development workflow

Enter an interactive shell inside the build container:

```bash
make shell
```

### Local development (SDK)

```bash
cd satellite1-rpi
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
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
sat1 [-h] [--config CONFIG] [-v] {dac,xmos,pd} ...
```


| Option            | Description                                                |
| ------------------- | ------------------------------------------------------------ |
| `-h`, `--help`    | Show help message                                          |
| `--config FILE`   | Custom TOML configuration (default:`/etc/satellite1.conf`) |
| `-v`, `--verbose` | Increase verbosity                                         |

### Subcommands


| Subcommand | Description                              |
| ------------ | ------------------------------------------ |
| `dac`      | Audio DAC controls (volume, mute, setup) |
| `xmos`     | XMOS firmware and interface management   |
| `pd`       | USB-C Power Delivery status              |

### DAC Commands

```bash
sat1 dac {volume|set-volume|mute|unmute|setup|plugged-in|status} [options]
```


| Command      | Description                         |
| -------------- | ------------------------------------- |
| `volume`     | Read current output volume          |
| `set-volume` | Set volume (0.0 – 1.0)             |
| `mute`       | Mute line-out or speaker            |
| `unmute`     | Unmute output                       |
| `setup`      | Initialize DAC hardware             |
| `plugged-in` | Detect if headphones are plugged in |
| `status`     | Show complete DAC status            |

#### DAC Selection

Use `--dac` to target a specific output:

```bash
sat1 dac volume --dac line-out    # Line-out RCA
sat1 dac volume --dac speaker     # Built-in speaker
sat1 dac volume --dac auto        # Auto-detect (default)
```

#### Line-out Options

```bash
--line-out-enabled / --no-line-out-enabled
--line-out-startup-volume <0..1>
--line-out-startup-muted / --no-line-out-startup-muted
--line-out-restore-on-startup / --no-line-out-restore-on-startup
```

#### Speaker Options

```bash
--speaker-enabled / --no-speaker-enabled
--speaker-startup-volume <0..1>
--speaker-startup-muted / --no-speaker-startup-muted
--speaker-restore-on-startup / --no-speaker-restore-on-startup
--speaker-channel {left,right,dwn_mix}
--speaker-amp-level <int>  # Amplifier gain (0–31)
```

### XMOS Commands

```bash
sat1 xmos {setup|read-firmware|read-status|reset|enable-flashing|disable-flashing|run-spi-test|set-mic-output|flash-firmware}
```


| Command            | Description                       |
| -------------------- | ----------------------------------- |
| `setup`            | Initialize SPI and GPIO pins      |
| `read-firmware`    | Read firmware version string      |
| `read-status`      | Read XMOS status register         |
| `reset`            | Toggle XMOS reset line            |
| `enable-flashing`  | Enter firmware flashing mode      |
| `disable-flashing` | Exit flashing mode                |
| `run-spi-test`     | Perform SPI loopback test         |
| `set-mic-output`   | Configure I²S microphone routing |
| `flash-firmware`   | Flash new XMOS firmware           |

### Power Delivery

```bash
sat1 pd
```

Shows the current USB-C Power Delivery contract: voltage, current, maximum power, and contract type (PD, USB, etc.).

## Configuration

The CLI reads configuration from `/etc/satellite1.conf` by default (TOML format).

Override with:

```bash
sat1 --config /path/to/custom.conf dac volume
```

## Python API

```python
from satellite1 import Sat1Hat

hat = Sat1Hat()
hat.dac.set_volume(0.5)
status = hat.pd.get_status()
```

See the `src/` directory for the full API.

### mmWave presence sensor (LD2410)

The `LD2410` component reads target-presence reports from an HLK-LD2410
24 GHz sensor over the UART. Enable the UART first (the
`satellite1-rpi-setup` package configures `enable_uart=1` and routes the
PL011 UART to the GPIO header):

```python
from satellite1.components.ld2410 import LD2410

with LD2410() as sensor:          # defaults: /dev/serial0 @ 256000 baud
    report = sensor.read()
    if report and report.present:
        print("occupied", report.detection_distance_cm, "cm")
```

`report.present` is true when a moving and/or stationary target is
detected; individual distances/energies are available on the report.

## Systemd Service

The `satellite1-init.service` runs once at boot to initialize the DAC. View logs with:

```bash
sudo journalctl -u satellite1-init -f
```

## License

See the top-level LICENSE file.

## Repository

https://github.com/futureproofhomes/Satellite1-RPi/tree/main/satellite1-rpi
