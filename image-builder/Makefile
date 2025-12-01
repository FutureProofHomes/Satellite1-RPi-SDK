DOCKER        ?= docker
IMAGE_NAME    ?= rpi-image-builder
PLATFORM      ?= linux/arm64
DEB_STORE     ?= ../build-assets
PKG_LIST      ?= $(DEB_STORE)/pkg.list

# Build the Docker image with the kernel tree and build script
.PHONY: docker-image
docker-image: Dockerfile
	$(DOCKER) build --platform=$(PLATFORM) -t $(IMAGE_NAME) .

.PHONY: pi-image
pi-image: docker-image
	docker run --privileged --name rpi-img-build\
	  -v "$(CURDIR)/config:/pi-gen/config" \
	  -v "$(CURDIR)/stage-sat1:/pi-gen/stage-sat1" \
	  -v "$(CURDIR)/$(DEB_STORE):/deb-store" \
	  $(IMAGE_NAME) \
	  bash -lc 'touch stage2/SKIP_IMAGES && ./build.sh'
	docker cp rpi-img-build:/pi-gen/deploy ./
	docker rm rpi-img-build
	


.PHONY: shell
shell: docker-image
	mkdir -p deploy
	docker run -it --rm --privileged \
	  -v "$(CURDIR)/deploy:/pi-gen/deploy" \
	  -v "$(CURDIR)/config:/pi-gen/config" \
	  -v "$(CURDIR)/stage-sat1:/pi-gen/stage-sat1"\
	  -v "$(CURDIR)/$(DEB_STORE):/deb-store" \
	  $(IMAGE_NAME) \
	  /bin/bash
