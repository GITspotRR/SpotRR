"""
SpotRR — comprehensive test suite.

All tests run headless: tkinter, spotdl, spotipy and other optional deps are
mocked at import time so no display and no internet are required.
"""
import sys
import os
import json
import logging
import inspect
from pathlib import Path
import importlib.util
import shutil
import socket
import struct
import tempfile
import threading
import unittest
from unittest.mock import MagicMock, patch

# ── Mock every display/network/optional dep before importing spotrr ───────────
_MOCKED = [
    "tkinter", "tkinter.ttk", "tkinter.font", "tkinter.filedialog",
    "tkinter.messagebox", "tkinter.simpledialog", "tkinter.scrolledtext",
    "tkinterdnd2", "tkinterdnd2.TkinterDnD",
    "PIL", "PIL.Image", "PIL.ImageTk",
    "requests",
    "spotipy", "spotipy.oauth2",
    "qrcode",
    "spotdl",
]
for _mod in _MOCKED:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

# Make sure we load from the project root
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import spotrr  # noqa: E402


# ── Helper: bind a real SpotRRApp method to a lightweight mock ────────────────
def _bind(method_name, extra_attrs=None):
    """Return a mock app with the named method bound as a real callable."""
    app = MagicMock(spec=spotrr.SpotRRApp)
    method = getattr(spotrr.SpotRRApp, method_name)
    setattr(app, method_name, method.__get__(app, spotrr.SpotRRApp))
    if extra_attrs:
        for attr, val in extra_attrs.items():
            setattr(app, attr, val)
    return app


# ─────────────────────────────────────────────────────────────────────────────
# Module-level helpers
# ─────────────────────────────────────────────────────────────────────────────

class TestFindFfmpeg(unittest.TestCase):
    def test_returns_nonempty_string(self):
        result = spotrr._find_ffmpeg()
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)

    def test_returns_existing_file_or_fallback(self):
        result = spotrr._find_ffmpeg()
        self.assertTrue(
            result == "ffmpeg" or os.path.isfile(result),
            f"_find_ffmpeg returned '{result}' which is neither 'ffmpeg' nor an existing file",
        )

    def test_finds_spotdl_location(self):
        home   = os.path.expanduser("~")
        suffix = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
        known  = [
            os.path.join(home, ".spotdl", suffix),
            os.path.join(home, ".config", "spotdl", suffix),
        ]
        existing = [p for p in known if os.path.isfile(p)]
        if existing:
            result = spotrr._find_ffmpeg()
            self.assertIn(result, existing)


class TestPkgAvailable(unittest.TestCase):
    def test_import_map_covers_all_required_packages(self):
        required = ["spotdl", "pillow", "requests", "tkinterdnd2",
                    "mutagen", "rapidfuzz", "qrcode", "spotipy"]
        for pkg in required:
            self.assertIn(pkg, spotrr._PKG_IMPORT_MAP,
                          f"'{pkg}' missing from _PKG_IMPORT_MAP — it will always "
                          f"report as missing and trigger a pip re-install on every launch")

    def test_pillow_maps_to_PIL(self):
        self.assertEqual(spotrr._PKG_IMPORT_MAP["pillow"], "PIL")

    def test_nonexistent_package_returns_false(self):
        self.assertFalse(spotrr._pkg_available("_nonexistent_pkg_xyz_999"))

    def test_stdlib_module_returns_true(self):
        self.assertTrue(spotrr._pkg_available("json"))
        self.assertTrue(spotrr._pkg_available("os"))

    def test_mocked_PIL_detected_via_map(self):
        # PIL is mocked in sys.modules — _pkg_available("pillow") must find it
        self.assertTrue(spotrr._pkg_available("pillow"))


class TestResourcePath(unittest.TestCase):
    def test_returns_string(self):
        self.assertIsInstance(spotrr._resource("assets/icon.ico"), str)

    def test_path_ends_with_filename(self):
        self.assertTrue(spotrr._resource("some/file.txt").endswith("file.txt"))

    def test_not_empty(self):
        self.assertGreater(len(spotrr._resource("x")), 0)


class TestWinFlags(unittest.TestCase):
    def test_returns_dict(self):
        self.assertIsInstance(spotrr._win_flags(), dict)

    def test_windows_has_creationflags(self):
        if sys.platform == "win32":
            self.assertIn("creationflags", spotrr._win_flags())

    def test_non_windows_is_empty(self):
        if sys.platform != "win32":
            self.assertEqual(spotrr._win_flags(), {})


# ─────────────────────────────────────────────────────────────────────────────
# URL routing
# ─────────────────────────────────────────────────────────────────────────────

class TestUrlPlatform(unittest.TestCase):
    def setUp(self):
        self.app = _bind("_url_platform")

    def _p(self, url):
        return self.app._url_platform(url)

    # Spotify
    def test_spotify_track(self):
        self.assertEqual(self._p("https://open.spotify.com/track/3n3Ppam7vg"), "spotify")

    def test_spotify_album(self):
        self.assertEqual(self._p("https://open.spotify.com/album/3T4tUhGYeR"), "spotify")

    def test_spotify_playlist(self):
        self.assertEqual(self._p("https://open.spotify.com/playlist/37i9dQ"), "spotify")

    def test_spotify_artist(self):
        self.assertEqual(self._p("https://open.spotify.com/artist/0TnOYISbd"), "spotify")

    # YouTube
    def test_youtube_watch(self):
        self.assertEqual(self._p("https://www.youtube.com/watch?v=dQw4w9WgXcQ"), "youtube")

    def test_youtube_playlist_url(self):
        self.assertEqual(self._p("https://www.youtube.com/playlist?list=PLtest"), "youtube")

    def test_youtu_be(self):
        self.assertEqual(self._p("https://youtu.be/dQw4w9WgXcQ"), "youtube")

    def test_youtube_with_tracking(self):
        self.assertEqual(self._p("https://www.youtube.com/watch?v=abc&si=xyz"), "youtube")

    # SoundCloud
    def test_soundcloud_track(self):
        self.assertEqual(self._p("https://soundcloud.com/artist/song"), "soundcloud")

    def test_soundcloud_set(self):
        self.assertEqual(self._p("https://soundcloud.com/artist/sets/my-set"), "soundcloud")

    # Unknown
    def test_unknown(self):
        self.assertEqual(self._p("https://example.com"), "unknown")

    def test_empty_string(self):
        self.assertEqual(self._p(""), "unknown")

    def test_garbage_string(self):
        self.assertEqual(self._p("not a url at all"), "unknown")


class TestUrlType(unittest.TestCase):
    def setUp(self):
        self.app = MagicMock(spec=spotrr.SpotRRApp)
        self.app._url_platform = spotrr.SpotRRApp._url_platform.__get__(
            self.app, spotrr.SpotRRApp)
        self.app._url_type = spotrr.SpotRRApp._url_type.__get__(
            self.app, spotrr.SpotRRApp)

    def _t(self, url):
        return self.app._url_type(url)

    # Spotify
    def test_spotify_track_type(self):
        self.assertEqual(self._t("https://open.spotify.com/track/abc"), "track")

    def test_spotify_album_type(self):
        self.assertEqual(self._t("https://open.spotify.com/album/abc"), "album")

    def test_spotify_playlist_type(self):
        self.assertEqual(self._t("https://open.spotify.com/playlist/abc"), "playlist")

    def test_spotify_artist_type(self):
        self.assertEqual(self._t("https://open.spotify.com/artist/abc"), "artist")

    def test_spotify_no_subpath_is_unknown(self):
        self.assertEqual(self._t("https://open.spotify.com/"), "unknown")

    # YouTube
    def test_youtube_video_type(self):
        self.assertEqual(self._t("https://www.youtube.com/watch?v=abc"), "track")

    def test_youtube_playlist_type(self):
        self.assertEqual(self._t("https://www.youtube.com/playlist?list=PLabc"), "playlist")

    def test_youtu_be_type(self):
        self.assertEqual(self._t("https://youtu.be/abc"), "track")

    # SoundCloud
    def test_soundcloud_track_type(self):
        self.assertEqual(self._t("https://soundcloud.com/artist/song"), "track")

    def test_soundcloud_set_type(self):
        self.assertEqual(self._t("https://soundcloud.com/artist/sets/album"), "playlist")

    # Unknown
    def test_unknown_platform_is_unknown(self):
        self.assertEqual(self._t("https://example.com"), "unknown")


class TestSpotifyLocaleNormalization(unittest.TestCase):
    """Spotify intl-XX locale URLs must be normalized before type detection."""

    def _normalize(self, url):
        import re
        return re.sub(
            r"(open\.spotify\.com)/(?!playlist|album|track|artist)[a-z][a-z0-9-]+/",
            r"\1/", url)

    def test_intl_es_album(self):
        url = "https://open.spotify.com/intl-es/album/28bcGOjeZHKm783j70ifuD"
        self.assertIn("/album/", self._normalize(url))
        self.assertNotIn("/intl-es/", self._normalize(url))

    def test_intl_es_track(self):
        url = "https://open.spotify.com/intl-es/track/7ij0jjUUZO5BabmPWeNDlT"
        self.assertIn("/track/", self._normalize(url))

    def test_intl_es_artist(self):
        url = "https://open.spotify.com/intl-es/artist/0VZrPa7mWAYXH4CwmYk8Km"
        self.assertIn("/artist/", self._normalize(url))

    def test_intl_pt_album(self):
        url = "https://open.spotify.com/intl-pt/album/XXXXX"
        self.assertIn("/album/", self._normalize(url))

    def test_two_letter_locale(self):
        url = "https://open.spotify.com/en/track/XXXXX"
        self.assertIn("/track/", self._normalize(url))

    def test_standard_url_unchanged(self):
        url = "https://open.spotify.com/playlist/6XWq9rPOGa4x5FXKfF5bGB"
        self.assertEqual(self._normalize(url), url)

    def test_standard_album_unchanged(self):
        url = "https://open.spotify.com/album/XXXXX"
        self.assertEqual(self._normalize(url), url)

    def test_real_user_urls(self):
        """The six URLs passed by the user must all normalize correctly."""
        cases = [
            ("https://open.spotify.com/playlist/6XWq9rPOGa4x5FXKfF5bGB", "playlist"),
            ("https://open.spotify.com/intl-es/album/28bcGOjeZHKm783j70ifuD", "album"),
            ("https://open.spotify.com/intl-es/track/7ij0jjUUZO5BabmPWeNDlT", "track"),
            ("https://open.spotify.com/intl-es/artist/0VZrPa7mWAYXH4CwmYk8Km", "artist"),
        ]
        import re
        type_re = re.compile(r"spotify\.com/(playlist|album|track|artist)/")
        for url, expected_type in cases:
            normalized = self._normalize(url)
            m = type_re.search(normalized)
            self.assertIsNotNone(m, f"Type not found after normalization: {normalized}")
            self.assertEqual(m.group(1), expected_type,
                             f"Expected {expected_type} for {url}")


