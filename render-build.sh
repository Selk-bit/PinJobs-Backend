#!/usr/bin/env bash
# Exit on error
set -o errexit

# Define the target directory
TARGET_DIR=/opt/render/chromium/chrome-linux

# Check if Chromium is already installed
if [ ! -f $TARGET_DIR/chrome ]; then
    echo "Downloading Chromium..."
    mkdir -p $TARGET_DIR
    cd $TARGET_DIR
    # Download the latest stable Chromium build for Linux
    wget -O chromium.tar.xz https://download-chromium.appspot.com/dl/Linux_x64?type=snapshots
    # Extract the downloaded archive
    tar -xf chromium.tar.xz --strip-components=1
    # Remove the archive to save space
    rm chromium.tar.xz
    echo "Chromium installed at $TARGET_DIR/chrome"
else
    echo "Chromium already installed at $TARGET_DIR/chrome"
fi