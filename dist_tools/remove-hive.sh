#!/bin/bash
# remove-hive.sh - Cleanup Hive WiFi Direct configuration from Linux

set -e

# Professional formatting helper
info() { echo -e "\e[34m[INFO]\e[0m $1"; }
check() { echo -e "\e[32m[✓]\e[0m $1"; }

echo "==========================================="
echo "   Hive WiFi Direct - Linux Removal Script "
echo "==========================================="

DBUS_POLICY="/etc/dbus-1/system.d/hive-wifidirect.conf"

if [ -f "$DBUS_POLICY" ]; then
    info "Removing D-Bus security policy..."
    sudo rm "$DBUS_POLICY"
    sudo systemctl reload dbus 2>/dev/null || true
    check "Security policy removed"
else
    info "No D-Bus policy found at $DBUS_POLICY"
fi

echo ""
echo "=== Cleanup Complete ==="
echo "Note: The 'netdev' group was not removed as it may be used by other applications."
echo "If you wish to remove yourself from the netdev group, run:"
echo "  sudo gpasswd -d \$USER netdev"
echo ""