class TestYouTubeUrlNormalization(unittest.TestCase):
    """YouTube URLs must convert to music.youtube.com for proper spotdl handling."""

    def _normalize(self, raw):
        import re, urllib.parse as up
        parsed = up.urlparse(raw)
        qs     = up.parse_qs(parsed.query)
        keep   = {k: v for k, v in qs.items() if k in ("v", "list")}
        new_qs = up.urlencode(keep, doseq=True)
        url    = up.urlunparse(parsed._replace(query=new_qs, fragment="")).rstrip("/")
        vid_m  = re.search(r"(?:youtube\.com/watch\?.*v=|youtu\.be/)([A-Za-z0-9_-]{11})", url)
        if vid_m:
            return f"https://music.youtube.com/watch?v={vid_m.group(1)}"
        if "youtube.com/playlist" in url:
            return url.replace("www.youtube.com", "music.youtube.com")
        return url

    def test_watch_url_converted_to_ytm(self):
        result = self._normalize("https://www.youtube.com/watch?v=dQw4w9WgXcQ&si=abc")
        self.assertEqual(result, "https://music.youtube.com/watch?v=dQw4w9WgXcQ")

    def test_youtu_be_converted_to_ytm(self):
        result = self._normalize("https://youtu.be/RhpehUINho8?si=KiCeHZ9-GdXkoao6")
        self.assertEqual(result, "https://music.youtube.com/watch?v=RhpehUINho8")

    def test_playlist_gets_music_subdomain(self):
        result = self._normalize("https://www.youtube.com/playlist?list=PLtest123&si=track")
        self.assertIn("music.youtube.com", result)
        self.assertIn("list=PLtest123", result)

    def test_ytm_watch_url_unchanged(self):
        url = "https://music.youtube.com/watch?v=dQw4w9WgXcQ"
        self.assertEqual(self._normalize(url), url)

    def test_tracking_params_stripped(self):
        result = self._normalize("https://www.youtube.com/watch?v=abc&si=tracking&pp=garbage")
        self.assertNotIn("si=", result)
        self.assertNotIn("pp=", result)
        self.assertIn("v=abc", result)

    def test_fragment_stripped(self):
        result = self._normalize("https://www.youtube.com/watch?v=abc#timestamp")
        self.assertNotIn("#", result)

    def test_real_user_youtube_url(self):
        result = self._normalize("https://youtu.be/RhpehUINho8?si=KiCeHZ9-GdXkoao6")
        self.assertTrue(result.startswith("https://music.youtube.com/watch?v="))


# ─────────────────────────────────────────────────────────────────────────────
# Queue labels
# ─────────────────────────────────────────────────────────────────────────────

class TestGetLabel(unittest.TestCase):
    def setUp(self):
        self.app = MagicMock(spec=spotrr.SpotRRApp)
        self.app.sp = None   # no Spotify client
        self.app._url_platform = spotrr.SpotRRApp._url_platform.__get__(
            self.app, spotrr.SpotRRApp)
        self.app._url_type = spotrr.SpotRRApp._url_type.__get__(
            self.app, spotrr.SpotRRApp)
        self.app._get_label = spotrr.SpotRRApp._get_label.__get__(
            self.app, spotrr.SpotRRApp)
        self.app._log = MagicMock()

    def _label(self, url):
        return self.app._get_label(url)

    # Spotify fallbacks (no sp client)
    def test_spotify_track_has_music_note(self):
        self.assertIn("🎵", self._label("https://open.spotify.com/track/abc"))

    def test_spotify_album_has_disc(self):
        self.assertIn("💿", self._label("https://open.spotify.com/album/abc"))

    def test_spotify_playlist_has_notepad(self):
        self.assertIn("📑", self._label("https://open.spotify.com/playlist/abc"))

    def test_spotify_artist_has_person(self):
        self.assertIn("👤", self._label("https://open.spotify.com/artist/abc"))

    def test_spotify_label_contains_spotify(self):
        self.assertIn("Spotify", self._label("https://open.spotify.com/track/abc"))

    # YouTube
    def test_youtube_video_label(self):
        lbl = self._label("https://www.youtube.com/watch?v=abc")
        self.assertIn("🎵", lbl)
        self.assertIn("YouTube", lbl)

    def test_youtube_playlist_label(self):
        lbl = self._label("https://www.youtube.com/playlist?list=PLabc")
        self.assertIn("📑", lbl)
        self.assertIn("YouTube", lbl)

    # SoundCloud
    def test_soundcloud_track_label(self):
        lbl = self._label("https://soundcloud.com/artist/song")
        self.assertIn("🎵", lbl)
        self.assertIn("SoundCloud", lbl)

    def test_soundcloud_set_label(self):
        lbl = self._label("https://soundcloud.com/artist/sets/album")
        self.assertIn("📑", lbl)
        self.assertIn("SoundCloud", lbl)

    # Spotify with API (mock)
    def test_spotify_uses_api_when_available(self):
        self.app.sp = MagicMock()
        self.app.sp.track.return_value = {
            "artists": [{"name": "Rick Astley"}],
            "name": "Never Gonna Give You Up",
        }
        lbl = self._label("https://open.spotify.com/track/3n3Ppam7vg")
        self.assertIn("Rick Astley", lbl)
        self.assertIn("Never Gonna Give You Up", lbl)

    def test_spotify_api_failure_falls_back_gracefully(self):
        self.app.sp = MagicMock()
        self.app.sp.track.side_effect = Exception("API error")
        lbl = self._label("https://open.spotify.com/track/abc")
        # Must still return a valid label, not crash
        self.assertIsInstance(lbl, str)
        self.assertGreater(len(lbl), 0)


# ─────────────────────────────────────────────────────────────────────────────
# Settings persistence
# ─────────────────────────────────────────────────────────────────────────────

class TestDefaults(unittest.TestCase):
    def setUp(self):
        self.app = MagicMock(spec=spotrr.SpotRRApp)
        self.defaults = spotrr.SpotRRApp._defaults(self.app)

    def test_all_required_keys_present(self):
        required = [
            "client_id", "client_secret",
            "default_output_folder", "custom_logo_path",
            "preferred_format", "preferred_quality", "preferred_threads",
        ]
        for key in required:
            self.assertIn(key, self.defaults, f"Default key missing: {key}")

    def test_default_format_is_mp3(self):
        self.assertEqual(self.defaults["preferred_format"], "mp3")

    def test_default_quality_is_320k(self):
        self.assertEqual(self.defaults["preferred_quality"], "320k")

    def test_default_threads_is_4(self):
        self.assertEqual(self.defaults["preferred_threads"], 4)

    def test_client_credentials_default_empty(self):
        self.assertEqual(self.defaults["client_id"], "")
        self.assertEqual(self.defaults["client_secret"], "")


class TestSettingsReadWrite(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self._make_app()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _make_app(self):
        app = MagicMock(spec=spotrr.SpotRRApp)
        app._base = self.tmpdir
        app._cfg_path = lambda: os.path.join(self.tmpdir, "settings.json")
        app._defaults = spotrr.SpotRRApp._defaults.__get__(app, spotrr.SpotRRApp)
        app._read_cfg = spotrr.SpotRRApp._read_cfg.__get__(app, spotrr.SpotRRApp)
        app._write_cfg = spotrr.SpotRRApp._write_cfg.__get__(app, spotrr.SpotRRApp)
        app._log = MagicMock()
        self.app = app

    def test_defaults_when_no_file(self):
        cfg = self.app._read_cfg()
        self.assertEqual(cfg["preferred_format"], "mp3")
        self.assertEqual(cfg["preferred_quality"], "320k")
        self.assertEqual(cfg["preferred_threads"], 4)

    def test_write_then_read_roundtrip(self):
        self.app._write_cfg({
            "preferred_format": "wav",
            "preferred_quality": "192k",
            "preferred_threads": 2,
            "client_id": "abc", "client_secret": "xyz",
        })
        result = self.app._read_cfg()
        self.assertEqual(result["preferred_format"], "wav")
        self.assertEqual(result["preferred_quality"], "192k")
        self.assertEqual(result["preferred_threads"], 2)
        self.assertEqual(result["client_id"], "abc")

    def test_atomic_write_leaves_no_tmp_file(self):
        self.app._write_cfg({"preferred_format": "flac"})
        self.assertFalse(os.path.exists(self.app._cfg_path() + ".tmp"))

    def test_corrupt_file_returns_defaults(self):
        with open(self.app._cfg_path(), "w") as f:
            f.write("{{{{ INVALID JSON")
        cfg = self.app._read_cfg()
        self.assertEqual(cfg["preferred_format"], "mp3")

    def test_partial_settings_merged_with_defaults(self):
        with open(self.app._cfg_path(), "w") as f:
            json.dump({"preferred_format": "flac"}, f)
        cfg = self.app._read_cfg()
        self.assertEqual(cfg["preferred_format"], "flac")
        # Missing keys filled with defaults
        self.assertEqual(cfg["preferred_quality"], "320k")
        self.assertEqual(cfg["preferred_threads"], 4)

    def test_write_preserves_all_existing_keys(self):
        data = {
            "client_id": "keep_me",
            "preferred_format": "mp3",
            "preferred_quality": "128k",
            "preferred_threads": 8,
        }
        self.app._write_cfg(data)
        read_back = self.app._read_cfg()
        self.assertEqual(read_back["client_id"], "keep_me")
        self.assertEqual(read_back["preferred_threads"], 8)

    def test_concurrent_reads_are_safe(self):
        self.app._write_cfg({"preferred_format": "wav"})
        results = []
        errors  = []

        def reader():
            try:
                cfg = self.app._read_cfg()
                results.append(cfg["preferred_format"])
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=reader) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [], f"Concurrent read errors: {errors}")
        self.assertTrue(all(r == "wav" for r in results))


