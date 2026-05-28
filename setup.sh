#!/usr/bin/env bash
# SpotRR — Easy Setup (Linux / macOS)
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

ok()   { echo -e "  ${GREEN}[OK]${NC}  $1"; }
err()  { echo -e "  ${RED}[ERROR]${NC}  $1"; }
warn() { echo -e "  ${YELLOW}[WARN]${NC}  $1"; }
info() { echo -e "  [..]  $1"; }

echo ""
echo "  ====================================================="
echo "    SPOTRR  |  Easy Setup"
echo "  ====================================================="
echo ""

# ── Check Python ──────────────────────────────────────────────────────────────
PYTHON=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        VER=$("$cmd" -c "import sys; print(sys.version_info.major, sys.version_info.minor)")
        MAJOR=$(echo $VER | cut -d' ' -f1)
        MINOR=$(echo $VER | cut -d' ' -f2)
        if [ "$MAJOR" -ge 3 ] && [ "$MINOR" -ge 10 ]; then
            PYTHON="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    err "Python 3.10+ not found."
    echo ""
    echo "  Install it with:"
    echo "    Ubuntu/Debian:  sudo apt install python3 python3-venv"
    echo "    macOS:          brew install python"
    echo ""
    exit 1
fi
ok "Python found: $($PYTHON --version)"

# ── Virtual environment ────────────────────────────────────────────────────────
if [ ! -d ".venv" ]; then
    info "Creating virtual environment..."
    $PYTHON -m venv .venv
    ok "Virtual environment created"
else
    ok "Virtual environment already exists"
fi

# ── Install dependencies ──────────────────────────────────────────────────────
info "Installing dependencies (first time may take a few minutes)..."
.venv/bin/pip install -r requirements.txt --quiet --disable-pip-version-check
ok "All dependencies installed"

# ── Download FFmpeg ───────────────────────────────────────────────────────────
FFMPEG_SPOTDL="$HOME/.config/spotdl/ffmpeg"
if command -v ffmpeg &>/dev/null; then
    ok "FFmpeg found in system"
elif [ -f "$FFMPEG_SPOTDL" ]; then
    ok "FFmpeg already downloaded"
else
    info "Downloading FFmpeg (one-time download)..."
    .venv/bin/python -m spotdl --download-ffmpeg && ok "FFmpeg downloaded" \
        || warn "FFmpeg download failed — the app will retry on launch"
fi

# ── Desktop shortcut ──────────────────────────────────────────────────────────
DESKTOP_FILE=""

# Linux (XDG)
if [ "$(uname)" = "Linux" ]; then
    XDG_DESKTOP="${XDG_DESKTOP_DIR:-$HOME/Desktop}"
    if [ ! -d "$XDG_DESKTOP" ]; then
        XDG_DESKTOP="$HOME/Bureau"   # French locale
    fi
    if [ -d "$XDG_DESKTOP" ]; then
        DESKTOP_FILE="$XDG_DESKTOP/SpotRR.desktop"
    else
        DESKTOP_FILE="$HOME/.local/share/applications/SpotRR.desktop"
        mkdir -p "$(dirname "$DESKTOP_FILE")"
    fi
fi

# macOS — create .command file on Desktop
if [ "$(uname)" = "Darwin" ]; then
    DESKTOP_FILE="$HOME/Desktop/SpotRR.command"
    cat > "$DESKTOP_FILE" << EOF
#!/bin/bash
cd "$SCRIPT_DIR"
.venv/bin/python spotrr.py
EOF
    chmod +x "$DESKTOP_FILE"
    ok "Launcher created on Desktop: SpotRR.command"
    DESKTOP_FILE=""   # skip the .desktop block below
fi

if [ -n "$DESKTOP_FILE" ]; then
    ICON_PATH="$SCRIPT_DIR/assets/logo.png"
    cat > "$DESKTOP_FILE" << EOF
[Desktop Entry]
Name=SpotRR
Comment=SpotRR
Exec=$SCRIPT_DIR/.venv/bin/python $SCRIPT_DIR/spotrr.py
Icon=$ICON_PATH
Terminal=false
Type=Application
Categories=Music;AudioVideo;
StartupWMClass=SpotRR
EOF
    chmod +x "$DESKTOP_FILE"

    # Mark as trusted on GNOME so it doesn't show "Allow Launching" dialog
    if command -v gio &>/dev/null; then
        gio set "$DESKTOP_FILE" metadata::trusted true 2>/dev/null || true
    fi
    ok "Desktop shortcut created: $DESKTOP_FILE"
fi

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo "  ====================================================="
echo "    Setup complete!  Launching..."
echo "  ====================================================="
echo ""
sleep 1
.venv/bin/python spotrr.py &
