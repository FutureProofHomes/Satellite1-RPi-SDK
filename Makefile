PACKAGE_NAME  ?= satellite1-rpi-sdk
ARCH          ?= arm64
BUILD_KIND    ?= local

# The Debian changelog is the public release authority. Local builds use a
# lower-sorting Debian version without changing the tracked changelog.
PUBLIC_DEB_VERSION := $(shell sed -n '1s/.*(\(.*\)).*/\1/p' debian/changelog)
PUBLIC_PYTHON_VERSION := $(shell printf '%s' '$(PUBLIC_DEB_VERSION)' | sed 's/-[^-]*$$//')
LOCAL_BUILD_ID ?= $(shell date -u +%Y%m%dT%H%M%SZ).g$(shell git rev-parse --short=12 HEAD 2>/dev/null || echo unknown)
LOCAL_PYTHON_BUILD_ID ?= $(shell date -u +%Y%m%d%H%M%S)+g$(shell git rev-parse --short=12 HEAD 2>/dev/null || echo unknown)

ifeq ($(BUILD_KIND),public)
DEB_VERSION := $(PUBLIC_DEB_VERSION)
PYTHON_VERSION := $(PUBLIC_PYTHON_VERSION)
else ifeq ($(BUILD_KIND),local)
DEB_VERSION := $(PUBLIC_DEB_VERSION)~local.$(LOCAL_BUILD_ID)
PYTHON_VERSION := $(PUBLIC_PYTHON_VERSION).dev$(LOCAL_PYTHON_BUILD_ID)
else
$(error BUILD_KIND must be either "local" or "public")
endif

DOCKER        ?= docker
PLATFORM      ?= linux/arm64
DOCKER_MAKE   ?= docker/Makefile
DOCKER_IMAGE  ?= satellite1-deb-builder

OUT_ROOT      ?= ${PWD}/out
OUT_DIR       := ${OUT_ROOT}/$(BUILD_KIND)
DEB_TARGET    := ${OUT_DIR}/$(PACKAGE_NAME)_$(DEB_VERSION)_$(ARCH).deb

BUILD_DIR     ?= ${PWD}/.debian-build/sdk
DEBIAN_DIR    := ${BUILD_DIR}/debian
PACKAGE_INPUTS := Makefile $(shell git ls-files debian etc udev)

LOCAL_VENV    ?= ${PWD}/.venv

# --- Metadata ---
PYPROJ_VERSION = $(shell python -m setuptools_scm)
PYPROJ_RELEASE = $(shell python -m setuptools_scm --strip-dev)

GIT_NAME := $(shell git config user.name)
GIT_EMAIL := $(shell git config user.email)

# --- check for uncomitted changes ---
.PHONY: verify-git-is-clean
verify-git-is-clean:
ifndef ALLOW_DIRTY
	@echo "Checking for uncomitted changes..."
	@if ! git diff --quiet --ignore-submodules --; then \
	  echo "ERROR: Working tree is dirty. Commit or stash changes first."; \
	  echo "       (override with ALLOW_DIRTY=1)"; \
	  exit 1; \
	fi
else
    @echo "Skipping clean-tree check (ALLOW_DIRTY=$(ALLOW_DIRTY))"
endif

.PHONY: print-meta
print-meta:
	@echo "PYPROJ_VERSION=$(PYPROJ_VERSION)"
	@echo "GIT_NAME=$(GIT_NAME)"
	@echo "GIT_EMAIL=$(GIT_EMAIL)"

.PHONY: all shell deb docker-image clean print-config

all: $(DEB_TARGET) build

deb: $(DEB_TARGET)

print-config:
	@echo "BUILD_KIND=$(BUILD_KIND)"
	@echo "PUBLIC_DEB_VERSION=$(PUBLIC_DEB_VERSION)"
	@echo "DEB_VERSION=$(DEB_VERSION)"
	@echo "PYTHON_VERSION=$(PYTHON_VERSION)"

docker-image:
	$(MAKE) -C ./docker deb-image

build: verify-git-is-clean | $(OUT_DIR)
	$(DOCKER) run --rm -it \
		-v "${PWD}":/work \
		-v "${OUT_DIR}":/out \
		$(DOCKER_IMAGE) \
		/usr/bin/python3 -m build --outdir /out

$(OUT_DIR):
	@echo "Creating $(OUT_DIR)"
	mkdir -p "$(OUT_DIR)"
	echo "*" > "$(OUT_DIR)/.gitignore"

# build the wheel file and wrap it into a .deb package
$(DEB_TARGET): docker-image verify-git-is-clean $(DEBIAN_DIR) | $(OUT_DIR)
	mkdir -p "$(OUT_DIR)"
	$(DOCKER) run --rm --platform=$(PLATFORM) \
	  -v "$(BUILD_DIR)":/work/src \
	  -v "$(OUT_DIR)":/out \
	  -v "${PWD}":/project \
	  -e BUILD_KIND="$(BUILD_KIND)" \
	  -e DEB_VERSION="$(DEB_VERSION)" \
	  -e SETUPTOOLS_SCM_PRETEND_VERSION="$(PYTHON_VERSION)" \
	  -w /work/src \
	  $(DOCKER_IMAGE) \
	  bash -lc 'set -e; \
	  if [ "$$BUILD_KIND" = local ]; then \
	    export DEBFULLNAME="Satellite1 local build" DEBEMAIL="local@invalid"; \
	    dch --newversion "$$DEB_VERSION" --force-bad-version --distribution UNRELEASED --force-distribution "Local, non-release build."; \
	  fi; \
	  	dpkg-buildpackage -b -us -uc && \
		ls -la ../ && \
		cp ../$(PACKAGE_NAME)_$${DEB_VERSION}_$(ARCH).deb /out && \
		cp debian/.wheelhouse/satellite1_rpi-*.whl /out'
	@echo
	@echo "Built package: $(DEB_TARGET)"

$(DEBIAN_DIR): $(PACKAGE_INPUTS)
	@echo "Creating $(BUILD_DIR)"
	mkdir -p "$(BUILD_DIR)"
	echo "*" > "$(BUILD_DIR)/.gitignore"
	rm -rf "$(DEBIAN_DIR)" "$(BUILD_DIR)/etc" "$(BUILD_DIR)/udev"
	cp -r "debian" "$(BUILD_DIR)"
	cp -r "etc" "$(BUILD_DIR)"
	cp -r "udev" "$(BUILD_DIR)"



$(LOCAL_VENV):
	python3 -m venv $(LOCAL_VENV)
	$(LOCAL_VENV)/bin/pip install --upgrade pip
	$(LOCAL_VENV)/bin/pip install -e .


.PHONY: kernel-pkg
kernel-pkg: $(OUR_DIR)
	$(MAKE) -C ./sys-packages/rpi-kernel-fusb302 deb OUT_DIR="$(OUT_DIR)"

.PHONY: rpi-setup-deb
rpi-setup-deb: $(OUT_DIR)
	$(MAKE) -C ./sys-packages/satellite1-rpi-setup deb OUT_DIR="$(OUT_DIR)"

clean:
	rm -rf "$(BUILD_DIR)" "${PWD}/out"

shell: docker-image
	$(DOCKER) run --rm -it \
		-v "${PWD}":/work \
		-e "EDITOR=/usr/bin/vim" \
		-e "DEBEMAIL=$(GIT_EMAIL)" \
		-e "DEBFULLNAME=$(GIT_NAME)" \
		-e "PRJ_VER=$(PYPROJ_RELEASE)" \
		$(DOCKER_IMAGE) \
		/bin/bash
