#!/bin/bash
# build.sh - build script for Hive Hardware Agent (Linux)
# Handles multi-distro include paths and WSL detection

set -e

# formatting helper
info() { echo -e "\e[34m[INFO]\e[0m $1"; }
check() { echo -e "\e[32m[✓]\e[0m $1"; }
error() { echo -e "\e[31m[ERROR]\e[0m $1"; exit 1; }

# Handle clean command
if [ "$1" == "clean" ]; then
    info "Cleaning build artifacts..."
    rm -f HiveAgent Test_Telemetry *.o
    check "Clean complete"
    exit 0
fi

echo "==========================================="
echo "      HiveAgent Compilation - Linux        "
echo "==========================================="

# 1. Detect D-Bus Include Paths
info "Detecting D-Bus headers..."

# Try pkg-config first
if command -v pkg-config &> /dev/null && pkg-config --exists dbus-1; then
    DBUS_CFLAGS=$(pkg-config --cflags dbus-1)
    DBUS_LIBS=$(pkg-config --libs dbus-1)
    info "Using pkg-config for D-Bus flags"
else
    # Fallback to manual detection
    info "Falling back to manual header detection..."
    
    # Common paths for x86_64 and aarch64
    ARCH=$(uname -m)
    PATHS=(
        "/usr/include/dbus-1.0"
        "/usr/lib/${ARCH}-linux-gnu/dbus-1.0/include"
        "/usr/lib64/dbus-1.0/include"
        "/usr/lib/dbus-1.0/include"
    )
    
    DBUS_CFLAGS=""
    for path in "${PATHS[@]}"; do
        if [ -d "$path" ]; then
            DBUS_CFLAGS="$DBUS_CFLAGS -I$path"
        fi
    done
    DBUS_LIBS="-ldbus-1"
fi

if [ -z "$DBUS_CFLAGS" ]; then
    error "Could not locate D-Bus headers. Run ./setup-hive.sh first."
fi

# 2. WSL Detection
if grep -q Microsoft /proc/version; then
    info "WSL environment detected - disabling D-Bus iface checks (mock mode fallback)"
    WSL_FLAGS="-DWSL_PLATFORM"
fi

# 3. Compilation
info "Compiling HiveAgent..."

g++ -std=c++17 -Wall -Wextra -O2 $WSL_FLAGS \
    HiveAgent.cpp Telemetry.cpp WifiManager.cpp DataPlane.cpp \
    $DBUS_CFLAGS \
    $DBUS_LIBS -lpthread \
    -I../shared \
    -o HiveAgent

if [ -f "HiveAgent" ]; then
    check "Build Successful: ./HiveAgent"
else
    error "Build failed."
fi

echo ""
info "To test the agent:"
echo "  echo '{\"type\":\"STATUS\"}' | ./HiveAgent"
