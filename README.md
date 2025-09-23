# Satellite1-RPi

Control software for the **Satellite1 Raspberry Pi HAT**, including:

- **Line‑out DAC (PCM5122)**: volume/mute and jack‑sense
- **XMOS controller (SPI)**: detection, basic reset, and flashing helpers (via `flashrom`)
- **Config** via TOML (Pydantic models + CLI overrides)
- **CLIs** (`sat1`, `sat1-line-out`, `sat1-xmos`) with `-v/--verbose`
- A Debian package that ships an **offline wheelhouse** and installs into a dedicated **virtualenv** at `/opt/satellite1/venv`

> Target: Raspberry Pi OS (Bookworm), Python 3.11.


---

## Table of contents

- [Quick start](#quick-start)
- [Configuration](#configuration)
- [CLI usage](#cli-usage)
  - [`sat1-line-out`](#sat1-line-out)
  - [`sat1`](#sat1)
  - [`sat1-xmos`](#sat1-xmos)
- [Service](#service)
- [Build the Debian package](#build-the-debian-package)
- [Install the .deb on the Pi](#install-the-deb-on-the-pi)
- [Development & tests](#development--tests)
- [Troubleshooting](#troubleshooting)
- [License](#license)


---

## Quick start

1. **Enable I2C/SPI** and add your user to device groups (reboot afterwards):

   ```bash
   sudo raspi-config nonint do_i2c 0
   sudo raspi-config nonint do_spi 0
   sudo usermod -aG i2c,spi,gpio $USER
   ```

2. **Install** the prebuilt `.deb` (see [Install the .deb on the Pi](#install-the-deb-on-the-pi)).  
   The post‑install script will:
   - copy an **offline wheelhouse** to `/usr/share/satellite1/wheels/`
   - create `/opt/satellite1/venv` and install from those wheels (offline)
   - install a default config at `/etc/satellite1.conf`
   - install CLI wrappers in `/usr/bin/`
   - install an optional systemd unit (disabled by default)

3. **Try the DAC CLI**:

   ```bash
   sat1-line-out volume           # print current volume (0..1)
   sat1-line-out set-volume 0.75  # set volume
   sat1-line-out mute             # mute
   sat1-line-out unmute           # unmute
   sat1-line-out plugged-in       # jack sensor status
   sat1-line-out -v volume        # verbose logging
   ```

> If the wrapper isn’t present for some reason, you can run via the venv:
>
> `sudo /opt/satellite1/venv/bin/python -m satellite1.cli.cli_line_out_dac volume`


---

## Configuration

Configuration is **TOML**. Default search order:

1. `/etc/satellite1.conf`
2. `/etc/satellite1/satellite1.conf`
3. `~/.config/satellite1/config.toml`

All CLIs accept `--config` to point to a specific file. CLI flags **override** file values at runtime.

**Example: `/etc/satellite1.conf`**

```toml
[line_out_dac]
# Enable the DAC at startup
enabled = true

# Default volume (0.0 .. 1.0)
startup_volume = 0.50

# Start muted?
startup_muted = false
```

- `JACK_SENSOR_PIN` is a `ClassVar` and **not user‑configurable**.
- Example override:

  ```bash
  # Use /etc/satellite1.conf, but override just the startup volume for this run:
  sat1-line-out --config /etc/satellite1.conf --startup-volume 0.9 set-volume 0.3
  ```


---

## CLI usage

### `sat1-line-out`

Line‑out DAC controls.

```
usage: sat1-line-out [-h] [--config PATH] [-v|-vv]
                     [--enabled | --no-enabled]
                     [--startup-volume FLOAT]
                     [--startup-muted | --no-startup-muted]
                     {volume,set-volume,mute,unmute,plugged-in,setup} ...
```

Examples:

```bash
sat1-line-out volume
sat1-line-out set-volume 0.42
sat1-line-out mute
sat1-line-out unmute
sat1-line-out setup   # idempotent hardware init
```

### `sat1`

Aggregates component CLIs and provides a small `init` helper.

```bash
sat1 dac volume
sat1 dac set-volume 0.6
```

- `sat1` forwards `--config` to subcommands and supports `-v/--verbose`.

### `sat1-xmos`

Early XMOS helpers (SPI + flashrom wrapper).

```bash

sat1-xmos -vv flash-firmware satellite1_firmware_fixed_delay.factory.bin
```


---

## Service

The package ships an optional systemd unit `satellite1-init.service` (disabled by default).

```bash
# Enable at boot and start now:
sudo systemctl enable --now satellite1-init.service

# Logs:
journalctl -u satellite1-init.service -e

# Disable:
sudo systemctl disable --now satellite1-init.service
```


---

## Build the Debian package
Cross-build:
```bash
tools\build_deb.sh
```


Build on a Debian/Ubuntu dev machine.

**Prerequisites**

```bash
sudo apt-get update
sudo apt-get install -y \
  build-essential devscripts debhelper-compat dh-python dh-sequence-python3 \
  fakeroot python3-venv python3-pip \
  device-tree-compiler
```

**Build**

From the repo root:

```bash
# Build source + binary without signing
debuild -b -us -uc
# or
dpkg-buildpackage -b -uc -us
```

The build will:
- compile overlays in `overlays/` to `*.dtbo`
- create a **wheelhouse** with **all dependencies** under `debian/.wheelhouse/`
- produce the `.deb` in the parent directory (e.g. `../satellite1-rpi_0.1.1-1_arm64.deb`)


---

## Install the .deb on the Pi

Copy the `.deb` to the Pi and install:

```bash
sudo dpkg -i satellite1-rpi_<version>_arm64.deb
# If dpkg reports missing deps (usually shouldn’t):
# sudo apt-get -f install
```

Post‑install does the following:

- Creates `/opt/satellite1/venv` and installs from `/usr/share/satellite1/wheels/` (**offline**)
- Installs config `/etc/satellite1.conf` (respecting local changes on upgrade)
- Installs `sat1`, `sat1-line-out`, `sat1-xmos` wrappers in `/usr/bin/`
- Installs `satellite1-init.service` (disabled by default)

> You may need a **reboot** after the first install if overlays / boot config were updated.


---

## Development & tests

```bash
# Create a local venv
python3 -m venv .venv
. .venv/bin/activate

# Editable install for dev (if you define extras)
pip install -U pip
pip install -e '.[dev]'   # provides pytest/black if configured

# Run tests
pytest -q
```

Run the CLIs from the working tree (no .deb required):

```bash
python -m satellite1.cli.cli_line_out_dac volume -v
python -m satellite1.cli.cli_sat1 init
```


---

## Troubleshooting

- **Permissions / GPIO mode**
  - We select BCM mode where needed, but your process still must access `/dev/gpiochip*`, `/dev/spidev*`, `/dev/i2c-*`. Ensure your user is in `gpio`, `spi`, and `i2c`, then reboot.
- **SPI/I2C disabled**
  - Enable via `raspi-config` or ensure `/boot/firmware/config.txt` has:
    ```
    dtparam=spi=on
    dtparam=i2c_arm=on
    ```
- **`flashrom` not found**
  - `sudo apt-get install flashrom` and ensure the chip is wired to the Pi SPI bus (usually CS0).
- **Service didn’t appear**
  - `dpkg -L satellite1-rpi | grep systemd`
  - If missing, check build logs; the package expects `dh_installsystemd` to run during build.
- **Verbose logging**
  - All CLIs support `-v` (INFO) and `-vv` (DEBUG).


---

## License

This project is released under the terms specified in `LICENSE`.
