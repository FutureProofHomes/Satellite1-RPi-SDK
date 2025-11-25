FROM debian:bookworm

ENV DEBIAN_FRONTEND=noninteractive

# Basic build + kernel deps + deb packaging tools
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y \
    bc \
    bison \
    build-essential \
    flex \
    git \
    libncurses-dev \
    libssl-dev \
    libelf-dev \
    dwarves \
    cpio \
    kmod \
    fakeroot \
    dpkg-dev \
    debhelper \
    rsync \
    lsb-release \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /usr/src

# Clone Raspberry Pi Linux (6.12 branch)
RUN git clone --depth=1 -b rpi-6.12.y https://github.com/raspberrypi/linux.git rpi-linux

WORKDIR /usr/src/rpi-linux

# Add a helper script that will build the kernel + .deb packages
COPY build-rpi-kernel-deb.sh /usr/local/bin/build-rpi-kernel-deb.sh
RUN chmod +x /usr/local/bin/build-rpi-kernel-deb.sh

# Default to an interactive shell so you can run the build script with args
# ENTRYPOINT ["/bin/bash"]
