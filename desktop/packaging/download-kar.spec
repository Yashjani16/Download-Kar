# PyInstaller spec for Download Kar Desktop.
# Build from the desktop/ folder:  pyinstaller --noconfirm packaging/download-kar.spec
import os
import sys

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
IS_MAC = sys.platform == "darwin"
IS_WIN = sys.platform == "win32"
VERSION = os.environ.get("DK_VERSION", "1.1.0")

datas = [
    (os.path.join(ROOT, "templates"), "templates"),
    (os.path.join(ROOT, "static"), "static"),
    (os.path.join(ROOT, "LICENSE-RECLIP"), "."),
]
bin_dir = os.path.join(ROOT, "bin")
if os.path.isdir(bin_dir):
    # Shipped as plain data: server.py copies them to the user's data folder on first run.
    datas.append((bin_dir, "bin"))

a = Analysis(
    [os.path.join(ROOT, "main.py")],
    pathex=[ROOT],
    datas=datas,
    hiddenimports=["pystray._darwin" if IS_MAC else "pystray._win32" if IS_WIN else "pystray._xorg"],
    excludes=["yt_dlp", "tkinter"],
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Download Kar",
    console=False,
    icon=os.path.join(SPECPATH, "icon.ico" if IS_WIN else "icon.png"),
)

coll = COLLECT(exe, a.binaries, a.datas, name="Download Kar")

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
            "LSUIElement": True,  # menu-bar app: no Dock icon
            "NSHighResolutionCapable": True,
        },
    )
