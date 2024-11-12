#!/usr/bin/env bash

# Define directories
mkdir -p $HOME/bin

# Download and install Chrome
CHROME_URL="https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb"
wget -O $HOME/bin/google-chrome.deb "$CHROME_URL"
dpkg -x $HOME/bin/google-chrome.deb $HOME/bin

# Set Chrome binary location
export CHROME_BIN=$HOME/bin/opt/google/chrome/google-chrome

# Download ChromeDriver
CHROME_VERSION=$(google-chrome --version | awk '{print $3}')
CHROMEDRIVER_VERSION=$(curl -s "https://chromedriver.storage.googleapis.com/LATEST_RELEASE_$CHROME_VERSION" || echo "latest")
wget -N "https://chromedriver.storage.googleapis.com/$CHROMEDRIVER_VERSION/chromedriver_linux64.zip" -P $HOME/bin
unzip $HOME/bin/chromedriver_linux64.zip -d $HOME/bin
chmod +x $HOME/bin/chromedriver

# Update PATH
export PATH=$PATH:$HOME/bin
