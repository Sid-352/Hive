#!/bin/bash
# setup-hive.sh - User setup for Hive WiFi Direct on Linux
# Handles dependencies, D-Bus policies, and group permissions

set -e

# Professional formatting helper
info() { echo -e "\e[34m[INFO]\e[0m $1"; }
warn() { echo -e "\e[33m[WARN]\e[0m $1"; }
error() { echo -e "\e[31m[ERROR]\e[0m $1"; exit 1; }
check() { echo -e "\e[32m[✓]\e[0m $1"; }

echo "==========================================="
echo "   Hive WiFi Direct - Linux Setup Script   "
echo "==========================================="

# Ensure we are in the script's directory
cd "$(dirname "$0")"

CURRENT_USER=${SUDO_USER:-$USER}

# 1. Dependency Check
info "Checking system dependencies..."
deps=("nmcli" "ip" "awk" "dbus-daemon")
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
        info "Suggested fix: sudo apt-get update && sudo apt-get install -y network-manager libdbus-1-3"
    elif command -v pacman &> /dev/null; then
        info "Suggested fix: sudo pacman -S networkmanager dbus"
    elif command -v dnf &> /dev/null; then
        info "Suggested fix: sudo dnf install NetworkManager dbus"
    fi
    error "Please install missing dependencies and try again."
fi
check "Core dependencies present"

# 2. D-Bus Directory Detection
info "Locating D-Bus configuration path..."
DBUS_SYSTEM_D="/etc/dbus-1/system.d"
if [ ! -d "$DBUS_SYSTEM_D" ]; then
    error "D-Bus system directory not found at $DBUS_SYSTEM_D. Is D-Bus installed?"
fi

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
# Policy might be in agents/linux/ if packaged via hive.spec or next to this script
POLICY_SRC="hive-wifidirect.conf"
if [ ! -f "$POLICY_SRC" ]; then
    POLICY_SRC="agents/linux/hive-wifidirect.conf"
fi

if [ ! -f "$POLICY_SRC" ]; then
    error "hive-wifidirect.conf missing from bundle."
fi

sudo install -m 644 "$POLICY_SRC" "$DBUS_SYSTEM_D/"
sudo systemctl reload dbus 2>/dev/null || true
check "Security policy applied"

# 5. NetworkManager Verification
info "Checking NetworkManager status..."
if ! systemctl is-active --quiet NetworkManager; then
    warn "NetworkManager is not running. Hive may have limited functionality."
else
    check "NetworkManager is active"
fi

echo ""
echo "=== Setup Complete ==="
echo "Note: You must log out and back in for group changes to take effect."
echo "Or run 'newgrp netdev' in your current terminal session."
echo ""
echo "You can now run the 'Hive' executable."
