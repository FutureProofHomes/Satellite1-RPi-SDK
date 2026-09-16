# Porting Satellite1 to Pi 5 and other ARM hosts

The Satellite1 HAT is wired for a **Raspberry Pi 40-pin header** (Pi Zero / Pi 3 / Pi 4 / Pi 5 numbering). This document is the work list for:

1. Raspberry Pi 5 (same pinout, different SoC I/O chip).
2. Any other ARM board that **copies that pinout** (Orange Pi Zero 2W, Radxa ZERO 3W, and similar).

Official software today targets Raspberry Pi OS arm64 on **Pi Zero 2 W**. This Python SDK talks to Linux userspace devices. It does not drive I2S PCM; that is ALSA plus a device-tree overlay in `satellite1-rpi-setup` ([FutureProofHomes/Satellite1-RPi](https://github.com/FutureProofHomes/Satellite1-RPi)).

## Hard rule: the 40-pin pinout

If the board does not put the same functions on the same header pins as a Raspberry Pi, **the HAT will not work**. There is no software workaround.

The only alternative is a **wiring jig** that remaps every HAT signal (I2C, SPI, I2S, GPIOs, 3.3 V, 5 V, GND) onto the foreign header. That is hardware, not an SDK port.

“Same form factor” is not enough. A Zero-sized Orange Pi or Radxa still only works if its 40-pin *functions* match the table below (I2C / SPI / I2S usually do; Linux GPIO line numbers and `/dev/spidevB.C` names do not).

## Header map (what the HAT actually uses)

BCM numbers are Raspberry Pi GPIO numbers. On a Pi they are also the `libgpiod` line offsets on the header gpiochip.

| Header pin | BCM | HAT signal | Linux on Raspberry Pi |
| ---: | ---: | --- | --- |
| 3 / 5 | 2 / 3 | I2C-1 SDA / SCL | `/dev/i2c-1` |
| 19 / 21 / 23 / 24 | 10 / 9 / 11 / 8 | SPI0 MOSI / MISO / SCLK / CE0 | `/dev/spidev0.0` |
| 12 / 35 / 38 / 40 | 18 / 19 / 20 / 21 | I2S BCLK / LRCLK / DIN / DOUT | ALSA `hw:Satellite1` |
| 29 | 5 | XMOS reset (output) | gpiochip line 5 |
| 26 | 7 | Action button (input, pull-up) | gpiochip line 7 |
| 11 | 17 | FUSB302 IRQ (level-low) | DT only; not used by this SDK |
| 1 / 17 | — | 3.3 V | — |
| 2 / 4 | — | 5 V | Do not backfeed a Pi 5 / Orange Pi / Radxa USB-C from the HAT |
| 6, 9, 14, 20, 25, 30, 34, 39 | — | GND | — |

I2C addresses on that bus:

| Address | Device | How this SDK talks to it |
| --- | --- | --- |
| `0x4D` | PCM5122 line-out DAC | smbus (`i2c_bus=1`) |
| `0x3F` | TAS2780 speaker amp | smbus (`i2c_bus=1`) |
| `0x29` | LTR303 ambient light | smbus (`i2c_bus=1`) |
| `0x22` | FUSB302 USB-C PD | **not** smbus; sysfs `tcpm-source-psy-1-0022` |
| AHT20 | temp / humidity | kernel `i2c-sensor` overlay → hwmon (`aht10` / `aht20`) |

XMOS SPI: `/dev/spidev0.0`, **mode 3**, **8 MHz**, 8-bit. Flashrom uses the same SPI device for the W25Q64JV.

XMOS I2S: the XMOS is **clock master** at 48 kHz, 32-bit slots, 2 channels. The SoC must be the **clock slave**. PCM never goes through `satellite1d`.

## Who owns what

```
HAT  --I2C-->  kernel i2c-dev     -->  satellite1d (DACs, LTR303)
     --SPI-->  kernel spidev      -->  satellite1d (XMOS control, flashrom)
     --GPIO--> gpiochip           -->  satellite1d (reset, action)
     --IRQ-->  fusb302.ko         -->  sysfs PD  -->  satellite1d (read only)
     --I2S-->  SoC I2S + overlay  -->  ALSA      -->  not this SDK
```

A port is mostly **device tree + kernel config**. The daemon already uses portable Linux APIs (`spidev`, `smbus`, `libgpiod`, sysfs). What is *not* portable is hardcoded Raspberry Pi names: gpiochip index, BCM line offsets, `i2c-1`, `spidev0.0`, and the PD sysfs path.

---

## Raspberry Pi 5

Same pinout. The 40-pin header is on **RP1**, not BCM2711. Three changes.

### 1. GPIO chip (this SDK)

Default `[gpio] chip = /dev/gpiochip0` is correct on Zero 2 / Pi 4. On Pi 5 the header controller is `pinctrl-rp1`. Its `/dev/gpiochipN` index has moved across kernel versions (historically `gpiochip4`, later often `gpiochip0` again).

Hardcoding `gpiochip4` will break again. Resolve the chip by **driver name** `pinctrl-rp1` (and `pinctrl-bcm2711` on Pi 4 / Zero 2). BCM offsets **5** and **7** stay.

Until that lands, set in `/etc/satellite1.conf`:

```toml
[gpio]
chip = "/dev/gpiochipN"   # the pinctrl-rp1 chip; check /sys/class/gpio or gpioinfo
```

### 2. I2S overlay (`satellite1-rpi-setup`, not this repo)

`satellite1-i2s.dts` already lists `brcm,bcm2712` and already makes the Pi the I2S slave. It still binds the CPU DAI to `&i2s`.

On Pi 5, `&i2s` is the **clock producer**. Header pins 12 / 35 / 38 / 40 are `&i2s_clk_consumer` (RP1 I2S1). Leave `&i2s` and the XMOS will clock-fight; ALSA will be silent or noisy.

Change both `sound-dai = <&i2s>` sites and `fragment@2` to `&i2s_clk_consumer`. Keep `simple-audio-card,name = "Satellite1"` so `/etc/alsa/conf.d/50-satellite1.conf` still finds `hw:Satellite1`.

### 3. Kernel (FUSB302)

The custom kernel [FutureProofHomes/RPi-Kernel-Fusb302](https://github.com/FutureProofHomes/RPi-Kernel-Fusb302) is **config + packaging only**. It enables:

```
CONFIG_TYPEC=m
CONFIG_TYPEC_TCPM=m
CONFIG_TYPEC_TCPCI=m
CONFIG_TYPEC_FUSB302=m
```

Every published branch is **`rpi-v8`**: 4K pages, `kernel8.img`. That boots Zero 2 / Pi 4. **It does not boot a Pi 5.** Pi 5 wants `linux-image-rpi-2712` / `kernel_2712.img` (16K pages). `PINCTRL_RP1=y` in the v8 `.config` does not make a 2712 Image.

Do **not** install `linux-image-*-fusb302-*-rpi-v8` on a Pi 5.

Options:

- Wait for stock `linux-image-rpi-2712` ≥ **6.18.42** (Raspberry Pi Linux includes FUSB302 from that version; Trixie `rpi-v8` will drop the custom package once validated).
- Or add a **2712** packaging flavor of `RPi-Kernel-Fusb302` (same TYPEC modules, 16K pages, `kernel_2712.img`).

`fusb302b.dts` (`i2c1` `0x22`, IRQ GPIO 17) can stay; I2C-1 and GPIO 17 are still those header pins on RP1.

### Pi 5 also

- Enable `dtparam=i2c_arm=on` and `dtparam=spi=on`.
- Bench SPI0 mode 3 at 8 MHz (`sat1 xmos read-firmware`).
- Power the **Pi** from the Pi USB-C PSU. The HAT FUSB302 is a second PD controller. Do not backfeed 5 V onto the 40-pin to run a Pi 5.

SPI / I2C userspace in this SDK does not use `libbcm2835` MMIO, so RP1 does not require a rewrite of those paths.

**Effort:** on the order of days, once a Pi 5 is on the bench. Overlay + gpiochip detection + kernel choice.

---

## Orange Pi Zero 2W (4 GB) and Radxa Zero

These are the boards this port is aimed at: Raspberry Pi Zero 2 W **size**, 40-pin header in the same place, not Broadcom silicon. The HAT will plug in. Raspberry Pi overlays and this SDK’s default `gpiochip0` / BCM 5 / 7 / `spidev0.0` will not.

The closest Radxa sibling is **ZERO 3W** (RK3566). Original **Radxa Zero** / **Zero 2** (Amlogic) are the same class of work with different device trees. Confirm the silkscreen before writing overlays.

Power both from their own USB-C. Do not run them from HAT 5 V unless you have measured the budget and the PMIC allows it.

### Orange Pi Zero 2W (Allwinner H618)

Header I2C and SPI *land* on the Pi pins. Linux names do not.

| HAT need | Header pins | Orange Pi reality |
| --- | --- | --- |
| I2C | 3 / 5 | TWI/I2C1 (`PI8` / `PI7`). Adapter number is often **not** `i2c-1`. |
| SPI to XMOS | 19 / 21 / 23 / 24 | **SPI1** (`PH7` / `PH8` / `PH6` / `PH5` CS0). Creates `/dev/spidev1.0` if CS0 is muxed. |
| Onboard SPI flash | (not on header) | **SPI0** / `/dev/spidev0.0` is the 16 MB NOR. **Do not point this SDK at it.** |
| Action button | 26 | `PH9`, also SPI1 CS1. Keep it GPIO; do not enable a CS1 overlay. |
| XMOS reset | 29 | `PI0`. Also I2S0 **MCLK** in vendor overlays. Must stay GPIO. |
| FUSB302 IRQ | 11 | `PH2`. |
| I2S | 12 / 35 / 38 / 40 | I2S0 `PI1` BCLK, `PI2` LRCLK, `PI4` DIN, `PI3` DOUT. |

All header GPIOs sit on **`gpiochip1`** (`300b000.pinctrl`), not `gpiochip0`. Line offsets are sunxi numbers, for example reset `PI0` ≈ line **256**, action `PH9` ≈ line **233** ([orangepi-whisplay pin map](https://github.com/turfptax/orangepi-whisplay)). BCM 5 and 7 are wrong.

I2S overlay must mux **only** PI1/PI2/PI3/PI4. Vendor PCM5122 overlays often mux **PI0 as MCLK** as well, which steals the XMOS reset pin. XMOS is clock master; the H618 must be I2S **slave** and does not need to drive MCLK. Allwinner I2S slave is the likely long pole (people usually run the SoC as master into a PCM5122).

SPI: enable **SPI1 CS0** (pin 24), mode 3, 8 MHz, and teach the SDK `bus=1,dev=0`. Default Armbian `spidev1` overlays have been CS1-only.

### Radxa ZERO 3W (Rockchip RK3566)

Power / GND / I2C / SPI / I2S **positions** match a Pi. Alternate functions are Rockchip names.

| HAT need | Header pins | ZERO 3W reality |
| --- | --- | --- |
| I2C | 3 / 5 | `I2C3` (not necessarily `/dev/i2c-1`). |
| SPI to XMOS | 19 / 21 / 23 / 24 | `SPI3_*_M1`. Linux will be something like `/dev/spidev3.0`, **not** `spidev0.0`. |
| Action button | 26 | `GPIO4_D1` / `SPI3_CS1`. GPIO, not CS1. |
| XMOS reset | 29 | `GPIO3_B3` / `I2C5_SCL`. GPIO. MCLK is **not** on this pin. |
| FUSB302 IRQ | 11 | `GPIO3_A1`. |
| I2S | 12 / 35 / 38 / 40 | `I2S3_SCLK_M0` / `LRCK_M0` / `SDI_M0` / `SDO_M0`. |

MCLK lives on pin **13** (`I2S3_MCLK_M0`), so reset on pin 29 does not collide with I2S the way it does on the Orange Pi. Pin 24 is also `I2S3_SDI_M1` — pinmux must pick **SPI CS0**, not that I2S alt.

Rockchip I2S-as-slave is generally less cursed than Allwinner. SPI mode 3 and overlay bugs (clock reported on the wrong pin on some images) still need a scope or `sat1 xmos` before you trust it.

GPIO line offsets are Rockchip bank numbers on the header gpiochip, not BCM 5 / 7.

### What to change in this SDK for these two

| Today (Pi) | Orange Pi Zero 2W | Radxa ZERO 3W |
| --- | --- | --- |
| `gpiochip0` lines 5, 7 | `gpiochip1` lines for `PI0`, `PH9` | header gpiochip lines for pin 29 / 26 |
| `i2c_bus=1` | whichever adapter is pins 3/5 | whichever adapter is pins 3/5 |
| `spidev0.0` | **`spidev1.0`** (never `0.0`) | `spidev3.0` (confirm with `ls /dev/spidev*`) |
| `tcpm-source-psy-1-0022` | `tcpm-source-psy-<adapter>-0022` | same |

Until those are configurable, a board-local `/etc/satellite1.conf` plus a small pin table is enough. Device tree still has to exist first.

---

## Other ARM boards (same pinout)

Assume the board **copied the Raspberry Pi 40-pin functions**. If it did not, stop (or build a jig).

This is a **board bring-up**, not a Pi overlay tweak. Raspberry Pi OS, `dtoverlay=`, BCM line offsets, `raspi-firmware`, and `linux-image-*-rpi-v8` do not apply. Distro is whatever that SoC runs (Armbian, Orange Pi OS, Radxa OS, mainline).

Orange Pi Zero 2W vs Radxa ZERO 3W vs an older Radxa Zero does not change the *kind* of work. Different SoC → different DT. The Orange Pi’s SPI0-is-flash trap and pin-29 MCLK trap are H618-specific.

### 1. Device tree (the real job)

You need a board DT or overlay that, on the **header-equivalent** pins:

| Bind | Compatible / notes |
| --- | --- |
| Header I2C | Status okay. PCM5122 / TAS2780 / LTR303 need no extra nodes for this SDK (it uses `/dev/i2c-N`). AHT20 needs `compatible = "aosong,aht20"` (or the `i2c-sensor` equivalent) so hwmon appears. |
| FUSB302 | `compatible = "fcs,fusb302"`, `reg = <0x22>`, IRQ on **header pin 11**, level-low. Connector node as sink. Same shape as `fusb302b.dts`, different interrupt-parent. |
| Header SPI | Master, CS0 on pin 24, **SPI mode 3** for the XMOS slave. Creates `/dev/spidevB.C`. |
| Header I2S / PCM | SoC is **bitclock and frame slave**. 2 slots × 32 bits, 48 kHz. `simple-audio-card` (or equivalent) with card name `Satellite1` keeps ALSA conf. |
| GPIO | Reset = header pin 29, output. Action = header pin 26, input pull-up. |

Copying `satellite1-i2s.dts` / `fusb302b.dts` and only changing `compatible = "brcm,bcm2712"` **will not work**. Those targets (`&i2s`, `&i2c1`, `&gpio`) are Raspberry Pi DT node names.

### 2. Kernel config

Enable and load:

- I2C, SPI, GPIO, and the SoC I2S/PCM controller (often DesignWare or Allwinner I2S).
- `CONFIG_TYPEC`, `CONFIG_TYPEC_TCPM`, `CONFIG_TYPEC_TCPCI`, `CONFIG_TYPEC_FUSB302`.
- `CONFIG_SND_SIMPLE_CARD` (or whatever the overlay uses).
- AHT20 hwmon driver.

The FUSB302 **driver** is mainline. The custom RPi kernel repo is only a Raspberry Pi `.config` + `.deb` wrapper. It is the wrong tree for Allwinner / Rockchip / etc.

### 3. GPIO line numbers (this SDK will be wrong as-is)

On Raspberry Pi, gpiochip line **5** is BCM 5 (header pin 29). That is a Pi convention.

On Allwinner / Rockchip, line offsets are **SoC pin numbers**. On Orange Pi Zero 2W, header pin 29 is `PI0` (line ~256), not line 5. `[gpio] chip = /dev/gpiochip0` plus hardcoded BCM 5 / 7 will wiggle the wrong pins.

For a proper port, map **functions** (xmos-reset, action-button) to gpiochip + line, by pin name or a board table — not BCM numbers. Today those pins are constants in `sat1_hat.py` (`XMOS_RESET_BCM_PIN = 5`, `ACTION_BUTTON_BCM_PIN = 7`).

### 4. I2C / SPI / PD names

This SDK currently assumes:

| Assumption | Where |
| --- | --- |
| I2C adapter **1** | DACs, LTR303 |
| `spidev0.0` | XMOS, flashrom |
| `/sys/class/power_supply/tcpm-source-psy-1-0022/` | PD (`1-0022` = i2c-1 addr 0x22) |

If the header I2C comes up as `/dev/i2c-0`, DACs and PD both miss. Either force that adapter to number 1 in DT, or make bus / spidev / PD path configurable.

AHT20 lookup by hwmon name is already portable.

### 5. Things that blow the estimate

- SoC I2S **slave** mode (Allwinner has a history of this being painful).
- SPI **mode 3** on the SoC controller.
- FUSB302 IRQ pinmux + `fusb302.ko` actually creating the power-supply class.
- 5 V / PD: power the SBC from its own USB-C; treat HAT USB-C as HAT-only unless you have a proven power tree.

**Effort:** on the order of **1–3 weeks** of DT/kernel bring-up if I2S slave and SPI mode 3 work, longer if they do not. The Python daemon is the small part.

---

## SDK changes worth doing once (Pi 5 + other ARM)

None of this replaces device tree. It stops the daemon assuming it is always a Pi 4.

| Change | Why |
| --- | --- |
| Resolve gpiochip by pinctrl / gpiochip **label**, not index | Pi 5 index drift |
| Configurable reset / action **line offsets** (or pin names) | Non-Pi gpio numbering |
| Configurable I2C adapter, SPI `bus.cs`, PD sysfs path | Adapter numbers differ |
| Document that I2S is overlay/ALSA, not `satellite1d` | Ports keep looking in this repo |

Do not add a `libbcm2835` path. Do not ship the v8 FUSB302 kernel on non-Pi or Pi 5 boards.

## Bring-up checklist

On the target, after DT/kernel are in:

1. Header I2C: `i2cdetect` shows `0x22`, `0x29`, `0x3F`, `0x4D`.
2. `gpioinfo` on the header chip: pin 29 can reset XMOS; pin 26 reads the button.
3. `sat1 xmos read-firmware` over SPI mode 3.
4. `sat1 pd` if FUSB302 bound (`tcpm-source-psy-*-0022`).
5. `sat1 environment` if AHT20 hwmon + LTR303 are up.
6. `arecord` / `aplay` on `hw:Satellite1` at 48 kHz S32_LE — **this is the hard I2S test**.
7. Confirm the SBC is not powered only by HAT 5 V unless that is a designed, safe path.

Until step 6 works, beamforming / capture / Echo-style LEDs that depend on mics will not work, even if LEDs over SPI do.
