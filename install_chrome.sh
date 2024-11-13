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
CHROME_VERSION=$($CHROME_BIN --version | awk '{print $3}')

# Echo the Chrome version for debugging
echo "Installed Chrome version: $CHROME_VERSION"

# Query and echo the Chrome binary path without using CHROME_BIN variable
CHROME_PATH=$(find $HOME/bin -name google-chrome -type f)
echo "Chrome binary path: $CHROME_PATH"
chmod +x $CHROME_PATH

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
unzip -o $HOME/bin/chromedriver-linux64.zip -d $HOME/bin

# Move the chromedriver binary from the nested folder to $HOME/bin
mv $HOME/bin/chromedriver-linux64/chromedriver $HOME/bin/chromedriver
chmod +x $HOME/bin/chromedriver

# Custom chmod on the chromedriver binary
chmod 777 /opt/render/project/src/chromedriver/chromedriver

# Clean up the extracted folder and zip file
rm -rf $HOME/bin/chromedriver-linux64
rm -f $HOME/bin/chromedriver-linux64.zip

# Update PATH
export PATH=$PATH:$HOME/bin
