"""Download the tools bundled with Download Kar Desktop into desktop/bin/.

Usage: python packaging/fetch_tools.py <mac-arm64|mac-x64|windows-x64>

- (yt-dlp itself is built into the app; see ytdlp_runner.py)
- ffmpeg + ffprobe: static builds from the ffmpeg-static project's GitHub release
- deno: JavaScript runtime that yt-dlp needs for full YouTube support
"""
import gzip
import io
import os
import stat
import sys
import urllib.request
import zipfile

TARGETS = {
    "mac-arm64": {"deno": "deno-aarch64-apple-darwin.zip", "exe": "", "ffmpeg": "darwin-arm64"},
    "mac-x64": {"deno": "deno-x86_64-apple-darwin.zip", "exe": "", "ffmpeg": "darwin-x64"},
    "windows-x64": {"deno": "deno-x86_64-pc-windows-msvc.zip", "exe": ".exe", "ffmpeg": "win32-x64"},
}
FFMPEG_STATIC = "https://github.com/eugeneware/ffmpeg-static/releases/download/b6.1.1"

HERE = os.path.dirname(os.path.abspath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")


def fetch(url: str) -> bytes:
    print("Downloading", url)
    with urllib.request.urlopen(url, timeout=300) as response:
        return response.read()


def make_executable(path: str) -> None:
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def main() -> None:
    target = sys.argv[1] if len(sys.argv) > 1 else ""
    if target not in TARGETS:
        sys.exit(f"Usage: fetch_tools.py <{'|'.join(TARGETS)}>")
    spec = TARGETS[target]
    exe = spec["exe"]
    os.makedirs(BIN, exist_ok=True)

    for tool in ("ffmpeg", "ffprobe"):
        path = os.path.join(BIN, tool + exe)
        with open(path, "wb") as fh:
            fh.write(gzip.decompress(fetch(f"{FFMPEG_STATIC}/{tool}-{spec['ffmpeg']}.gz")))
        make_executable(path)
    for tool in ("ffmpeg", "ffprobe"):
        if os.path.getsize(os.path.join(BIN, tool + exe)) < 5_000_000:
            sys.exit(f"{tool} download looks wrong (file too small)")

    archive = zipfile.ZipFile(io.BytesIO(fetch(f"https://github.com/denoland/deno/releases/latest/download/{spec['deno']}")))
    deno = os.path.join(BIN, "deno" + exe)
    with open(deno, "wb") as fh:
        fh.write(archive.read("deno" + exe))
    make_executable(deno)

    for name in sorted(os.listdir(BIN)):
        print(f"  bin/{name}: {os.path.getsize(os.path.join(BIN, name)) / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
