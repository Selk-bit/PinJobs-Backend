#!/usr/bin/env bash

# Define directories
mkdir -p $HOME/bin
cd $HOME/bin

# Download a standalone Chrome binary
wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
ar x google-chrome-stable_current_amd64.deb data.tar.xz
tar -xf data.tar.xz --strip 2 -C $HOME/bin opt/google/chrome/google-chrome

# Set Chrome binary path
export CHROME_BIN=$HOME/bin/google-chrome

# Get the exact Chrome version
CHROME_VERSION=$($CHROME_BIN --version | awk '{print $3}' | cut -d '.' -f 1)
CHROMEDRIVER_VERSION=$(curl -s "https://chromedriver.storage.googleapis.com/LATEST_RELEASE_$CHROME_VERSION")

# Fallback to the latest ChromeDriver if version retrieval fails
if [[ -z "$CHROMEDRIVER_VERSION" ]]; then
    CHROMEDRIVER_VERSION=$(curl -s "https://chromedriver.storage.googleapis.com/LATEST_RELEASE")
fi

# Download ChromeDriver
wget -N "https://chromedriver.storage.googleapis.com/$CHROMEDRIVER_VERSION/chromedriver_linux64.zip" -P $HOME/bin
unzip $HOME/bin/chromedriver_linux64.zip -d $HOME/bin
chmod +x $HOME/bin/chromedriver

# Update PATH
export PATH=$PATH:$HOME/bin
