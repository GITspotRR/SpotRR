"""
SpotRR  v2.2.0
Desktop application to get music using spotdl.

Usage:
    python spotrr.py

Requirements:
    pip install -r requirements.txt
"""

import asyncio
import importlib
import io
import json
import logging
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.parse
import warnings
import webbrowser
from datetime import datetime

warnings.filterwarnings("ignore", category=DeprecationWarning, module="pkg_resources")
warnings.filterwarnings("ignore", category=UserWarning, message=".*pkg_resources.*")
warnings.filterwarnings("ignore", category=UserWarning, message=".*PyInstaller.*")
warnings.filterwarnings("ignore", category=UserWarning, message=".*setuptools.*")

if sys.platform == "win32":
    os.environ["PYTHONIOENCODING"] = "utf-8"
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass

    # Patch subprocess.Popen so every process spawned from this app (including
    # yt-dlp's ffmpeg calls, which run in-process via the spotdl API) never
    # opens a visible CMD/console window on Windows.
    _CREATE_NO_WINDOW = 0x08000000
    _orig_popen_init  = subprocess.Popen.__init__

    def _silent_popen_init(self, args, **kwargs):
        cf = kwargs.get("creationflags", 0) & ~0x00000010  # strip CREATE_NEW_CONSOLE
        cf |= _CREATE_NO_WINDOW
        kwargs["creationflags"] = cf
        if "startupinfo" not in kwargs:
            _si = subprocess.STARTUPINFO()
            _si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            _si.wShowWindow = 0  # SW_HIDE
            kwargs["startupinfo"] = _si
        _orig_popen_init(self, args, **kwargs)

    subprocess.Popen.__init__ = _silent_popen_init

import tkinter as tk
from tkinter import filedialog, font, messagebox, scrolledtext, simpledialog, ttk

import requests

try:
    import spotipy
    from spotipy.oauth2 import SpotifyClientCredentials
    SPOTIPY_AVAILABLE = True
except ImportError:
    SPOTIPY_AVAILABLE = False

try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    Image = ImageTk = None

try:
    import qrcode
    QR_AVAILABLE = True
except ImportError:
    QR_AVAILABLE = False
    qrcode = None

try:
    from tkinterdnd2 import DND_TEXT
    from tkinterdnd2.TkinterDnD import _require as _dnd_require
    TKDND_AVAILABLE = True
except (ImportError, RuntimeError, AttributeError):
    TKDND_AVAILABLE = False

# ── App metadata ──────────────────────────────────────────────────────────────
APP_NAME    = "SpotRR"
APP_VERSION = "2.2.0"
APP_GITHUB  = "https://github.com/GITspotRR/SpotRR"

CRYPTO_ADDRESSES: dict = {
    "BTC":   "bc1q6lz2yhwqcttjm8m7tr8jtd4sdnj3l7vgv36m0l",
    "ETH":   "0x556a352adF94B68ef0FC6a1274F1a76991502bBd",
    "BASE":  "0x556a352adF94B68ef0FC6a1274F1a76991502bBd",
    "BNB":   "0x556a352adF94B68ef0FC6a1274F1a76991502bBd",
    "XRP":   "rfzSCZRKDvqhs3bDFH3LZDBuLX3Qt82Q1r",
    "XLM":   {"address": "GD5KTTLVKSJBQYKYM2CIWUJHGHRNL3YTTUVKW4W37PVXPPU7MLE3CJYK",
              "memo": "7MLE3CJYK"},
    "SOL":   "8MrxFodmdzgEmqVbAePuCPqVoJtjvBBY9KESrNbZfJbB",
    "TRX":   "TTbjt6oBLXCytgZ52wzizTiYZBgmynLAdG",
    "DOGE":  "DN1ogZQUEcYAVPL57rPwMAwoejVRqJbfa7",
    "LTC":   "ltc1qxyagvq8ma7ufgl5maqesqmjjrzq50puwclr82l",
    "ZCASH": "t1eKBpbkMKcUJQFUeyaHpna6bSYpq8xw2ri",
}

# Visual metadata: brand colour, button symbol, network label
CRYPTO_META: dict = {
    "BTC":   {"color": "#F7931A", "symbol": "₿",  "network": "Bitcoin"},
    "ETH":   {"color": "#627EEA", "symbol": "Ξ",  "network": "Ethereum (ERC-20)"},
    "BASE":  {"color": "#0052FF", "symbol": "Ξ",  "network": "Base (L2)"},
    "BNB":   {"color": "#F3BA2F", "symbol": "⬡",  "network": "BNB Smart Chain"},
    "XRP":   {"color": "#00AAE4", "symbol": "✦",  "network": "XRP Ledger"},
    "XLM":   {"color": "#14B6E7", "symbol": "✦",  "network": "Stellar"},
    "SOL":   {"color": "#9945FF", "symbol": "◎",  "network": "Solana"},
    "TRX":   {"color": "#E50915", "symbol": "◈",  "network": "TRON"},
    "DOGE":  {"color": "#C2A633", "symbol": "Ð",  "network": "Dogecoin"},
    "LTC":   {"color": "#BFBBBB", "symbol": "Ł",  "network": "Litecoin"},
    "ZCASH": {"color": "#F4B728", "symbol": "ⓩ",  "network": "Zcash"},
}

LEGAL_DISCLAIMER = (
    "EDUCATIONAL USE ONLY\n\n"
    "This software is for EDUCATIONAL PURPOSES ONLY.\n\n"
    "You are responsible for:\n"
    "  •  Having permission to download content\n"
    "  •  Complying with all applicable laws\n"
    "  •  Respecting copyright\n\n"
    "By using this software you acknowledge these terms.\n"
    "The developer is not liable for any misuse.\n\n"
    "Distributed 'AS IS' without warranty."
)

# ── Design tokens ─────────────────────────────────────────────────────────────
C = {
    "bg0": "#080808", "bg1": "#101010", "bg2": "#161616",
    "bg3": "#1E1E1E", "bg4": "#262626", "bg5": "#2E2E2E",
    "green": "#1DB954", "green_hi": "#1FD460", "green_lo": "#17913F",
    "t1": "#FFFFFF",   "t2": "#B3B3B3",  "t3": "#6A6A6A",
    "red": "#E74C3C",  "orange": "#E67E22", "blue": "#3498DB",
    "div": "#242424",
}

# ─────────────────────────────────────────────────────────────────────────────
# Rate-limit handler
# ─────────────────────────────────────────────────────────────────────────────

class _RateLimitHandler:
    """Exponential-backoff handler for Spotify API 429 responses."""

    def __init__(self) -> None:
        self._retry_after = 0.0
        self._count       = 0
        self._last        = 0.0

    def wait(self) -> None:
        now = time.monotonic()
        if self._retry_after > 0:
            remaining = self._retry_after - (now - self._last)
            if remaining > 0:
                time.sleep(remaining)
            self._retry_after = 0.0
        # Minimum 100 ms between requests
        if self._last > 0 and (time.monotonic() - self._last) < 0.1:
            time.sleep(0.1)
        self._last = time.monotonic()
        self._count += 1

    def on_429(self, header: str | None = None) -> None:
        try:
            self._retry_after = float(header) if header else min(0.2 * 2 ** self._count, 30.0)
        except (ValueError, TypeError):
            self._retry_after = 5.0


_rl = _RateLimitHandler()


def _spotify_call(fn, *args, **kwargs):
    """Wrap any callable with automatic 429 retry (max 3 attempts)."""
    for attempt in range(3):
        try:
            _rl.wait()
            return fn(*args, **kwargs)
        except Exception as exc:
            msg = str(exc).lower()
            if "429" in msg or "rate limit" in msg:
                _rl.on_429()
                if attempt == 2:
                    raise
                time.sleep(_rl._retry_after)
            else:
                raise
    raise RuntimeError("Max retries reached")


# ── Resource path helpers ─────────────────────────────────────────────────────

