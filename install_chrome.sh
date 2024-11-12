#!/usr/bin/env bash
# Update package lists and install Chrome
apt-get update && apt-get install -y wget unzip
wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add -
echo "deb http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list
apt-get update
apt-get install -y google-chrome-stable

# Create chromedriver directory
mkdir -p chromedriver

# Install ChromeDriver
CHROME_VERSION=$(google-chrome --version | grep -oP '\d+\.\d+\.\d+')
CHROMEDRIVER_VERSION=$(curl -s "https://chromedriver.storage.googleapis.com/LATEST_RELEASE_$CHROME_VERSION")
wget -N "https://chromedriver.storage.googleapis.com/$CHROMEDRIVER_VERSION/chromedriver_linux64.zip" -P /tmp/
unzip /tmp/chromedriver_linux64.zip -d chromedriver/
rm /tmp/chromedriver_linux64.zip
chmod +x chromedriver/chromedriver
