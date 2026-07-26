PACKAGE_NAME  ?= satellite1-rpi-sdk
SDK_VERSION   ?= 1.1
ARCH          ?= arm64

DOCKER        ?= docker
PLATFORM      ?= linux/arm64
DOCKER_MAKE   ?= docker/Makefile
DOCKER_IMAGE  ?= satellite1-deb-builder

OUT_DIR       ?= ${PWD}/out
DEB_TARGET    := ${OUT_DIR}/$(PACKAGE_NAME)_$(SDK_VERSION)_$(ARCH).deb

BUILD_DIR     ?= ${PWD}/build/sdk
DEBIAN_DIR    := ${BUILD_DIR}/debian

LOCAL_VENV    ?= ${PWD}/.venv

# --- Metadata ---
PYPROJ_VERSION := $(shell python -m setuptools_scm)
PYPROJ_RELEASE := $(shell python -m setuptools_scm --strip-dev)

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

.PHONY: all shell deb docker-image clean

all: $(DEB_TARGET) build

deb: $(DEB_TARGET)

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
	  -w /work/src \
	  $(DOCKER_IMAGE) \
	  bash -lc ' \
	  	dpkg-buildpackage -b -us -uc && \
		ls -la ../ && \
		cp ../*.deb /out && \
		cp debian/.wheelhouse/satellite1*.whl /out'
	@echo
	@echo "Built package: $(DEB_TARGET)"

$(DEBIAN_DIR):
	@echo "Creating $(BUILD_DIR)"
	mkdir -p "$(BUILD_DIR)"
	echo "*" > "$(BUILD_DIR)/.gitignore"
	cp -r "debian" "$(BUILD_DIR)"
	cp -r "etc" "$(BUILD_DIR)"



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
	rm -rf "$(BUILD_DIR)" "$(DEB_TARGET)"

shell: docker-image
	$(DOCKER) run --rm -it \
		-v "${PWD}":/work \
		-e "EDITOR=/usr/bin/vim" \
		-e "DEBEMAIL=$(GIT_EMAIL)" \
		-e "DEBFULLNAME=$(GIT_NAME)" \
		-e "PRJ_VER=$(PYPROJ_RELEASE)" \
		$(DOCKER_IMAGE) \
		/bin/bash