def _resource(rel: str) -> str:
    """Resolve a bundled asset path — works in both dev and PyInstaller one-file builds."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)


def _ffmpeg_exe() -> str | None:
    """Return the path to the bundled ffmpeg.exe, or None when not available."""
    if sys.platform != "win32":
        return None
    path = _resource(os.path.join("assets", "ffmpeg.exe"))
    return path if os.path.isfile(path) else None


def _find_ffmpeg() -> str:
    """Find FFmpeg: bundled → spotdl download location → PATH → fallback."""
    bundled = _ffmpeg_exe()
    if bundled:
        return bundled

    home   = os.path.expanduser("~")
    suffix = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
    for candidate in (
        os.path.join(home, ".spotdl",        suffix),
        os.path.join(home, ".config", "spotdl", suffix),
        os.path.join(home, "AppData", "Local", "spotdl", suffix),
    ):
        if os.path.isfile(candidate):
            return candidate

    found = shutil.which("ffmpeg")
    return found or "ffmpeg"


# ── Subprocess helpers ────────────────────────────────────────────────────────

def _win_flags() -> dict:
    """Suppress console window on Windows."""
    return {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}


def _popen(cmd: list, **kwargs) -> subprocess.Popen:
    return subprocess.Popen(cmd, **{**_win_flags(), **kwargs})


# ── Single-instance protection ────────────────────────────────────────────────

_INSTANCE_SOCK: "socket.socket | None" = None
_INSTANCE_PORT = 19847


def _acquire_instance() -> bool:
    global _INSTANCE_SOCK
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
        sock.bind(("127.0.0.1", _INSTANCE_PORT))
        sock.listen(1)
        _INSTANCE_SOCK = sock
        return True
    except OSError:
        return False


def _release_instance() -> None:
    global _INSTANCE_SOCK
    if _INSTANCE_SOCK:
        try:
            _INSTANCE_SOCK.close()
        except Exception:
            pass
        _INSTANCE_SOCK = None


# ── UI primitives ─────────────────────────────────────────────────────────────

def _divider(parent, bg: str | None = None, orient: str = "h") -> tk.Frame:
    if orient == "h":
        return tk.Frame(parent, bg=bg or C["div"], height=1)
    return tk.Frame(parent, bg=bg or C["div"], width=1)


def _section_label(parent, text: str, bg: str | None = None) -> tk.Label:
    f = font.Font(family="Segoe UI", size=9, weight="bold")
    return tk.Label(parent, text=text.upper(), fg=C["t2"], bg=bg or C["bg2"], font=f)


# ─────────────────────────────────────────────────────────────────────────────
# Main application
# ─────────────────────────────────────────────────────────────────────────────

class SpotRRApp:

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.sp   = None
        self.logo_image = None

        # Download state
        self.download_queue:  list[tuple[str, str]] = []
        self.is_downloading   = False
        self.download_paused  = False
        self.current_process: subprocess.Popen | None = None
        self._queue_lock      = threading.Lock()  # protects download_queue

        # Per-download stats (reset at the start of each download)
        self._dl_ok    = 0   # tracks successfully downloaded
        self._dl_fail  = 0   # tracks that failed
        self._dl_total = 0   # total tracks expected (from spotdl output)

        # Format / quality / threads
        self.format_var     = tk.StringVar(value="mp3")
        self.quality_var    = tk.StringVar(value="320k")
        self.batch_size     = 4
        self.fmt_buttons:     dict[str, tk.Button] = {}
        self.quality_buttons: dict[str, tk.Button] = {}
        self.batch_buttons:   dict[int, tk.Button] = {}

        # Cache base directory so we don't recompute it on every access
        self._base = (os.path.dirname(sys.executable) if getattr(sys, "frozen", False)
                      else os.path.dirname(os.path.abspath(__file__)))

        # Spotdl client cache — created once per session, reused across downloads.
        # SpotifyClient inside spotdl is a class-level singleton: it can only be
        # initialized once per process.  We must NEVER call _Spotdl() a second
        # time unless we first reset SpotifyClient._instance = None.
        self._spotdl_client     = None
        self._spotdl_init_creds = None   # (cid, cs) — only creds require recreation
        self._spotdl_lock       = threading.Lock()  # guards client creation

        # Logo debounce timer
        self._logo_resize_timer: str | None = None

        self._build_fonts()
        self._build_styles()
        self._build_ui()
        self._load_settings()
        self._setup_drag_drop()
        self._bind_shortcuts()

        self.root.after(200, self._deferred_init)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def _deferred_init(self) -> None:
        # Fast, synchronous UI setup — these must run on the main thread
        self._init_spotify_client()
        self._load_logo()
        self._restore_geometry()
        cfg = self._read_cfg()
        if not cfg.get("shortcut_created"):
            self._create_shortcut()
            cfg["shortcut_created"] = True
            self._write_cfg(cfg)
        # Slow work (package checks, FFmpeg/Deno download, spotdl pre-warm)
        # goes to a daemon thread so the UI stays responsive immediately.
        threading.Thread(target=self._startup_worker, daemon=True).start()

    def _startup_worker(self) -> None:
        """Background startup: dependency checks → Spotify client → spotdl pre-warm."""
        self._check_and_install_deps()
        # If spotipy was just installed, retry the Spotify client init
        if self.sp is None:
            self._init_spotify_client()
        self._preload_spotdl()

    def _on_close(self) -> None:
        self._save_geometry()
        _release_instance()
        self.root.destroy()

    def _preload_spotdl(self) -> None:
        """Pre-create the spotdl client so the first download has no cold-start delay.

        spotdl's Spotdl.__init__ initialises SpotifyClient (FreeSpotify or official
        spotipy), creates an asyncio event loop, and does an HTTP token fetch — all
        of which take 2-5 s.  Doing it here in the background startup thread means
        that delay is invisible to the user.

        The asyncio event loop is NOT permanently bound to its creating thread in
        Python 3.10+.  The download worker always calls
            asyncio.set_event_loop(client.downloader.loop)
        before touching the loop, which re-binds it to the worker thread.  No
        cross-thread violation occurs.
        """
        try:
            from spotdl import Spotdl as _Spotdl
            from spotdl.utils.spotify import SpotifyClient as _SC
        except ImportError:
            return

        cid, cs   = self._get_creds()
        creds_key = (cid or "", cs or "")
        ffmpeg    = _find_ffmpeg()

        try:
            with self._spotdl_lock:
                if self._spotdl_client is not None:
                    return  # already created (user started a download first)
                _SC._instance = None
                client = _Spotdl(
                    client_id=cid or "",
                    client_secret=cs or "",
                    downloader_settings={
                        "output":          os.path.expanduser("~"),
                        "format":          "mp3",
                        "bitrate":         "320k",
                        "threads":         4,
                        "ffmpeg":          ffmpeg,
                        "audio_providers": ["youtube-music", "youtube", "soundcloud"],
                        "simple_tui":      True,
                        "print_errors":    False,
                        "log_format":      None,
                    },
                )
                self._spotdl_client     = client
                self._spotdl_init_creds = creds_key
        except Exception:
            pass

    # ── Paths & config ────────────────────────────────────────────────────────

    def _base_dir(self) -> str:
        return self._base

    def _cfg_path(self) -> str:
        return os.path.join(self._base, "settings.json")

    def _defaults(self) -> dict:
        return {
            "client_id": "", "client_secret": "",
            "default_output_folder": "", "custom_logo_path": "",
            "preferred_format": "mp3", "preferred_quality": "320k",
            "preferred_threads": 4,
        }

    def _read_cfg(self) -> dict:
        try:
            if os.path.exists(self._cfg_path()):
                with open(self._cfg_path(), encoding="utf-8") as f:
                    return {**self._defaults(), **json.load(f)}
        except Exception:
            pass
        return self._defaults()

    def _write_cfg(self, data: dict) -> None:
        path = self._cfg_path()
        tmp  = path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
            os.replace(tmp, path)   # atomic rename — prevents corruption on crash
        except Exception as exc:
            self._log(f"⚠️  Settings save error: {exc}", "warning")
            try:
                os.unlink(tmp)
            except Exception:
                pass

    def _load_settings(self) -> None:
        s = self._read_cfg()
        self.format_var.set(s.get("preferred_format", "mp3"))
        self.quality_var.set(s.get("preferred_quality", "320k"))
        saved_threads = int(s.get("preferred_threads", 4))
        if saved_threads not in (2, 4, 8):
            saved_threads = 4
        self.batch_size = saved_threads
        folder = s.get("default_output_folder", "")
        if folder:
            self.entry_folder.delete(0, tk.END)
            self.entry_folder.insert(0, folder)
        self._sel_fmt(self.format_var.get())
        self._sel_quality(self.quality_var.get())
        self._sel_batch(self.batch_size)

    # ── Credentials ───────────────────────────────────────────────────────────

    def _get_creds(self) -> tuple[str | None, str | None]:
        """Load credentials: env vars → .env file → settings.json."""
        cid = os.environ.get("SPOTIPY_CLIENT_ID") or os.environ.get("SPOTDL_CLIENT_ID")
        cs  = os.environ.get("SPOTIPY_CLIENT_SECRET") or os.environ.get("SPOTDL_CLIENT_SECRET")
        if cid and cs:
            return cid.strip(), cs.strip()

        # .env file
        env_file = os.path.join(self._base, ".env")
        if os.path.exists(env_file):
            try:
                with open(env_file, encoding="utf-8") as f:
                    for raw in f:
                        line = raw.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        k, _, v = line.partition("=")
                        k, v = k.strip(), v.strip().strip('"').strip("'")
                        if k in ("SPOTIPY_CLIENT_ID", "SPOTDL_CLIENT_ID") and not cid:
                            cid = v
                        elif k in ("SPOTIPY_CLIENT_SECRET", "SPOTDL_CLIENT_SECRET") and not cs:
                            cs = v
            except Exception:
                pass
        if cid and cs:
            return cid.strip(), cs.strip()

        # settings.json
        cfg = self._read_cfg()
        cid = cid or cfg.get("client_id")
        cs  = cs  or cfg.get("client_secret")
        if cid and cs:
            return cid.strip(), cs.strip()

        return None, None

    def _init_spotify_client(self) -> None:
        if not SPOTIPY_AVAILABLE:
            self._log("ℹ️  spotipy not available — queue labels use URL patterns", "info")
            return
        cid, cs = self._get_creds()
        if not cid or not cs:
            self._log("⚠️  No API credentials — use 🔑 Client ID / Secret buttons", "warning")
            return
        try:
            self.sp = spotipy.Spotify(
                client_credentials_manager=SpotifyClientCredentials(
                    client_id=cid, client_secret=cs))
            self._log("✅  API client ready", "success")
        except Exception as exc:
            self.sp = None
            self._log(f"❌  API client error: {exc}", "error")

    # ── Dependency check ──────────────────────────────────────────────────────

    def _check_and_install_deps(self) -> None:
        if getattr(sys, "frozen", False):
            self._log("✅  Portable mode — dependencies bundled", "success")
            # FFmpeg is bundled; Deno is downloaded at runtime (not bundled).
            self._ensure_deno()
            return

        # ── Python packages ───────────────────────────────────────────────────
        required = [
            "spotdl", "pillow", "requests", "tkinterdnd2",
            "mutagen", "rapidfuzz", "qrcode", "spotipy",
        ]
        missing = [p for p in required if not _pkg_available(p)]

        if not missing:
            self._log("✅  All dependencies installed", "success")
        else:
            self._log(f"📦  Installing: {', '.join(missing)}", "info")
            for pkg in missing:
                try:
                    subprocess.run(
                        [sys.executable, "-m", "pip", "install", pkg, "--quiet"],
                        check=True, capture_output=True, text=True, **_win_flags())
                    self._log(f"     ✅  {pkg}", "success")
                except subprocess.CalledProcessError as exc:
                    self._log(f"     ⚠️  {pkg}: {exc.stderr[:80]}", "warning")

        # ── FFmpeg & Deno ─────────────────────────────────────────────────────
        self._ensure_ffmpeg()
        self._ensure_deno()

    def _ensure_ffmpeg(self) -> None:
        """Verify FFmpeg is available; download it via spotdl if missing."""
        found = _find_ffmpeg()
        if found != "ffmpeg" or shutil.which("ffmpeg"):
            source = "bundled" if _ffmpeg_exe() else "found"
            self._log(f"✅  FFmpeg ready ({source}: {found})", "success")
            return

        self._log("📦  FFmpeg not found — downloading automatically (one-time setup)…", "info")
        try:
            subprocess.run(
                [sys.executable, "-m", "spotdl", "--download-ffmpeg"],
                capture_output=True, text=True, timeout=180, **_win_flags())
            found2 = _find_ffmpeg()
            if found2 != "ffmpeg":
                self._log(f"✅  FFmpeg downloaded and ready: {found2}", "success")
                # Invalidate cached client so it picks up the new ffmpeg path
                self._invalidate_spotdl_client()
            else:
                self._log(
                    "⚠️  FFmpeg download may have failed.\n"
                    "     WAV/FLAC downloads require FFmpeg.\n"
                    "     Run manually:  spotdl --download-ffmpeg\n"
                    "     Or install FFmpeg from ffmpeg.org and add it to PATH.",
                    "warning")
        except subprocess.TimeoutExpired:
            self._log("⚠️  FFmpeg download timed out — retrying on next launch", "warning")
        except Exception as exc:
            self._log(f"⚠️  FFmpeg setup error: {exc}", "warning")

    def _ensure_deno(self) -> None:
        """Ensure Deno is available — required for some YouTube Music tracks."""
        try:
            from spotdl.utils.deno import download_deno, is_deno_installed
        except ImportError:
            return  # older spotdl version without Deno support

        if is_deno_installed():
            self._log("✅  Deno ready", "success")
            return

        self._log("📦  Deno not found — downloading automatically (one-time setup)…", "info")
        try:
            path = download_deno()
            if path and path.is_file():
                self._log("✅  Deno downloaded and ready", "success")
            else:
                self._log("⚠️  Deno download may have failed — some tracks may not download", "warning")
        except Exception as exc:
            self._log(f"⚠️  Deno setup error: {exc}", "warning")

    # ── Logo ──────────────────────────────────────────────────────────────────

    @staticmethod
    def _center_sash(paned: tk.PanedWindow) -> None:
        """Place the sash so terminal gets ~65 % of the right panel height."""
        h = paned.winfo_height()
        if h > 10:
            paned.sash_place(0, 0, int(h * 0.65))

    def _schedule_logo_reload(self) -> None:
        """Debounce logo reloads: only reload 200 ms after the last resize event."""
        if self._logo_resize_timer:
            self.root.after_cancel(self._logo_resize_timer)
        self._logo_resize_timer = self.root.after(200, self._load_logo)

    def _load_logo(self) -> None:
        if not PIL_AVAILABLE:
            return
        try:
            cfg  = self._read_cfg()
            path = cfg.get("custom_logo_path", "")
            if not path or not os.path.exists(path):
                candidates = [
                    _resource(os.path.join("assets", "logo.png")),
                    _resource(os.path.join("assets", "logo.jpg")),
                    os.path.join(self._base, "assets", "logo.png"),
                    os.path.join(self._base, "logo.png"),
                ]
                path = next((p for p in candidates if os.path.exists(p)), None)

            if not path:
                return

            fw = max(self.logo_frame.winfo_width(),  320)
            fh = max(self.logo_frame.winfo_height(), 320)
            img   = Image.open(path).convert("RGBA")
            ratio = min(fw / img.width, fh / img.height) * 0.88
            img   = img.resize(
                (int(img.width * ratio), int(img.height * ratio)),
                Image.Resampling.LANCZOS)

            self.logo_image = ImageTk.PhotoImage(img)
            self.logo_label.configure(image=self.logo_image)
            self.logo_label.place(relx=0.5, rely=0.5, anchor="center")

        except Exception as exc:
            self._log(f"⚠️  Logo load error: {exc}", "warning")

    # ── Fonts & ttk styles ────────────────────────────────────────────────────

    def _build_fonts(self) -> None:
        self.fn_title   = font.Font(family="Segoe UI", size=20, weight="bold")
        self.fn_normal  = font.Font(family="Segoe UI", size=10, weight="bold")
        self.fn_small   = font.Font(family="Segoe UI", size=9,  weight="bold")
        self.fn_tiny    = font.Font(family="Segoe UI", size=8,  weight="bold")
        self.fn_mono    = font.Font(family="Consolas",  size=9)
        self.fn_mono_sm = font.Font(family="Consolas",  size=8)

    def _build_styles(self) -> None:
        s = ttk.Style()
        s.theme_use("clam")
        s.configure(
            "App.Horizontal.TProgressbar",
            thickness=6, troughcolor=C["bg4"], background=C["green"],
            borderwidth=0, relief="flat",
            darkcolor=C["green"], lightcolor=C["green"], bordercolor=C["bg4"])

    # ─────────────────────────────────────────────────────────────────────────
    # UI construction
    # ─────────────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        self.root.title(f"{APP_NAME}  v{APP_VERSION}")
        self.root.minsize(900, 560)
        self.root.configure(bg=C["bg1"])

        # Maximize window
        for method in ("zoomed", "-zoomed"):
            try:
                if method.startswith("-"):
                    self.root.attributes(method, True)
                else:
                    self.root.state(method)
                break
            except tk.TclError:
                continue

        # 3 px green accent bar at top
        tk.Frame(self.root, bg=C["green"], height=3).pack(fill="x", side="top")

        body = tk.Frame(self.root, bg=C["bg1"])
        body.pack(fill="both", expand=True)

        # Both panels share the window 50/50 horizontally
        self.left_panel = tk.Frame(body, bg=C["bg2"])
        self.left_panel.pack(side="left", fill="both", expand=True)

        _divider(body, orient="v").pack(side="left", fill="y")

        self.right_panel = tk.Frame(body, bg=C["bg1"])
        self.right_panel.pack(side="left", fill="both", expand=True)

        self._build_left()
        self._build_right()

    # ── Left panel ────────────────────────────────────────────────────────────

    def _build_left(self) -> None:
        P = self.left_panel

        # Header — compact
        hdr = tk.Frame(P, bg=C["bg2"])
        hdr.pack(fill="x", padx=16, pady=(10, 6))

        title_area = tk.Frame(hdr, bg=C["bg2"])
        title_area.pack(side="left", fill="x", expand=True)
        tk.Label(title_area, text=APP_NAME.upper(), bg=C["bg2"], fg=C["t1"],
                 font=self.fn_title).pack(anchor="w")
        tk.Label(title_area, text="Your music, your way",
                 bg=C["bg2"], fg=C["t2"], font=self.fn_small).pack(anchor="w")

        badge = tk.Frame(hdr, bg=C["bg4"])
        badge.pack(side="right", anchor="n", pady=2)
        tk.Label(badge, text=f"v{APP_VERSION}", bg=C["bg4"], fg=C["green"],
                 font=self.fn_tiny, padx=6, pady=2).pack()

        _divider(P).pack(fill="x", padx=16, pady=(0, 6))

        # URL input
        url_section = tk.Frame(P, bg=C["bg2"])
        url_section.pack(fill="x", padx=16, pady=(0, 5))
        _section_label(url_section, "Download URL  (Spotify · YouTube · SoundCloud)", C["bg2"]).pack(anchor="w", pady=(0, 2))
        url_row = tk.Frame(url_section, bg=C["bg4"],
                           highlightbackground=C["bg5"], highlightthickness=1)
        url_row.pack(fill="x")
        self.entry_link = tk.Entry(url_row, bg=C["bg4"], fg=C["t1"], bd=0,
                                   insertbackground=C["green"], font=self.fn_normal,
                                   highlightthickness=0)
        self.entry_link.pack(side="left", fill="x", expand=True, ipady=5, padx=(10, 0))
        self._bind_focus_border(self.entry_link, url_row)
        self._add_entry_ctx(self.entry_link)
        self.entry_link.bind("<Return>", lambda _: self._add_to_queue())
        tk.Button(url_row, text="Add to Queue", bg=C["green"], fg=C["t1"],
                  font=self.fn_small, bd=0, relief="flat", cursor="hand2",
                  padx=12, pady=6,
                  highlightbackground=C["green"], highlightcolor=C["green_hi"],
                  highlightthickness=2,
                  activebackground=C["green_hi"], activeforeground=C["t1"],
                  command=self._add_to_queue).pack(side="right")

        # Folder input
        folder_section = tk.Frame(P, bg=C["bg2"])
        folder_section.pack(fill="x", padx=16, pady=(0, 5))
        _section_label(folder_section, "Output Folder", C["bg2"]).pack(anchor="w", pady=(0, 2))
        folder_row = tk.Frame(folder_section, bg=C["bg4"],
                              highlightbackground=C["bg5"], highlightthickness=1)
        folder_row.pack(fill="x")
        self.entry_folder = tk.Entry(folder_row, bg=C["bg4"], fg=C["t2"], bd=0,
                                     insertbackground=C["green"], font=self.fn_normal,
                                     highlightthickness=0)
        self.entry_folder.pack(side="left", fill="x", expand=True, ipady=5, padx=(10, 0))
        self._bind_focus_border(self.entry_folder, folder_row)
        self._add_entry_ctx(self.entry_folder)
        tk.Button(folder_row, text="Browse", bg=C["bg5"], fg=C["t1"],
                  font=self.fn_small, bd=0, relief="flat", cursor="hand2",
                  padx=12, pady=6,
                  highlightbackground=C["green"], highlightcolor=C["green_hi"],
                  highlightthickness=2,
                  activebackground=C["bg5"], activeforeground=C["t1"],
                  command=self._browse_folder).pack(side="right")

        self._build_fqt(P)
        self._build_toolbar(P)

        _divider(P).pack(fill="x", padx=16, pady=(2, 0))

        # Logo
        self.logo_frame = tk.Frame(P, bg=C["bg1"])
        self.logo_frame.pack(fill="both", expand=True)
        self.logo_label = tk.Label(self.logo_frame, bg=C["bg1"], bd=0, highlightthickness=0)
        self.logo_label.place(relx=0.5, rely=0.5, anchor="center")
        self.logo_frame.bind("<Configure>", lambda _: self._schedule_logo_reload())

        self._build_donation(P)

    def _build_fqt(self, parent: tk.Frame) -> None:
        """Format / Quality / Threads segmented controls."""
        card = tk.Frame(parent, bg=C["bg3"])
        card.pack(fill="x", padx=16, pady=(0, 5))
        row  = tk.Frame(card, bg=C["bg3"])
        row.pack(fill="x", padx=10, pady=(6, 5))

        def _group(label: str) -> tk.Frame:
            g = tk.Frame(row, bg=C["bg3"])
            g.pack(side="left")
            _section_label(g, label, C["bg3"]).pack(anchor="w", pady=(0, 2))
            btns = tk.Frame(g, bg=C["bg3"])
            btns.pack()
            return btns

        def _seg_btn(parent: tk.Frame, text: str, cmd) -> tk.Button:
            b = tk.Button(parent, text=text, command=cmd,
                          bg=C["bg4"], fg=C["t2"], font=self.fn_small,
                          bd=0, relief="flat", cursor="hand2", padx=10, pady=3,
                          highlightthickness=0,
                          activebackground=C["bg5"], activeforeground=C["t1"])
            b.bind("<Enter>", lambda e, w=b: w.configure(bg=C["bg5"], fg=C["t1"])
                   if w.cget("bg") != C["green"] else None)
            b.bind("<Leave>", lambda e, w=b: w.configure(bg=C["bg4"], fg=C["t2"])
                   if w.cget("bg") != C["green"] else None)
            return b

        def _vsep():
            _divider(row, orient="v").pack(side="left", fill="y", padx=10)

        # Format
        fmt_btns = _group("Format")
        for lbl, val in (("MP3", "mp3"), ("WAV", "wav"), ("FLAC", "flac")):
            b = _seg_btn(fmt_btns, lbl, lambda v=val: self._sel_fmt(v))
            b.pack(side="left")
            self.fmt_buttons[val] = b

        _vsep()

        # Quality
        q_btns = _group("Quality")
        for q in ("128k", "192k", "320k"):
            b = _seg_btn(q_btns, q, lambda v=q: self._sel_quality(v))
            b.pack(side="left")
            self.quality_buttons[q] = b

        _vsep()

        # Threads
        t_btns = _group("Threads")
        for n in (2, 4, 8):
            label = "4 ★" if n == 4 else str(n)
            b = _seg_btn(t_btns, label, lambda v=n: self._sel_batch(v))
            b.pack(side="left")
            self.batch_buttons[n] = b

        _divider(card).pack(fill="x", padx=12)

        # * Threads footnote
        tk.Label(card,
                 text="* Threads = simultaneous downloads. ★ = recommended. Higher = faster but may cause errors.",
                 bg=C["bg3"], fg=C["t3"],
                 font=font.Font(family="Segoe UI", size=7),
                 anchor="w").pack(fill="x", padx=12, pady=(4, 6))

    def _build_toolbar(self, parent: tk.Frame) -> None:
        bar = tk.Frame(parent, bg=C["bg2"])
        bar.pack(fill="x", padx=16, pady=(0, 2))

        def _tb(icon: str, label: str, cmd) -> tk.Button:
            wrap = tk.Frame(bar, bg=C["bg2"])
            wrap.pack(side="left", expand=True, fill="x", padx=1)
            b = tk.Button(wrap, text=f"{icon}\n{label}", command=cmd,
                          bg=C["bg2"], fg=C["t2"], font=self.fn_tiny,
                          bd=0, relief="flat", cursor="hand2", pady=4,
                          justify="center", highlightthickness=0,
                          activebackground=C["bg3"], activeforeground=C["t1"])
            b.pack(fill="x")
            b.bind("<Enter>", lambda e: b.configure(bg=C["bg3"], fg=C["t1"]))
            b.bind("<Leave>", lambda e: b.configure(bg=C["bg2"], fg=C["t2"]))
            return b

        _tb("🎨", "Insert your logo",  self._change_logo)
        _tb("🔑", "Client ID",         self._change_client_id)
        _tb("🔐", "Client Secret",     self._change_client_secret)
        _tb("📌", "Shortcut",          self._create_shortcut)
        _tb("❓", "How to Setup",      self._show_how_to_setup)
        _tb("🔄", "Update spotdl",     self._check_spotdl_updates)
        _tb("ℹ️", "About",             self._show_about)

    def _build_donation(self, parent: tk.Frame) -> None:
        """Compact single-row donation bar at the bottom of the left panel."""
        card = tk.Frame(parent, bg=C["bg3"],
                        highlightbackground=C["green_lo"], highlightthickness=1)
        card.pack(fill="x", side="bottom", padx=16, pady=(0, 10))

        row = tk.Frame(card, bg=C["bg3"])
        row.pack(fill="x", padx=8, pady=5)

        # ♥ label
        tk.Label(row, text="♥", bg=C["bg3"], fg=C["red"],
                 font=font.Font(family="Segoe UI", size=9, weight="bold")).pack(
                 side="left", padx=(2, 4))

        # "Support" text
        tk.Label(row, text="Support", bg=C["bg3"], fg=C["t2"],
                 font=font.Font(family="Segoe UI", size=8, weight="bold")).pack(
                 side="left", padx=(0, 8))

        # ── Crypto buttons inline ─────────────────────────────────────────────
        for coin, meta in CRYPTO_META.items():
            if coin == "BASE":
                continue

            brand    = meta["color"]
            symbol   = meta["symbol"]
            btn_bg   = C["bg4"]
            btn_fg   = brand
            cmd      = (lambda: self._show_eth_picker()) if coin == "ETH" else (lambda c=coin: self._show_crypto(c))

            b = tk.Button(row, text=f"{symbol} {coin}", command=cmd,
                          bg=btn_bg, fg=btn_fg,
                          font=font.Font(family="Segoe UI", size=7, weight="bold"),
                          bd=0, relief="flat", cursor="hand2",
                          padx=5, pady=3, highlightthickness=0,
                          activebackground=brand, activeforeground=C["t1"])
            b.pack(side="left", padx=2)
            b.bind("<Enter>", lambda e, bg=brand: e.widget.configure(bg=bg, fg=C["t1"]))
            b.bind("<Leave>", lambda e, bg=btn_bg, fg=btn_fg: e.widget.configure(bg=bg, fg=fg))

    # ── Right panel ───────────────────────────────────────────────────────────

    def _build_right(self) -> None:
        P = self.right_panel

        # PanedWindow splits terminal and controls at 50 / 50 — user can drag the sash
        paned = tk.PanedWindow(P, orient="vertical",
                               bg=C["div"], sashwidth=4, sashpad=0,
                               sashrelief="flat", handlesize=0, handlepad=0,
                               opaqueresize=True)
        paned.pack(fill="both", expand=True)

        # ── Top pane: terminal ────────────────────────────────────────────────
        top = tk.Frame(paned, bg=C["bg0"])
        paned.add(top, stretch="always", minsize=120)

        # Console header
        ch = tk.Frame(top, bg=C["bg3"])
        ch.pack(fill="x")
        dots = tk.Frame(ch, bg=C["bg3"])
        dots.pack(side="left", padx=(14, 0), pady=9)
        for color in ("#ED6A5E", "#F4BF4F", "#61C554"):
            tk.Label(dots, text="●", bg=C["bg3"], fg=color,
                     font=self.fn_tiny).pack(side="left", padx=(0, 4))
        tk.Label(ch, text="Terminal", bg=C["bg3"], fg=C["t2"],
                 font=self.fn_small).pack(side="left", padx=12)

        rch = tk.Frame(ch, bg=C["bg3"])
        rch.pack(side="right", padx=12)
        self.status_dot = tk.Label(rch, text="●", bg=C["bg3"], fg=C["t3"], font=self.fn_tiny)
        self.status_dot.pack(side="left", padx=(0, 10))
        clr = tk.Button(rch, text="Clear", command=self._clear_console,
                        bg=C["bg4"], fg=C["t3"], font=self.fn_tiny,
                        bd=0, relief="flat", cursor="hand2", padx=10, pady=2,
                        activebackground=C["bg5"], activeforeground=C["t1"])
        clr.pack(side="left")
        clr.bind("<Enter>", lambda e: clr.configure(fg=C["t1"]))
        clr.bind("<Leave>", lambda e: clr.configure(fg=C["t3"]))

        _divider(top).pack(fill="x")

        self.console = scrolledtext.ScrolledText(
            top, bg=C["bg0"], fg=C["t2"],
            font=self.fn_mono, wrap=tk.WORD, bd=0, state="disabled",
            insertbackground=C["green"],
            selectbackground=C["green_lo"], selectforeground=C["t1"],
            padx=14, pady=10)
        self.console.pack(fill="both", expand=True)
        self._setup_console_tags()
        self._add_console_ctx()

        # ── Bottom pane: progress + queue ─────────────────────────────────────
        bot = tk.Frame(paned, bg=C["bg2"])
        paned.add(bot, stretch="always", minsize=180)

        # Set sash at 50 % after the widget is mapped and has real dimensions
        paned.bind("<Map>", lambda _: paned.after(50, lambda: self._center_sash(paned)))

        # Progress area
        prog = tk.Frame(bot, bg=C["bg2"])
        prog.pack(fill="x", padx=16, pady=(14, 10))
        prog_row = tk.Frame(prog, bg=C["bg2"])
        prog_row.pack(fill="x", pady=(0, 6))
        self.status_text = tk.Label(prog_row, text="Ready", bg=C["bg2"],
                                    fg=C["t2"], font=self.fn_small, anchor="w")
        self.status_text.pack(side="left", fill="x", expand=True)
        self.pct_label = tk.Label(prog_row, text="", bg=C["bg2"],
                                  fg=C["green"], font=self.fn_mono_sm)
        self.pct_label.pack(side="right")
        self.progress_bar = ttk.Progressbar(prog, style="App.Horizontal.TProgressbar",
                                            mode="determinate")
        self.progress_bar.pack(fill="x")

        _divider(bot).pack(fill="x", padx=16, pady=(10, 0))
        self._build_queue(bot)

    def _build_queue(self, parent: tk.Frame) -> None:
        qf = tk.Frame(parent, bg=C["bg2"])
        qf.pack(fill="x")

        # Header
        q_hdr = tk.Frame(qf, bg=C["bg2"])
        q_hdr.pack(fill="x", padx=16, pady=(10, 6))
        _section_label(q_hdr, "Download Queue", C["bg2"]).pack(side="left")
        self.queue_count_label = tk.Label(q_hdr, text="0 items",
                                          bg=C["bg2"], fg=C["t2"], font=self.fn_tiny)
        self.queue_count_label.pack(side="left", padx=6)

        # List
        self.queue_list = tk.Listbox(
            qf, bg=C["bg3"], fg=C["t2"],
            selectmode=tk.SINGLE, height=3,
            font=self.fn_mono_sm, activestyle="none",
            bd=0, highlightthickness=0,
            selectbackground=C["bg5"], selectforeground=C["t1"])
        self.queue_list.pack(fill="x", padx=16, pady=(0, 8))

        # Buttons
        btn_row = tk.Frame(qf, bg=C["bg2"])
        btn_row.pack(fill="x", padx=16, pady=(8, 14))

        def _action_btn(text: str, cmd, accent: str, fg: str) -> tk.Button:
            """Button with a 3 px left accent strip."""
            wrap = tk.Frame(btn_row, bg=C["bg2"])
            wrap.pack(side="left", padx=(0, 8))
            # Left accent strip
            tk.Frame(wrap, bg=accent, width=3).pack(side="left", fill="y")
            b = tk.Button(wrap, text=text, command=cmd,
                          bg=C["bg3"], fg=fg, font=self.fn_small,
                          bd=0, relief="flat", cursor="hand2",
                          padx=14, pady=8, highlightthickness=0,
                          activebackground=C["bg5"], activeforeground=C["t1"])
            b.pack(side="left")
            b.bind("<Enter>", lambda e: b.configure(bg=C["bg5"], fg=C["t1"]))
            b.bind("<Leave>", lambda e: b.configure(bg=C["bg3"], fg=fg))
            return b

        self.btn_remove = _action_btn("✕  Remove",    self._remove_from_queue, "#7B2020", C["red"])
        self.btn_pause  = _action_btn("⏸  Pause",     self._pause_download,    "#7A4A10", C["orange"])
        self.btn_stop   = _action_btn("⬛  Stop",      self._stop_download,     "#5A1A1A", C["red"])
        self.btn_clear  = _action_btn("⌫  Clear All", self._clear_queue,       "#2A2A2A", C["t2"])

        self._add_queue_ctx()

    # ── Console ───────────────────────────────────────────────────────────────

    def _setup_console_tags(self) -> None:
        self.console.tag_configure("ts",      foreground="#FFFFFF",  font=self.fn_mono_sm)
        self.console.tag_configure("success", foreground="#1DB954")
        self.console.tag_configure("error",   foreground="#E05252")
        self.console.tag_configure("warning", foreground="#E8A838")
        self.console.tag_configure("info",    foreground="#5B9BD5")
        self.console.tag_configure("song",    foreground="#C97BC0")
        self.console.tag_configure("folder",  foreground="#D4872A")
        self.console.tag_configure("link",    foreground="#7E8CE0")
        self.console.tag_configure("sep",     foreground="#282828")

    def _clear_console(self) -> None:
        self.console.configure(state="normal")
        self.console.delete("1.0", tk.END)
        self.console.configure(state="disabled")

    def _log(self, msg: str, kind: str = "info") -> None:
        """Thread-safe console output. Call from any thread."""
        ts = datetime.now().strftime("%H:%M:%S")

        def _do() -> None:
            self.console.configure(state="normal")

            # Determine tag from emoji prefix or kind argument
            tag = kind
            if msg.startswith("✅"):    tag = "success"
            elif msg.startswith("❌"):  tag = "error"
            elif msg.startswith("⚠️"):  tag = "warning"
            elif msg.startswith("🎵"):  tag = "song"
            elif msg.startswith("📂"):  tag = "folder"

            # Separator lines: no timestamp, different colour
            is_sep = msg.strip("─ =\n") == ""
            if not is_sep:
                self.console.insert("end", f"{ts}  ", "ts")
            self.console.insert("end", msg + "\n", tag if not is_sep else "sep")

            self.console.see("end")
            self.console.configure(state="disabled")

        if threading.current_thread() is threading.main_thread():
            _do()
        else:
            self.root.after_idle(_do)

    def _set_status(self, text: str, color: str = C["t2"]) -> None:
        """Thread-safe status bar update."""
        dot_map = {C["green"]: C["green"], C["red"]: C["red"], C["orange"]: C["orange"]}

        def _do():
            self.status_text.configure(text=text, fg=color)
            self.status_dot.configure(fg=dot_map.get(color, C["t3"]))

        if threading.current_thread() is threading.main_thread():
            _do()
        else:
            self.root.after_idle(_do)

    def _set_progress(self, value: int, label: str | None = None) -> None:
        """Thread-safe progress bar update (0-100). Pass label="" to clear text."""
        def _do():
            # Stop any running indeterminate animation first
            try:
                self.progress_bar.stop()
                self.progress_bar.configure(mode="determinate")
            except Exception:
                pass
            self.progress_bar.configure(value=max(0, min(100, value)))
            if label is not None:
                self.pct_label.configure(text=label)
            elif value <= 0:
                self.pct_label.configure(text="")
            else:
                if self._dl_total > 1 and self._dl_ok > 0:
                    self.pct_label.configure(text=f"{self._dl_ok}/{self._dl_total}")
                else:
                    self.pct_label.configure(text=f"{value}%")

        if threading.current_thread() is threading.main_thread():
            _do()
        else:
            self.root.after_idle(_do)

    def _set_progress_busy(self, label: str = "Searching…") -> None:
        """Thread-safe: switch progress bar to indeterminate pulsing mode."""
        def _do():
            self.progress_bar.configure(mode="indeterminate")
            self.progress_bar.start(15)  # 15 ms between steps
            self.pct_label.configure(text=label)

        if threading.current_thread() is threading.main_thread():
            _do()
        else:
            self.root.after_idle(_do)

    # ── Entry helpers ─────────────────────────────────────────────────────────

    def _bind_focus_border(self, entry: tk.Entry, frame: tk.Frame) -> None:
        entry.bind("<FocusIn>",  lambda _: frame.configure(highlightbackground=C["green"]))
        entry.bind("<FocusOut>", lambda _: frame.configure(highlightbackground=C["bg5"]))

    def _add_entry_ctx(self, entry: tk.Entry) -> None:
        m = tk.Menu(self.root, tearoff=0, bg=C["bg3"], fg=C["t2"],
                    activebackground=C["bg5"], activeforeground=C["t1"])
        m.add_command(label="Cut",        command=lambda: entry.event_generate("<<Cut>>"))
        m.add_command(label="Copy",       command=lambda: entry.event_generate("<<Copy>>"))
        m.add_command(label="Paste",      command=lambda: entry.event_generate("<<Paste>>"))
        m.add_separator()
        m.add_command(label="Select All", command=lambda: entry.select_range(0, "end"))
        entry.bind("<Button-3>", lambda ev: m.tk_popup(ev.x_root, ev.y_root))

    def _add_console_ctx(self) -> None:
        m = tk.Menu(self.root, tearoff=0, bg=C["bg3"], fg=C["t2"],
                    activebackground=C["bg5"], activeforeground=C["t1"])
        m.add_command(label="Copy",       command=lambda: self.console.event_generate("<<Copy>>"))
        m.add_command(label="Select All", command=lambda: self.console.tag_add("sel", "1.0", "end"))
        m.add_separator()
        m.add_command(label="Clear",      command=self._clear_console)
        self.console.bind("<Button-3>", lambda ev: m.tk_popup(ev.x_root, ev.y_root))

    def _add_queue_ctx(self) -> None:
        m = tk.Menu(self.root, tearoff=0, bg=C["bg3"], fg=C["t2"],
                    activebackground=C["bg5"], activeforeground=C["t1"])
        m.add_command(label="Copy URL",   command=self._copy_link)
        m.add_command(label="Move Up",    command=self._q_up)
        m.add_command(label="Move Down",  command=self._q_down)
        m.add_separator()
        m.add_command(label="Remove",     command=self._remove_from_queue)

        def _show(ev):
            self.queue_list.selection_clear(0, tk.END)
            self.queue_list.selection_set(self.queue_list.nearest(ev.y))
            try:
                m.tk_popup(ev.x_root, ev.y_root)
            finally:
                m.grab_release()

        self.queue_list.bind("<Button-3>", _show)

    # ── Toggle button state ───────────────────────────────────────────────────

    def _sel_fmt(self, val: str) -> None:
        prev = self.format_var.get()
        self.format_var.set(val)
        for v, b in self.fmt_buttons.items():
            b.configure(bg=C["green"] if v == val else C["bg4"],
                        fg=C["t1"]   if v == val else C["t2"])
        if val != prev:
            s = self._read_cfg()
            s["preferred_format"] = val
            self._write_cfg(s)

    def _sel_quality(self, val: str) -> None:
        prev = self.quality_var.get()
        self.quality_var.set(val)
        for v, b in self.quality_buttons.items():
            b.configure(bg=C["green"] if v == val else C["bg4"],
                        fg=C["t1"]   if v == val else C["t2"])
        if val != prev:
            s = self._read_cfg()
            s["preferred_quality"] = val
            self._write_cfg(s)

    def _sel_batch(self, val: int) -> None:
        prev = self.batch_size
        self.batch_size = int(val)
        for v, b in self.batch_buttons.items():
            b.configure(bg=C["green"] if v == val else C["bg4"],
                        fg=C["t1"]   if v == val else C["t2"])
        if self.batch_size != prev:
            s = self._read_cfg()
            s["preferred_threads"] = self.batch_size
            self._write_cfg(s)

    # ── Dialogs ───────────────────────────────────────────────────────────────

    def _browse_folder(self) -> None:
        folder = filedialog.askdirectory(
            initialdir=self.entry_folder.get() or os.path.expanduser("~"))
        if folder:
            self.entry_folder.delete(0, tk.END)
            self.entry_folder.insert(0, folder)
            s = self._read_cfg()
            s["default_output_folder"] = folder
            self._write_cfg(s)

    def _change_logo(self) -> None:
        path = filedialog.askopenfilename(
            title="Select Logo",
            filetypes=[("Image files", "*.png *.jpg *.jpeg *.gif *.bmp"), ("All", "*.*")])
        if path:
            s = self._read_cfg()
            s["custom_logo_path"] = path
            self._write_cfg(s)
            self._load_logo()
            self._log("✅  Logo updated", "success")

    def _change_client_id(self) -> None:
        val = simpledialog.askstring("Client ID",
                                     "Enter your Client ID:", parent=self.root)
        if val:
            s = self._read_cfg()
            s["client_id"] = val.strip()
            self._write_cfg(s)
            self._invalidate_spotdl_client()
            self._init_spotify_client()
            self._log("✅  Client ID saved", "success")

    def _change_client_secret(self) -> None:
        val = simpledialog.askstring("Client Secret",
                                     "Enter your Client Secret:",
                                     parent=self.root, show="*")
        if val:
            s = self._read_cfg()
            s["client_secret"] = val.strip()
            self._write_cfg(s)
            self._invalidate_spotdl_client()
            self._init_spotify_client()
            self._log("✅  Client Secret saved", "success")

    def _invalidate_spotdl_client(self) -> None:
        """Discard the cached client AND reset the SpotifyClient singleton so
        the next download can create a fresh _Spotdl with new credentials."""
        with self._spotdl_lock:
            self._spotdl_client     = None
            self._spotdl_init_creds = None
            try:
                from spotdl.utils.spotify import SpotifyClient
                SpotifyClient._instance = None
            except Exception:
                pass

    # ── URL / Queue ───────────────────────────────────────────────────────────

    def _url_platform(self, url: str) -> str:
        """Return 'spotify', 'youtube', 'soundcloud', or 'unknown'."""
        if "spotify.com" in url:
            return "spotify"
        if "youtube.com" in url or "youtu.be" in url:
            # covers youtube.com, music.youtube.com, www.youtube.com
            return "youtube"
        if "soundcloud.com" in url:
            return "soundcloud"
        return "unknown"

    def _url_type(self, url: str) -> str:
        """Detect content type for a supported URL."""
        platform = self._url_platform(url)
        if platform == "spotify":
            m = re.search(r"spotify\.com/(playlist|album|track|artist)/", url)
            return m.group(1) if m else "unknown"
        if platform == "youtube":
            if "list=" in url or "/playlist" in url:
                return "playlist"
            return "track"   # watch?v=, music.youtube.com/watch?v=, youtu.be/
        if platform == "soundcloud":
            if "/sets/" in url:
                return "playlist"
            # artist page (exactly soundcloud.com/ARTIST with no extra path)
            path = urllib.parse.urlparse(url).path.strip("/")
            if path and "/" not in path:
                return "artist"
            return "track"
        return "unknown"

    def _get_label(self, url: str) -> str:
        """Return a human-readable queue label for any supported URL."""
        platform = self._url_platform(url)
        kind     = self._url_type(url)

        # ── Spotify: use the API for rich labels ─────────────────────────────
        if platform == "spotify":
            id_match = re.search(
                r"spotify\.com/(?:playlist|album|track|artist)/([A-Za-z0-9]+)", url)
            item_id = id_match.group(1) if id_match else None

            if self.sp and item_id:
                try:
                    if kind == "playlist":
                        pl = _spotify_call(self.sp.playlist, item_id,
                                           fields="name,tracks.total")
                        return f"📑  {pl['name']}  ({pl['tracks']['total']} tracks)"
                    if kind == "album":
                        al = _spotify_call(self.sp.album, item_id)
                        return f"💿  {al['name']}  ({al['total_tracks']} tracks)"
                    if kind == "track":
                        tr = _spotify_call(self.sp.track, item_id)
                        artists = ", ".join(a["name"] for a in tr["artists"])
                        return f"🎵  {artists} — {tr['name']}"
                    if kind == "artist":
                        ar = _spotify_call(self.sp.artist, item_id)
                        return f"👤  {ar['name']}"
                except Exception as exc:
                    if "403" not in str(exc):
                        self._log(f"⚠️  API error: {exc}", "warning")

            fallback = {
                "playlist": "📑  Spotify Playlist",
                "album":    "💿  Spotify Album",
                "track":    "🎵  Spotify Track",
                "artist":   "👤  Spotify Artist",
            }
            return fallback.get(kind, f"🔗  {url}")

        # ── YouTube ──────────────────────────────────────────────────────────
        if platform == "youtube":
            if kind == "playlist":
                return "📑  YouTube Playlist"
            return "🎵  YouTube Video"

        # ── SoundCloud — resolve URL for rich label ───────────────────────────
        if platform == "soundcloud":
            try:
                from soundcloud import SoundCloud as _SC
                sc       = _SC()
                resource = sc.resolve(url)
                if resource is not None:
                    rtype = type(resource).__name__
                    if rtype == "Track":
                        artist = getattr(getattr(resource, "user", None), "username", "") or ""
                        title  = getattr(resource, "title", "") or ""
                        return f"🎵  {artist} — {title}" if artist else f"🎵  {title}"
                    if rtype in ("AlbumPlaylist", "BasicAlbumPlaylist"):
                        name  = getattr(resource, "title", "SoundCloud Set") or "SoundCloud Set"
                        count = getattr(resource, "track_count", None)
                        return f"📑  {name}  ({count} tracks)" if count else f"📑  {name}"
                    if rtype == "User":
                        name = getattr(resource, "username", "SoundCloud Artist") or "SoundCloud Artist"
                        return f"👤  {name}"
            except Exception:
                pass
            # Fallback if resolve fails
            if kind == "playlist":
                return "📑  SoundCloud Set"
            if kind == "artist":
                return "👤  SoundCloud Artist"
            return "🎵  SoundCloud Track"

        return f"🔗  {url}"

    def _add_to_queue(self) -> None:
        raw = self.entry_link.get().strip()
        if not raw:
            self._log("⚠️  Please paste a URL (Spotify, YouTube or SoundCloud)", "warning")
            return

        platform = self._url_platform(raw)

        # ── Clean and normalise URL per platform ─────────────────────────────
        if platform == "youtube":
            # Keep only v= and list= — strip tracking params (si=, pp=, etc.)
            parsed = urllib.parse.urlparse(raw)
            qs     = urllib.parse.parse_qs(parsed.query)
            keep   = {k: v for k, v in qs.items() if k in ("v", "list")}
            new_qs = urllib.parse.urlencode(keep, doseq=True)
            url    = urllib.parse.urlunparse(parsed._replace(query=new_qs, fragment="")).rstrip("/")

            # spotdl only handles music.youtube.com/watch?v= directly.
            # Regular youtube.com/watch?v= and youtu.be/ fall through to a
            # Spotify text search (unreliable).  Convert them so spotdl gets
            # the correct YouTube Music URL and downloads the right track.
            vid_m = re.search(r"(?:youtube\.com/watch\?.*v=|youtu\.be/)([A-Za-z0-9_-]{11})", url)
            if vid_m:
                url = f"https://music.youtube.com/watch?v={vid_m.group(1)}"
            elif "youtube.com/playlist" in url:
                url = url.replace("www.youtube.com", "music.youtube.com")

        elif platform == "soundcloud":
            url = raw.split("?")[0].split("#")[0].rstrip("/")
            # SoundCloud URLs are passed directly to spotdl.  spotdl will use
            # them as the download_url via yt-dlp, which fully supports
            # SoundCloud.  Tracks, playlists (/sets/), and artist pages all work.

        else:
            url = raw.split("?")[0].split("#")[0].rstrip("/")

        # Normalize Spotify locale-prefixed URLs:
        # open.spotify.com/intl-es/album/ID  →  open.spotify.com/album/ID
        if platform == "spotify":
            url = re.sub(
                r"(open\.spotify\.com)/(?!playlist|album|track|artist)[a-z][a-z0-9-]+/",
                r"\1/", url)

        if platform == "unknown":
            self._log(
                "❌  Unsupported URL — paste a Spotify, YouTube or SoundCloud link",
                "error")
            return

        if self._url_type(url) == "unknown":
            self._log("❌  Unrecognised URL type (track, album, playlist, artist, video…)",
                      "error")
            return

        # Fetch label in background to avoid freezing the UI
        self.entry_link.delete(0, tk.END)
        placeholder = f"🔗  {url}"
        with self._queue_lock:
            self.download_queue.append((url, placeholder))
            idx = len(self.download_queue) - 1   # capture inside lock — safe
        self.queue_list.insert(tk.END, f"  {placeholder}")
        self._update_queue_count()
        self._log(f"ℹ️  Queuing:  {url}", "info")

        def _fetch():
            label = self._get_label(url)
            with self._queue_lock:
                if idx < len(self.download_queue) and self.download_queue[idx][0] == url:
                    self.download_queue[idx] = (url, label)
            color = (C["green"] if "📑" in label else
                     C["blue"]  if "💿" in label else
                     "#E74C6F"  if "🎵" in label else C["t2"])

            def _update_ui():
                # Validate idx is still valid and still refers to the same URL
                if idx < self.queue_list.size():
                    self.queue_list.delete(idx)
                    self.queue_list.insert(idx, f"  {label}")
                    self.queue_list.itemconfig(idx, fg=color)
                self._log(f"✅  Queued: {label}", "success")
                if not self.is_downloading:
                    self._start_download()

            self.root.after_idle(_update_ui)

        threading.Thread(target=_fetch, daemon=True).start()

    def _update_queue_count(self) -> None:
        n = len(self.download_queue)
        self.queue_count_label.configure(text=f"{n} item{'s' if n != 1 else ''}")

    def _remove_from_queue(self) -> None:
        sel = self.queue_list.curselection()
        if not sel:
            return
        i = sel[0]
        # Don't allow removing an item that is currently being downloaded
        if i == 0 and self.is_downloading:
            self._log("⚠️  Cannot remove the item currently being downloaded — stop it first",
                      "warning")
            return
        with self._queue_lock:
            self.download_queue.pop(i)
        self.queue_list.delete(i)
        self._update_queue_count()

    def _clear_queue(self) -> None:
        if self.is_downloading:
            self._log("⚠️  Stop the current download before clearing the queue", "warning")
            return
        with self._queue_lock:
            self.download_queue.clear()
        self.queue_list.delete(0, tk.END)
        self._update_queue_count()
        self._log("✅  Queue cleared", "success")

    def _copy_link(self) -> None:
        sel = self.queue_list.curselection()
        if sel:
            url, _ = self.download_queue[sel[0]]
            self.root.clipboard_clear()
            self.root.clipboard_append(url)
            self._log("✅  URL copied", "success")

    def _q_up(self) -> None:
        sel = self.queue_list.curselection()
        if not sel:
            return
        i = sel[0]
        # Cannot move item 0 up (and cannot move the active download item)
        if i == 0:
            return
        # Don't let the user move the currently-downloading item (always idx 0)
        # or swap any item with it while a download is in progress.
        if self.is_downloading and i == 1:
            self._log("⚠️  Cannot move ahead of the active download", "warning")
            return
        with self._queue_lock:
            self.download_queue[i], self.download_queue[i - 1] = (
                self.download_queue[i - 1], self.download_queue[i])
        text  = self.queue_list.get(i)
        color = self.queue_list.itemcget(i, "fg")
        self.queue_list.delete(i)
        self.queue_list.insert(i - 1, text)
        self.queue_list.itemconfig(i - 1, fg=color)
        self.queue_list.selection_set(i - 1)

    def _q_down(self) -> None:
        sel = self.queue_list.curselection()
        if not sel or sel[0] >= self.queue_list.size() - 1:
            return
        i = sel[0]
        # Don't allow moving the active download item out of position 0
        if self.is_downloading and i == 0:
            self._log("⚠️  Cannot move the active download", "warning")
            return
        with self._queue_lock:
            self.download_queue[i], self.download_queue[i + 1] = (
                self.download_queue[i + 1], self.download_queue[i])
        text  = self.queue_list.get(i)
        color = self.queue_list.itemcget(i, "fg")
        self.queue_list.delete(i)
        self.queue_list.insert(i + 1, text)
        self.queue_list.itemconfig(i + 1, fg=color)
        self.queue_list.selection_set(i + 1)

    # ── Download control ──────────────────────────────────────────────────────

    def _start_download(self) -> None:
        if not self.download_queue or self.is_downloading:
            return
        self.is_downloading = True
        url, label = self.download_queue[0]
        folder = self.entry_folder.get().strip()
        if not folder:
            folder = os.path.join(os.path.expanduser("~"), "Downloads", "SpotRR")
            self.entry_folder.delete(0, tk.END)
            self.entry_folder.insert(0, folder)

        threading.Thread(
            target=self._worker,
            args=(url, label, folder, self.format_var.get(), self.quality_var.get()),
            daemon=True,
        ).start()

    def _stop_download(self) -> None:
        if not self.is_downloading:
            self._log("ℹ️  No active download", "info")
            return
        self.is_downloading = False  # signal worker to exit after current track

        proc = self.current_process
        if proc is not None:
            # Subprocess mode — terminate immediately
            def _kill():
                try:
                    proc.terminate()
                    for _ in range(15):
                        if proc.poll() is not None:
                            break
                        time.sleep(0.1)
                    if proc.poll() is None:
                        proc.kill()
                except Exception:
                    pass
            threading.Thread(target=_kill, daemon=True).start()
            self._log("🛑  Download stopped", "warning")
        else:
            # In-process spotdl — current track will finish, no more after it
            self._log(
                "🛑  Stop requested — current track will finish, then downloads stop.",
                "warning")

        self._set_status("Stopping…", C["red"])
        self._set_progress(0)

    def _pause_download(self) -> None:
        if not self.is_downloading:
            self._log("ℹ️  No active download", "info")
            return
        self.download_paused = not self.download_paused
        if self.download_paused:
            self._log("⏸️  Paused", "warning")
            self.btn_pause.configure(text="▶  Resume")
            self._set_status("Paused", C["orange"])
        else:
            self._log("▶️  Resumed", "success")
            self.btn_pause.configure(text="⏸  Pause")
            self._set_status("Downloading…", C["green"])

    def _finish(self) -> None:
        """Called from the worker thread when a download completes or is stopped."""
        with self._queue_lock:
            if self.download_queue:
                self.download_queue.pop(0)

        self.is_downloading  = False
        self.download_paused = False

        def _ui():
            if self.queue_list.size() > 0:
                self.queue_list.delete(0)
            self._update_queue_count()
            self.btn_pause.configure(text="⏸  Pause")
            if self.download_queue:
                self._start_download()
            else:
                # Queue empty — reset to Ready after a short delay so the
                # "Complete" / summary message remains visible for a moment.
                def _deferred_ready():
                    if not self.is_downloading:
                        self._set_status("Ready", C["t2"])
                        self._set_progress(0, "")
                self.root.after(4000, _deferred_ready)

        self.root.after_idle(_ui)

    # ── Download worker ───────────────────────────────────────────────────────

    def _worker(self, url: str, label: str, folder: str, fmt: str, quality: str) -> None:
        try:
            os.makedirs(folder, exist_ok=True)

            # Reset per-download counters
            self._dl_ok    = 0
            self._dl_fail  = 0
            self._dl_total = 0

            self._log(f"\n{'─' * 50}")
            self._log(f"🎵  {label}", "song")
            self._log(f"📂  {folder}", "folder")
            self._log(f"     {fmt.upper()} · {quality} · {self.batch_size} thread(s)")
            self._log(f"{'─' * 50}\n")

            # Block Spotify downloads without credentials — they will always fail
            if "spotify.com" in url:
                cid, cs = self._get_creds()
                if not (cid and cs):
                    self._log(
                        "❌  Spotify credentials required.\n"
                        "     Click 🔑 Client ID and 🔐 Client Secret to add them.\n"
                        "     See ❓ How to Setup for step-by-step instructions.",
                        "error")
                    self._set_status("No credentials", C["red"])
                    return   # abort before wasting time on a doomed download

            # Warn if FFmpeg is missing for lossless formats
            if fmt in ("wav", "flac"):
                ffpath = _find_ffmpeg()
                if ffpath == "ffmpeg" and not shutil.which("ffmpeg"):
                    self._log(
                        "⚠️  FFmpeg not found — WAV/FLAC conversion will fail.\n"
                        "     Run setup.bat again to download FFmpeg automatically.",
                        "warning")

            self._set_status(f"Downloading…  {label[:42]}", C["green"])
            self._set_progress(0)

            success = self._run_spotdl(url, folder, fmt, quality)

            if success:
                self._show_download_summary(label)
            else:
                if self.is_downloading:
                    # is_downloading still True → genuine failure (not a user stop)
                    self._log(f"❌  Failed: {label}", "error")
                    self._set_status("Failed", C["red"])
                self._set_progress(0, "")
        except Exception as exc:
            self._log(f"❌  Unexpected error: {exc}", "error")
            import traceback
            self._log(traceback.format_exc(), "error")
            self._set_status("Error", C["red"])
            self._set_progress(0, "")
        finally:
            self._finish()

    def _show_download_summary(self, label: str) -> None:
        """Log a human-friendly summary and update the status bar."""
        ok, fail, total = self._dl_ok, self._dl_fail, self._dl_total

        # If spotdl didn't emit count lines, fall back to just "Complete"
        if ok == 0 and fail == 0:
            self._log(f"✅  Complete: {label}", "success")
            self._set_status("Complete", C["green"])
            self._set_progress(100)
            self._notify("SpotRR — Download complete", label[:60])
            return

        denominator = ok + fail
        if fail == 0:
            self._log(f"✅  {ok}/{denominator} tracks downloaded — {label}", "success")
            self._set_status(f"Complete  ·  {ok} track{'s' if ok != 1 else ''}", C["green"])
            self._notify("SpotRR — Download complete",
                         f"{ok} track{'s' if ok != 1 else ''} downloaded")
        else:
            self._log(
                f"⚠️  {ok}/{denominator} tracks downloaded · {fail} failed\n"
                f"     Failed tracks may be unavailable right now.\n"
                f"     Try again later or check with a VPN.",
                "warning")
            self._set_status(
                f"{ok}/{denominator} downloaded  ·  {fail} failed",
                C["orange"])
            self._notify("SpotRR — Download finished",
                         f"{ok}/{denominator} tracks  ·  {fail} failed")
        self._set_progress(100)

    def _resolve_soundcloud_songs(self, url: str) -> list:
        """Resolve a SoundCloud URL to a list of Song objects with download_url set.

        spotdl has no native SoundCloud URL discovery — it would fall through to a
        Spotify text search and return at most one (possibly wrong) result.
        Instead we use the soundcloud library directly:
          - Track URL   → one Song
          - Set/Playlist → all tracks in the set
          - Artist page  → all public tracks of the artist
        Each Song has download_url = SoundCloud permalink_url so yt-dlp downloads
        directly from SoundCloud without any Spotify search involved.
        """
        try:
            from soundcloud import SoundCloud as _SC
            from spotdl.types.song import Song as _Song
        except ImportError as e:
            self._log(f"⚠️  SoundCloud library missing: {e}", "warning")
            return []

        try:
            sc       = _SC()
            resource = sc.resolve(url)
        except Exception as e:
            self._log(f"⚠️  SoundCloud resolve error: {e}", "warning")
            return []

        if resource is None:
            self._log("⚠️  SoundCloud URL could not be resolved", "warning")
            return []

        kind = type(resource).__name__

        # ── Collect raw Track objects ─────────────────────────────────────────
        raw_tracks: list = []
        try:
            if kind == "Track":
                raw_tracks = [resource]

            elif kind in ("AlbumPlaylist", "BasicAlbumPlaylist"):
                playlist = sc.get_playlist(resource.id)
                if playlist and playlist.tracks:
                    raw_tracks = [t for t in playlist.tracks
                                  if hasattr(t, "permalink_url") and t.permalink_url]

            elif kind == "User":
                raw_tracks = list(sc.get_user_tracks(resource.id))

            else:
                self._log(f"⚠️  Unrecognised SoundCloud resource type: {kind}", "warning")

        except Exception as e:
            self._log(f"⚠️  SoundCloud fetch error: {e}", "warning")

        # ── Convert to Song objects ───────────────────────────────────────────
        songs: list = []
        total = len(raw_tracks)
        for track in raw_tracks:
            try:
                permalink = getattr(track, "permalink_url", None)
                if not permalink:
                    continue
                artist   = getattr(getattr(track, "user", None), "username", "Unknown") or "Unknown"
                title    = getattr(track, "title", "Unknown") or "Unknown"
                duration = max(0, (getattr(track, "full_duration", 0) or 0) // 1000)
                cover    = getattr(track, "artwork_url", None)
                track_id = str(getattr(track, "id", "") or "")
                songs.append(_Song.from_missing_data(
                    name          = title,
                    artists       = [artist],
                    artist        = artist,
                    genres        = [],        # [] ≠ None → won't trigger reinit_song()
                    disc_number   = 1,
                    disc_count    = 1,
                    album_name    = artist,
                    album_artist  = artist,
                    duration      = duration,
                    year          = 0,
                    date          = "",
                    track_number  = len(songs) + 1,
                    tracks_count  = total,
                    song_id       = track_id,
                    album_id      = track_id,  # non-None → prevents reinit_song() crash
                    explicit      = False,
                    publisher     = "",
                    url           = permalink,
                    isrc          = "",        # "" not None — mutagen TSRC frame rejects None
                    cover_url     = cover,
                    copyright_text= "",        # "" not None — same reason
                    download_url  = permalink,
                ))
            except Exception:
                pass

        return songs

    def _resolve_spotify_songs(self, url: str) -> list:
        """Fetch all songs from a Spotify playlist or album using parallel API pages.

        Bypasses spotdl's sequential pagination (which makes one HTTP call per page
        of 100 tracks) by fetching all pages concurrently with our own spotipy client.
        Falls back to an empty list on any error so the caller can use client.search().
        """
        import concurrent.futures

        try:
            from spotdl.types.song import Song as _Song
        except ImportError:
            return []

        if not self.sp:
            return []

        m = re.search(r"spotify\.com/(playlist|album)/([A-Za-z0-9]+)", url)
        if not m:
            return []
        kind, item_id = m.group(1), m.group(2)

        all_items: list = []
        album_meta: dict | None = None

        try:
            if kind == "playlist":
                _fields = (
                    "items(track(id,name,duration_ms,disc_number,track_number,"
                    "explicit,external_ids(isrc),external_urls(spotify),"
                    "artists(name),album(id,name,album_type,total_tracks,"
                    "release_date,images,artists(name)))),next,total"
                )
                resp = _spotify_call(self.sp.playlist_items, item_id,
                                     limit=100, fields=_fields)
                if resp is None:
                    return []
                total     = resp.get("total", 0)
                all_items = list(resp.get("items", []))
                offsets   = list(range(100, total, 100))

                if offsets:
                    def _fetch_pl_page(offset: int) -> list:
                        try:
                            r = _spotify_call(self.sp.playlist_items, item_id,
                                              limit=100, offset=offset, fields=_fields)
                            return r.get("items", []) if r else []
                        except Exception:
                            return []

                    with concurrent.futures.ThreadPoolExecutor(
                            max_workers=min(5, len(offsets))) as pool:
                        for page in pool.map(_fetch_pl_page, offsets):
                            all_items.extend(page)

            else:  # album
                album_data = _spotify_call(self.sp.album, item_id)
                if album_data is None:
                    return []
                album_meta = {
                    "id":           album_data.get("id"),
                    "name":         album_data.get("name"),
                    "album_type":   album_data.get("album_type"),
                    "total_tracks": album_data.get("total_tracks"),
                    "release_date": album_data.get("release_date"),
                    "images":       album_data.get("images", []),
                    "artists":      album_data.get("artists", []),
                }
                tracks_resp = album_data.get("tracks") or {}
                all_items   = list(tracks_resp.get("items", []))
                total       = tracks_resp.get("total", len(all_items))
                offsets     = list(range(50, total, 50))

                if offsets:
                    def _fetch_al_page(offset: int) -> list:
                        try:
                            r = _spotify_call(self.sp.album_tracks, item_id,
                                              limit=50, offset=offset)
                            return r.get("items", []) if r else []
                        except Exception:
                            return []

                    with concurrent.futures.ThreadPoolExecutor(
                            max_workers=min(5, len(offsets))) as pool:
                        for page in pool.map(_fetch_al_page, offsets):
                            all_items.extend(page)

        except Exception as exc:
            if "403" not in str(exc):
                self._log(f"⚠️  Spotify fast-fetch failed, using fallback: {exc}", "warning")
            return []

        songs = []
        for track_no, item in enumerate(all_items):
            try:
                if kind == "playlist":
                    track_meta = (item.get("track") or item.get("item")) if isinstance(item, dict) else None
                else:
                    track_meta = item

                if not isinstance(track_meta, dict):
                    continue
                if track_meta.get("is_local"):
                    continue
                if track_meta.get("type") not in ("track", None):
                    continue
                track_id = track_meta.get("id")
                if not track_id or track_meta.get("duration_ms", 1) == 0:
                    continue

                t_album   = (track_meta.get("album") or {}) if kind == "playlist" else (album_meta or {})
                rel_date  = t_album.get("release_date") if t_album else None
                artists   = [a["name"] for a in (track_meta.get("artists") or [])
                             if isinstance(a, dict) and a.get("name")]
                if not artists:
                    continue

                images    = t_album.get("images", []) if t_album else []
                cover_url = None
                if images:
                    try:
                        cover_url = max(
                            images,
                            key=lambda i: ((i.get("width") or 0) * (i.get("height") or 0))
                        )["url"]
                    except Exception:
                        pass

                al_artists  = t_album.get("artists", []) if t_album else []
                ext_ids     = track_meta.get("external_ids") or {}
                ext_urls    = track_meta.get("external_urls") or {}

                song = _Song.from_missing_data(
                    name         = track_meta["name"],
                    artists      = artists,
                    artist       = artists[0],
                    album_id     = t_album.get("id") if t_album else None,
                    album_name   = t_album.get("name") if t_album else None,
                    album_artist = (al_artists[0]["name"] if al_artists else None),
                    album_type   = t_album.get("album_type") if t_album else None,
                    disc_number  = track_meta.get("disc_number", 1),
                    duration     = int(track_meta.get("duration_ms", 0) / 1000),
                    year         = rel_date[:4] if rel_date else None,
                    date         = rel_date,
                    track_number = track_meta.get("track_number", track_no + 1),
                    tracks_count = t_album.get("total_tracks") if t_album else None,
                    song_id      = track_id,
                    explicit     = track_meta.get("explicit", False),
                    url          = ext_urls.get("spotify", ""),
                    isrc         = ext_ids.get("isrc", ""),
                    cover_url    = cover_url,
                    list_position= track_no + 1,
                )
                songs.append(song)
            except Exception:
                pass

        return songs

    def _run_spotdl(self, url: str, folder: str, fmt: str, quality: str) -> bool:
        """Download via spotdl's Python API (in-process, batched for pause/stop support)."""
        import logging as _logging

        try:
            from spotdl import Spotdl as _Spotdl
        except ImportError:
            self._log("❌  spotdl not available — run setup.bat", "error")
            return False

        cid, cs    = self._get_creds()
        ffmpeg     = _find_ffmpeg()
        creds_key  = (cid or "", cs or "")
        _providers = ("youtube-music", "youtube", "soundcloud")

        settings = {
            "output":          folder,
            "format":          fmt,
            "bitrate":         quality,
            "threads":         self.batch_size,
            "ffmpeg":          ffmpeg,
            "audio_providers": list(_providers),
            "simple_tui":      True,
            "print_errors":    False,
            "log_format":      None,
        }

        with self._spotdl_lock:
            if self._spotdl_client is not None and self._spotdl_init_creds == creds_key:
                # Reuse existing client — SpotifyClient singleton stays untouched.
                # Just update the per-download mutable settings so format/quality/
                # output/threads changes take effect without recreating anything.
                client = self._spotdl_client
            else:
                # First launch, or credentials changed.
                # Reset the SpotifyClient singleton so _Spotdl.__init__ can call
                # SpotifyClient.init() without hitting "already initialized".
                try:
                    from spotdl.utils.spotify import SpotifyClient as _SC
                    _SC._instance = None
                except Exception:
                    pass
                client = _Spotdl(
                    client_id=cid or "",
                    client_secret=cs or "",
                    downloader_settings=settings,
                )
                self._spotdl_client     = client
                self._spotdl_init_creds = creds_key

            # Always refresh per-download settings on the cached client.
            for k in ("output", "format", "bitrate", "threads"):
                client.downloader.settings[k] = settings[k]
            client.downloader.settings["audio_providers"] = settings["audio_providers"]

            # Rebuild the asyncio Semaphore to match the current thread count.
            # The semaphore is created once at Downloader.__init__ and never
            # updated when settings["threads"] changes — so changing from 4 to 8
            # threads in the UI had no effect on actual concurrency.
            client.downloader.semaphore = asyncio.Semaphore(settings["threads"])

        # ── Log handler ────────────────────────────────────────────────────────
        # Tracks completed count for the progress bar.
        # _verbose[0] = True during first pass (show not-found inline),
        #               False during retries (suppress spam; final list shown at end).
        _completed = [0]
        _verbose   = [True]
        _app       = self

        class _Fwd(_logging.Handler):
            def emit(self, record: _logging.LogRecord) -> None:
                try:
                    msg = self.format(record)
                    lvl = record.levelno

                    if 'Downloaded "' in msg or "Downloaded '" in msg:
                        _completed[0] += 1
                        done  = _completed[0]
                        total = _app._dl_total
                        pct   = int(done / total * 100) if total else 100
                        _app._set_progress(pct)
                        _app._set_status(f"Downloading…  {done}/{total} track{'s' if total != 1 else ''}", C["green"])
                        m    = re.search(r'Downloaded ["\'](.+?)["\']', msg)
                        name = m.group(1) if m else "track"
                        _app._log(f"✅  [{done}/{total}]  {name}", "success")

                    elif "No results found" in msg or "LookupError" in msg:
                        if _verbose[0]:
                            m = re.search(r"for song:\s*(.+)", msg)
                            name = m.group(1).strip() if m else msg[:120]
                            _app._log(f"⚠️  Not found: {name}", "warning")

                    elif "AudioProviderError" in msg or "YT-DLP download error" in msg:
                        if _verbose[0]:
                            _app._log(f"⚠️  {msg[:200]}", "warning")

                    elif "Skipping" in msg:
                        _app._log(f"ℹ️   {msg}", "info")

                    elif lvl >= _logging.ERROR:
                        _app._log(msg[:300], "error")

                    elif lvl >= _logging.WARNING and "spotdl" in record.name:
                        _app._log(msg[:200], "warning")

                except Exception:
                    pass

        handler = _Fwd()
        handler.setFormatter(_logging.Formatter("%(message)s"))

        watched: list[tuple[_logging.Logger, int]] = []
        for lg_name in ("spotdl", "yt_dlp"):
            lg = _logging.getLogger(lg_name)
            lg.addHandler(handler)
            watched.append((lg, lg.level))
            lg.setLevel(_logging.INFO)

        # The Downloader creates its asyncio event loop in whichever thread calls
        # __init__ (the first worker thread) and sets it there via
        # asyncio.set_event_loop().  Every subsequent worker thread is a NEW
        # thread with no loop assigned — asyncio.gather() raises
        # "There is no current event loop in thread X" without this line.
        asyncio.set_event_loop(client.downloader.loop)

        def _check_pause_stop() -> bool:
            """Block while paused; return False if stopped."""
            while self.download_paused and self.is_downloading:
                time.sleep(0.2)
            return self.is_downloading

        try:
            if not self.is_downloading:
                return False

            platform  = self._url_platform(url)
            src_label = {"spotify": "Spotify", "youtube": "YouTube",
                         "soundcloud": "SoundCloud"}.get(platform, "source")
            self._set_status(f"Searching {src_label}…", C["blue"])
            self._set_progress_busy("Searching…")

            # SoundCloud: resolve URL directly to get ALL tracks.
            # spotdl's parse_query has no standalone SoundCloud URL handler —
            # it would fall through to a Spotify text search and return only
            # one (possibly wrong) result.  We bypass it completely and use
            # the soundcloud library's resolve() + get_user_tracks() instead.
            #
            # Spotify playlists/albums: bypass spotdl's sequential pagination
            # (playlist() + playlist_items() + N×next()) with parallel page
            # fetches via our own spotipy client.  Falls back to client.search()
            # if anything goes wrong (e.g. no credentials, rate-limit, etc.).
            kind = self._url_type(url)
            if platform == "soundcloud":
                songs = self._resolve_soundcloud_songs(url)
            elif platform == "spotify" and kind in ("playlist", "album") and self.sp:
                songs = self._resolve_spotify_songs(url)
                if not songs:
                    songs = client.search([url])
            else:
                songs = client.search([url])

            self._dl_total = len(songs)
            self._set_progress(0)

            if not songs:
                self._log("❌  No songs found for this URL", "error")
                return False

            self._log(
                f"ℹ️   Found {self._dl_total} song{'s' if self._dl_total != 1 else ''}",
                "info")

            if not _check_pause_stop():
                return False

            # ── First pass: download in batches ───────────────────────────────
            # spotdl's asyncio.gather + Semaphore model fills empty slots the
            # instant a song finishes — no idle time within a batch.  The only
            # overhead is the gap between our manual batch calls.  Using a batch
            # 8× the thread count (min 32) makes that gap negligible: with 4
            # threads and 32 songs per batch, a straggler only idles slots for
            # the final ≤4 songs of each batch instead of every batch of 4.
            # Pause/Stop still works between batches.
            all_songs = list(songs)
            pending   = []
            batch_sz  = min(len(all_songs), max(self.batch_size * 8, 32))

            for i in range(0, len(all_songs), batch_sz):
                if not _check_pause_stop():
                    break
                batch   = all_songs[i:i + batch_sz]
                results = client.download_songs(batch)
                self._dl_ok += sum(1 for _, p in results if p is not None)
                pending += [song for song, p in results if p is None]

            # ── Retries (up to 2) ─────────────────────────────────────────────
            _verbose[0] = False  # suppress per-track "Not found" during retries
            for retry_n in range(1, 3):
                if not pending or not _check_pause_stop():
                    break
                self._log(
                    f"⏳  Retry {retry_n}/2 — "
                    f"{len(pending)} track{'s' if len(pending) != 1 else ''} remaining…",
                    "warning")
                for _ in range(10):   # 1-second pause before retry
                    if not self.is_downloading:
                        break
                    time.sleep(0.1)
                if not _check_pause_stop():
                    break
                results      = client.download_songs(pending)
                self._dl_ok += sum(1 for _, p in results if p is not None)
                pending      = [song for song, p in results if p is None]

            # ── Last resort: disable result-quality filter ────────────────────
            if pending and _check_pause_stop():
                self._log(
                    f"⏳  Last resort — unfiltered search for "
                    f"{len(pending)} track{'s' if len(pending) != 1 else ''}…",
                    "warning")
                toggled = []
                for provider in list(client.downloader.audio_providers):
                    if hasattr(provider, "filter_results"):
                        provider.filter_results = False
                        toggled.append(provider)
                try:
                    results      = client.download_songs(pending)
                    self._dl_ok += sum(1 for _, p in results if p is not None)
                    pending      = [song for song, p in results if p is None]
                finally:
                    for provider in toggled:
                        provider.filter_results = True

            self._dl_fail = len(pending)
            if pending:
                names = ", ".join(s.display_name for s in pending)
                self._log(
                    f"ℹ️   Could not find: {names}\n"
                    "     These tracks may not be available — try later or with a VPN.",
                    "info")

            return True

        except Exception as exc:
            self._log(f"❌  spotdl error: {exc}", "error")
            import traceback as _tb
            self._log(_tb.format_exc(), "error")
            return False

        finally:
            for lg, lvl in watched:
                lg.removeHandler(handler)
                if lvl != _logging.NOTSET:
                    lg.setLevel(lvl)

    # ── spotdl updater ────────────────────────────────────────────────────────

    def _check_spotdl_updates(self) -> None:
        def _work():
            try:
                current = self._spotdl_version()
                self._log(f"ℹ️   spotdl installed: {current}", "info")
                if current == "not installed":
                    return
                latest = self._spotdl_latest_version()
                if not latest:
                    self._log("⚠️   Could not reach PyPI", "warning")
                    return
                self._log(f"ℹ️   spotdl latest:    {latest}", "info")
                if latest != current:
                    self._log(f"⬆   Updating {current} → {latest}…", "info")
                    subprocess.run(
                        [sys.executable, "-m", "pip", "install", "--upgrade", "spotdl", "--quiet"],
                        check=True, capture_output=True, text=True,
                        timeout=300, **_win_flags())
                    self._invalidate_spotdl_client()
                    self._log("✅  spotdl updated successfully — restart recommended", "success")
                else:
                    self._log("✅  spotdl is up to date", "success")
            except Exception as exc:
                self._log(f"❌  Update error: {exc}", "error")

        threading.Thread(target=_work, daemon=True).start()

    def _spotdl_version(self) -> str:
        """Return the installed spotdl version number (e.g. '4.5.0')."""
        try:
            r = subprocess.run(
                [sys.executable, "-m", "spotdl", "--version"],
                capture_output=True, text=True, timeout=10, **_win_flags())
            raw = (r.stdout + r.stderr).strip()
            # spotdl outputs either "4.5.0" or "spotdl 4.5.0" — return just the number
            return raw.split()[-1] if raw else "unknown"
        except Exception:
            return "not installed"

    def _spotdl_latest_version(self) -> str | None:
        """Fetch the latest spotdl version from PyPI."""
        try:
            r = requests.get("https://pypi.org/pypi/spotdl/json", timeout=8)
            return r.json()["info"]["version"] if r.ok else None
        except Exception:
            return None

    # ── Drag & Drop ───────────────────────────────────────────────────────────

    def _setup_drag_drop(self) -> None:
        if not TKDND_AVAILABLE:
            return
        try:
            _dnd_require(self.root)
            self.entry_link.drop_target_register(DND_TEXT)
            self.entry_link.dnd_bind("<<Drop>>", self._on_drop)
        except Exception:
            pass  # Drag and drop is optional

    def _on_drop(self, event) -> None:
        data = getattr(event, "data", "").strip()
        if any(x in data for x in ("spotify.com", "youtube.com", "youtu.be", "soundcloud.com")):
            self.entry_link.delete(0, tk.END)
            self.entry_link.insert(0, data)
            self._add_to_queue()

    # ── Desktop shortcut ──────────────────────────────────────────────────────

    def _create_shortcut(self) -> None:
        """Create a desktop shortcut / launcher for the current platform."""
        threading.Thread(target=self._create_shortcut_worker, daemon=True).start()

    def _create_shortcut_worker(self) -> None:
        base   = self._base
        icon   = _resource(os.path.join("assets", "icon.ico"))
        logo   = _resource(os.path.join("assets", "logo.png"))
        script = os.path.join(base, "spotrr.py")

        try:
            if sys.platform == "win32":
                self._create_shortcut_windows(base, icon, script)
            else:
                self._create_shortcut_unix(base, logo, script)
        except Exception as exc:
            self._log(f"❌  Shortcut error: {exc}", "error")

    @staticmethod
    def _windows_desktop() -> str:
        """Return the real Desktop path — reads from registry (any locale, OneDrive)."""
        try:
            import winreg
            with winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders") as k:
                path, _ = winreg.QueryValueEx(k, "Desktop")
                if path and os.path.isdir(path):
                    return path
        except Exception:
            pass
        return os.path.join(os.path.expanduser("~"), "Desktop")

    def _create_shortcut_windows(self, base: str, icon: str, script: str) -> None:
        pythonw = os.path.join(base, ".venv", "Scripts", "pythonw.exe")
        if not os.path.exists(pythonw):
            pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
        if not os.path.exists(pythonw):
            pythonw = sys.executable

        desktop = self._windows_desktop()
        target  = os.path.join(desktop, "SpotRR.lnk")

        ps = (
            f'$q=[char]34;'
            f'$s=(New-Object -COM WScript.Shell).CreateShortcut("{target}");'
            f'$s.TargetPath="{pythonw}";'
            f'$s.Arguments=$q+"{script}"+$q;'
            f'$s.WorkingDirectory="{base}";'
            f'$s.IconLocation="{icon}";'
            f'$s.Description="SpotRR";'
            f'$s.WindowStyle=1;'
            f'$s.Save()'
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
            capture_output=True, text=True, timeout=15, **_win_flags())

        if os.path.exists(target):
            self._log("✅  Shortcut created on Desktop", "success")
        else:
            self._log(f"⚠️  Could not create shortcut: {result.stderr.strip()}", "warning")

    def _create_shortcut_unix(self, base: str, icon: str, script: str) -> None:
        python  = os.path.join(base, ".venv", "bin", "python")
        if not os.path.exists(python):
            python = sys.executable

        home = os.path.expanduser("~")
        desktop_dirs: list[str] = []

        # Most reliable: XDG user-dirs config (already locale-resolved)
        user_dirs = os.path.join(home, ".config", "user-dirs.dirs")
        if os.path.isfile(user_dirs):
            try:
                with open(user_dirs, encoding="utf-8") as _f:
                    for _line in _f:
                        if _line.strip().startswith("XDG_DESKTOP_DIR="):
                            _val = _line.split("=", 1)[1].strip().strip('"')
                            desktop_dirs.append(_val.replace("$HOME", home))
                            break
            except Exception:
                pass

        # Environment variable (set by session manager)
        _xdg = os.environ.get("XDG_DESKTOP_DIR", "")
        if _xdg:
            desktop_dirs.append(_xdg)

        # Localized name fallbacks
        for _name in ("Desktop", "Escritorio", "Bureau", "Schreibtisch",
                      "Рабочий стол", "桌面", "바탕화면", "デスクトップ"):
            desktop_dirs.append(os.path.join(home, _name))

        desktop = next((d for d in desktop_dirs if d and os.path.isdir(d)), None)

        if sys.platform == "darwin":
            # macOS — .command file
            target = os.path.join(
                desktop or os.path.expanduser("~"), "SpotRR.command")
            with open(target, "w", encoding="utf-8") as f:
                f.write(f'#!/bin/bash\ncd "{base}"\n"{python}" "{script}"\n')
            os.chmod(target, 0o755)
            self._log(f"✅  Launcher created: {target}", "success")
            return

        # Linux — .desktop file
        if desktop:
            target = os.path.join(desktop, "SpotRR.desktop")
        else:
            apps_dir = os.path.join(os.path.expanduser("~"), ".local", "share", "applications")
            os.makedirs(apps_dir, exist_ok=True)
            target = os.path.join(apps_dir, "SpotRR.desktop")

        content = (
            "[Desktop Entry]\n"
            "Name=SpotRR\n"
            "Comment=SpotRR\n"
            f"Exec={python} {script}\n"
            f"Icon={icon}\n"
            "Terminal=false\n"
            "Type=Application\n"
            "Categories=Music;AudioVideo;\n"
            "StartupWMClass=SpotRR\n"
        )
        with open(target, "w", encoding="utf-8") as f:
            f.write(content)
        os.chmod(target, 0o755)

        # Mark as trusted on GNOME
        try:
            subprocess.run(["gio", "set", target, "metadata::trusted", "true"],
                           capture_output=True, timeout=5)
        except Exception:
            pass

        self._log(f"✅  Shortcut created: {target}", "success")

    # ── How to Setup ──────────────────────────────────────────────────────────

    def _show_how_to_setup(self) -> None:
        win = tk.Toplevel(self.root)
        win.title("How to Setup — SpotRR")
        win.configure(bg=C["bg2"])
        win.resizable(False, False)
        win.transient(self.root)
        win.grab_set()

        # Accent strip
        tk.Frame(win, bg=C["green"], height=3).pack(fill="x")

        # Header
        hdr = tk.Frame(win, bg=C["bg3"])
        hdr.pack(fill="x")
        tk.Label(hdr, text="❓  How to Setup", bg=C["bg3"], fg=C["t1"],
                 font=font.Font(family="Segoe UI", size=13, weight="bold"),
                 padx=20, pady=12).pack(side="left")

        # Content
        content = tk.Frame(win, bg=C["bg2"])
        content.pack(fill="both", expand=True, padx=20, pady=16)

        def _section(title: str, color: str = C["green"]) -> None:
            tk.Label(content, text=title, bg=C["bg2"], fg=color,
                     font=font.Font(family="Segoe UI", size=10, weight="bold"),
                     anchor="w").pack(fill="x", pady=(12, 4))

        def _line(text: str, indent: bool = False) -> None:
            padx = (18, 0) if indent else (0, 0)
            tk.Label(content, text=text, bg=C["bg2"], fg=C["t2"],
                     font=font.Font(family="Segoe UI", size=9),
                     anchor="w", justify="left", wraplength=440).pack(
                     fill="x", padx=padx)

        # ── Step 1 ────────────────────────────────────────────────────────────
        _section("Step 1 — Create a Developer App")
        _line("1.  Open your browser and go to:")
        url_lbl = tk.Label(content,
                           text="   🔗  developer.spotify.com/dashboard",
                           bg=C["bg2"], fg=C["blue"],
                           font=font.Font(family="Segoe UI", size=9, weight="bold"),
                           anchor="w", cursor="hand2")
        url_lbl.pack(fill="x")
        url_lbl.bind("<Button-1>", lambda e: webbrowser.open("https://developer.spotify.com/dashboard"))

        _line("2.  Log in with your account.")
        _line('3.  Click  "Create app".')
        _line('4.  Fill in any name and description (e.g. "My Downloader").')
        _line('5.  Set the Redirect URI to:  http://localhost')
        _line('6.  Accept the terms and click  "Save".')

        _divider(content, bg=C["div"]).pack(fill="x", pady=(12, 0))

        # ── Step 2 ────────────────────────────────────────────────────────────
        _section("Step 2 — Copy your credentials")
        _line('1.  Inside your new app, click  "Settings".')
        _line("2.  You will see your  Client ID  — copy it.")
        _line('3.  Click  "View client secret"  — copy it too.')
        _line("4.  Back in this app, click  🔑 Client ID  and paste it.")
        _line("5.  Click  🔐 Client Secret  and paste it.")
        _line("6.  Done!  The app will reconnect automatically.")

        _divider(content, bg=C["div"]).pack(fill="x", pady=(12, 0))

        # ── Safety tip ────────────────────────────────────────────────────────
        _section("⚠️  Safety Tip", color=C["orange"])
        tip = tk.Label(content,
                       text=(
                           "We recommend creating a FREE secondary account\n"
                           "just for this app — not your main account.\n"
                           "This is a precaution in case the API ever flags\n"
                           "the developer app for unusual usage."
                       ),
                       bg=C["bg3"], fg=C["t1"],
                       font=font.Font(family="Segoe UI", size=9, weight="bold"),
                       justify="left", padx=14, pady=10,
                       wraplength=440)
        tip.pack(fill="x", pady=(0, 4))

        _divider(content, bg=C["div"]).pack(fill="x", pady=(12, 0))

        _divider(content, bg=C["div"]).pack(fill="x", pady=(12, 0))

        # ── YouTube & SoundCloud ───────────────────────────────────────────────
        _section("🎬  YouTube & SoundCloud (no setup needed)")
        _line("You can also paste YouTube and SoundCloud links directly.")
        _line("• YouTube video:    youtube.com/watch?v=…", indent=True)
        _line("• YouTube playlist: youtube.com/playlist?list=…", indent=True)
        _line("• SoundCloud track: soundcloud.com/artist/track", indent=True)
        _line("• SoundCloud set:   soundcloud.com/artist/sets/…", indent=True)
        _line("Spotify credentials are recommended but not required for these sources.")

        _divider(content, bg=C["div"]).pack(fill="x", pady=(12, 0))

        # ── Note ──────────────────────────────────────────────────────────────
        _section("ℹ️  Note", color=C["blue"])
        _line(
            "Spotify credentials unlock rich queue labels (song names, track counts) "
            "and avoid shared API rate limits. Without them the app still works for "
            "YouTube and SoundCloud links, and uses URL patterns for Spotify links."
        )

        # Close button
        tk.Button(win, text="Got it  ✓", command=win.destroy,
                  bg=C["green"], fg=C["t1"],
                  font=font.Font(family="Segoe UI", size=10, weight="bold"),
                  bd=0, relief="flat", cursor="hand2",
                  padx=24, pady=8, highlightthickness=0,
                  activebackground=C["green_hi"]).pack(pady=(16, 20))

        # Centre over parent
        win.update_idletasks()
        px, py = self.root.winfo_x(), self.root.winfo_y()
        pw, ph = self.root.winfo_width(), self.root.winfo_height()
        ww, wh = win.winfo_width(), win.winfo_height()
        win.geometry(f"+{px + (pw - ww)//2}+{py + (ph - wh)//2}")

    # ── About ─────────────────────────────────────────────────────────────────

    def _show_about(self) -> None:
        win = tk.Toplevel(self.root)
        win.title(f"About {APP_NAME}")
        win.configure(bg=C["bg2"])
        win.resizable(False, False)
        win.transient(self.root)
        win.grab_set()

        tk.Frame(win, bg=C["green"], height=3).pack(fill="x")

        # Header
        hdr = tk.Frame(win, bg=C["bg3"])
        hdr.pack(fill="x")
        tk.Label(hdr, text=APP_NAME, bg=C["bg3"], fg=C["green"],
                 font=font.Font(family="Segoe UI", size=22, weight="bold"),
                 pady=14).pack()
        tk.Label(hdr, text=f"v{APP_VERSION}  ·  Your music, your way",
                 bg=C["bg3"], fg=C["t3"],
                 font=font.Font(family="Segoe UI", size=9)).pack(pady=(0, 12))

        content = tk.Frame(win, bg=C["bg2"])
        content.pack(fill="both", expand=True, padx=24, pady=(14, 0))

        def _row(label: str, value: str, clickable: bool = False, url: str = "") -> None:
            r = tk.Frame(content, bg=C["bg2"])
            r.pack(fill="x", pady=3)
            tk.Label(r, text=label, bg=C["bg2"], fg=C["t3"],
                     font=font.Font(family="Segoe UI", size=8),
                     width=14, anchor="e").pack(side="left", padx=(0, 10))
            color = C["blue"] if clickable else C["t1"]
            lbl = tk.Label(r, text=value, bg=C["bg2"], fg=color,
                           font=font.Font(family="Segoe UI", size=9,
                                         weight="bold" if clickable else "normal"),
                           cursor="hand2" if clickable else "", anchor="w")
            lbl.pack(side="left")
            if clickable and url:
                lbl.bind("<Button-1>", lambda e: webbrowser.open(url))
                lbl.bind("<Enter>", lambda e: lbl.configure(fg=C["t1"]))
                lbl.bind("<Leave>", lambda e: lbl.configure(fg=C["blue"]))

        _row("Version", f"{APP_VERSION}")
        _row("Source", "github.com/GITspotRR/SpotRR", clickable=True, url=APP_GITHUB)
        _row("License", "MIT — Free & open source")
        _row("Powered by", "spotdl  ·  spotipy  ·  tkinter")

        _divider(content, bg=C["div"]).pack(fill="x", pady=(12, 8))

        # Keyboard shortcuts
        tk.Label(content, text="KEYBOARD SHORTCUTS", bg=C["bg2"], fg=C["t3"],
                 font=font.Font(family="Segoe UI", size=8, weight="bold"),
                 anchor="w").pack(fill="x", pady=(0, 6))

        shortcuts = [
            ("Ctrl + L",       "Focus URL field"),
            ("Ctrl + Enter",   "Add URL to queue"),
            ("F5",             "Start download"),
            ("Delete",         "Remove selected queue item"),
            ("F9",             "Clear console"),
        ]
        for keys, desc in shortcuts:
            r = tk.Frame(content, bg=C["bg2"])
            r.pack(fill="x", pady=1)
            kb = tk.Label(r, text=keys,
                          bg=C["bg4"], fg=C["green"],
                          font=font.Font(family="Consolas", size=8),
                          padx=6, pady=1)
            kb.pack(side="left")
            tk.Label(r, text=desc, bg=C["bg2"], fg=C["t2"],
                     font=font.Font(family="Segoe UI", size=8),
                     padx=8).pack(side="left")

        _divider(content, bg=C["div"]).pack(fill="x", pady=(12, 8))

        # Legal (compact)
        tk.Label(content, text="LEGAL", bg=C["bg2"], fg=C["t3"],
                 font=font.Font(family="Segoe UI", size=8, weight="bold"),
                 anchor="w").pack(fill="x", pady=(0, 4))
        tk.Label(content, text=LEGAL_DISCLAIMER, bg=C["bg2"], fg=C["t3"],
                 font=("Segoe UI", 8), justify="left").pack(fill="x")

        tk.Button(win, text="Close", command=win.destroy,
                  bg=C["green"], fg=C["t1"],
                  font=font.Font(family="Segoe UI", size=10, weight="bold"),
                  bd=0, relief="flat", cursor="hand2",
                  padx=32, pady=8, highlightthickness=0,
                  activebackground=C["green_hi"]).pack(pady=(16, 20))

        win.update_idletasks()
        px, py = self.root.winfo_x(), self.root.winfo_y()
        pw, ph = self.root.winfo_width(), self.root.winfo_height()
        ww, wh = win.winfo_width(), win.winfo_height()
        win.geometry(f"+{px + (pw - ww)//2}+{py + (ph - wh)//2}")

    # ── Crypto donations ──────────────────────────────────────────────────────

    def _show_eth_picker(self) -> None:
        win = tk.Toplevel(self.root)
        win.title("ETH — Select Network")
        win.configure(bg=C["bg2"])
        win.resizable(False, False)
        win.transient(self.root)

        tk.Frame(win, bg="#627EEA", height=3).pack(fill="x")

        tk.Label(win, text="Ξ  ETH — Select Network",
                 bg=C["bg3"], fg="#627EEA",
                 font=font.Font(family="Segoe UI", size=13, weight="bold"),
                 padx=20, pady=14).pack(fill="x")

        _divider(win, bg=C["div"]).pack(fill="x")

        frame = tk.Frame(win, bg=C["bg2"])
        frame.pack(padx=24, pady=20, fill="x")

        def _pick(coin):
            win.destroy()
            self.root.after(100, lambda c=coin: self._show_crypto(c))

        for coin, label, desc, color in (
            ("ETH",  "Ethereum",  "ERC-20 mainnet",  "#627EEA"),
            ("BASE", "Ethereum - BASE NETWORK", "Layer 2 (Base)",  "#0052FF"),
        ):
            row = tk.Frame(frame, bg=C["bg3"], cursor="hand2")
            row.pack(fill="x", pady=4)

            tk.Frame(row, bg=color, width=4).pack(side="left", fill="y")
            inner = tk.Frame(row, bg=C["bg3"])
            inner.pack(side="left", fill="x", expand=True, padx=14, pady=10)

            lbl_title = tk.Label(inner, text=f"Ξ  {label}", bg=C["bg3"], fg=color,
                     font=font.Font(family="Segoe UI", size=11, weight="bold"),
                     anchor="w", cursor="hand2")
            lbl_title.pack(fill="x")
            lbl_desc = tk.Label(inner, text=desc, bg=C["bg3"], fg=C["t3"],
                     font=font.Font(family="Segoe UI", size=8),
                     anchor="w", cursor="hand2")
            lbl_desc.pack(fill="x")

            def _bind_row(r, i, lt, ld, c):
                all_w = (r, i, lt, ld)
                for w in all_w:
                    w.bind("<Button-1>", lambda e, x=c: _pick(x))
                    w.bind("<Enter>", lambda e, ws=all_w: [x.configure(bg=C["bg4"]) for x in ws])
                    w.bind("<Leave>", lambda e, ws=all_w: [x.configure(bg=C["bg3"]) for x in ws])

            _bind_row(row, inner, lbl_title, lbl_desc, coin)

        tk.Button(win, text="Cancel", command=win.destroy,
                  bg=C["bg2"], fg=C["t3"],
                  font=font.Font(family="Segoe UI", size=8),
                  bd=0, relief="flat", cursor="hand2",
                  pady=8, highlightthickness=0).pack(pady=(0, 10))

        win.update_idletasks()
        px, py = self.root.winfo_x(), self.root.winfo_y()
        pw, ph = self.root.winfo_width(), self.root.winfo_height()
        ww, wh = win.winfo_width(), win.winfo_height()
        win.geometry(f"+{px + (pw - ww)//2}+{py + (ph - wh)//2}")

    def _show_crypto(self, coin: str) -> None:
        entry   = CRYPTO_ADDRESSES[coin]
        addr    = entry["address"] if isinstance(entry, dict) else entry
        memo    = entry.get("memo", "") if isinstance(entry, dict) else ""
        meta    = CRYPTO_META.get(coin, {"color": C["green"], "symbol": "", "network": coin})
        brand   = meta["color"]
        symbol  = meta["symbol"]
        network = meta.get("network", coin)

        win = tk.Toplevel(self.root)
        win.title(f"Donate  {symbol} {coin}")
        win.configure(bg=C["bg2"])
        win.resizable(False, False)
        win.transient(self.root)
        win.grab_set()

        # ── Coloured header strip ──────────────────────────────────────────────
        tk.Frame(win, bg=brand, height=4).pack(fill="x")

        hdr = tk.Frame(win, bg=C["bg3"])
        hdr.pack(fill="x")
        left_hdr = tk.Frame(hdr, bg=C["bg3"])
        left_hdr.pack(side="left", padx=20, pady=10)
        tk.Label(left_hdr, text=f"{symbol}  {coin}", bg=C["bg3"], fg=brand,
                 font=font.Font(family="Segoe UI", size=16, weight="bold")).pack(anchor="w")
        tk.Label(left_hdr, text=f"Network: {network}", bg=C["bg3"], fg=C["t3"],
                 font=font.Font(family="Segoe UI", size=8)).pack(anchor="w")

        # ── Thank-you message ──────────────────────────────────────────────────
        tk.Label(win,
                 text="Thank you for considering a donation! ♥\n"
                      "Every contribution helps keep this project alive\n"
                      "and motivates future improvements.",
                 bg=C["bg2"], fg=C["t2"],
                 font=font.Font(family="Segoe UI", size=9),
                 justify="center", pady=10).pack(padx=20)

        _divider(win, bg=C["div"]).pack(fill="x", padx=16)

        # ── QR code ───────────────────────────────────────────────────────────
        # Priority: 1) pre-made PNG in assets/qr/  2) auto-generate  3) skip
        qr_shown = False
        if addr and PIL_AVAILABLE:
            qr_file = _resource(os.path.join("assets", "qr", f"{coin}.png"))
            if os.path.exists(qr_file):
                try:
                    img = Image.open(qr_file).convert("RGBA")
                    img.thumbnail((260, 260), Image.Resampling.LANCZOS)
                    photo = ImageTk.PhotoImage(img)
                    lbl = tk.Label(win, image=photo, bg="white", padx=6, pady=6)
                    lbl.image = photo
                    lbl.pack(pady=12)
                    qr_shown = True
                except Exception:
                    pass

        if not qr_shown and QR_AVAILABLE and addr:
            try:
                qr_data = f"stellar:{addr}?memo={memo}" if coin == "XLM" else addr
                qr = qrcode.QRCode(version=1, box_size=7, border=3)
                qr.add_data(qr_data)
                qr.make(fit=True)
                qr_img = qr.make_image(fill_color=brand, back_color="white")
                buf = io.BytesIO()
                qr_img.save(buf, "PNG")
                buf.seek(0)
                photo = tk.PhotoImage(data=buf.getvalue())
                lbl = tk.Label(win, image=photo, bg="white", padx=6, pady=6)
                lbl.image = photo
                lbl.pack(pady=12)
                qr_shown = True
            except Exception:
                pass

        if not addr:
            tk.Label(win, text="🚧  Wallet address coming soon",
                     bg=C["bg2"], fg=C["t3"],
                     font=font.Font(family="Segoe UI", size=9, weight="bold"),
                     pady=20).pack()

        # ── Address box ────────────────────────────────────────────────────────
        if addr:
            addr_frame = tk.Frame(win, bg=C["bg3"])
            addr_frame.pack(fill="x", padx=16, pady=(0, 6))

            addr_text = addr if not memo else f"{addr}\n\nMemo: {memo}"
            addr_lbl = tk.Label(addr_frame, text=addr_text,
                                bg=C["bg3"], fg=C["t1"],
                                font=("Consolas", 8),
                                wraplength=300, justify="center",
                                padx=12, pady=8)
            addr_lbl.pack(fill="x")

            # Copy buttons
            copy_row = tk.Frame(win, bg=C["bg2"])
            copy_row.pack(pady=(0, 4))

            tk.Button(copy_row, text="📋  Copy Address",
                      command=lambda: self._copy_to_clipboard(addr),
                      bg=brand, fg=C["t1"],
                      font=font.Font(family="Segoe UI", size=9, weight="bold"),
                      bd=0, relief="flat", cursor="hand2",
                      padx=18, pady=7, highlightthickness=0,
                      activebackground=C["bg5"], activeforeground=C["t1"]).pack(side="left", padx=4)

            if memo:
                tk.Button(copy_row, text="📋  Copy Memo",
                          command=lambda: self._copy_to_clipboard(memo),
                          bg=C["bg4"], fg=C["t2"],
                          font=font.Font(family="Segoe UI", size=9, weight="bold"),
                          bd=0, relief="flat", cursor="hand2",
                          padx=18, pady=7, highlightthickness=0).pack(side="left", padx=4)

        # ── Close ──────────────────────────────────────────────────────────────
        tk.Button(win, text="Close", command=win.destroy,
                  bg=C["bg3"], fg=C["t3"],
                  font=font.Font(family="Segoe UI", size=8),
                  bd=0, relief="flat", cursor="hand2",
                  pady=8, highlightthickness=0).pack(pady=(6, 12))

        # Centre over parent
        win.update_idletasks()
        px, py = self.root.winfo_x(), self.root.winfo_y()
        pw, ph = self.root.winfo_width(), self.root.winfo_height()
        ww, wh = win.winfo_width(), win.winfo_height()
        win.geometry(f"+{px + (pw - ww)//2}+{py + (ph - wh)//2}")

    def _copy_to_clipboard(self, text: str) -> None:
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self._log("✅  Copied to clipboard", "success")

    # ── Keyboard shortcuts ────────────────────────────────────────────────────

    def _bind_shortcuts(self) -> None:
        r = self.root
        r.bind("<Control-l>", lambda e: (
            self.entry_link.focus_set(), self.entry_link.select_range(0, "end")))
        r.bind("<Control-Return>", lambda e: self._add_to_queue())
        r.bind("<F5>", lambda e: self._start_download() if not self.is_downloading else None)
        r.bind("<F9>", lambda e: self._clear_console())
        # Delete on queue listbox (bound after _build_queue creates it)
        self.root.after(100, lambda: self.queue_list.bind(
            "<Delete>", lambda e: self._remove_from_queue()))

    # ── Window geometry ───────────────────────────────────────────────────────

    def _save_geometry(self) -> None:
        try:
            cfg = self._read_cfg()
            state = self.root.state()
            cfg["window_state"] = state
            if state == "normal":
                cfg["window_geometry"] = self.root.geometry()
            self._write_cfg(cfg)
        except Exception:
            pass

    def _restore_geometry(self) -> None:
        cfg = self._read_cfg()
        state = cfg.get("window_state")
        geom  = cfg.get("window_geometry")
        if state == "normal" and geom:
            try:
                self.root.state("normal")
                self.root.geometry(geom)
            except Exception:
                pass

    # ── System notifications ──────────────────────────────────────────────────

    def _notify(self, title: str, body: str) -> None:
        def _xml(s: str) -> str:
            return (s.replace("&", "&amp;").replace("<", "&lt;")
                     .replace(">", "&gt;").replace('"', "&quot;"))

        def _send():
            try:
                if sys.platform == "win32":
                    t, b = _xml(title), _xml(body)
                    ps = (
                        "[Windows.UI.Notifications.ToastNotificationManager,"
                        "Windows.UI.Notifications,ContentType=WindowsRuntime]|Out-Null;"
                        "[Windows.Data.Xml.Dom.XmlDocument,"
                        "Windows.Data.Xml.Dom.XmlDocument,ContentType=WindowsRuntime]|Out-Null;"
                        "$xml=[Windows.Data.Xml.Dom.XmlDocument]::new();"
                        f"$xml.LoadXml('<toast><visual><binding template=\"ToastGeneric\">"
                        f"<text>{t}</text><text>{b}</text>"
                        "</binding></visual></toast>');"
                        "$toast=[Windows.UI.Notifications.ToastNotification]::new($xml);"
                        "[Windows.UI.Notifications.ToastNotificationManager]::"
                        "CreateToastNotifier('SpotRR').Show($toast)"
                    )
                    subprocess.run(
                        ["powershell", "-NoProfile", "-WindowStyle", "Hidden",
                         "-Command", ps],
                        capture_output=True, timeout=6, **_win_flags())
                elif sys.platform == "darwin":
                    subprocess.run(
                        ["osascript", "-e",
                         f'display notification "{body}" with title "{title}"'],
                        capture_output=True, timeout=5)
                else:
                    subprocess.run(
                        ["notify-send", "-a", "SpotRR", "-t", "4000", title, body],
                        capture_output=True, timeout=5)
            except Exception:
                pass

        threading.Thread(target=_send, daemon=True).start()

    # ── Run ───────────────────────────────────────────────────────────────────

    def run(self) -> None:
        self.root.mainloop()


