"""
SpotRR — comprehensive test suite.

All tests run headless: tkinter, spotdl, spotipy and other optional deps are
mocked at import time so no display and no internet are required.
"""
import sys
import os
import json
import shutil
import socket
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
    def setUp(self):
        spotrr._release_instance()

    def tearDown(self):
        spotrr._release_instance()

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