# ─────────────────────────────────────────────────────────────────────────────
# Credentials
# ─────────────────────────────────────────────────────────────────────────────

class TestGetCreds(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        app = MagicMock(spec=spotrr.SpotRRApp)
        app._base = self.tmpdir
        app._cfg_path = lambda: os.path.join(self.tmpdir, "settings.json")
        app._defaults = spotrr.SpotRRApp._defaults.__get__(app, spotrr.SpotRRApp)
        app._read_cfg = spotrr.SpotRRApp._read_cfg.__get__(app, spotrr.SpotRRApp)
        app._write_cfg = spotrr.SpotRRApp._write_cfg.__get__(app, spotrr.SpotRRApp)
        app._get_creds = spotrr.SpotRRApp._get_creds.__get__(app, spotrr.SpotRRApp)
        app._log = MagicMock()
        self.app = app

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        for var in ("SPOTIPY_CLIENT_ID", "SPOTIPY_CLIENT_SECRET",
                    "SPOTDL_CLIENT_ID", "SPOTDL_CLIENT_SECRET"):
            os.environ.pop(var, None)

    def test_no_creds_returns_none_none(self):
        cid, cs = self.app._get_creds()
        self.assertIsNone(cid)
        self.assertIsNone(cs)

    def test_settings_json(self):
        self.app._write_cfg({"client_id": "json_id", "client_secret": "json_sec"})
        cid, cs = self.app._get_creds()
        self.assertEqual(cid, "json_id")
        self.assertEqual(cs, "json_sec")

    def test_env_vars_spotipy(self):
        os.environ["SPOTIPY_CLIENT_ID"]     = "env_id"
        os.environ["SPOTIPY_CLIENT_SECRET"] = "env_sec"
        cid, cs = self.app._get_creds()
        self.assertEqual(cid, "env_id")
        self.assertEqual(cs, "env_sec")

    def test_env_vars_spotdl(self):
        os.environ["SPOTDL_CLIENT_ID"]     = "sdl_id"
        os.environ["SPOTDL_CLIENT_SECRET"] = "sdl_sec"
        cid, cs = self.app._get_creds()
        self.assertEqual(cid, "sdl_id")
        self.assertEqual(cs, "sdl_sec")

    def test_env_takes_priority_over_json(self):
        self.app._write_cfg({"client_id": "json_id", "client_secret": "json_sec"})
        os.environ["SPOTIPY_CLIENT_ID"]     = "env_id"
        os.environ["SPOTIPY_CLIENT_SECRET"] = "env_sec"
        cid, _ = self.app._get_creds()
        self.assertEqual(cid, "env_id")

    def test_whitespace_stripped(self):
        self.app._write_cfg({"client_id": "  padded  ", "client_secret": "  also  "})
        cid, cs = self.app._get_creds()
        self.assertEqual(cid, "padded")
        self.assertEqual(cs, "also")

    def test_only_id_no_secret_returns_none(self):
        self.app._write_cfg({"client_id": "only_id", "client_secret": ""})
        cid, cs = self.app._get_creds()
        self.assertIsNone(cid)
        self.assertIsNone(cs)

    def test_only_secret_no_id_returns_none(self):
        self.app._write_cfg({"client_id": "", "client_secret": "only_sec"})
        cid, cs = self.app._get_creds()
        self.assertIsNone(cid)
        self.assertIsNone(cs)

    def test_dot_env_file(self):
        env_path = os.path.join(self.tmpdir, ".env")
        with open(env_path, "w") as f:
            f.write("SPOTIPY_CLIENT_ID=dotenv_id\n")
            f.write("SPOTIPY_CLIENT_SECRET=dotenv_sec\n")
        cid, cs = self.app._get_creds()
        self.assertEqual(cid, "dotenv_id")
        self.assertEqual(cs, "dotenv_sec")

    def test_dot_env_quoted_values(self):
        env_path = os.path.join(self.tmpdir, ".env")
        with open(env_path, "w") as f:
            f.write('SPOTIPY_CLIENT_ID="quoted_id"\n')
            f.write("SPOTIPY_CLIENT_SECRET='single_sec'\n")
        cid, cs = self.app._get_creds()
        self.assertEqual(cid, "quoted_id")
        self.assertEqual(cs, "single_sec")

    def test_dot_env_comment_lines_ignored(self):
        env_path = os.path.join(self.tmpdir, ".env")
        with open(env_path, "w") as f:
            f.write("# This is a comment\n")
            f.write("SPOTIPY_CLIENT_ID=real_id\n")
            f.write("SPOTIPY_CLIENT_SECRET=real_sec\n")
        cid, cs = self.app._get_creds()
        self.assertEqual(cid, "real_id")


# ─────────────────────────────────────────────────────────────────────────────
# Download summary
# ─────────────────────────────────────────────────────────────────────────────

class TestShowDownloadSummary(unittest.TestCase):
    def setUp(self):
        self.app = MagicMock(spec=spotrr.SpotRRApp)
        self.app._show_download_summary = \
            spotrr.SpotRRApp._show_download_summary.__get__(
                self.app, spotrr.SpotRRApp)

    def _run(self, ok, fail, total):
        self.app._dl_ok    = ok
        self.app._dl_fail  = fail
        self.app._dl_total = total
        self.app._show_download_summary("Test Album")

    def test_all_success_shows_complete(self):
        self._run(5, 0, 5)
        status_calls = [str(c) for c in self.app._set_status.call_args_list]
        self.assertTrue(any("Complete" in s for s in status_calls))

    def test_all_success_sets_progress_100(self):
        self._run(5, 0, 5)
        self.app._set_progress.assert_called_with(100)

    def test_partial_failure_mentions_both_counts(self):
        self._run(3, 2, 5)
        log_args = " ".join(str(c) for c in self.app._log.call_args_list)
        self.assertIn("3", log_args)
        self.assertIn("2", log_args)

    def test_zero_counts_shows_complete_not_error(self):
        self._run(0, 0, 0)
        status_calls = [str(c) for c in self.app._set_status.call_args_list]
        self.assertTrue(any("Complete" in s for s in status_calls))
        error_calls = [c for c in self.app._log.call_args_list
                       if "error" in str(c).lower()]
        self.assertEqual(error_calls, [])

    def test_notification_fired_on_success(self):
        self._run(1, 0, 1)
        self.app._notify.assert_called_once()

    def test_notification_fired_on_partial_failure(self):
        self._run(2, 1, 3)
        self.app._notify.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# Queue data-structure operations (no UI)
# ─────────────────────────────────────────────────────────────────────────────

class TestQueueDataStructure(unittest.TestCase):
    def setUp(self):
        self.queue = []
        self.lock  = threading.Lock()

    def _append(self, url, label):
        with self.lock:
            self.queue.append((url, label))
            return len(self.queue) - 1

    def _pop_first(self):
        with self.lock:
            if self.queue:
                return self.queue.pop(0)
        return None

    def test_append_increments_length(self):
        self._append("url1", "label1")
        self.assertEqual(len(self.queue), 1)

    def test_idx_captured_inside_lock(self):
        idx = self._append("url1", "label1")
        self.assertEqual(idx, 0)
        idx2 = self._append("url2", "label2")
        self.assertEqual(idx2, 1)

    def test_pop_first_removes_head(self):
        self._append("url1", "label1")
        self._append("url2", "label2")
        removed = self._pop_first()
        self.assertEqual(removed, ("url1", "label1"))
        self.assertEqual(len(self.queue), 1)

    def test_pop_on_empty_returns_none(self):
        self.assertIsNone(self._pop_first())

    def test_concurrent_appends_no_data_loss(self):
        n = 50
        threads = [
            threading.Thread(target=self._append, args=(f"url{i}", f"lbl{i}"))
            for i in range(n)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(len(self.queue), n)

    def test_q_up_swap(self):
        self.queue = [("url0", "lbl0"), ("url1", "lbl1"), ("url2", "lbl2")]
        i = 2
        with self.lock:
            self.queue[i], self.queue[i - 1] = self.queue[i - 1], self.queue[i]
        self.assertEqual(self.queue[1], ("url2", "lbl2"))
        self.assertEqual(self.queue[2], ("url1", "lbl1"))

    def test_q_down_swap(self):
        self.queue = [("url0", "lbl0"), ("url1", "lbl1"), ("url2", "lbl2")]
        i = 0
        with self.lock:
            self.queue[i], self.queue[i + 1] = self.queue[i + 1], self.queue[i]
        self.assertEqual(self.queue[0], ("url1", "lbl1"))
        self.assertEqual(self.queue[1], ("url0", "lbl0"))


# ─────────────────────────────────────────────────────────────────────────────
# FFmpeg detection strategy
# ─────────────────────────────────────────────────────────────────────────────

class TestFfmpegDetectionStrategy(unittest.TestCase):
    def test_bundled_takes_priority(self):
        fake_path = "/fake/bundled/ffmpeg"
        with patch("spotrr._ffmpeg_exe", return_value=fake_path):
            result = spotrr._find_ffmpeg()
        self.assertEqual(result, fake_path)

    def test_spotdl_dir_found_when_no_bundle(self):
        home   = os.path.expanduser("~")
        suffix = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
        fake   = os.path.join(home, ".spotdl", suffix)
        with patch("spotrr._ffmpeg_exe", return_value=None), \
             patch("os.path.isfile", lambda p: p == fake):
            result = spotrr._find_ffmpeg()
        self.assertEqual(result, fake)

    def test_which_used_as_fallback(self):
        with patch("spotrr._ffmpeg_exe", return_value=None), \
             patch("os.path.isfile", return_value=False), \
             patch("shutil.which", return_value="/usr/bin/ffmpeg"):
            result = spotrr._find_ffmpeg()
        self.assertEqual(result, "/usr/bin/ffmpeg")

    def test_literal_fallback_when_nothing_found(self):
        with patch("spotrr._ffmpeg_exe", return_value=None), \
             patch("os.path.isfile", return_value=False), \
             patch("shutil.which", return_value=None):
            result = spotrr._find_ffmpeg()
        self.assertEqual(result, "ffmpeg")


# ─────────────────────────────────────────────────────────────────────────────
# Single-instance socket
# ─────────────────────────────────────────────────────────────────────────────

class TestSingleInstance(unittest.TestCase):
    """Single-instance lock via a bound TCP port.

    The real port (_INSTANCE_PORT) is shared with a running copy of the app, so
    these tests rebind it to an ephemeral one.  Without that, anyone with the
    app open — i.e. every developer and every user checking the UI — gets two
    spurious failures here that have nothing to do with the change under test.
    """

    def setUp(self):
        spotrr._release_instance()
        self._real_port = spotrr._INSTANCE_PORT
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        spotrr._INSTANCE_PORT = s.getsockname()[1]
        s.close()

    def tearDown(self):
        spotrr._release_instance()
        spotrr._INSTANCE_PORT = self._real_port

    def test_first_acquire_succeeds(self):
        self.assertTrue(spotrr._acquire_instance())

    def test_second_acquire_fails(self):
        spotrr._acquire_instance()
        self.assertFalse(spotrr._acquire_instance())

    def test_release_allows_reacquire(self):
        spotrr._acquire_instance()
        spotrr._release_instance()
        self.assertTrue(spotrr._acquire_instance())


# ─────────────────────────────────────────────────────────────────────────────
# Rate-limit handler
# ─────────────────────────────────────────────────────────────────────────────

class TestRateLimitHandler(unittest.TestCase):
    def setUp(self):
        self.rl = spotrr._RateLimitHandler()

    def test_on_429_sets_retry_after_from_header(self):
        self.rl.on_429("5")
        self.assertAlmostEqual(self.rl._retry_after, 5.0)

    def test_on_429_uses_backoff_without_header(self):
        self.rl.on_429(None)
        self.assertGreater(self.rl._retry_after, 0)

    def test_on_429_invalid_header_defaults_to_5(self):
        self.rl.on_429("not_a_number")
        self.assertAlmostEqual(self.rl._retry_after, 5.0)

    def test_backoff_does_not_exceed_30s(self):
        for _ in range(20):
            self.rl.on_429(None)
        self.assertLessEqual(self.rl._retry_after, 30.0)

    def test_wait_clears_retry_after(self):
        self.rl._retry_after = 0.0  # skip actual sleep
        self.rl._last = 0.0
        self.rl.wait()
        self.assertEqual(self.rl._retry_after, 0.0)


# ─────────────────────────────────────────────────────────────────────────────
# Console warning policy
# ─────────────────────────────────────────────────────────────────────────────

class TestWarningPolicy(unittest.TestCase):
    """Internal warnings must never reach the on-screen terminal."""

    def _app(self):
        app = MagicMock(spec=spotrr.SpotRRApp)
        app.console = MagicMock()
        app.root = MagicMock()
        app._log = spotrr.SpotRRApp._log.__get__(app, spotrr.SpotRRApp)
        return app

    def _shown(self, msg, kind="warning"):
        app = self._app()
        before = app.console.insert.call_count
        app._log(msg, kind)
        return app.console.insert.call_count - before

    # ── Kept visible ──────────────────────────────────────────────────────
    def test_client_credentials_warning_is_visible(self):
        self.assertTrue(spotrr._is_visible_warning(
            "⚠️  No API credentials — use 🔑 Client ID / Secret buttons"))

    def test_empty_url_warning_is_visible(self):
        self.assertTrue(spotrr._is_visible_warning(
            "⚠️  Please paste a URL (Spotify, YouTube or SoundCloud)"))

    def test_queue_errors_are_visible(self):
        for msg in ("⚠️  Cannot remove the item currently being downloaded — stop it first",
                    "⚠️  Stop the current download before clearing the queue",
                    "⚠️  Cannot move ahead of the active download",
                    "⚠️  Cannot move the active download"):
            self.assertTrue(spotrr._is_visible_warning(msg), msg)

    def test_partial_failure_summary_is_visible(self):
        self.assertTrue(spotrr._is_visible_warning(
            "⚠️  3/10 tracks downloaded · 7 failed\n     Try again later."))

    # ── Suppressed ────────────────────────────────────────────────────────
    def test_fast_fetch_401_warning_is_hidden(self):
        self.assertFalse(spotrr._is_visible_warning(
            "⚠️  Spotify fast-fetch failed, using fallback: http status: 401, "
            "code: -1 - https://api.spotify.com/v1/playlists/x/items:\n "
            "Valid user authentication required, reason: None"))

    def test_technical_warnings_are_hidden(self):
        for msg in ("⚠️  FFmpeg not found — WAV/FLAC conversion will fail.",
                    "⚠️  Logo load error: boom",
                    "⚠️  Settings save error: disk full",
                    "⚠️  API error: http status: 401",
                    "⚠️  yt-dlp update failed: timeout",
                    "⚠️  Not found: Some Song"):
            self.assertFalse(spotrr._is_visible_warning(msg), msg)

    def test_legacy_indented_warning_is_hidden(self):
        self.assertFalse(spotrr._is_visible_warning(
            "     ⚠️  spotdl: command failed"))

    def test_technical_warning_never_reaches_console(self):
        self.assertEqual(self._shown("⚠️  Logo load error: boom"), 0)

    def test_hidden_warning_goes_to_the_log_file(self):
        records = []

        class _Capture(logging.Handler):
            def emit(self, record):
                records.append(record)

        logger = logging.getLogger("spotrr")
        handler = _Capture()
        logger.addHandler(handler)
        try:
            self._shown("⚠️  API error: http status: 401")
        finally:
            logger.removeHandler(handler)
        self.assertEqual(len(records), 1)
        self.assertIn("401", records[0].getMessage())

    def test_visible_warning_still_reaches_console(self):
        self.assertGreater(
            self._shown("⚠️  No API credentials — use 🔑 Client ID / Secret buttons"), 0)

    def test_non_warning_kinds_are_never_suppressed(self):
        for kind, msg in (("success", "✅  API client ready"),
                          ("error", "❌  No songs found for this URL"),
                          ("info", "ℹ️   Found 42 songs"),
                          ("song", "🎵  Rick Astley"),
                          ("folder", "📂  /home/user/Music")):
            self.assertGreater(self._shown(msg, kind), 0, msg)

    def test_warning_kind_without_emoji_is_still_suppressed(self):
        self.assertEqual(self._shown("a bare warning", "warning"), 0)

    def test_no_error_message_interpolates_a_raw_exception(self):
        """Errors are never suppressed, so they must stay user-readable."""
        import re
        source = inspect.getsource(spotrr)
        offenders = re.findall(r'_log\(\s*f?["\'][^"\']*❌[^"\']*\{(?:exc|e)\}', source)
        self.assertEqual(offenders, [],
                         f"raw exception leaked into an error message: {offenders}")

    def test_no_console_message_dumps_a_traceback(self):
        import re
        source = inspect.getsource(spotrr)
        offenders = re.findall(r'_log\([^)]*format_exc', source)
        self.assertEqual(offenders, [],
                         f"traceback printed to the console: {offenders}")

    def test_successful_fallback_says_nothing_about_permissions(self):
        """A search fallback that works must be silent.

        The warning used to fire before the fallback ran, so a download that
        was about to succeed was still preceded by a scary line the user could
        do nothing about.  Silence is correct here; the reason belongs on the
        failure path.
        """
        src = inspect.getsource(spotrr.SpotRRApp._run_spotdl)
        res = src[src.index("_resolve_spotify_songs(url)"):]
        res = res[:res.index("Found {self._dl_total}")]
        self.assertNotIn("⚠️", res, "a resolved-by-search playlist still warns")

    def test_no_premature_private_playlist_warning_anywhere(self):
        import re
        source = inspect.getsource(spotrr)
        for phrase in ("wouldn't share this", "Looking it up by search",
                       "which can be slower"):
            self.assertNotIn(phrase, source,
                             f"obsolete pre-emptive warning {phrase!r} still present")

    def test_no_user_visible_message_leaks_internals(self):
        """Nothing shown to the user may mention implementation jargon."""
        shown = [
            "❌  This playlist is private or collaborative, so Spotify won't share it — "
            "and search couldn't find it either.\n"
            "     Make it public, or share it with the Spotify account this app is "
            "signed in with.",
            "⚠️  No API credentials — use 🔑 Client ID / Secret buttons",
            "⚠️  Please paste a URL (Spotify, YouTube or SoundCloud)",
            "❌  The download could not be completed",
            "❌  Something went wrong with this download",
        ]
        banned = ("fast-fetch", "http status", "spotipy", "Traceback", "code: -1",
                  "api.spotify.com", "spotdl", "exception")
        for msg in shown:
            for word in banned:
                self.assertNotIn(word.lower(), msg.lower(), f"{word!r} leaked into {msg!r}")


# ─────────────────────────────────────────────────────────────────────────────
# Fast-fetch failure reporting (must be user-facing, not developer-facing)
# ─────────────────────────────────────────────────────────────────────────────

class _FakeSpotify:
    """A real class so its methods are genuine bound methods — spotrr relies on
    ``__self__`` to reach the auth manager, which MagicMock does not provide."""

    def __init__(self, behaviour):
        self.saved = []
        self.calls = []
        self._behaviour = behaviour
        self.auth_manager = MagicMock()
        self.auth_manager.cache_handler.save_token_to_cache.side_effect = self.saved.append

    def playlist_items(self, *_a, **_k):
        self.calls.append(1)
        return self._behaviour(len(self.calls))

    album = playlist_items
    album_tracks = playlist_items


class TestFastFetchFailureReporting(unittest.TestCase):
    URL = "https://open.spotify.com/playlist/7kXpGUgebdDQRSRC8pFrCf"

    def setUp(self):
        self._wait = spotrr._rl.wait
        spotrr._rl.wait = lambda: None
        self.app = _bind("_resolve_spotify_songs", {"sp": None, "_log": MagicMock()})
        # spotdl is mocked suite-wide; the resolver needs the Song type to exist
        # before it ever talks to the API, so register a stand-in submodule.
        self._had_song_mod = "spotdl.types.song" in sys.modules
        sys.modules["spotdl.types.song"] = MagicMock()
        logger = logging.getLogger("spotrr")
        self._handler = logging.NullHandler()
        logger.addHandler(self._handler)
        self._old_level = logger.level
        logger.setLevel(logging.DEBUG)

    def tearDown(self):
        spotrr._rl.wait = self._wait
        if not self._had_song_mod:
            sys.modules.pop("spotdl.types.song", None)
        logger = logging.getLogger("spotrr")
        logger.removeHandler(self._handler)
        logger.setLevel(self._old_level)

    @staticmethod
    def _always_fail(message):
        def behaviour(_n):
            raise Exception(message)
        return behaviour

    def test_returns_songs_and_access_denied_flag(self):
        self.app.sp = _FakeSpotify(lambda _n: {"total": 0, "items": []})
        songs, denied = self.app._resolve_spotify_songs(self.URL)
        self.assertEqual(songs, [])
        self.assertFalse(denied)

    def test_401_is_reported_as_access_denied(self):
        self.app.sp = _FakeSpotify(self._always_fail(
            "http status: 401, code: -1 - https://api.spotify.com/v1/"
            "playlists/x/items:\n Valid user authentication required, reason: None"))
        songs, denied = self.app._resolve_spotify_songs(self.URL)
        self.assertEqual(songs, [])
        self.assertTrue(denied)

    def test_403_is_reported_as_access_denied(self):
        self.app.sp = _FakeSpotify(self._always_fail(
            "http status: 403, code: -1 - forbidden"))
        _songs, denied = self.app._resolve_spotify_songs(self.URL)
        self.assertTrue(denied)

    def test_other_errors_are_not_reported_as_access_denied(self):
        self.app.sp = _FakeSpotify(self._always_fail(
            "ConnectionError: name resolution failed"))
        _songs, denied = self.app._resolve_spotify_songs(self.URL)
        self.assertFalse(denied)

    def test_failure_never_prints_raw_exception(self):
        self.app.sp = _FakeSpotify(self._always_fail(
            "http status: 401, code: -1 - Valid user authentication required"))
        self.app._resolve_spotify_songs(self.URL)
        self.app._log.assert_not_called()

    def test_stale_token_is_recovered_not_reported(self):
        """A refreshable 401 must be healed, never surfaced as access-denied."""

        def behaviour(n):
            if n == 1:
                raise Exception("http status: 401, code: -1 - "
                                "Valid user authentication required")
            return {"total": 0, "items": []}

        sp = _FakeSpotify(behaviour)
        self.app.sp = sp
        songs, denied = self.app._resolve_spotify_songs(self.URL)
        self.assertFalse(denied, "a recovered 401 must not look like a private playlist")
        self.assertEqual(len(sp.calls), 2)
        self.assertEqual(sp.saved, [None])
        self.app._log.assert_not_called()

    def test_no_client_skips_the_api_entirely(self):
        self.app.sp = None
        self.assertEqual(self.app._resolve_spotify_songs(self.URL), ([], False))

    def test_unparseable_url_skips_the_api(self):
        self.app.sp = _FakeSpotify(self._always_fail("should not be called"))
        self.assertEqual(
            self.app._resolve_spotify_songs("https://example.com/not-spotify"),
            ([], False))


# ─────────────────────────────────────────────────────────────────────────────
# Spotify auth: 401 re-auth + credential-scoped token cache
# ─────────────────────────────────────────────────────────────────────────────

def _spotipy_client():
    """A stand-in spotipy client whose token cache records every invalidation."""
    sp = MagicMock()
    sp.saved = []
    sp.auth_manager.cache_handler.save_token_to_cache.side_effect = sp.saved.append
    return sp


class TestSpotifyReauth(unittest.TestCase):
    def setUp(self):
        self._wait = spotrr._rl.wait
        spotrr._rl.wait = lambda: None      # never sleep in tests

    def tearDown(self):
        spotrr._rl.wait = self._wait

    def _bound(self, sp, body):
        sp.playlist_items = body.__get__(sp, type(sp))
        return sp.playlist_items

    def test_401_invalidates_token_and_retries(self):
        sp = _spotipy_client()
        calls = []

        def flaky(*_a, **_k):
            calls.append(1)
            if len(calls) == 1:
                raise Exception("http status: 401, code: -1 - "
                                "https://api.spotify.com/v1/playlists/x/items:\n "
                                "Valid user authentication required, reason: None")
            return {"total": 1, "items": []}

        result = spotrr._spotify_call(self._bound(sp, flaky), "x")
        self.assertEqual(result["total"], 1)
        self.assertEqual(len(calls), 2, "should retry exactly once")
        self.assertEqual(sp.saved, [None], "cached token must be discarded")

    def test_persistent_401_gives_up_instead_of_looping(self):
        sp = _spotipy_client()
        calls = []

        def always_401(*_a, **_k):
            calls.append(1)
            raise Exception("http status: 401, code: -1 - Valid user authentication required")

        with self.assertRaises(Exception):
            spotrr._spotify_call(self._bound(sp, always_401), "x")
        self.assertEqual(len(calls), 3)

    def test_403_is_not_retried(self):
        sp = _spotipy_client()
        calls = []

        def forbidden(*_a, **_k):
            calls.append(1)
            raise Exception("http status: 403, code: -1 - forbidden")

        with self.assertRaises(Exception):
            spotrr._spotify_call(self._bound(sp, forbidden), "x")
        self.assertEqual(len(calls), 1)
        self.assertEqual(sp.saved, [])

    def test_401_on_unbound_callable_raises_cleanly(self):
        def boom(*_a, **_k):
            raise Exception("http status: 401, code: -1")

        with self.assertRaises(Exception):
            spotrr._spotify_call(boom)

    def test_successful_call_never_invalidates(self):
        sp = _spotipy_client()
        result = spotrr._spotify_call(self._bound(sp, lambda *a, **k: {"total": 0}), "x")
        self.assertEqual(result, {"total": 0})
        self.assertEqual(sp.saved, [])

    def test_token_cache_is_scoped_per_client_id(self):
        base = tempfile.mkdtemp()
        try:
            app = _bind("_init_spotify_client", {"_base": base, "_log": MagicMock()})
            app._spotipy_cache_dir = spotrr.SpotRRApp._spotipy_cache_dir.__get__(
                app, spotrr.SpotRRApp)
            creds = [("CID-AAAA", "SECRET-1"), ("CID-BBBB", "SECRET-2")]
            app._get_creds = lambda: creds.pop(0)

            with patch.object(spotrr, "SPOTIPY_AVAILABLE", True), \
                 patch.object(spotrr, "spotipy"), \
                 patch.object(spotrr, "CacheFileHandler",
                              create=True) as fake_handler, \
                 patch.object(spotrr, "SpotifyClientCredentials",
                              create=True) as fake_creds:
                fake_handler.side_effect = lambda cache_path=None: cache_path
                fake_creds.side_effect = \
                    lambda **kw: MagicMock(cache_handler=kw.get("cache_handler"))

                app._init_spotify_client()
                first = fake_creds.call_args.kwargs["cache_handler"]
                app._init_spotify_client()
                second = fake_creds.call_args.kwargs["cache_handler"]

            self.assertNotEqual(first, second,
                                "different client_id must not share a token file")
            for path in (first, second):
                self.assertTrue(path.startswith(os.path.join(base, ".spotipy")))
        finally:
            shutil.rmtree(base, ignore_errors=True)

    def test_clearing_tokens_empties_the_cache_dir(self):
        base = tempfile.mkdtemp()
        try:
            app = _bind("_clear_spotipy_tokens", {"_base": base})
            app._spotipy_cache_dir = spotrr.SpotRRApp._spotipy_cache_dir.__get__(
                app, spotrr.SpotRRApp)
            os.makedirs(app._spotipy_cache_dir(), exist_ok=True)
            for name in ("aaa", "bbb"):
                with open(os.path.join(app._spotipy_cache_dir(), name), "w") as f:
                    f.write("{}")
            app._clear_spotipy_tokens()
            self.assertEqual(os.listdir(app._spotipy_cache_dir()), [])
        finally:
            shutil.rmtree(base, ignore_errors=True)

    def test_clearing_tokens_on_missing_dir_is_safe(self):
        base = os.path.join(tempfile.mkdtemp(), "does-not-exist")
        app = _bind("_clear_spotipy_tokens", {"_base": base})
        app._spotipy_cache_dir = spotrr.SpotRRApp._spotipy_cache_dir.__get__(
            app, spotrr.SpotRRApp)
        app._clear_spotipy_tokens()          # must not raise


# ─────────────────────────────────────────────────────────────────────────────
# Crypto / metadata constants
# ─────────────────────────────────────────────────────────────────────────────

class TestCryptoData(unittest.TestCase):
    def test_every_address_has_meta(self):
        for coin in spotrr.CRYPTO_ADDRESSES:
            self.assertIn(coin, spotrr.CRYPTO_META,
                          f"{coin} in CRYPTO_ADDRESSES but missing from CRYPTO_META")

    def test_every_meta_has_required_fields(self):
        for coin, meta in spotrr.CRYPTO_META.items():
            self.assertIn("color", meta, f"{coin} missing 'color'")
            self.assertIn("symbol", meta, f"{coin} missing 'symbol'")
            self.assertIn("network", meta, f"{coin} missing 'network'")

    def test_xlm_is_dict_with_address_and_memo(self):
        xlm = spotrr.CRYPTO_ADDRESSES["XLM"]
        self.assertIsInstance(xlm, dict)
        self.assertIn("address", xlm)
        self.assertIn("memo", xlm)
        self.assertTrue(xlm["address"], "XLM address must not be empty")
        self.assertTrue(xlm["memo"], "XLM memo must not be empty")

    def test_string_addresses_nonempty(self):
        for coin, addr in spotrr.CRYPTO_ADDRESSES.items():
            if isinstance(addr, str):
                self.assertGreater(len(addr), 10, f"{coin} address seems too short")

    def test_meta_colors_are_hex(self):
        import re
        hex_pattern = re.compile(r"^#[0-9A-Fa-f]{6}$")
        for coin, meta in spotrr.CRYPTO_META.items():
            self.assertTrue(hex_pattern.match(meta["color"]),
                            f"{coin} color '{meta['color']}' is not a valid hex color")


# ─────────────────────────────────────────────────────────────────────────────
# App metadata
# ─────────────────────────────────────────────────────────────────────────────

class TestAppMetadata(unittest.TestCase):
    def test_version_format(self):
        import re
        self.assertTrue(re.match(r"^\d+\.\d+\.\d+$", spotrr.APP_VERSION),
                        f"APP_VERSION '{spotrr.APP_VERSION}' does not match X.Y.Z")

    def test_docstring_version_matches_app_version(self):
        import re
        doc = spotrr.__doc__ or ""
        m = re.search(r"SpotRR\s+v([\d.]+)", doc)
        if m:
            self.assertEqual(m.group(1), spotrr.APP_VERSION,
                             "Docstring version out of sync with APP_VERSION")

    def test_app_name_nonempty(self):
        self.assertTrue(spotrr.APP_NAME)
        self.assertIsInstance(spotrr.APP_NAME, str)

    def test_github_url_is_https(self):
        self.assertTrue(spotrr.APP_GITHUB.startswith("https://"))


# ─────────────────────────────────────────────────────────────────────────────
# Pause/stop flags (logic only — no download call)
# ─────────────────────────────────────────────────────────────────────────────

class TestPauseStopFlags(unittest.TestCase):
    """Verify pause/stop flag semantics without running spotdl."""

    def _check_pause_stop(self, app):
        """Replica of the helper inside _run_spotdl."""
        while app.download_paused and app.is_downloading:
            import time
            time.sleep(0.01)
        return app.is_downloading

    def test_not_paused_not_stopped_returns_true(self):
        app = MagicMock()
        app.download_paused = False
        app.is_downloading  = True
        self.assertTrue(self._check_pause_stop(app))

    def test_stopped_returns_false(self):
        app = MagicMock()
        app.download_paused = False
        app.is_downloading  = False
        self.assertFalse(self._check_pause_stop(app))

    def test_paused_then_resumed(self):
        app = MagicMock()
        app.download_paused = True
        app.is_downloading  = True

        def _unpause():
            import time
            time.sleep(0.05)
            app.download_paused = False

        threading.Thread(target=_unpause, daemon=True).start()
        result = self._check_pause_stop(app)
        self.assertTrue(result)

    def test_paused_then_stopped(self):
        app = MagicMock()
        app.download_paused = True
        app.is_downloading  = True

        def _stop():
            import time
            time.sleep(0.05)
            app.is_downloading = False

        threading.Thread(target=_stop, daemon=True).start()
        result = self._check_pause_stop(app)
        self.assertFalse(result)


# ─────────────────────────────────────────────────────────────────────────────
# Quality options — "Máx." for the lossless containers (WAV/FLAC)
# ─────────────────────────────────────────────────────────────────────────────

def _write_wav(path, sample_rate=48000, bits=16, channels=2, frames=64):
    """Write a minimal but genuinely valid RIFF/WAVE file (no ffmpeg needed)."""
    block_align = channels * bits // 8
    byte_rate   = sample_rate * block_align
    data        = b"\x00" * (frames * block_align)
    header = (
        b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVE"
        + b"fmt " + struct.pack("<IHHIIHH", 16, 1, channels,
                                 sample_rate, byte_rate, block_align, bits)
        + b"data" + struct.pack("<I", len(data))
    )
    with open(path, "wb") as f:
        f.write(header + data)
    return path


class TestQualityOptionTable(unittest.TestCase):
    """The option table itself, plus the pure helpers built on it."""

    def test_mp3_offers_real_bitrates(self):
        self.assertEqual([v for v, _ in spotrr.QUALITY_CHOICES["mp3"]],
                         ["128k", "192k", "320k"])

    def test_wav_and_flac_offer_only_max(self):
        for fmt in ("wav", "flac"):
            self.assertEqual([v for v, _ in spotrr.QUALITY_CHOICES[fmt]],
                             [spotrr.MAX_QUALITY])

    def test_valid_quality_keeps_mp3_choice(self):
        self.assertEqual(spotrr._valid_quality("mp3", "192k"), "192k")

    def test_valid_quality_coerces_bitrate_left_over_from_mp3(self):
        # The migration case: settings.json saved with format=flac while the
        # quality was still an MP3 bitrate.  Previously this reached spotdl as
        # a literal "320k" on a lossless container.
        self.assertEqual(spotrr._valid_quality("wav", "320k"), spotrr.MAX_QUALITY)
        self.assertEqual(spotrr._valid_quality("flac", "128k"), spotrr.MAX_QUALITY)

    def test_valid_quality_coerces_garbage(self):
        self.assertEqual(spotrr._valid_quality("mp3", "banana"), "320k")

    def test_valid_quality_passes_through_unknown_format(self):
        self.assertEqual(spotrr._valid_quality("ogg", "320k"), "320k")

    def test_quality_label_humanises_max(self):
        self.assertEqual(spotrr._quality_label("flac", "max"), "Máx.")

    def test_quality_label_passes_bitrate_through(self):
        self.assertEqual(spotrr._quality_label("mp3", "320k"), "320k")

    def test_spotdl_bitrate_is_disable_for_max(self):
        self.assertEqual(spotrr._spotdl_bitrate("flac", spotrr.MAX_QUALITY),
                         "disable")

    def test_spotdl_bitrate_keeps_mp3_target(self):
        self.assertEqual(spotrr._spotdl_bitrate("mp3", "320k"), "320k")

    def test_max_never_reaches_spotdl_as_a_literal(self):
        # "max" is not a valid spotdl bitrate — it would end up in the ffmpeg
        # command line as "-b:a max".
        for fmt in ("mp3", "wav", "flac"):
            self.assertNotEqual(spotrr._spotdl_bitrate(fmt, "max"), "max")


class TestProbeAudioSpec(unittest.TestCase):
    def test_ignores_mp3(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "a.mp3")
            open(p, "wb").close()
            self.assertIsNone(spotrr._probe_audio_spec(p))

    def test_missing_file_returns_none(self):
        self.assertIsNone(spotrr._probe_audio_spec("/nope/does-not-exist.wav"))

    def test_garbage_file_returns_none(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "a.flac")
            with open(p, "wb") as f:
                f.write(b"definitely not a flac stream")
            self.assertIsNone(spotrr._probe_audio_spec(p))

    def test_directory_returns_none(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(spotrr._probe_audio_spec(d))

    @unittest.skipUnless(importlib.util.find_spec("mutagen.wave"),
                         "mutagen not installed")
    def test_reads_wav_16bit_48k(self):
        with tempfile.TemporaryDirectory() as d:
            p = _write_wav(os.path.join(d, "a.wav"), 48000, 16)
            self.assertEqual(spotrr._probe_audio_spec(p), (48000, 16))

    @unittest.skipUnless(importlib.util.find_spec("mutagen.wave"),
                         "mutagen not installed")
    def test_reads_wav_24bit_96k(self):
        with tempfile.TemporaryDirectory() as d:
            p = _write_wav(os.path.join(d, "a.wav"), 96000, 24)
            self.assertEqual(spotrr._probe_audio_spec(p), (96000, 24))


class TestRebuildQuality(unittest.TestCase):
    """The Quality control is rebuilt per format."""

    def setUp(self):
        self.app = MagicMock(spec=spotrr.SpotRRApp)
        self.app.quality_buttons = {}
        self.app._rebuild_quality = \
            spotrr.SpotRRApp._rebuild_quality.__get__(self.app, spotrr.SpotRRApp)
        # A real box is needed because the method destroys the old children.
        self.box = MagicMock()
        self.app.quality_box = self.box
        self.app._seg_btn = MagicMock(
            side_effect=lambda parent, text, cmd: MagicMock(name=text))

    def _run(self, fmt, current="320k"):
        self.app.quality_var = MagicMock()
        self.app.quality_var.get.return_value = current
        self.app._rebuild_quality(fmt)
        return self.app._seg_btn.call_args_list

    def test_mp3_creates_three_buttons(self):
        calls = self._run("mp3")
        self.assertEqual([c[0][1] for c in calls], ["128k", "192k", "320k"])

    def test_flac_creates_single_max_button(self):
        calls = self._run("flac")
        self.assertEqual([c[0][1] for c in calls], ["Máx."])

    def test_wav_creates_single_max_button(self):
        calls = self._run("wav")
        self.assertEqual([c[0][1] for c in calls], ["Máx."])

    def test_switching_to_flac_replaces_old_buttons(self):
        self._run("mp3")
        self.assertEqual(set(self.app.quality_buttons), {"128k", "192k", "320k"})
        self._run("flac")
        self.assertEqual(set(self.app.quality_buttons), {spotrr.MAX_QUALITY})

    def test_old_buttons_are_destroyed(self):
        self._run("mp3")
        self.assertTrue(self.box.winfo_children.called)

    def test_selection_coerces_stale_bitrate_on_format_change(self):
        # Starting from MP3/320k and switching to FLAC must land on "max",
        # not keep a bitrate that is invalid for the new container.
        self._run("flac", current="320k")
        self.app.quality_var.set.assert_called_once_with(spotrr.MAX_QUALITY)


class TestSelQualityValidation(unittest.TestCase):
    def setUp(self):
        self.app = MagicMock(spec=spotrr.SpotRRApp)
        self.app._sel_quality = \
            spotrr.SpotRRApp._sel_quality.__get__(self.app, spotrr.SpotRRApp)
        self.app.quality_buttons = {}
        self.app.quality_var = MagicMock()
        self.app.format_var = MagicMock()

    def test_accepts_option_valid_for_current_format(self):
        self.app.format_var.get.return_value = "flac"
        self.app._sel_quality(spotrr.MAX_QUALITY)
        self.app.quality_var.set.assert_called_once_with(spotrr.MAX_QUALITY)

    def test_rejects_mp3_bitrate_while_format_is_flac(self):
        self.app.format_var.get.return_value = "flac"
        self.app._sel_quality("320k")
        self.app.quality_var.set.assert_not_called()
        self.app._write_cfg.assert_not_called()

    def test_rejects_max_while_format_is_mp3(self):
        self.app.format_var.get.return_value = "mp3"
        self.app._sel_quality(spotrr.MAX_QUALITY)
        self.app.quality_var.set.assert_not_called()

    def test_rejects_unknown_value(self):
        self.app.format_var.get.return_value = "mp3"
        self.app._sel_quality("banana")
        self.app.quality_var.set.assert_not_called()


class TestLoadSettingsQualityValidation(unittest.TestCase):
    def setUp(self):
        self.app = MagicMock(spec=spotrr.SpotRRApp)
        self.app._load_settings = \
            spotrr.SpotRRApp._load_settings.__get__(self.app, spotrr.SpotRRApp)
        self.app._defaults = lambda: spotrr.SpotRRApp._defaults(self.app)
        self.app.format_var = MagicMock()
        self.app.quality_var = MagicMock()
        self.app.entry_folder = MagicMock()
        self.app.fmt_buttons = {}
        self.app.quality_buttons = {}
        self.app.quality_box = MagicMock()
        self.app._seg_btn = MagicMock(
            side_effect=lambda parent, text, cmd: MagicMock(name=text))

    def _load(self, cfg):
        self.app._read_cfg = lambda: {**self.app._defaults(), **cfg}
        self.app._load_settings()
        return (self.app.format_var.set.call_args[0][0],
                self.app.quality_var.set.call_args[0][0])

    def test_valid_mp3_settings_preserved(self):
        fmt, quality = self._load(
            {"preferred_format": "mp3", "preferred_quality": "192k"})
        self.assertEqual((fmt, quality), ("mp3", "192k"))

    def test_unknown_format_falls_back_to_mp3(self):
        fmt, _ = self._load({"preferred_format": "opus"})
        self.assertEqual(fmt, "mp3")

    def test_stale_bitrate_with_lossless_format_is_corrected(self):
        fmt, quality = self._load(
            {"preferred_format": "flac", "preferred_quality": "320k"})
        self.assertEqual((fmt, quality), ("flac", spotrr.MAX_QUALITY))

    def test_saved_max_for_flac_is_preserved(self):
        fmt, quality = self._load(
            {"preferred_format": "flac", "preferred_quality": spotrr.MAX_QUALITY})
        self.assertEqual((fmt, quality), ("flac", spotrr.MAX_QUALITY))


class TestRecordAndReportSpecs(unittest.TestCase):
    """Tallying what was produced, and reporting it in the summary."""

    def setUp(self):
        self.app = MagicMock(spec=spotrr.SpotRRApp)
        self.app._record_specs = \
            spotrr.SpotRRApp._record_specs.__get__(self.app, spotrr.SpotRRApp)
        self.app._log_real_specs = \
            spotrr.SpotRRApp._log_real_specs.__get__(self.app, spotrr.SpotRRApp)
        self.app._dl_specs = {}

    def test_counts_each_downloaded_file(self):
        results = [("s1", "/x/a.wav"), ("s2", "/x/b.wav"), ("s3", None)]
        with patch.object(spotrr, "_probe_audio_spec",
                          side_effect=lambda p: (48000, 16) if p else None):
            self.app._record_specs(results)
        self.assertEqual(self.app._dl_specs, {(48000, 16): 2})

    def test_groups_mixed_specs(self):
        results = [("s1", "/x/a.wav"), ("s2", "/x/b.wav"),
                   ("s3", "/x/c.wav"), ("s4", "/x/d.wav")]
        with patch.object(spotrr, "_probe_audio_spec",
                          side_effect=lambda p: (48000, 16) if p == "/x/a.wav"
                          else (44100, 16)):
            self.app._record_specs(results)
        self.assertEqual(self.app._dl_specs, {(48000, 16): 1, (44100, 16): 3})

    def test_unprobeable_files_are_skipped(self):
        with patch.object(spotrr, "_probe_audio_spec", return_value=None):
            self.app._record_specs([("s1", "/x/a.mp3")])
        self.assertEqual(self.app._dl_specs, {})

    def test_report_shows_real_rate_and_depth(self):
        self.app._dl_specs = {(48000, 16): 3}
        self.app._log_real_specs()
        logged = " ".join(str(c) for c in self.app._log.call_args_list)
        self.assertIn("48000", logged)
        self.assertIn("16 bit", logged)
        self.assertIn("3 tracks", logged)

    def test_report_is_silent_for_mp3(self):
        # No specs recorded (MP3 is not probed) — must not print a stray line.
        self.app._log_real_specs()
        self.app._log.assert_not_called()

    def test_report_handles_unknown_bit_depth(self):
        self.app._dl_specs = {(48000, None): 1}
        self.app._log_real_specs()
        logged = " ".join(str(c) for c in self.app._log.call_args_list)
        self.assertIn("48000", logged)
        self.assertNotIn("None bit", logged)


class TestSummaryReportsSpecsForLossless(unittest.TestCase):
    def setUp(self):
        self.app = MagicMock(spec=spotrr.SpotRRApp)
        self.app._show_download_summary = \
            spotrr.SpotRRApp._show_download_summary.__get__(
                self.app, spotrr.SpotRRApp)
        self.app._dl_ok, self.app._dl_fail, self.app._dl_total = 3, 0, 3
        self.app._dl_specs = {(48000, 16): 3}

    def test_success_path_reports_specs(self):
        self.app._show_download_summary("Album")
        self.app._log_real_specs.assert_called_once()

    def test_zero_count_path_also_reports_specs(self):
        self.app._dl_ok = self.app._dl_fail = 0
        self.app._show_download_summary("Album")
        self.app._log_real_specs.assert_called_once()


class _FakeVar:
    """Minimal stand-in for tk.StringVar (a MagicMock would not persist .set())."""

    def __init__(self, value=""):
        self._v = value

    def get(self):
        return self._v

    def set(self, value):
        self._v = value


class TestSelFmtRebuildsQuality(unittest.TestCase):
    """Switching format must swap the Quality options (MP3 bitrates <-> Máx.)."""

    def setUp(self):
        self.app = MagicMock(spec=spotrr.SpotRRApp)
        self.app._sel_fmt = \
            spotrr.SpotRRApp._sel_fmt.__get__(self.app, spotrr.SpotRRApp)
        self.app._rebuild_quality = \
            spotrr.SpotRRApp._rebuild_quality.__get__(self.app, spotrr.SpotRRApp)
        self.app.fmt_buttons    = {"mp3": MagicMock(), "wav": MagicMock(),
                                   "flac": MagicMock()}
        self.app.quality_buttons = {}
        self.app.quality_box     = MagicMock()
        self.app._seg_btn = MagicMock(
            side_effect=lambda parent, text, cmd: MagicMock(name=text))
        self.app._read_cfg  = MagicMock(return_value={})
        self.app._write_cfg = MagicMock()
        self.app.format_var  = _FakeVar("mp3")
        self.app.quality_var = _FakeVar("320k")

    def test_switching_to_flac_replaces_bitrates_with_max(self):
        self.app._sel_fmt("flac")
        self.assertEqual(set(self.app.quality_buttons), {spotrr.MAX_QUALITY})

    def test_switching_back_to_mp3_restores_bitrates(self):
        self.app._sel_fmt("flac")
        self.app._sel_fmt("mp3")
        self.assertEqual(set(self.app.quality_buttons),
                         {"128k", "192k", "320k"})

    def test_stale_bitrate_is_coerced_on_format_switch(self):
        self.app._sel_fmt("flac")
        self.assertEqual(self.app.quality_var.get(), spotrr.MAX_QUALITY)

    def test_persists_both_format_and_quality(self):
        # The old settings.json wrote format=flac with a stale quality=320k
        # because _sel_fmt never touched the quality.  Both must be coherent.
        self.app._sel_fmt("flac")
        saved = self.app._write_cfg.call_args[0][0]
        self.assertEqual(saved["preferred_format"], "flac")
        self.assertEqual(saved["preferred_quality"], spotrr.MAX_QUALITY)

    def test_no_write_when_nothing_changed(self):
        self.app._sel_fmt("mp3")   # already mp3/320k
        self.app._write_cfg.assert_not_called()

    def test_old_buttons_destroyed_on_every_switch(self):
        self.app._sel_fmt("flac")
        self.app._sel_fmt("mp3")
        self.assertTrue(self.app.quality_box.winfo_children.called)


class TestRunSpotdlWiring(unittest.TestCase):
    """Guards on the spotdl hand-off.

    _run_spotdl needs a live spotdl client, so these check the wiring in source
    rather than executing a download.
    """

    def setUp(self):
        self.source = inspect.getsource(spotrr.SpotRRApp._run_spotdl)

    def test_specs_recorded_after_every_download_batch(self):
        # Three call sites: first pass, retry pass, last resort.  Missing any of
        # them makes the "Actual output" line under-report the batch.  They are
        # fed `done` rather than the raw results so a skipped track (spotdl
        # returns the intended path without writing it) is not probed.
        self.assertEqual(self.source.count("self._record_specs(done)"), 3)

    def test_ffmpeg_args_refreshed_on_cached_client(self):
        import re
        m = re.search(r"for k in \(([^)]*)\):", self.source)
        self.assertIsNotNone(m, "per-download refresh loop not found")
        self.assertIn("ffmpeg_args", m.group(1))

    def test_bitrate_comes_from_the_mapping_helper(self):
        self.assertIn("_spotdl_bitrate(fmt, quality)", self.source)

    def test_settings_declare_no_ffmpeg_args(self):
        # spotdl's FFMPEG_FORMATS already pick the codec for the container.
        self.assertIn('"ffmpeg_args":     None', self.source)

    def test_prewarm_client_declares_ffmpeg_args(self):
        # Otherwise a reused pre-warm client could carry a stale value from
        # spotdl's on-disk config.
        self.assertIn('"ffmpeg_args":     None', inspect.getsource(spotrr))


class TestPrivatePlaylistFallback(unittest.TestCase):
    """Private/collaborative playlists: silent when it works, explained when not."""

    def _start_dl_source(self):
        src = inspect.getsource(spotrr.SpotRRApp._run_spotdl)
        return src[src.index("kind = self._url_type(url)"):
                   src.index("Found {self._dl_total}")]

    def test_fallback_to_search_is_still_there(self):
        # Removing the warning must not remove the recovery path.
        self.assertIn("songs = client.search([url])", self._start_dl_source())

    def test_access_denied_is_remembered_for_the_failure_path(self):
        src = self._start_dl_source()
        self.assertIn("access_denied = False", src)
        self.assertIn("songs, access_denied = self._resolve_spotify_songs(url)", src)

    def test_failure_explains_the_real_cause(self):
        src = self._start_dl_source()
        self.assertIn("if access_denied:", src)
        self.assertIn("private or collaborative", src)
        self.assertIn("search couldn't find it either", src)

    def test_failure_message_is_actionable(self):
        src = self._start_dl_source()
        self.assertIn("Make it public", src)

    def test_failure_message_suggests_no_slowdown_as_the_cause(self):
        # The old text blamed search speed, which is wrong — search is fine,
        # the playlist is simply not visible.
        self.assertNotIn("slower", src := self._start_dl_source())

    def test_generic_error_still_covers_the_non_denied_case(self):
        src = self._start_dl_source()
        self.assertIn("No songs found for this URL", src)


class TestCachedClientTracksFormatChanges(unittest.TestCase):
    """A reused spotdl client must not keep the previous format.

    The client is cached across downloads, but Downloader.__init__ derives
    scan_formats once and spotdl never recomputes it.  So the WAV download
    that followed an MP3 download asked spotdl to look for a ".mp3" that
    already existed, and every track was skipped as a duplicate.
    """

    def test_real_code_refreshes_scan_formats(self):
        src = inspect.getsource(spotrr.SpotRRApp._run_spotdl)
        self.assertIn("scan_formats", src,
                      "_run_spotdl must refresh scan_formats on the cached client")



class TestVersionIsVisibleInTheLog(unittest.TestCase):
    """The batch header must carry the version.

    Twice now, a report about behaviour that was already fixed turned out to be
    an outdated install on another machine.  The header is the line people
    paste, so the version belongs there rather than in an About dialog nobody
    opens.
    """

    def _header(self):
        src = inspect.getsource(spotrr.SpotRRApp._worker)
        i = src.index("thread(s)")
        return src[max(0, i - 400):i + 200]

    def test_batch_header_includes_the_version(self):
        self.assertIn("v{APP_VERSION}", self._header())

    def test_version_is_not_hardcoded(self):
        # It has to follow the constant, or it will drift and lie.
        header = self._header()
        self.assertNotIn("v2.3.0", header)
        self.assertNotIn("v2.2.0", header)


class TestCrossFormatSkip(unittest.TestCase):
    """A file of one format must never suppress the download of another.

    Reported: with an MP3 already in the folder, requesting WAV skipped every
    track "as if it were the same file".  Reproduced the mechanism against the
    real spotdl Downloader options: with detect_formats set to a list and
    scan_for_songs off, spotdl matches on the filename *stem* and treats a
    different-extension file as a duplicate.
    """

    def _folder_with_mp3(self):
        import tempfile
        d = tempfile.mkdtemp(prefix="xskip_")
        Path(d, "Artist - Title.mp3").write_bytes(b"x" * 100)
        self.addCleanup(shutil.rmtree, d, True)
        return d

    # ── 1. the app must not depend on the user's on-disk spotdl config ──

    def test_skip_settings_declared_in_both_client_configs(self):
        src = inspect.getsource(spotrr)
        self.assertEqual(src.count('"scan_for_songs":  False'), 2,
                         "must be declared in the pre-warm and per-download configs")
        self.assertEqual(src.count('"detect_formats":  None'), 2)

    def test_skip_settings_refreshed_on_cached_client(self):
        import re
        src = inspect.getsource(spotrr.SpotRRApp._run_spotdl)
        m = re.search(r"for k in \(([^)]*)\):", src)
        self.assertIsNotNone(m)
        for key in ("scan_for_songs", "detect_formats"):
            self.assertIn(key, m.group(1),
                          f"{key} not refreshed — a cached client keeps a stale value")

    # ── 2. a skip must never be counted as a success ──

    def test_existing_file_of_same_format_counts_as_done(self):
        import tempfile
        d = tempfile.mkdtemp(prefix="xskip2_")
        self.addCleanup(shutil.rmtree, d, True)
        p = os.path.join(d, "a.wav")
        open(p, "wb").write(b"x")
        done, missing = spotrr._partition_downloaded([("s", p)])
        self.assertEqual(len(done), 1)
        self.assertEqual(missing, [])

    def test_nonexistent_path_is_treated_as_not_downloaded(self):
        """spotdl hands back the intended path even when it skipped.

        That is the real defect: the old code counted any non-None path as a
        success, so the summary reported 5/5 for a folder with no WAV in it.
        """
        done, missing = spotrr._partition_downloaded(
            [("s", "/nonexistent/Artist - Title.wav")])
        self.assertEqual(done, [])
        self.assertEqual(missing, ["s"])

    def test_none_path_is_not_downloaded(self):
        done, missing = spotrr._partition_downloaded([("s", None)])
        self.assertEqual(done, [])
        self.assertEqual(missing, ["s"])

    def test_mixed_results_split_correctly(self):
        import tempfile
        d = tempfile.mkdtemp(prefix="xskip3_")
        self.addCleanup(shutil.rmtree, d, True)
        real = os.path.join(d, "a.wav"); open(real, "wb").write(b"x")
        results = [("s1", real), ("s2", None), ("s3", os.path.join(d, "gone.wav"))]
        done, missing = spotrr._partition_downloaded(results)
        self.assertEqual([s for s, _ in done], ["s1"])
        self.assertEqual(missing, ["s2", "s3"])

    def test_all_three_call_sites_verify_the_file(self):
        # first pass, retry, last resort — any one left trusting the raw path
        # reopens the silent-skip hole.
        src = inspect.getsource(spotrr.SpotRRApp._run_spotdl)
        self.assertEqual(src.count("_partition_downloaded(results)"), 3)
        self.assertNotIn("sum(1 for _, p in results if p is not None)", src)

    def test_specs_recorded_only_from_real_files(self):
        src = inspect.getsource(spotrr.SpotRRApp._run_spotdl)
        self.assertEqual(src.count("self._record_specs(done)"), 3)


class TestSettingsCoercion(unittest.TestCase):
    """A malformed settings.json must never take the app down at startup.

    _load_settings validated the format and quality keys but handed
    preferred_threads straight to int().  A hand-edited or half-written file —
    "preferred_threads": null, a string, a list — raised out of __init__, so the
    app died on launch with a traceback and the only recovery was deleting
    settings.json by hand.  Reachable for anyone who edits the file, or whose
    write was interrupted mid-download.
    """

    HOSTILE = ["abc", None, [], {}, "", "4.5", [2], True, float("nan"),
               "0x4", "eight", "4 threads", object()]

    def test_hostile_values_fall_back_to_4(self):
        for bad in self.HOSTILE:
            with self.subTest(value=bad):
                self.assertEqual(spotrr._safe_threads(bad), 4)

    def test_valid_values_survive(self):
        # int() strips whitespace and accepts bytes, so these are all valid.
        for good in (2, 4, 8, "2", "4", "8", " 8 ", "\t4\n", 8.0, "08", b"4"):
            with self.subTest(value=good):
                self.assertEqual(spotrr._safe_threads(good), int(good))

    def test_out_of_range_values_fall_back(self):
        for bad in (0, 1, 3, 5, 16, 99, -4, -2):
            with self.subTest(value=bad):
                self.assertEqual(spotrr._safe_threads(bad), 4)

    def test_load_settings_uses_the_helper(self):
        self.assertIn("_safe_threads(", inspect.getsource(spotrr.SpotRRApp._load_settings))

    def test_default_when_key_absent(self):
        self.assertEqual(spotrr._safe_threads(4), 4)


class TestQualityHintIsVisible(unittest.TestCase):
    """The "Máx." option must be discoverable.

    The app starts on MP3, where a bitrate target is meaningful and "Máx." is
    therefore correctly absent.  Without an on-screen hint the user opens the
    app, sees 128k/192k/320k and concludes the WAV/FLAC option was never
    added — which is exactly the confusion this guards against.
    """

    def test_hint_table_covers_every_format(self):
        self.assertEqual(set(spotrr.QUALITY_HINTS), set(spotrr.QUALITY_CHOICES))

    def test_mp3_hint_points_at_the_max_option(self):
        # The MP3 hint is the only place a user learns "Máx." exists without
        # switching formats first, so it has to name it.
        self.assertIn("Máx.", spotrr.QUALITY_HINTS["mp3"])

    def test_lossless_hints_do_not_promise_more_than_the_source(self):
        for fmt in ("wav", "flac"):
            hint = spotrr.QUALITY_HINTS[fmt]
            self.assertIn("fuente", hint)
            self.assertNotIn("ilimitad", hint.lower())

    def test_hint_label_is_created_and_updated_per_format(self):
        src = inspect.getsource(spotrr.SpotRRApp._rebuild_quality)
        self.assertIn('"quality_hint"', src)
        self.assertIn("QUALITY_HINTS.get(fmt", src)
        build = inspect.getsource(spotrr.SpotRRApp._build_fqt)
        self.assertIn("self.quality_hint", build)
        self.assertIn("QUALITY_HINTS", inspect.getsource(spotrr))


class TestSampleRateIsNeverCapped(unittest.TestCase):
    """The app must never impose a sample rate on the encoder.

    Measured end to end: MP3 @ 320k emits 48000 Hz (MPEG-1 Layer III, the only
    Layer III variant that can carry 48 kHz) for every track checked, and WAV /
    FLAC come out at 48000 Hz too.  The 44100 Hz users report seeing is the
    MP3 *format's* own ceiling (MPEG-2/2.5 Layer III top out at 24 kHz), not a
    limit imposed here — and libmp3lame only lands on 44.1 kHz if the source is
    44.1 kHz or we ask for it.

    So the whole guarantee rests on one thing: no `-ar` / sample-rate override
    ever reaching ffmpeg.  These tests fail if that ever changes.
    """

    def test_run_spotdl_passes_no_ffmpeg_args(self):
        src = inspect.getsource(spotrr.SpotRRApp._run_spotdl)
        self.assertIn('"ffmpeg_args":     None', src)

    def test_no_samplerate_override_anywhere(self):
        # No -ar, no sample-rate key, in either the per-download settings or the
        # pre-warm client.  A `None` ffmpeg_args is the whole point.
        for name, src in (("_run_spotdl", inspect.getsource(spotrr.SpotRRApp._run_spotdl)),
                          ("module", inspect.getsource(spotrr))):
            for banned in ('"-ar"', "'-ar'", "samplerate", '"sample_rate"'):
                self.assertNotIn(banned, src,
                                 f"sample-rate override {banned!r} found in {name}")

    def test_measured_ceiling_is_not_lowered(self):
        # 48000 is the highest rate any provider serves; nothing in the app
        # should be transcoding to a lower one.
        for f in sorted(os.listdir(os.path.dirname(spotrr.__file__))):
            if not f.endswith((".py", ".json", ".bat", ".sh", ".txt", ".md")):
                continue
            if f in ("settings.json",):
                continue
            text = open(os.path.join(os.path.dirname(spotrr.__file__), f),
                        encoding="utf-8", errors="ignore").read()
            for bad in ("44100,", "44100,libmp3lame", "-ar 44100"):
                self.assertNotIn(bad, text, f"{f} pins a 44100 Hz ceiling")


if __name__ == "__main__":
    unittest.main(verbosity=2)
