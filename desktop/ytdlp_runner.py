"""Entry point of the bundled `dk-ytdlp` helper program.

yt-dlp is built into Download Kar itself (same Python, same CPU architecture as the app),
so it works on Apple-chip Macs, Intel Macs and Windows alike. Sites change often, so the
app also downloads yt-dlp's newest pure-Python release (`yt-dlp-latest.zip`, see
server.py) into the data folder; when that copy loads, it is used instead of the built-in one.
"""
import os
import sys


def data_dir() -> str:
    if sys.platform == "darwin":
        return os.path.expanduser("~/Library/Application Support/Download Kar")
    if sys.platform == "win32":
        return os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "Download Kar")
    return os.path.expanduser("~/.local/share/download-kar")


def load_yt_dlp():
    latest = os.environ.get("DK_YTDLP_ZIP") or os.path.join(data_dir(), "yt-dlp-latest.zip")
    if os.path.isfile(latest) and os.environ.get("DK_BUILTIN_YTDLP") != "1":
        import importlib.machinery
        sys.path.insert(0, latest)
        # In the packaged app the built-in copy is found first by PyInstaller's importer;
        # put the normal path finder in front so the downloaded update wins.
        sys.meta_path.insert(0, importlib.machinery.PathFinder)
        try:
            import yt_dlp
            if os.path.abspath(latest) in os.path.abspath(yt_dlp.__file__ or ""):
                return yt_dlp
            raise ImportError("update not loaded")
        except Exception:
            # The downloaded update doesn't work here: fall back to the built-in copy.
            sys.meta_path.remove(importlib.machinery.PathFinder)
            sys.path.remove(latest)
            for name in [m for m in sys.modules if m == "yt_dlp" or m.startswith("yt_dlp.")]:
                del sys.modules[name]
    import yt_dlp
    return yt_dlp


def main() -> None:
    yt_dlp = load_yt_dlp()
    if sys.argv[1:] == ["--dk-source"]:
        from yt_dlp.version import __version__
        print(f"{__version__} {'update' if 'yt-dlp-latest' in (yt_dlp.__file__ or '') else 'built-in'}")
        return
    sys.argv[0] = "yt-dlp"
    yt_dlp.main()


if __name__ == "__main__":
    main()
