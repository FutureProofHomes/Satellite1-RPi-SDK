# Makefile for building Raspberry Pi kernel .deb packages via Docker

# ----- Configuration -------------------------------------------------------

DOCKER        ?= docker
IMAGE_NAME    ?= rpi-kernel-builder
PLATFORM      ?= linux/arm64

# Path to kernel config on the host (override with: make deb CONFIG=/path/to/config)
CONFIG        ?= $(PWD)/config/kernel.config

# Where to put the resulting .deb files
OUT_DIR       ?= $(PWD)/out

# Extra env you might want to pass into the build script
# e.g.: make deb LOCALVERSION=-fusb302 KDEB_PKGVERSION=2fusb302
LOCALVERSION  ?= -fusb302-v8
KDEB_PKGVERSION ?= 1fusb302
EXTRAVERSION ?= -v8
# ----- Targets -------------------------------------------------------------

.PHONY: help image deb shell clean-out clean-all

help:
	@echo "Targets:"
	@echo "  make deb           Build kernel .deb packages using Docker"
	@echo "  make image         Build the Docker image only"
	@echo "  make shell         Open an interactive shell inside the build container"
	@echo "  make clean-out     Remove ./out (deb output directory)"
	@echo "  make clean-all     Remove ./out and the Docker image"
	@echo ""
	@echo "Variables (override like: make deb CONFIG=/path/to/config):"
	@echo "  CONFIG=$(CONFIG)"
	@echo "  OUT_DIR=$(OUT_DIR)"
	@echo "  IMAGE_NAME=$(IMAGE_NAME)"
	@echo "  PLATFORM=$(PLATFORM)"
	@echo "  LOCALVERSION=$(LOCALVERSION)"
	@echo "  KDEB_PKGVERSION=$(KDEB_PKGVERSION)"

# Build the Docker image with the kernel tree and build script
image: Dockerfile build-rpi-kernel-deb.sh
	$(DOCKER) build --platform=$(PLATFORM) -t $(IMAGE_NAME) .

# Main target: build .deb packages via Docker
deb: image
	@if [ ! -f "$(CONFIG)" ]; then \
		echo "ERROR: CONFIG file not found: $(CONFIG)"; \
		echo "       Set CONFIG=... or place kernel.config in ./config"; \
		exit 1; \
	fi
	mkdir -p "$(OUT_DIR)"
	echo "*" > "$(OUT_DIR)"/.gitignore
	$(DOCKER) run --rm --platform=$(PLATFORM) \
		-e LOCALVERSION="$(LOCALVERSION)" \
		-e EXTRAVERSION="$(EXTRAVERSION)" \
		-e KDEB_PKGVERSION="$(KDEB_PKGVERSION)" \
		-v "$(dir $(CONFIG))":/config:ro \
		-v "$(OUT_DIR)":/out \
		$(IMAGE_NAME) \
		/usr/local/bin/build-rpi-kernel-deb.sh

# Drop into a shell inside the build container (for debugging / manual makes)
shell: image
	$(DOCKER) run --rm -it \
		-e LOCALVERSION="$(LOCALVERSION)" \
		-e KDEB_PKGVERSION="$(KDEB_PKGVERSION)" \
		-v "$(dir $(CONFIG))":/config:ro \
		-v "$(OUT_DIR)":/out \
		$(IMAGE_NAME) \
		/bin/bash

clean-out:
	rm -rf "$(OUT_DIR)"

clean-all: clean-out
	-$(DOCKER) rmi $(IMAGE_NAME) || true
