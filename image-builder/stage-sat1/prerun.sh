#!/bin/bash -e

# This runs before any of the 00-run.sh scripts in this stage.
# It ensures ROOTFS_DIR exists by copying from the previous stage.

if [ ! -d "${ROOTFS_DIR}" ]; then
    echo "[stage-sat1] ROOTFS_DIR not found, copying from previous stage..."
    copy_previous
fi
