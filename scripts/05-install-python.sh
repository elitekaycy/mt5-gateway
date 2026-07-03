#!/bin/bash

source /scripts/02-common.sh

log_message "RUNNING" "05-install-python.sh"

# Install Python in Wine if not present
if ! $wine_executable python --version > /dev/null 2>&1; then
    log_message "INFO" "Installing Python in Wine..."
    wget -O /tmp/python-installer.exe $python_url > /dev/null 2>&1
    $wine_executable /tmp/python-installer.exe /quiet InstallAllUsers=1 PrependPath=1 Include_test=0
    rm /tmp/python-installer.exe
    log_message "INFO" "Python installed in Wine."
else
    log_message "INFO" "Python is already installed in Wine."
fi

log_message "INFO" "Wine Python: $($wine_executable python --version 2>&1)"