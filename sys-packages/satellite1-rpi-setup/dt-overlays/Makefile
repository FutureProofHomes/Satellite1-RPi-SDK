# Simple Makefile for Raspberry Pi DT overlays
# --------------------------------------------
# Usage:
#   make               # build .dtbo(s) into ./build
#   sudo make install  # copy .dtbo(s) to /boot/*/overlays
#   sudo make enable   # add dtparams + dtoverlay lines to config.txt
#   make clean         # remove ./build
#
# Change this to your overlay basename(s) (without extension):
OVERLAYS := satellite1-i2s fusb302b

SRC_DIR   := .
BUILD_DIR := build

DTC      ?= dtc
# -@ adds symbols; -H epapr is the header used by Pi firmware.
# The warning suppress is optional (quietens "unit_address_vs_reg" noise).
DTCFLAGS ?= -@ -H epapr -Wno-unit_address_vs_reg

DTSS  := $(addprefix $(SRC_DIR)/,$(addsuffix .dts,$(OVERLAYS)))
DTBOS := $(addprefix $(BUILD_DIR)/,$(addsuffix .dtbo,$(OVERLAYS)))

# Detect Raspberry Pi paths
OVERLAY_DIR := $(shell if [ -d /boot/firmware/overlays ]; then echo /boot/firmware/overlays; else echo /boot/overlays; fi)
CONFIG_TXT  := $(shell if [ -f /boot/firmware/config.txt ]; then echo /boot/firmware/config.txt; else echo /boot/config.txt; fi)

SUDO ?= sudo

.PHONY: all install uninstall enable clean help
all: $(DTBOS)

$(BUILD_DIR):
	@mkdir -p "$(BUILD_DIR)"

# Build build/foo.dtbo from src/foo.dts
$(BUILD_DIR)/%.dtbo: $(SRC_DIR)/%.dts | $(BUILD_DIR)
	@echo "[BUILD] $< -> $@"
	@command -v $(DTC) >/dev/null || { echo "ERROR: 'dtc' not found. Install 'device-tree-compiler'." >&2; exit 1; }
	$(DTC) $(DTCFLAGS) -O dtb -o "$@" "$<"

install: all
	@echo "[INSTALL] -> $(OVERLAY_DIR)"
	$(SUDO) install -D -m 0644 $(DTBOS) -t "$(OVERLAY_DIR)"

uninstall:
	@echo "[UNINSTALL] from $(OVERLAY_DIR)"
	-$(SUDO) rm -f $(addprefix "$(OVERLAY_DIR)/",$(addsuffix .dtbo,$(OVERLAYS)))

enable:
	@echo "[ENABLE] Updating $(CONFIG_TXT)"
	# Ensure I2S + SPI dtparams exist
	@grep -q '^dtparam=i2s=on$$' "$(CONFIG_TXT)" || echo 'dtparam=i2s=on' | $(SUDO) tee -a "$(CONFIG_TXT)" >/dev/null
	@grep -q '^dtparam=spi=on$$' "$(CONFIG_TXT)" || echo 'dtparam=spi=on' | $(SUDO) tee -a "$(CONFIG_TXT)" >/dev/null
	# Disable legacy analog audio (optional but avoids card conflicts)
	@$(SUDO) sed -i 's/^[[:space:]]*dtparam=audio=on[[:space:]]*$$/#dtparam=audio=on/' "$(CONFIG_TXT)" || true
	# Add dtoverlay lines for each overlay
	@for o in $(OVERLAYS); do \
	  grep -q "^dtoverlay=$$o$$" "$(CONFIG_TXT)" || echo "dtoverlay=$$o" | $(SUDO) tee -a "$(CONFIG_TXT)" >/dev/null; \
	done
	@echo "[ENABLE] Done. Reboot to apply: sudo reboot"

verify:
	@echo "[VERIFY] Checking overlay status..."
	@if [ -f "$(OVERLAY_DIR)/$(firstword $(OVERLAYS)).dtbo" ]; then \
		echo "✓ Overlay file found: $(OVERLAY_DIR)/$(firstword $(OVERLAYS)).dtbo"; \
	else \
		echo "✗ Overlay file missing: $(OVERLAY_DIR)/$(firstword $(OVERLAYS)).dtbo"; \
		exit 1; \
	fi
	@for o in $(OVERLAYS); do \
		if grep -q "^dtoverlay=$$o$$" "$(CONFIG_TXT)"; then \
			echo "✓ dtoverlay=$$o found in $(CONFIG_TXT)"; \
		else \
			echo "✗ dtoverlay=$$o NOT found in $(CONFIG_TXT)"; \
		fi; \
	done
	@echo "[VERIFY] Done."

clean:
	@echo "[CLEAN] Removing $(BUILD_DIR)"
	@rm -rf "$(BUILD_DIR)"

help:
	@echo "Targets: all (build), install, uninstall, enable, clean"
	@echo "Vars: OVERLAYS, SRC_DIR, BUILD_DIR, DTC, DTCFLAGS, SUDO"

