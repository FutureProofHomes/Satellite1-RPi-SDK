#!/bin/bash -e

REPO_URL="https://github.com/FutureProofHomes/linux-voice-assistant.git"
REPO_DIR="/opt/linux-voice-assistant"  
SETUP_SCRIPT="script/setup"  

on_chroot << EOF
set -e

# Make sure /opt exists
mkdir -p /opt

# Clone or update the repo
if [ ! -d "$REPO_DIR/.git" ]; then
    git clone "$REPO_URL" "$REPO_DIR"
else
    cd "$REPO_DIR"
    git pull --ff-only || true
fi

cd "$REPO_DIR"

# Make sure the setup script is executable
chmod +x "$SETUP_SCRIPT"

# Run the setup script
./"$SETUP_SCRIPT"
EOF
