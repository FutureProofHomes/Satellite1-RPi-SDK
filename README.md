# Satellite1-RPi

**Raspberry Pi SDK for the Satellite1-HAT**

Components:
- `satellite1-rpi` Python SDK library
- `satellite1-rpi-setup` required pi setup wrapped into a debian package 
- `rpi-kernel-fusb302` custom kernel with fusb302 support
- `image-builder` builds images ready to flash to an sd-card

> Target: Raspberry Pi Zero W2, Raspberry Pi OS (Bookworm)
---

## Table of contents

- [Quick start](#quick-start)
- [RPi - Setup](#rpi---setup)
- [CLI - Usage](#cli---usage) 
- [Development](#development)


---

## Quick start
### Flash Satellite1-SDK-Image
The most convenient way to setup your RPi is to flash the Satellite1-SDK-Image which gives you a Rapsberry Pi OS versions already prepared for the Satellite1-HAT.  

1. Install [Raspberry Pi Imager](https://www.raspberrypi.com/software/)
2. Set `Content Repository` in `APP OPTIONS` to ...
3. Follow wizard

## RPi - Setup
### Kernel with USB-C PD Support
The default Kernel of Raspberry Pi Os doesn't support usb-c power delivery.

`linux-image-6.12.58-fusb302-rpi-v8_2_arm64.deb` contains the Raspberry Pi Os Kernel with these additional settings: 
```
CONFIG_TYPEC=m
CONFIG_TYPEC_TCPM=m
CONFIG_TYPEC_TCPCI=m
CONFIG_TYPEC_FUSB302=m
```
```bash
sudo dpkg -i linux-image-6.12.58-fusb302-rpi-v8_2_arm64.deb
```

### Device Tree Overlays and Modules Setup

```bash
sudo dpkg -i satellite1-rpi-setup_1.0-1_arm64.deb
```
Installs:
- fusb302b overlays (usb-c power delivery)
- satellite1-i2s overlays (audio device)
- etc/alsa/conf.d/50-satellite1.conf (alsa configuration)
- /etc/modules-load.d/i2c.conf (load i2c-dev module on startup)
- config.txt: spi on, i2s on, i2c_arm on, i2c_arm_baudrate 100000
- i2c-sensor: "i2c-sensor,addr=0x38,chip=aht20" 

### Python Satellite1-Rpi SDK 
```bash
sudo dpkg -i satellite1-rpi-sdk_0.1.5_arm64.deb
```
- creates virtual env at /opt/satellite1/venv
- installs satellite1-rpi python lib into that venv
- creates /usr/bin/sat1 link
- installs satellite1-init.service (initilizes the DACs at startup)

## CLI - Usage
The `sat1` command-line tool provides control over all Satellite1 HAT components, including:

- The DAC (audio output)
- The XMOS audio processor
- USB-C Power Delivery status

A typical invocation looks like:

```bash
sat1 [global options] <component> <command> [options...]
```

### Global Usage

```bash
sat1 [-h] [--config CONFIG] [-v] {dac,xmos,pd} ...
```

#### Components

| Component | Description |
|----------|-------------|
| `dac`    | DAC audio controls |
| `xmos`   | XMOS interface and firmware controls |
| `pd`     | Show current USB-C Power Delivery contract |

#### Global Options

| Option | Description |
|--------|-------------|
| `-h`, `--help` | Show help and exit |
| `--config FILE` | Custom TOML config file (default: `/etc/satellite1.conf`) |
| `-v`, `--verbose` | Increase verbosity (`-v`, `-vv`) |

### DAC Controls

```bash
sat1 dac [options] {volume,set-volume,mute,unmute,setup,plugged-in,status} ...
```

#### DAC Commands

| Command | Description |
|---------|-------------|
| `volume`       | Read current volume (0..1) |
| `set-volume`   | Set output volume (0..1) |
| `mute`         | Mute the line-out |
| `unmute`       | Unmute the line-out |
| `setup`        | Initialise the DAC |
| `plugged-in`   | Check whether headphones are plugged in |
| `status`       | Show current DAC state |

#### DAC Selection

```bash
--dac {auto,line-out,speaker}
```

#### Line-Out Overrides

| Option | Description |
|--------|-------------|
| `--line-out-enabled` / `--no-line-out-enabled` | Enable/disable line-out |
| `--line-out-startup-volume <0..1>` | Initial output volume |
| `--line-out-startup-muted` / `--no-line-out-startup-muted` | Mute on startup |
| `--line-out-restore-on-startup` / `--no-line-out-restore-on-startup` | Restore previous state |

#### Speaker Overrides

| Option | Description |
|--------|-------------|
| `--speaker-enabled` / `--no-speaker-enabled` | Enable/disable speaker output |
| `--speaker-startup-volume <0..1>` | Initial speaker volume |
| `--speaker-startup-muted` / `--no-speaker-startup-muted` | Mute on startup |
| `--speaker-restore-on-startup` / `--no-speaker-restore-on-startup` | Restore previous state |
| `--speaker-channel {left,right,dwn_mix}` | Choose audio routing |
| `--speaker-amp-level <int>` | Amplifier gain |

### XMOS Controls

```bash
sat1 xmos {setup,read-firmware,read-status,reset,enable-flashing,disable-flashing,run-spi-test,set-mic-output,flash-firmware}
```

#### XMOS Commands

| Command | Description |
|---------|-------------|
| `setup`             | Initialise SPI & GPIO for XMOS |
| `read-firmware`     | Read XMOS firmware version |
| `read-status`       | Read status register |
| `reset`             | Toggle the XMOS reset pin |
| `enable-flashing`   | Enter XMOS flashing/reset mode |
| `disable-flashing`  | Exit flashing/reset mode |
| `run-spi-test`      | Perform SPI loopback test |
| `set-mic-output`    | Configure I²S microphone output routing |
| `flash-firmware`    | Flash the XMOS factory image |

### Power Delivery Information

```bash
sat1 pd
```

Displays the currently negotiated USB-C Power Delivery contract, including voltage and current.

## Development