# ─────────────────────────────────────────────────────────────────────────────
# Module-level helpers
# ─────────────────────────────────────────────────────────────────────────────

_PKG_IMPORT_MAP = {
    "pillow":      "PIL",
    "tkinterdnd2": "tkinterdnd2",
    "qrcode":      "qrcode",
    "rapidfuzz":   "rapidfuzz",
    "mutagen":     "mutagen",
    "spotipy":     "spotipy",
    "spotdl":      "spotdl",
    "requests":    "requests",
}


def _pkg_available(pkg: str) -> bool:
    """Return True if `pkg` is importable (handles pip-name vs import-name mapping)."""
    import_name = _PKG_IMPORT_MAP.get(pkg.lower(), pkg)
    try:
        importlib.import_module(import_name)
        return True
    except ImportError:
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    # Set asyncio policy before ANY spotdl/yt-dlp import creates an event loop
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    if not _acquire_instance():
        # Another instance is already running — surface it instead of opening twice
        _tmp = tk.Tk()
        _tmp.withdraw()
        messagebox.showinfo(
            APP_NAME,
            f"{APP_NAME} is already running.\nCheck your taskbar.",
            parent=_tmp)
        _tmp.destroy()
        return

    base = (os.path.dirname(sys.executable) if getattr(sys, "frozen", False)
            else os.path.dirname(os.path.abspath(__file__)))

    if getattr(sys, "frozen", False):
        os.environ["PATH"] = base + os.pathsep + os.environ.get("PATH", "")

    logging.basicConfig(
        filename=os.path.join(base, "app.log"),
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        encoding="utf-8")

    for d in ("logs", "downloads"):
        os.makedirs(os.path.join(base, d), exist_ok=True)

    # Tell Windows this is its own app (not python.exe) so the taskbar
    # shows our icon instead of the Python icon.
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "spotrr.app.2")
        except Exception:
            pass

    root = tk.Tk()

    icon = os.path.join(base, "assets", "icon.ico")
    if os.path.exists(icon):
        try:
            root.iconbitmap(icon)
        except tk.TclError:
            pass

    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    w, h = 1100, 700
    root.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")

    app = SpotRRApp(root)
    app.run()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        import traceback as _tb
        logging.exception("Fatal error on startup")
        err_text = _tb.format_exc()
        # Write startup_error.log so setup.bat can detect and show it
        try:
            err_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "startup_error.log")
            with open(err_path, "w", encoding="utf-8") as _f:
                _f.write(err_text)
        except Exception:
            pass
        try:
            messagebox.showerror("Fatal Error", f"Could not start {APP_NAME}:\n\n{exc}")
        except Exception:
            print(f"Fatal: {exc}", file=sys.stderr)
        sys.exit(1)
