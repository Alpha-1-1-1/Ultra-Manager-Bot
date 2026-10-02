#!/usr/bin/env bash
# Render.com build script for Ultra Manager Bot
# This runs during the Build phase before the Start command

set -e

echo "=== Installing system dependencies ==="

# Install Node.js (required for yt-dlp JavaScript challenge solver)
if ! command -v node &> /dev/null; then
    echo "Installing Node.js..."
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - 2>/dev/null || true
    apt-get install -y nodejs 2>/dev/null || {
        # Fallback: install via nvm if apt fails (non-root Render environments)
        echo "apt install failed, trying standalone node binary..."
        curl -fsSL https://nodejs.org/dist/v20.18.0/node-v20.18.0-linux-x64.tar.xz | tar -xJ --strip-components=1 -C /usr/local/ 2>/dev/null || true
    }
fi
echo "Node.js version: $(node --version 2>/dev/null || echo 'not available')"

# Install ffmpeg if not already present
if ! command -v ffmpeg &> /dev/null; then
    echo "Installing ffmpeg..."
    apt-get update -qq && apt-get install -y -qq ffmpeg 2>/dev/null || true
fi
echo "ffmpeg: $(ffmpeg -version 2>/dev/null | head -1 || echo 'not available, will use static-ffmpeg')"

echo "=== Installing Python dependencies ==="
pip install --upgrade pip
pip install -r requirements.txt

echo "=== Build complete ==="
