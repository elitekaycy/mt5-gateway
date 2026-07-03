#!/bin/bash
set -euo pipefail

# Set variables
mt5setup_url="https://download.mql5.com/cdn/web/metaquotes.software.corp/mt5/mt5setup.exe"
mt5file="/config/.wine/drive_c/Program Files/MetaTrader 5/terminal64.exe"
python_url="https://www.python.org/ftp/python/3.9.13/python-3.9.13-amd64.exe"
python_sha256="fb3d0466f3754752ca7fd839a09ffe53375ff2c981279fd4bc23a005458f7f5d"
mono_sha256="75b3f45dca1dc89857fe9e932da78710f64cc6d49ef1ab0c723a177085b4711b"
mt5setup_sha256="d437fd760587d24e094864215b86a441cc64ab897cace2b2a21a46614b3f4e36"
wine_executable="wine"
export mt5setup_url mt5file python_url python_sha256 mono_sha256 mt5setup_sha256
export wine_executable

# Function to show messages
log_message() {
    local level=$1
    local message=$2
    echo "$(date '+%Y-%m-%d %H:%M:%S') - [$level] $message" >> /var/log/mt5_setup.log
}

verify_download() {
    local file="$1"
    local expected="$2"
    printf '%s  %s\n' "$expected" "$file" | sha256sum -c -
}

# Function to check if a Python package is installed in Wine
is_wine_python_package_installed() {
    "$wine_executable" python -c "import pkg_resources; pkg_resources.require('$1')" 2>/dev/null
}

# Function to check if a Python package is installed in Linux
is_python_package_installed() {
    python3 -c "import pkg_resources; pkg_resources.require('$1')" 2>/dev/null
}

# Mute Unnecessary Wine Errors
export WINEDEBUG=-all,err-toolbar,fixme-all
