# sys-packages/satellite1-rpi-setup/Makefile


# ---- High-level config ----------------------------------------------------

PACKAGE_NAME       ?= satellite1-rpi-setup
ACTIVATOR_VERSION  ?= 1.0
ARCH               ?= arm64

# Kernel we want to activate (single source of truth)
KERNEL_RELEASE     ?= 6.12.58-v8-fusb302-v8
KERNEL_PKG         ?= linux-image-$(KERNEL_RELEASE)

# Output dir for the built .deb (inside this package dir)
OUT_DIR            ?= ${PWD}/out
DEB_FILE           := $(PACKAGE_NAME)_$(ACTIVATOR_VERSION)_$(ARCH).deb

# Build staging directory: where we construct the fake filesystem tree
BUILD_DIR          := ${PWD}/build
DEBIAN_DIR         := ${BUILD_DIR}/debian
# Where we store the target kernel version so postinst can read it
TARGET_KERNEL_FILE := ${BUILD_DIR}/target-kernel
TARGET_KERNEL_DST  := /usr/share/$(PACKAGE_NAME)/target-kernel


# Source locations (things you edit by hand)
SRC_DEBIAN_DIR     := $(PWD)/debian
SRC_CONTROL_IN     := $(SRC_DEBIAN_DIR)/control.in
SRC_POSTINST       := $(SRC_DEBIAN_DIR)/postinst.in
SRC_INSTALL_FILE   := $(SRC_DEBIAN_DIR)/install.in

# ---- Docker-related config -----------------------------------------------

DOCKER        ?= docker
PLATFORM      ?= linux/arm64
DOCKER_MAKE   ?= ../../docker/Makefile
DOCKER_IMAGE  ?= satellite1-deb-builder   # must match DEB_IMAGE_NAME in prj/Docker/Makefile

# ---- Phony targets --------------------------------------------------------

.PHONY: all deb deb-local image clean distclean print-config help

all: deb

help:
	@echo "Targets:"
	@echo "  make deb           Build activator .deb package inside Docker"
	@echo "  make deb-local     Build activator .deb package on the host"
	@echo "  make image         Build the shared deb-builder Docker image"
	@echo "  make clean         Remove build/ and out/ directories"
	@echo "  make distclean     Alias for clean"
	@echo "  make print-config  Show current kernel/package configuration"

print-config:
	@echo "PACKAGE_NAME      = $(PACKAGE_NAME)"
	@echo "ACTIVATOR_VERSION = $(ACTIVATOR_VERSION)"
	@echo "ARCH              = $(ARCH)"
	@echo "KERNEL_RELEASE    = $(KERNEL_RELEASE)"
	@echo "KERNEL_PKG        = $(KERNEL_PKG)"
	@echo "OUT_DIR           = $(OUT_DIR)"
	@echo "BUILD_DIR         = $(BUILD_DIR)"
	@echo "PKG_ROOT          = $(PKG_ROOT)"
	@echo "DOCKER_IMAGE      = $(DOCKER_IMAGE)"

# ---- Top-level Docker-aware targets --------------------------------------

# Build via Docker: ensures image exists, then runs deb-local inside container
deb: image $(DEB_FILE) 

# Build the shared deb-builder image (delegated to prj/Docker/Makefile)
image:
	$(MAKE) -C ../../docker deb-image

# ---- Local packaging logic (no Docker here) ------------------------------

# This does the actual dpkg-deb work using the local toolchain
deb-local: $(DEB_FILE)

# Final .deb: build the staged tree, then run dpkg-deb
$(DEB_FILE): $(DEBIAN_DIR)/control $(DEBIAN_DIR)/postinst $(TARGET_KERNEL_FILE) $(DEBIAN_DIR)/$(PACKAGE_NAME).install
	mkdir -p "$(OUT_DIR)"
	echo "*" > "$(OUT_DIR)"/.gitignore
	$(DOCKER) run --rm --platform=$(PLATFORM) \
	  -v "$(BUILD_DIR)":/work/src \
	  -v "$(OUT_DIR)":/out \
	  -w /work/src \
	  $(DOCKER_IMAGE) \
	  bash -lc 'dpkg-buildpackage -b -us -uc && cp ../*.deb /out'
	@echo
	@echo "Built activator package: $(DEB_FILE)"

# Generate DEBIAN/control from template DEBIAN/control.in
$(DEBIAN_DIR)/control: $(SRC_CONTROL_IN) | $(DEBIAN_DIR)
	sed \
	  -e 's/@PACKAGE_NAME@/$(PACKAGE_NAME)/g' \
	  -e 's/@VERSION@/$(ACTIVATOR_VERSION)/g' \
	  -e 's/@ARCH@/$(ARCH)/g' \
	  -e 's/@KERNEL_PKG@/$(KERNEL_PKG)/g' \
	  "$<" > "$@"

# Copy postinst into the build tree and make it executable
$(DEBIAN_DIR)/postinst: $(SRC_POSTINST) | $(DEBIAN_DIR)
	sed \
	  -e 's/@KERNEL_RELEASE@/$(KERNEL_RELEASE)/g' \
	  "$<" > "$@"
	chmod 0755 "$@"

# Write the target kernel version into /usr/share/<pkgname>/target-kernel
$(TARGET_KERNEL_FILE):
	mkdir -p "$(dir $(TARGET_KERNEL_FILE))"
	echo "$(KERNEL_RELEASE)" > "$(TARGET_KERNEL_FILE)"
	
# Copy postinst into the build tree and make it executable
$(DEBIAN_DIR)/$(PACKAGE_NAME).install: $(SRC_INSTALL_FILE) $(TARGET_KERNEL_FILE) | $(DEBIAN_DIR)
	cp "$<" "$@"	
	echo "\ntarget-kernel ${TARGET_KERNEL_DST}" >> "$@"
	echo "debian/.dtbo-build/*.dtbo  /usr/share/$(PACKAGE_NAME)/overlays" >> "$@"

# Ensure DEBIAN dir exists in PKG_ROOT
$(DEBIAN_DIR):
	mkdir -p "$(BUILD_DIR)"
	echo "*" > "$(BUILD_DIR)"/.gitignore
	cp -r "$(SRC_DEBIAN_DIR)" "$(BUILD_DIR)"
	cp -r "dt-overlays" "$(BUILD_DIR)"
	cp -r "etc" "$(BUILD_DIR)"

# ---- Cleaning -------------------------------------------------------------

clean:
	rm -rf "$(BUILD_DIR)" "$(OUT_DIR)"

distclean: clean
	@echo "Nothing extra to distclean."
