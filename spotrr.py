"""
SpotRR  v2.1.0
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

    # Suppress CMD windows for all subprocesses in THIS process.
    # For child processes (spotdl), see rthook_no_console.py.
    _orig_popen_init = subprocess.Popen.__init__
    def _silent_popen_init(self, args, **kwargs):
        kwargs["creationflags"] = kwargs.get("creationflags", 0) | subprocess.CREATE_NO_WINDOW
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
APP_VERSION = "2.1.0"
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
        self._check_and_install_deps()
        self._init_spotify_client()
        self._load_logo()
        self._restore_geometry()
        # Auto-create shortcut on first ever launch
        cfg = self._read_cfg()
        if not cfg.get("shortcut_created"):
            self._create_shortcut()
            cfg["shortcut_created"] = True
            self._write_cfg(cfg)

    def _on_close(self) -> None:
        self._save_geometry()
        _release_instance()
        self.root.destroy()

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
        try:
            with open(self._cfg_path(), "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
        except Exception as exc:
            self._log(f"⚠️  Settings save error: {exc}", "warning")

    def _load_settings(self) -> None:
        s = self._read_cfg()
        self.format_var.set(s.get("preferred_format", "mp3"))
        self.quality_var.set(s.get("preferred_quality", "320k"))
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

    def _auth_args(self) -> list[str]:
        cid, cs = self._get_creds()
        return ["--client-id", cid, "--client-secret", cs] if cid and cs else []

    def _enc_env(self) -> dict:
        """Build subprocess environment with UTF-8 settings and injected credentials."""
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8:replace"
        env["PYTHONUTF8"]       = "1"
        env["PYTHONWARNINGS"]   = "ignore"
        cid, cs = self._get_creds()
        if cid:
            env["SPOTIPY_CLIENT_ID"]  = cid
            env["SPOTDL_CLIENT_ID"]   = cid
        if cs:
            env["SPOTIPY_CLIENT_SECRET"] = cs
            env["SPOTDL_CLIENT_SECRET"]  = cs
        return env

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

        # ── FFmpeg ────────────────────────────────────────────────────────────
        self._ensure_ffmpeg()

    def _ensure_ffmpeg(self) -> None:
        """Verify FFmpeg is available — uses the bundled binary when running from the .exe."""
        if _ffmpeg_exe():
            self._log("✅  FFmpeg ready (bundled)", "success")
            return

        suffix = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
        home   = os.path.expanduser("~")
        spotdl_paths = [
            os.path.join(home, ".spotdl",        suffix),
            os.path.join(home, ".config", "spotdl", suffix),
        ]
        if shutil.which("ffmpeg") or any(os.path.exists(p) for p in spotdl_paths):
            self._log("✅  FFmpeg ready", "success")
            return

        self._log("📦  FFmpeg not found — downloading automatically (one-time setup)…", "info")
        try:
            spotdl_ffmpeg = spotdl_paths[0]
            subprocess.run(
                [sys.executable, "-m", "spotdl", "--download-ffmpeg"],
                capture_output=True, text=True, timeout=180, **_win_flags())
            if os.path.exists(spotdl_ffmpeg) or shutil.which("ffmpeg"):
                self._log("✅  FFmpeg downloaded and ready", "success")
            else:
                self._log(
                    "⚠️  FFmpeg download may have failed. "
                    "Run: spotdl --download-ffmpeg  (or install via your package manager)",
                    "warning")
        except subprocess.TimeoutExpired:
            self._log("⚠️  FFmpeg download timed out — retrying on next launch", "warning")
        except Exception as exc:
            self._log(f"⚠️  FFmpeg setup error: {exc}", "warning")

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
        _section_label(url_section, "SpotRR URL", C["bg2"]).pack(anchor="w", pady=(0, 2))
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
        """Prominent donation / support card at the bottom of the left panel."""
        card = tk.Frame(parent, bg=C["bg3"],
                        highlightbackground=C["green_lo"], highlightthickness=1)
        card.pack(fill="x", side="bottom", padx=16, pady=(0, 10))

        # ── Header + message on the same compact row ──────────────────────────
        top = tk.Frame(card, bg=C["bg3"])
        top.pack(fill="x", padx=12, pady=(8, 6))

        tk.Label(top, text="♥", bg=C["bg3"], fg=C["red"],
                 font=font.Font(family="Segoe UI", size=11, weight="bold")).pack(side="left", padx=(0, 6))

        right = tk.Frame(top, bg=C["bg3"])
        right.pack(side="left", fill="x", expand=True)

        tk.Label(right, text="Support this project",
                 bg=C["bg3"], fg=C["t1"],
                 font=font.Font(family="Segoe UI", size=9, weight="bold"),
                 anchor="w").pack(fill="x")

        msg = (
            "This app is 100% free and took hundreds of hours to build.\n"
            "If it saves you time or brings you joy, any tip\n"
            "makes a huge difference. Thank you so much! ❤️"
        )
        tk.Label(right, text=msg, bg=C["bg3"], fg=C["t1"],
                 font=font.Font(family="Segoe UI", size=8, weight="bold"),
                 anchor="w", justify="left").pack(fill="x")

        # ── Thin divider ──────────────────────────────────────────────────────
        _divider(card, bg=C["div"]).pack(fill="x", padx=10)

        # ── Crypto buttons ────────────────────────────────────────────────────
        btns_frame = tk.Frame(card, bg=C["bg3"])
        btns_frame.pack(fill="x", padx=10, pady=(6, 8))

        for coin, meta in CRYPTO_META.items():
            if coin == "BASE":
                continue  # shown as a variant inside the ETH picker

            brand   = meta["color"]
            symbol  = meta["symbol"]
            address = CRYPTO_ADDRESSES.get(coin, "")
            # Treat dict entries (XLM) as having an address if the address key is non-empty
            has_addr = bool(address["address"] if isinstance(address, dict) else address)

            btn_bg   = C["bg4"]
            btn_fg   = brand
            lbl_text = f"{symbol} {coin}"
            cmd      = (lambda: self._show_eth_picker()) if coin == "ETH" else (lambda c=coin: self._show_crypto(c))

            b = tk.Button(btns_frame, text=lbl_text, command=cmd,
                          bg=btn_bg, fg=btn_fg,
                          font=font.Font(family="Segoe UI", size=8, weight="bold"),
                          bd=0, relief="flat", cursor="hand2",
                          padx=8, pady=5, highlightthickness=0,
                          activebackground=brand, activeforeground=C["t1"])
            b.pack(side="left", padx=3, pady=0)

            # Hover: fill with brand colour
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
        _section_label(q_hdr, "SpotRR Queue", C["bg2"]).pack(side="left")
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
        """Thread-safe progress bar update.

        value : 0-100 integer
        label : optional override for the percentage label;
                auto-generates from value when omitted
        """
        def _do():
            self.progress_bar.configure(value=max(0, min(100, value)))
            if label is not None:
                self.pct_label.configure(text=label)
            elif value <= 0:
                self.pct_label.configure(text="")
            else:
                # Show "2/5" when we know the total, otherwise "X%"
                if self._dl_total > 1 and self._dl_ok > 0:
                    self.pct_label.configure(text=f"{self._dl_ok}/{self._dl_total}")
                else:
                    self.pct_label.configure(text=f"{value}%")

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
        self.format_var.set(val)
        for v, b in self.fmt_buttons.items():
            b.configure(bg=C["green"] if v == val else C["bg4"],
                        fg=C["t1"]   if v == val else C["t2"])

    def _sel_quality(self, val: str) -> None:
        self.quality_var.set(val)
        for v, b in self.quality_buttons.items():
            b.configure(bg=C["green"] if v == val else C["bg4"],
                        fg=C["t1"]   if v == val else C["t2"])

    def _sel_batch(self, val: int) -> None:
        self.batch_size = int(val)
        for v, b in self.batch_buttons.items():
            b.configure(bg=C["green"] if v == val else C["bg4"],
                        fg=C["t1"]   if v == val else C["t2"])

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
            self._init_spotify_client()
            self._log("✅  Client Secret saved", "success")

    # ── URL / Queue ───────────────────────────────────────────────────────────

    def _url_type(self, url: str) -> str:
        """Detect Spotify URL type using regex to avoid false positives."""
        m = re.search(r"spotify\.com/(playlist|album|track|artist)/", url)
        return m.group(1) if m else "unknown"

    def _get_label(self, url: str) -> str:
        """Return a human-readable queue label for a Spotify URL."""
        kind = self._url_type(url)
        # Extract bare ID (everything after the type segment, before any query or hash)
        id_match = re.search(
            r"spotify\.com/(?:playlist|album|track|artist)/([A-Za-z0-9]+)", url)
        item_id = id_match.group(1) if id_match else None

        if self.sp and item_id:
            try:
                if kind == "playlist":
                    pl = _spotify_call(self.sp.playlist, item_id)
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
                self._log(f"⚠️  API error: {exc}", "warning")

        fallback = {
            "playlist": "📑  Playlist",
            "album":    "💿  Album",
            "track":    "🎵  Track",
            "artist":   "👤  Artist",
        }
        return fallback.get(kind, f"🔗  {url}")

    def _add_to_queue(self) -> None:
        raw = self.entry_link.get().strip()
        if not raw:
            self._log("⚠️  Please paste a SpotRR URL", "warning")
            return
        url = raw.split("?")[0].split("#")[0].rstrip("/")
        if "spotify.com" not in url:
            self._log("❌  Not a valid SpotRR URL", "error")
            return
        if self._url_type(url) == "unknown":
            self._log("❌  Unrecognised URL type (expected track/album/playlist/artist)",
                      "error")
            return

        # Fetch label in background to avoid freezing the UI
        self.entry_link.delete(0, tk.END)
        placeholder = f"🔗  {url}"
        with self._queue_lock:
            self.download_queue.append((url, placeholder))
        idx = len(self.download_queue) - 1
        self.queue_list.insert(tk.END, f"  {placeholder}")
        self._update_queue_count()
        self._log(f"ℹ️  Fetching info…  {url}", "info")

        def _fetch():
            label = self._get_label(url)
            # Update queue data and listbox with real label
            with self._queue_lock:
                if idx < len(self.download_queue) and self.download_queue[idx][0] == url:
                    self.download_queue[idx] = (url, label)
            color = (C["green"] if "📑" in label else
                     C["blue"]  if "💿" in label else
                     "#E74C6F"  if "🎵" in label else C["t2"])

            def _update_ui():
                # Update the listbox entry colour and text
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
        if not sel or sel[0] == 0:
            return
        i = sel[0]
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
        self._log("🛑  Stopping…", "warning")
        self.is_downloading = False  # signal worker to exit cleanly

        proc = self.current_process
        if proc is None:
            return

        # Terminate the subprocess in a background thread so we never block the UI
        def _kill():
            try:
                proc.terminate()
                for _ in range(15):           # wait up to 1.5 s
                    if proc.poll() is not None:
                        break
                    time.sleep(0.1)
                if proc.poll() is None:
                    proc.kill()
            except Exception:
                pass

        threading.Thread(target=_kill, daemon=True).start()
        self._set_status("Stopped", C["red"])
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
        """Called from the worker thread when a download completes or is stopped.
        Removes the first queue item and schedules the next download."""
        with self._queue_lock:
            if self.download_queue:
                self.download_queue.pop(0)

        self.is_downloading  = False
        self.download_paused = False

        def _ui():
            self.queue_list.delete(0)
            self._update_queue_count()
            self.btn_pause.configure(text="⏸  Pause")
            if self.download_queue:
                self._start_download()

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
            self._set_status(f"Downloading…  {label[:42]}", C["green"])
            self._set_progress(0)

            success = self._run_spotdl(url, folder, fmt, quality)

            if success:
                self._show_download_summary(label)
            else:
                self._log(f"❌  Failed: {label}", "error")
                self._set_status("Failed", C["red"])
                self._set_progress(0)
        except Exception as exc:
            self._log(f"❌  Unexpected error: {exc}", "error")
            self._set_status("Error", C["red"])
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
                f"     Failed tracks may be unavailable on YouTube Music right now.\n"
                f"     Try again later or check with a VPN.",
                "warning")
            self._set_status(
                f"{ok}/{denominator} downloaded  ·  {fail} failed",
                C["orange"])
            self._notify("SpotRR — Download finished",
                         f"{ok}/{denominator} tracks  ·  {fail} failed")
        self._set_progress(100)

    def _build_cmd(self, url: str, folder: str, fmt: str, quality: str,
                   threads: int | None = None) -> list[str]:
        cmd = [
            sys.executable, "-m", "spotdl",
            *self._auth_args(),
            "download", url,
            "--output",  folder,
            "--format",  fmt,
            "--bitrate", quality,
            "--threads", str(threads or self.batch_size),
        ]
        ffmpeg = _ffmpeg_exe()
        if ffmpeg:
            cmd += ["--ffmpeg", ffmpeg]
        return cmd

    def _interruptible_sleep(self, seconds: float) -> bool:
        """Sleep in 100 ms increments, returning False if stop is requested."""
        steps = int(seconds * 10)
        for _ in range(steps):
            if not self.is_downloading:
                return False
            time.sleep(0.1)
        return True

    def _run_spotdl(self, url: str, folder: str, fmt: str, quality: str,
                    max_attempts: int = 3) -> bool:
        for attempt in range(1, max_attempts + 1):
            if not self.is_downloading:
                return False

            cmd = self._build_cmd(url, folder, fmt, quality)
            self._log(f"⚙️   Attempt {attempt}/{max_attempts}", "info")

            try:
                self.current_process = _popen(
                    cmd,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, encoding="utf-8", errors="replace",
                    bufsize=1, env=self._enc_env())

                for raw in iter(self.current_process.stdout.readline, ""):
                    if not self.is_downloading:
                        break
                    while self.download_paused and self.is_downloading:
                        time.sleep(0.1)
                    self._handle_spotdl_line(raw.rstrip())

                self.current_process.stdout.close()
                rc = self.current_process.wait()
                self.current_process = None

                if rc == 0:
                    return True
                self._log(f"⚠️   spotdl exited with code {rc}", "warning")

            except Exception as exc:
                self._log(f"⚠️   Process error: {exc}", "warning")
                self.current_process = None

            if attempt < max_attempts:
                wait = 3 * attempt
                self._log(f"⏳  Retry in {wait}s…", "info")
                if not self._interruptible_sleep(wait):
                    return False  # stop was requested during the wait

        # Single-thread, no-auth fallback
        self._log("⚠️   Trying single-thread fallback…", "warning")
        if not self.is_downloading:
            return False
        try:
            fallback_cmd = [sys.executable, "-m", "spotdl", "download", url,
                            "--output", folder, "--format", fmt, "--bitrate", quality]
            ffmpeg = _ffmpeg_exe()
            if ffmpeg:
                fallback_cmd += ["--ffmpeg", ffmpeg]
            r = subprocess.run(
                fallback_cmd,
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=600,
                env=self._enc_env(), **_win_flags())
            for line in (r.stdout or "").splitlines():
                self._handle_spotdl_line(line)
            return r.returncode == 0
        except subprocess.TimeoutExpired:
            self._log("❌  Fallback timed out (10 min)", "error")
            return False
        except Exception as exc:
            self._log(f"❌  Fallback error: {exc}", "error")
            return False

    def _handle_spotdl_line(self, line: str) -> None:
        """Route a single spotdl output line to the console or progress bar."""
        if not line:
            return

        # ── Detect total track count ──────────────────────────────────────────
        m_total = re.search(r"Found (\d+) songs?", line, re.IGNORECASE)
        if m_total:
            self._dl_total = int(m_total.group(1))
            # Don't return — fall through to log the "Found N songs" line

        # ── yt-dlp per-track percentage ───────────────────────────────────────
        # "[download]  52.3% of …" lines come from yt-dlp and reflect a SINGLE
        # track's download progress, not the whole queue.
        m_ytdlp = re.search(r"\[download\]\s+(\d{1,3}(?:\.\d+)?)%", line)
        if m_ytdlp:
            track_pct = float(m_ytdlp.group(1))
            if self._dl_total <= 1:
                # Single track — use raw yt-dlp % directly
                self._set_progress(int(track_pct))
                self._set_status(f"Downloading…  {int(track_pct)}%", C["green"])
            else:
                # Playlist — blend completed tracks + current track progress
                # so the bar advances smoothly instead of resetting per track
                step = 100.0 / self._dl_total
                base = self._dl_ok * step
                extra = step * (track_pct / 100.0)
                total_pct = int(min(base + extra, 99))  # never reach 100 until truly done
                self._set_progress(total_pct)
                self._set_status(
                    f"Downloading…  {self._dl_ok}/{self._dl_total} tracks  ({int(track_pct)}%)",
                    C["green"])
            return  # yt-dlp lines are not worth logging

        # ── Successful track download ─────────────────────────────────────────
        if 'Downloaded "' in line or "Downloaded '" in line:
            self._dl_ok += 1
            name_m = re.search(r'Downloaded ["\'](.+?)["\']', line)
            name = name_m.group(1) if name_m else "track"
            if self._dl_total > 0:
                pct = int(self._dl_ok / self._dl_total * 100)
                self._set_progress(pct)
                self._set_status(
                    f"Downloading…  {self._dl_ok}/{self._dl_total} tracks", C["green"])
                self._log(f"✅  [{self._dl_ok}/{self._dl_total}]  {name}", "success")
            else:
                self._set_progress(100)
                self._log(f"✅  {name}", "success")
            return

        # ── YouTube Music server error (HTTP 500 — transient) ─────────────────
        if "YTMusicServerError" in line or "HTTP 500" in line or "Internal Server Error" in line:
            self._dl_fail += 1
            self._log(
                "⚠️  A track could not be downloaded (YouTube Music server error).\n"
                "     This is temporary — try again in a few minutes.",
                "warning")
            return

        # ── Lookup / not-found errors ─────────────────────────────────────────
        if "LookupError" in line or "No results found" in line:
            self._dl_fail += 1
            self._log(f"⚠️  Track not found on YouTube Music: {line.strip()}", "warning")
            return

        # ── "Blocked by YouTube Music" info tip ───────────────────────────────
        if "blocked by YouTube Music" in line or ("VPN" in line and "fail" in line.lower()):
            self._log(
                "ℹ️  Tip: if many tracks fail, YouTube Music may be rate-limiting you.\n"
                "     Wait a few minutes or use a VPN and try again.",
                "info")
            return

        # ── Rate limit ────────────────────────────────────────────────────────
        if "429" in line or "rate limit" in line.lower():
            self._log("⚠️  Rate limit — spotdl will retry automatically", "warning")
            return

        # ── Generic errors ────────────────────────────────────────────────────
        if any(k in line for k in ("Error", "error", "Failed", "failed")):
            noisy = ("WARNING", "DEBUG", "INFO", "charmap", "codec", "[download]")
            if not any(n in line for n in noisy):
                self._log(line, "error")
            return

        # ── Everything else ───────────────────────────────────────────────────
        if line.strip():
            self._log(line, "info")

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
                    self._log("✅  spotdl updated successfully", "success")
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
        if "spotify.com" in data:
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
        """Return the real Desktop path — handles OneDrive and locale redirects."""
        try:
            r = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "[Environment]::GetFolderPath('Desktop')"],
                capture_output=True, text=True, timeout=5, **_win_flags())
            path = r.stdout.strip()
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
            capture_output=True, text=True, **_win_flags())

        if os.path.exists(target):
            self._log("✅  Shortcut created on Desktop", "success")
        else:
            self._log(f"⚠️  Could not create shortcut: {result.stderr.strip()}", "warning")

    def _create_shortcut_unix(self, base: str, icon: str, script: str) -> None:
        python  = os.path.join(base, ".venv", "bin", "python")
        if not os.path.exists(python):
            python = sys.executable

        desktop_dirs = [
            os.environ.get("XDG_DESKTOP_DIR", ""),
            os.path.join(os.path.expanduser("~"), "Desktop"),
            os.path.join(os.path.expanduser("~"), "Bureau"),  # French locale
        ]
        desktop = next((d for d in desktop_dirs if d and os.path.isdir(d)), None)

        if sys.platform == "darwin":
            # macOS — .command file
            target = os.path.join(
                desktop or os.path.expanduser("~"), "SpotRR.command")
            with open(target, "w") as f:
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
        with open(target, "w") as f:
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

        # ── Note ──────────────────────────────────────────────────────────────
        _section("ℹ️  Note", color=C["blue"])
        _line(
            "Without credentials the app still works — it will use "
            "URL patterns to identify tracks. Adding your own credentials "
            "unlocks rich queue labels (song names, track counts) and "
            "avoids shared API rate limits."
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
        if sys.platform.startswith("win"):
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        self.root.mainloop()


# ─────────────────────────────────────────────────────────────────────────────
# Module-level helpers
# ─────────────────────────────────────────────────────────────────────────────

def _pkg_available(pkg: str) -> bool:
    """Return True if `pkg` can be imported."""
    try:
        importlib.import_module(pkg)
        return True
    except ImportError:
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
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
        logging.exception("Fatal error on startup")
        try:
            messagebox.showerror("Fatal Error", f"Could not start {APP_NAME}:\n\n{exc}")
        except Exception:
            print(f"Fatal: {exc}", file=sys.stderr)
        sys.exit(1)
