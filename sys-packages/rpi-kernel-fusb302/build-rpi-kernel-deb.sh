#!/usr/bin/env bash
set -euo pipefail

### --- CONFIG INPUT ------------------------------------------------------
# This script expects:
#  - a kernel config at /config/kernel.config (mounted from host)
#  - an output directory mounted at /out (for .deb files)

KERNEL_TREE="/usr/src/rpi-linux"
CONFIG_IN_CONTAINER="/config/kernel.config"
OUT_DIR="/out"

ARCH="${ARCH:-arm64}"
LOCALVERSION="${LOCALVERSION:--fusb302}"
KDEB_PKGVERSION="${KDEB_PKGVERSION:-1fusb302}"
JOBS="${JOBS:-$(nproc)}"

echo "==> KERNEL_TREE:       $KERNEL_TREE"
echo "==> CONFIG:            $CONFIG_IN_CONTAINER"
echo "==> OUT_DIR:           $OUT_DIR"
echo "==> ARCH:              $ARCH"
echo "==> LOCALVERSION:      $LOCALVERSION"
echo "==> KDEB_PKGVERSION:   $KDEB_PKGVERSION"
echo "==> JOBS:              $JOBS"
echo

if [[ ! -f "$CONFIG_IN_CONTAINER" ]]; then
  echo "ERROR: kernel config '$CONFIG_IN_CONTAINER' not found." >&2
  echo "Mount your config as /config/kernel.config" >&2
  exit 1
fi

if [[ ! -d "$OUT_DIR" ]]; then
  echo "ERROR: output directory '$OUT_DIR' does not exist." >&2
  echo "Mount an output directory as /out" >&2
  exit 1
fi

cd "$KERNEL_TREE"

echo "==> Installing .config..."
cp "$CONFIG_IN_CONTAINER" .config

echo "==> Syncing config (olddefconfig)..."
make ARCH="$ARCH" olddefconfig

echo "==> Building kernel + Debian packages (bindeb-pkg)..."
make -j"$JOBS" \
  ARCH="$ARCH" \
  LOCALVERSION="$LOCALVERSION" \
  KDEB_PKGVERSION="$KDEB_PKGVERSION" \
  bindeb-pkg

echo "==> Copying .deb packages to $OUT_DIR..."
# Debian packages are created in the parent directory of the kernel tree (/usr/src)
cp -v /usr/src/*.deb "$OUT_DIR"/

echo
echo "==> Build complete. Files in /out:"
ls -1 "$OUT_DIR"
