PACKAGE_NAME  ?= satellite1-rpi-sdk
SDK_VERSION   ?= 1.0
ARCH          ?= arm64

DOCKER        ?= docker
PLATFORM      ?= linux/arm64
DOCKER_MAKE   ?= docker/Makefile
DOCKER_IMAGE  ?= satellite1-deb-builder

OUT_DIR            ?= ${PWD}/build-assets
DEB_FILE           := ${OUT_DIR}/$(PACKAGE_NAME)_$(SDK_VERSION)_$(ARCH).deb

BUILD_DIR          := ${PWD}/build
DEBIAN_DIR         := ${BUILD_DIR}/debian

LOCAL_VENV ?= ${PWD}/.venv

.PHONY: all docker-image clean

all: $(DEB_FILE)

docker-image:
	$(MAKE) -C ./docker deb-image


# Final .deb: build the staged tree, then run dpkg-deb
$(DEB_FILE): docker-image | $(DEBIAN_DIR)
	mkdir -p "$(OUT_DIR)"
	$(DOCKER) run --rm --platform=$(PLATFORM) \
	  -v "$(BUILD_DIR)":/work/src \
	  -v "$(OUT_DIR)":/out \
	  -v "${PWD}":/project \
	  -w /work/src \
	  $(DOCKER_IMAGE) \
	  bash -lc 'dpkg-buildpackage -b -us -uc && cp ../*.deb /out'
	@echo
	@echo "Built package: $(DEB_FILE)"

$(DEBIAN_DIR):
	@echo "Creating $(BUILD_DIR)"
	mkdir -p "$(BUILD_DIR)"
	echo "*" > "$(BUILD_DIR)/.gitignore"
	cp -r "debian" "$(BUILD_DIR)"
	cp -r "etc" "$(BUILD_DIR)"

$(LOCAL_VENV):
	python3 -m venv $(LOCAL_VENV)
	$(LOCAL_VENV)/bin/pip install --upgrade pip

clean:
	rm -rf "$(BUILD_DIR)" "$(DEB_FILE)"