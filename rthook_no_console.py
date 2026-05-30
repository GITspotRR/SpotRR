# PyInstaller runtime hook — runs in EVERY process spawned from the exe
# (both the main SpotRR process and the spotdl child process).
# Patches subprocess.Popen so that yt-dlp's internal ffmpeg calls never
# open a visible console window on Windows.
import sys

if sys.platform == "win32":
    import subprocess

    _CREATE_NO_WINDOW = 0x08000000  # subprocess.CREATE_NO_WINDOW

    _orig_init = subprocess.Popen.__init__

    def _no_window(self, args, **kwargs):
        kwargs["creationflags"] = kwargs.get("creationflags", 0) | _CREATE_NO_WINDOW
        if "startupinfo" not in kwargs:
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = 0  # SW_HIDE
            kwargs["startupinfo"] = si
        _orig_init(self, args, **kwargs)

    subprocess.Popen.__init__ = _no_window
