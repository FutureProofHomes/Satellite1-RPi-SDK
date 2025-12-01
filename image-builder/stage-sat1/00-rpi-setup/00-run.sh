#!/bin/bash -e

echo "Installing custom .deb packages into target rootfs..."

TARGET_TMP="/var/tmp/sat1-debs"
PKG_LIST_HOST="/deb-store/package.list"
PKG_LIST_TARGET="${TARGET_TMP}/package.list"

# Sanity check
if [ ! -f "${PKG_LIST_HOST}" ]; then
    echo "ERROR: ${PKG_LIST_HOST} not found" >&2
    exit 1
fi

# Host side: copy debs listed in package.list into target rootfs
mkdir -p "${ROOTFS_DIR}${TARGET_TMP}"

# Copy package.list itself into the target
install -v -m 644 "${PKG_LIST_HOST}" "${ROOTFS_DIR}${PKG_LIST_TARGET}"

# Copy only the .deb files listed in package.list
while IFS= read -r debfile; do
    # skip empty lines and comments
    case "${debfile}" in
        ""|\#*) continue ;;
    esac

    if [ ! -f "/deb-store/${debfile}" ]; then
        echo "WARNING: /deb-store/${debfile} not found, skipping" >&2
        continue
    fi

    install -v -m 644 "/deb-store/${debfile}" "${ROOTFS_DIR}${TARGET_TMP}/"
done < "${PKG_LIST_HOST}"

# Now install inside chroot
on_chroot << EOF
set -e

TARGET_TMP="/var/tmp/sat1-debs"
PKG_LIST="${TARGET_TMP}/package.list"

cd "\$TARGET_TMP"

# Install each listed .deb in order
while IFS= read -r debfile; do
    case "\$debfile" in
        ""|\#*) continue ;;
    esac

    if [ ! -f "\$debfile" ]; then
        echo "WARNING: \$debfile listed in \$PKG_LIST but not found in \$TARGET_TMP, skipping" >&2
        continue
    fi

    echo "Installing \$debfile ..."
    dpkg -i "./\$debfile" || apt-get -f install -y
done < "\$PKG_LIST"

rm -f ./*.deb
rmdir "\$TARGET_TMP" || true

systemctl enable satellite1-init.service || true
EOF
