#!/bin/bash
# setup-hive.sh - Robust setup for Hive WiFi Direct on Linux
# Handles dependencies, D-Bus policies, and group permissions

set -e

# Professional formatting helper
info() { echo -e "\e[34m[INFO]\e[0m $1"; }
warn() { echo -e "\e[33m[WARN]\e[0m $1"; }
error() { echo -e "\e[31m[ERROR]\e[0m $1"; exit 1; }
check() { echo -e "\e[32m[✓]\e[0m $1"; }

echo "==========================================="
echo "   Hive WiFi Direct - Linux Environment    "
echo "==========================================="

CURRENT_USER=${SUDO_USER:-$USER}

# 1. Dependency Check
info "Checking system dependencies..."

deps=("nmcli" "ip" "awk" "g++" "dbus-daemon")
missing_deps=()

for cmd in "${deps[@]}"; do
    if ! command -v "$cmd" &> /dev/null; then
        missing_deps+=("$cmd")
    fi
done

if [ ${#missing_deps[@]} -ne 0 ]; then
    warn "Missing dependencies: ${missing_deps[*]}"
    info "Attempting to identify package manager..."
    
    if command -v apt-get &> /dev/null; then
        info "Suggested fix: sudo apt-get update && sudo apt-get install -y build-essential libdbus-1-dev network-manager"
    elif command -v pacman &> /dev/null; then
        info "Suggested fix: sudo pacman -S base-devel dbus networkmanager"
    elif command -v dnf &> /dev/null; then
        info "Suggested fix: sudo dnf install gcc-c++ dbus-devel NetworkManager"
    fi
    error "Please install missing dependencies and try again."
fi
check "Core dependencies present"

# 2. D-Bus Directory Detection
info "Locating D-Bus configuration path..."
DBUS_SYSTEM_D="/etc/dbus-1/system.d"
if [ ! -d "$DBUS_SYSTEM_D" ]; then
    warn "Standard D-Bus path not found, creating $DBUS_SYSTEM_D"
    sudo mkdir -p "$DBUS_SYSTEM_D"
fi
check "D-Bus path: $DBUS_SYSTEM_D"

# 3. netdev Group Setup
info "Verifying 'netdev' group permissions..."
if ! getent group netdev > /dev/null 2>&1; then
    info "Creating 'netdev' group for network management..."
    sudo groupadd netdev
fi
sudo usermod -aG netdev "$CURRENT_USER"
check "User '$CURRENT_USER' assigned to netdev group"

# 4. Policy Installation
info "Installing Hive D-Bus security policy..."
if [ ! -f "hive-wifidirect.conf" ]; then
    error "hive-wifidirect.conf missing from current directory."
fi

sudo install -m 644 hive-wifidirect.conf "$DBUS_SYSTEM_D/"
sudo systemctl reload dbus 2>/dev/null || true
check "Security policy applied"

# 5. NetworkManager Verification
info "Checking NetworkManager status..."
if ! systemctl is-active --quiet NetworkManager; then
    warn "NetworkManager is not running. Hive may have limited functionality."
    info "Start it with: sudo systemctl start NetworkManager"
else
    check "NetworkManager is active"
fi

echo ""
echo "=== Environment Hardening Complete ==="
echo "Note: You must log out and back in for group changes to take effect."
echo "Or run 'newgrp netdev' in your current terminal session."
echo ""
echo "Next step: Run ./build.sh to compile the agent."
