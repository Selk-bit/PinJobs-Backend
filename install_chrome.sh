#!/usr/bin/env bash

# Define directories
mkdir -p $HOME/bin
cd $HOME/bin

# Remove any existing Chrome .deb files with versioned extensions if they exist
rm -f google-chrome-stable_current_amd64.deb*

# Download and extract Chrome using dpkg-deb
wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
dpkg-deb -x google-chrome-stable_current_amd64.deb $HOME/bin

# Set Chrome binary path
export CHROME_BIN=$HOME/bin/opt/google/chrome/google-chrome

# Get the exact Chrome version
CHROME_VERSION=$($CHROME_BIN --version | awk '{print $3}' | cut -d '.' -f 1)

# Echo the Chrome version for debugging
echo "Installed Chrome version: $CHROME_VERSION"

# Retrieve the corresponding ChromeDriver version
CHROMEDRIVER_VERSION=$(curl -s "https://chromedriver.storage.googleapis.com/LATEST_RELEASE_$CHROME_VERSION" || echo "latest")

# Fallback to the latest ChromeDriver if version retrieval fails
if [[ -z "$CHROMEDRIVER_VERSION" ]]; then
    CHROMEDRIVER_VERSION=$(curl -s "https://chromedriver.storage.googleapis.com/LATEST_RELEASE")
fi

# Remove any existing ChromeDriver zip files if they exist
rm -f chromedriver-linux64.zip*

# Download ChromeDriver
wget -N "https://storage.googleapis.com/chrome-for-testing-public/131.0.6778.69/linux64/chromedriver-linux64.zip" -P $HOME/bin
unzip $HOME/bin/chromedriver-linux64.zip -d $HOME/bin
chmod +x $HOME/bin/chromedriver

# Update PATH
export PATH=$PATH:$HOME/bin
