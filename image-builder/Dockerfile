# image-builder/Dockerfile
FROM debian:bookworm

ENV DEBIAN_FRONTEND=noninteractive

# pi-gen dependencies (from upstream pi-gen Dockerfile)
RUN apt-get update && apt-get install -y \
    e2fsprogs grep gpg pigz xxd arch-test bmap-tools \
    git vim parted qemu-user-static debootstrap zerofree \
    zip dosfstools libcap2-bin rsync curl xz-utils file sudo \
    ca-certificates coreutils quilt libarchive-tools kmod bc pigz
  # && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /pi-gen

# Clone pi-gen
RUN git clone --depth=1 --branch bookworm-arm64 https://github.com/RPi-Distro/pi-gen.git . 

# Default command: build image
CMD ["bash", "-lc", "./build.sh"]
