#!/usr/bin/env bash
# SpotRR — Setup & Launch (Linux / macOS)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

ok()   { echo -e "  ${GREEN}[OK]${NC}  $1"; }
err()  { echo -e "  ${RED}[ERROR]${NC}  $1" >&2; }
warn() { echo -e "  ${YELLOW}[WARN]${NC}  $1"; }
info() { echo -e "  [..]  $1"; }

echo ""
echo "  ====================================================="
echo "    SPOTRR  |  Setup & Launch"
echo "  ====================================================="
echo ""

# ── Python ────────────────────────────────────────────────────────────────────
PYTHON=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        VER=$("$cmd" -c "import sys; print(sys.version_info.major, sys.version_info.minor)" 2>/dev/null)
        MAJOR=$(echo "$VER" | cut -d' ' -f1)
        MINOR=$(echo "$VER" | cut -d' ' -f2)
        if [ "${MAJOR:-0}" -ge 3 ] && [ "${MINOR:-0}" -ge 10 ]; then
            PYTHON="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    err "Python 3.10+ not found."
    echo ""
    echo "  Install it:"
    echo "    Ubuntu/Debian : sudo apt install python3 python3-venv python3-pip"
    echo "    Fedora/RHEL   : sudo dnf install python3"
    echo "    Arch          : sudo pacman -S python"
    echo "    macOS (Homebrew): brew install python"
    echo "    macOS (direct) : https://www.python.org/downloads/"
    echo ""
    exit 1
fi
ok "Python $($PYTHON --version 2>&1 | awk '{print $2}')"

# ── Virtual environment ───────────────────────────────────────────────────────
VENV_OK=0
if [ -f ".venv/bin/python" ]; then
    .venv/bin/python -m pip --version >/dev/null 2>&1 && VENV_OK=1
fi

if [ "$VENV_OK" -eq 0 ]; then
    if [ -d ".venv" ]; then
        info "Existing virtual environment is broken — recreating..."
        rm -rf .venv
    else
        info "Creating virtual environment..."
    fi
    if ! $PYTHON -m venv .venv 2>/dev/null; then
        err "Could not create virtual environment."
        echo ""
        if command -v apt-get &>/dev/null; then
            echo "  On Ubuntu/Debian, run first:"
            echo "    sudo apt install python3-venv python3-pip"
        elif command -v dnf &>/dev/null; then
            echo "  On Fedora/RHEL, run first:"
            echo "    sudo dnf install python3"
        else
            echo "  Try: $PYTHON -m pip install virtualenv"
            echo "       $PYTHON -m virtualenv .venv"
        fi
        echo ""
        exit 1
    fi
    ok "Virtual environment created"
else
    ok "Virtual environment ready"
fi

# ── pip ───────────────────────────────────────────────────────────────────────
info "Ensuring pip is up to date..."
.venv/bin/python -m pip install --upgrade pip --quiet --disable-pip-version-check 2>/dev/null
ok "pip ready"

# ── Dependencies ──────────────────────────────────────────────────────────────
# Skip install when requirements.txt is unchanged (faster re-runs).
HASH_FILE=".venv/.req_hash"
NEED_INSTALL=1
REQ_HASH=""

if command -v sha256sum &>/dev/null; then
    REQ_HASH=$(sha256sum requirements.txt 2>/dev/null | cut -d' ' -f1)
elif command -v md5sum &>/dev/null; then
    REQ_HASH=$(md5sum requirements.txt 2>/dev/null | cut -d' ' -f1)
elif command -v md5 &>/dev/null; then
    REQ_HASH=$(md5 -q requirements.txt 2>/dev/null)
fi

if [ -n "$REQ_HASH" ] && [ -f "$HASH_FILE" ] && [ "$(cat "$HASH_FILE" 2>/dev/null)" = "$REQ_HASH" ]; then
    NEED_INSTALL=0
fi

if [ "$NEED_INSTALL" -eq 1 ]; then
    info "Installing packages (first run takes a few minutes)..."
    if ! .venv/bin/pip install -r requirements.txt --quiet --prefer-binary --disable-pip-version-check 2>/dev/null; then
        err "Package installation failed."
        echo ""
        echo "  Common causes:"
        echo "    - No internet connection"
        echo "    - Firewall or proxy blocking pip"
        echo ""
        echo "  Try running this script again, or manually:"
        echo "    .venv/bin/pip install -r requirements.txt"
        echo ""
        exit 1
    fi
    [ -n "$REQ_HASH" ] && echo "$REQ_HASH" > "$HASH_FILE"
    ok "Packages installed"
else
    ok "Packages up to date"
fi

