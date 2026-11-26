# PyInstaller spec for Download Kar Desktop.
# Build from the desktop/ folder:  pyinstaller --noconfirm packaging/download-kar.spec
import os
import sys

from PyInstaller.utils.hooks import collect_all

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
IS_MAC = sys.platform == "darwin"
IS_WIN = sys.platform == "win32"
VERSION = os.environ.get("DK_VERSION", "1.2.2")

datas = [
    (os.path.join(ROOT, "templates"), "templates"),
    (os.path.join(ROOT, "static"), "static"),
    (os.path.join(ROOT, "LICENSE-RECLIP"), "."),
]
bin_dir = os.path.join(ROOT, "bin")
if os.path.isdir(bin_dir):
    # Shipped as plain data: server.py copies them to the user's data folder on first run.
    datas.append((bin_dir, "bin"))

# pywebview: the app's own window (WebKit on macOS, Edge WebView2 on Windows).
wv_datas, wv_binaries, wv_hidden = [], [], []
try:
    wv_datas, wv_binaries, wv_hidden = collect_all("webview")
except Exception:
    pass
if IS_WIN:
    for package in ("clr_loader", "pythonnet"):
        try:
            d, b, h = collect_all(package)
            wv_datas += d
            wv_binaries += b
            wv_hidden += h
        except Exception:
            pass

a = Analysis(
    [os.path.join(ROOT, "main.py")],
    pathex=[ROOT],
    datas=datas + wv_datas,
    binaries=wv_binaries,
    hiddenimports=wv_hidden + ["pystray._darwin" if IS_MAC else "pystray._win32" if IS_WIN else "pystray._xorg"],
    excludes=["yt_dlp", "tkinter"],
)
pyz = PYZ(a.pure)

# dk-ytdlp: yt-dlp built into the app (with all its optional extras), so it always matches
# the app's CPU architecture. A full stdlib is included so newer yt-dlp updates still load.
yt_datas, yt_binaries, yt_hidden = [], [], []
for package in ("yt_dlp", "yt_dlp_ejs", "certifi", "brotli", "mutagen", "Cryptodome", "websockets", "requests", "urllib3"):
    try:
        d, b, h = collect_all(package)
    except Exception:
        continue
    yt_datas += d
    yt_binaries += b
    yt_hidden += h
stdlib_extras = [
    "asyncio", "concurrent.futures", "ctypes", "email", "html.parser", "http.cookiejar", "http.cookies",
    "sqlite3", "xml.etree.ElementTree", "zipfile", "hashlib", "hmac", "secrets", "uuid", "netrc",
    "getpass", "shlex", "unicodedata", "gzip", "lzma", "bz2", "zlib", "decimal", "fractions",
    "statistics", "string", "struct", "tempfile", "xml.dom.minidom", "base64", "binascii",
]
yt = Analysis(
    [os.path.join(ROOT, "ytdlp_runner.py")],
    pathex=[ROOT],
    datas=yt_datas,
    binaries=yt_binaries,
    hiddenimports=yt_hidden + stdlib_extras,
    excludes=["tkinter"],
)
yt_pyz = PYZ(yt.pure)
yt_exe = EXE(
    yt_pyz,
    yt.scripts,
    [],
    exclude_binaries=True,
    name="dk-ytdlp",
    console=True,  # its output is read by the app; it never shows a window (see server.py)
)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Download Kar",
    console=False,
    icon=os.path.join(SPECPATH, "icon.ico" if IS_WIN else "icon.png"),
)

coll = COLLECT(exe, a.binaries, a.datas, yt_exe, yt.binaries, yt.datas, name="Download Kar")

if IS_MAC:
    app = BUNDLE(
        coll,
        name="Download Kar.app",
        icon=os.path.join(SPECPATH, "icon.png"),
        bundle_identifier="app.downloadkar.desktop",
        version=VERSION,
        info_plist={
            "CFBundleDisplayName": "Download Kar",
            "CFBundleShortVersionString": VERSION,
            # The window is a normal app (Dock icon); the background service hides itself
            # from the Dock at runtime and lives in the menu bar (see main.py).
            "NSHighResolutionCapable": True,
        },
    )
