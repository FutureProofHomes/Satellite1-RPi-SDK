DOCKER   ?= docker
PLATFORM ?= linux/arm64

# Example image for building deb packages
DEB_IMAGE_NAME   ?= satellite1-deb-builder
DEB_DOCKERFILE   ?= Dockerfile.deb.bookworm.arm64
DEB_BUILD_CTX    ?= $(PWD)

.PHONY: help deb-image

help:
	@echo "Docker Makefile:"
	@echo "  make deb-image    Build deb-builder Docker image"

deb-image: $(DEB_DOCKERFILE)
	$(DOCKER) build --platform=$(PLATFORM) \
	  -f $(DEB_DOCKERFILE) \
	  -t $(DEB_IMAGE_NAME) \
	  $(DEB_BUILD_CTX)

clean-deb-image:
	$(DOCKER) rmi $(DEB_IMAGE_NAME) || true