# ── FFmpeg ────────────────────────────────────────────────────────────────────
FFMPEG_OK=0
command -v ffmpeg &>/dev/null                       && FFMPEG_OK=1
[ -f "$HOME/.config/spotdl/ffmpeg" ]                && FFMPEG_OK=1
[ -f "$HOME/.spotdl/ffmpeg" ]                        && FFMPEG_OK=1

if [ "$FFMPEG_OK" -eq 0 ]; then
    info "Downloading FFmpeg (one-time setup, ~50 MB)..."
    if .venv/bin/python -m spotdl --download-ffmpeg 2>/dev/null; then
        ok "FFmpeg downloaded and ready"
    else
        warn "FFmpeg download failed — WAV/FLAC downloads will not work."
        warn "Fix: .venv/bin/python -m spotdl --download-ffmpeg"
    fi
else
    ok "FFmpeg ready"
fi

# ── Desktop shortcut ──────────────────────────────────────────────────────────
if [ "$(uname)" = "Darwin" ]; then
    # macOS — .command file launched from Finder
    DESKTOP="$HOME/Desktop"
    [ ! -d "$DESKTOP" ] && DESKTOP="$HOME/Escritorio"   # Spanish macOS
    [ ! -d "$DESKTOP" ] && DESKTOP="$HOME/Bureau"        # French macOS

    if [ -d "$DESKTOP" ]; then
        LAUNCHER="$DESKTOP/SpotRR.command"
        cat > "$LAUNCHER" <<LAUNCHER_EOF
#!/usr/bin/env bash
cd "$SCRIPT_DIR"
"$SCRIPT_DIR/.venv/bin/python" "$SCRIPT_DIR/spotrr.py"
LAUNCHER_EOF
        chmod +x "$LAUNCHER"
        ok "Launcher created: $LAUNCHER"
    fi

elif [ "$(uname)" = "Linux" ]; then
    # Determine Desktop directory from XDG user-dirs (respects locale).
    XDG_DESKTOP=""
    if [ -f "$HOME/.config/user-dirs.dirs" ]; then
        # Extract and expand the value without eval
        _RAW=$(grep '^XDG_DESKTOP_DIR=' "$HOME/.config/user-dirs.dirs" 2>/dev/null | cut -d= -f2 | tr -d '"')
        XDG_DESKTOP="${_RAW/\$HOME/$HOME}"
    fi
    # Fallback chain for common locales
    [ -z "$XDG_DESKTOP" ] && XDG_DESKTOP="${XDG_DESKTOP_DIR:-}"
    [ -z "$XDG_DESKTOP" ] || [ ! -d "$XDG_DESKTOP" ] && XDG_DESKTOP="$HOME/Desktop"
    [ ! -d "$XDG_DESKTOP" ] && XDG_DESKTOP="$HOME/Escritorio"   # Spanish
    [ ! -d "$XDG_DESKTOP" ] && XDG_DESKTOP="$HOME/Bureau"        # French
    [ ! -d "$XDG_DESKTOP" ] && XDG_DESKTOP="$HOME/Schreibtisch"  # German
    [ ! -d "$XDG_DESKTOP" ] && XDG_DESKTOP="$HOME/Рабочий стол"  # Russian

    if [ -d "$XDG_DESKTOP" ]; then
        DESKTOP_FILE="$XDG_DESKTOP/SpotRR.desktop"
    else
        DESKTOP_FILE="$HOME/.local/share/applications/SpotRR.desktop"
        mkdir -p "$(dirname "$DESKTOP_FILE")"
    fi

    cat > "$DESKTOP_FILE" <<DESKTOP_EOF
[Desktop Entry]
Name=SpotRR
Comment=Spotify Downloader
Exec="$SCRIPT_DIR/.venv/bin/python" "$SCRIPT_DIR/spotrr.py"
Icon=$SCRIPT_DIR/assets/logo.png
Terminal=false
Type=Application
Categories=Music;AudioVideo;
StartupWMClass=SpotRR
DESKTOP_EOF
    chmod +x "$DESKTOP_FILE"
    # Trust on GNOME so it doesn't require "Allow Launching" confirmation
    command -v gio &>/dev/null && gio set "$DESKTOP_FILE" metadata::trusted true 2>/dev/null || true
    ok "Desktop shortcut: $DESKTOP_FILE"
fi

# ── Launch ────────────────────────────────────────────────────────────────────
echo ""
echo "  ====================================================="
echo "    All done!  Launching SpotRR..."
echo "  ====================================================="
echo ""

# nohup detaches the process from this terminal so closing the setup
# window does not kill the app.
nohup .venv/bin/python "$SCRIPT_DIR/spotrr.py" >/dev/null 2>&1 &
