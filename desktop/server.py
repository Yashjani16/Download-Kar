"""Download Kar Desktop: local download server.

Based on ReClip by averygan (MIT License, see LICENSE-RECLIP). Runs yt-dlp and ffmpeg
on the user's computer so the Download Kar extension (and the web UI) can download from
YouTube, Instagram, TikTok and 1000+ other sites.
"""
import json
import os
import platform
import shutil
import subprocess
import sys
import threading
import time
import uuid

from flask import Flask, jsonify, render_template, request

APP_NAME = "Download Kar"
APP_ID = "download-kar-desktop"
VERSION = "1.2.2"
PORT = int(os.environ.get("DK_PORT", "48123"))
HOST = "127.0.0.1"
MAX_PARALLEL = 3

IS_FROZEN = getattr(sys, "frozen", False)
SYSTEM = platform.system()  # "Darwin", "Windows", "Linux"
EXE = ".exe" if SYSTEM == "Windows" else ""

BASE_DIR = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
BUNDLED_BIN = os.path.join(BASE_DIR, "bin")


def data_dir() -> str:
    if SYSTEM == "Darwin":
        path = os.path.expanduser("~/Library/Application Support/Download Kar")
    elif SYSTEM == "Windows":
        path = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "Download Kar")
    else:
        path = os.path.expanduser("~/.local/share/download-kar")
    os.makedirs(path, exist_ok=True)
    return path


def download_dir() -> str:
    path = os.environ.get("DK_DOWNLOAD_DIR") or os.path.join(os.path.expanduser("~"), "Downloads", "Download Kar")
    os.makedirs(path, exist_ok=True)
    return path


# ---------------------------------------------------------------- tools

def _install_tool(name: str, keep_existing: bool = False) -> str:
    """Copy a bundled tool into the user's data folder and return its path.

    Running tools from the data folder (not from inside the app bundle) keeps them
    executable on every OS and lets yt-dlp update itself. ``keep_existing`` keeps a copy
    that already exists (yt-dlp's self-updated binary); other tools are refreshed when
    the bundled copy changes after an app update.
    """
    bundled = os.path.join(BUNDLED_BIN, name + EXE)
    if not os.path.isfile(bundled):
        return ""
    tools_dir = os.path.join(data_dir(), "bin")
    os.makedirs(tools_dir, exist_ok=True)
    target = os.path.join(tools_dir, name + EXE)
    stale = not os.path.isfile(target) or (
        not keep_existing and os.path.getsize(target) != os.path.getsize(bundled))
    if stale:
        tmp = target + ".tmp"
        shutil.copy2(bundled, tmp)
        os.replace(tmp, target)
    if SYSTEM != "Windows":
        os.chmod(target, 0o755)
    return target


def _ytdlp_command() -> list:
    """yt-dlp runs through the app's own `dk-ytdlp` helper (built in, same CPU architecture)."""
    if IS_FROZEN:
        return [os.path.join(os.path.dirname(sys.executable), "dk-ytdlp" + EXE)]
    return [sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "ytdlp_runner.py")]


YTDLP = _ytdlp_command()
FFMPEG = _install_tool("ffmpeg") or shutil.which("ffmpeg") or ""
_install_tool("ffprobe")  # yt-dlp finds ffprobe next to ffmpeg; needed to fix up stream downloads
DENO = _install_tool("deno") or shutil.which("deno") or ""


def base_args() -> list:
    args = list(YTDLP) + ["--no-playlist", "--no-warnings"]
    if FFMPEG:
        # Pass the folder so yt-dlp finds both ffmpeg and ffprobe.
        args += ["--ffmpeg-location", os.path.dirname(FFMPEG)]
    if DENO:
        args += ["--js-runtimes", f"deno:{DENO}"]
    return args


def popen_kwargs() -> dict:
    kwargs = {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE, "text": True,
              "encoding": "utf-8", "errors": "replace"}
    if SYSTEM == "Windows":
        kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
    return kwargs


YTDLP_LATEST_URL = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp"
YTDLP_UPDATE_EVERY = 12 * 3600


def ytdlp_version(extra_env=None, with_source=False) -> str:
    """yt-dlp's version ("" if it doesn't run); with_source adds "update"/"built-in"."""
    env = dict(os.environ, **(extra_env or {}))
    try:
        result = subprocess.run(YTDLP + ["--dk-source"], timeout=120, env=env, **popen_kwargs())
        out = result.stdout.strip() if result.returncode == 0 else ""
        return out if with_source else out.split(" ")[0]
    except Exception:
        return ""


def update_ytdlp() -> None:
    """Download yt-dlp's newest release and switch to it only if it runs correctly."""
    import ssl
    import urllib.request

    target = os.path.join(data_dir(), "yt-dlp-latest.zip")
    if os.path.isfile(target) and time.time() - os.path.getmtime(target) < YTDLP_UPDATE_EVERY:
        return
    try:
        import certifi
        context = ssl.create_default_context(cafile=os.environ.get("SSL_CERT_FILE") or certifi.where())
    except Exception:
        context = ssl.create_default_context()
    candidate = target + ".new"
    try:
        with urllib.request.urlopen(YTDLP_LATEST_URL, timeout=120, context=context) as response:
            data = response.read()
        with open(candidate, "wb") as fh:
            fh.write(data)
        new = ytdlp_version({"DK_YTDLP_ZIP": candidate}, with_source=True)
        builtin_version = ytdlp_version({"DK_BUILTIN_YTDLP": "1"})
        new_version = new.split(" ")[0] if new.endswith(" update") else ""
        if new_version and new_version >= builtin_version:
            os.replace(candidate, target)
        else:
            os.remove(candidate)
            os.utime(target) if os.path.isfile(target) else None
    except Exception:
        try:
            os.remove(candidate)
        except OSError:
            pass


def update_ytdlp_in_background() -> None:
    def loop():
        while True:
            update_ytdlp()
            time.sleep(YTDLP_UPDATE_EVERY)

    threading.Thread(target=loop, daemon=True).start()


def parse_ytdlp_json(stdout: str) -> dict:
    """yt-dlp -j prints one JSON object per line; return the first one."""
    for line in stdout.splitlines():
        line = line.strip()
        if line:
            return json.loads(line)
    raise ValueError("yt-dlp returned no data")


def last_error_line(stderr: str) -> str:
    lines = [l.strip() for l in stderr.splitlines() if l.strip()]
    errors = [l for l in lines if l.startswith("ERROR")]
    return (errors or lines or ["Download failed"])[-1].replace("ERROR: ", "")


# ---------------------------------------------------------------- jobs

jobs = {}
jobs_lock = threading.Lock()
slots = threading.Semaphore(MAX_PARALLEL)

PROGRESS_PREFIX = "DKPROG"
FILE_PREFIX = "DKFILE:"
PROGRESS_TEMPLATE = (
    "download:" + PROGRESS_PREFIX
    + " %(progress.downloaded_bytes)s %(progress.total_bytes)s"
    + " %(progress.total_bytes_estimate)s %(progress.speed)s %(progress.eta)s"
)


def _num(value: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def public_job(job: dict) -> dict:
    keys = ("id", "url", "title", "format", "status", "progress", "downloaded", "total",
            "speed", "eta", "filename", "error", "created", "source")
    return {k: job.get(k) for k in keys} | {"file_exists": bool(job.get("file") and os.path.exists(job["file"]))}


def run_download(job_id: str) -> None:
    job = jobs[job_id]
    with slots:
        if job["status"] == "cancelled":
            return
        job["status"] = "downloading"
        # Each job downloads into its own private folder and the finished file is moved into
        # Downloads afterwards, so two jobs for the same video (say MP4 and MP3) never touch
        # each other's files and an existing file is never overwritten or reused.
        temp_dir = os.path.join(data_dir(), "tmp", job_id)
        os.makedirs(temp_dir, exist_ok=True)
        cookie_args = []
        cookies = job.pop("_cookies", "")
        if cookies:
            # Your login for this site (sent by the extension), so sites that need it work.
            # Readable only by you, used for this download, deleted with the temp folder.
            cookie_file = os.path.join(temp_dir, "cookies.txt")
            with open(cookie_file, "w", encoding="utf-8") as fh:
                fh.write(cookies)
            os.chmod(cookie_file, 0o600)
            cookie_args = ["--cookies", cookie_file]
        if job.get("referer"):
            cookie_args += ["--referer", job["referer"]]
        # Streams (.mpd/.m3u8) have no real title of their own: name them after the page.
        name_template = "%(title).150B.%(ext)s"
        if job.get("use_title") and job.get("title"):
            safe = "".join(c for c in job["title"] if c not in '\\/:*?"<>|\n\r\t').strip()[:150].strip(". ")
            if safe:
                name_template = safe.replace("%", "%%") + ".%(ext)s"
        cmd = base_args() + cookie_args + [
            "--newline", "--progress", "--progress-template", PROGRESS_TEMPLATE,
            "--print", f"after_move:{FILE_PREFIX}%(filepath)s",
            "-P", temp_dir,
            "-o", name_template,
        ]
        if job["format"] == "audio":
            cmd += ["-x", "--audio-format", "mp3"]
        elif job.get("format_id"):
            fid = job["format_id"]
            cmd += ["-f", f"{fid}+bestaudio[acodec^=mp4a]/{fid}+bestaudio/best",
                    "-S", "vcodec:h264,res,acodec:m4a", "--merge-output-format", "mp4"]
        else:
            # Prefer H.264/AAC so the file plays everywhere (QuickTime, Windows Media Player,
            # phones). On YouTube that means up to 1080p.
            cmd += ["-f", "bv*[vcodec^=avc1]+ba[acodec^=mp4a]/bv*[vcodec^=avc1]+ba/b[vcodec^=avc1]/bv*+ba/b",
                    "-S", "vcodec:h264,res,acodec:m4a", "--merge-output-format", "mp4"]
        cmd.append(job["url"])

        try:
            proc = subprocess.Popen(cmd, **popen_kwargs())
        except Exception as error:  # yt-dlp missing or not executable
            job.update(status="error", error=str(error))
            return
        job["_proc"] = proc
        stderr_chunks = []
        threading.Thread(target=lambda: stderr_chunks.append(proc.stderr.read()), daemon=True).start()

        for line in proc.stdout:
            line = line.strip()
            if line.startswith(PROGRESS_PREFIX):
                _, done, total, estimate, speed, eta = (line.split(" ") + ["NA"] * 6)[:6]
                done_n, total_n = _num(done), _num(total) or _num(estimate)
                job["downloaded"] = int(done_n)
                job["total"] = int(total_n)
                job["speed"] = int(_num(speed))
                job["eta"] = int(_num(eta))
                job["progress"] = round(done_n * 100 / total_n, 1) if total_n else job.get("progress", 0)
                if job["progress"] >= 100:
                    job["status"] = "processing"
                else:
                    job["status"] = "downloading"
            elif line.startswith(FILE_PREFIX):
                job["file"] = line[len(FILE_PREFIX):]

        proc.wait()
        job.pop("_proc", None)
        try:
            if job["status"] == "cancelled":
                return
            if proc.returncode != 0:
                time.sleep(0.2)
                job.update(status="error", error=last_error_line("".join(stderr_chunks)))
                return
            if not job.get("file") or not os.path.exists(job["file"]):
                job.update(status="error", error="Download finished but the file was not found")
                return
            final = unique_path(os.path.join(download_dir(), os.path.basename(job["file"])))
            shutil.move(job["file"], final)
            job.update(status="done", progress=100, file=final, filename=os.path.basename(final))
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


def unique_path(path: str) -> str:
    """`video.mp4` -> `video (2).mp4` if a file with that name already exists."""
    if not os.path.exists(path):
        return path
    stem, ext = os.path.splitext(path)
    n = 2
    while os.path.exists(f"{stem} ({n}){ext}"):
        n += 1
    return f"{stem} ({n}){ext}"


def create_job(url: str, fmt: str, format_id: str, title: str, source: str, cookies: str = "",
               referer: str = "", use_title: bool = False) -> dict:
    job_id = uuid.uuid4().hex[:10]
    job = {
        "id": job_id, "url": url, "title": title or url, "format": "audio" if fmt == "audio" else "video",
        "format_id": format_id, "status": "queued", "progress": 0, "downloaded": 0, "total": 0,
        "speed": 0, "eta": 0, "filename": "", "error": None, "created": int(time.time() * 1000),
        "source": source, "_cookies": cookies, "referer": referer, "use_title": use_title,
    }
    with jobs_lock:
        jobs[job_id] = job
    threading.Thread(target=run_download, args=(job_id,), daemon=True).start()
    return job


def open_path(path: str, reveal: bool = False) -> None:
    if SYSTEM == "Darwin":
        subprocess.Popen(["open", "-R", path] if reveal else ["open", path])
    elif SYSTEM == "Windows":
        if reveal:
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
        else:
            os.startfile(path)  # type: ignore[attr-defined]
    else:
        subprocess.Popen(["xdg-open", os.path.dirname(path) if reveal else path])


# ---------------------------------------------------------------- web app

app = Flask(__name__, template_folder=os.path.join(BASE_DIR, "templates"),
            static_folder=os.path.join(BASE_DIR, "static"))

ALLOWED_HOSTS = {f"127.0.0.1:{PORT}", f"localhost:{PORT}"}
EXTENSION_SCHEMES = ("chrome-extension://", "moz-extension://", "safari-web-extension://")


def origin_allowed(origin: str) -> bool:
    if not origin:
        return True
    return origin in {f"http://{h}" for h in ALLOWED_HOSTS} or origin.startswith(EXTENSION_SCHEMES)


@app.before_request
def guard():
    # Only this computer's own UI and browser extensions may talk to the server. Websites
    # are rejected, so a page you visit can't start downloads or open files on your computer.
    if request.host not in ALLOWED_HOSTS:
        return jsonify({"error": "Forbidden host"}), 403
    if not origin_allowed(request.headers.get("Origin", "")):
        return jsonify({"error": "Forbidden origin"}), 403
    if request.method == "OPTIONS":
        return "", 204


@app.after_request
def cors(response):
    origin = request.headers.get("Origin", "")
    if origin and origin.startswith(EXTENSION_SCHEMES):
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


@app.route("/")
def index():
    return render_template("index.html", version=VERSION)


@app.route("/api/ping")
def ping():
    return jsonify({"app": APP_ID, "version": VERSION, "downloadDir": download_dir(),
                    "ffmpeg": bool(FFMPEG), "deno": bool(DENO)})


@app.route("/api/diagnostics")
def diagnostics():
    """Quick health check: open http://127.0.0.1:48123/api/diagnostics in a browser."""
    return jsonify({"version": VERSION, "ytdlp": ytdlp_version(with_source=True) or "NOT WORKING",
                    "ffmpeg": FFMPEG or "missing", "deno": DENO or "missing",
                    "downloadDir": download_dir(), "dataDir": data_dir()})


@app.route("/api/info", methods=["POST"])
def get_info():
    url = (request.json or {}).get("url", "").strip()
    if not url:
        return jsonify({"error": "No URL provided"}), 400
    try:
        result = subprocess.run(base_args() + ["-j", url], timeout=90, **popen_kwargs())
        if result.returncode != 0:
            return jsonify({"error": last_error_line(result.stderr)}), 400
        info = parse_ytdlp_json(result.stdout)
        video_formats = [f for f in info.get("formats", []) if f.get("height") and f.get("vcodec", "none") != "none"]
        # Offer only H.264 qualities when the site has them (YouTube: up to 1080p): VP9/AV1
        # in an .mp4 doesn't play in QuickTime and many other players.
        h264 = [f for f in video_formats if str(f.get("vcodec", "")).startswith("avc1")]
        best_by_height = {}
        for f in (h264 or video_formats):
            height = f.get("height")
            if height:
                tbr = f.get("tbr") or 0
                if height not in best_by_height or tbr > (best_by_height[height].get("tbr") or 0):
                    best_by_height[height] = f
        formats = sorted(
            ({"id": f["format_id"], "label": f"{h}p", "height": h} for h, f in best_by_height.items()),
            key=lambda x: x["height"], reverse=True)
        return jsonify({
            "title": info.get("title", ""), "thumbnail": info.get("thumbnail", ""),
            "duration": info.get("duration"), "uploader": info.get("uploader", ""), "formats": formats,
        })
    except subprocess.TimeoutExpired:
        return jsonify({"error": "Timed out fetching video info"}), 400
    except Exception as error:
        return jsonify({"error": str(error)}), 400


@app.route("/api/playlist", methods=["POST"])
def get_playlist_info():
    url = (request.json or {}).get("url", "").strip()
    if not url:
        return jsonify({"error": "No URL provided"}), 400
    try:
        args = [a for a in base_args() if a != "--no-playlist"]
        result = subprocess.run(args + ["--flat-playlist", "-J", url], timeout=90, **popen_kwargs())
        if result.returncode != 0:
            return jsonify({"error": last_error_line(result.stderr)}), 400
        entries = json.loads(result.stdout).get("entries", []) or []
        return jsonify({"urls": [e.get("url") for e in entries if e.get("url")]})
    except subprocess.TimeoutExpired:
        return jsonify({"error": "Timed out fetching playlist info"}), 400
    except Exception as error:
        return jsonify({"error": str(error)}), 400


@app.route("/api/download", methods=["POST"])
def start_download():
    data = request.json or {}
    url = str(data.get("url", "")).strip()
    if not url.lower().startswith(("http://", "https://")):
        return jsonify({"error": "Please give a web link (http or https)"}), 400
    source = "extension" if request.headers.get("Origin", "").startswith(EXTENSION_SCHEMES) else "app"
    cookies = str(data.get("cookies") or "")
    if not cookies.startswith("# Netscape HTTP Cookie File"):
        cookies = ""
    referer = str(data.get("referer") or "")
    if not referer.lower().startswith(("http://", "https://")):
        referer = ""
    job = create_job(url, str(data.get("format", "video")), data.get("format_id") or "",
                     str(data.get("title", "")), source, cookies, referer, bool(data.get("use_title")))
    return jsonify({"job_id": job["id"], "job": public_job(job)})


@app.route("/api/status/<job_id>")
def check_status(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(public_job(job))


@app.route("/api/jobs")
def list_jobs():
    with jobs_lock:
        items = [public_job(j) for j in jobs.values()]
    return jsonify({"jobs": sorted(items, key=lambda j: j["created"], reverse=True)})


@app.route("/api/jobs/<job_id>/<action>", methods=["POST"])
def job_action(job_id, action):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    if action == "cancel":
        if job["status"] in ("queued", "downloading", "processing"):
            job["status"] = "cancelled"
            proc = job.get("_proc")
            if proc:
                proc.terminate()
        return jsonify({"ok": True})
    if action in ("open", "reveal"):
        if not job.get("file") or not os.path.exists(job["file"]):
            return jsonify({"error": "File not found"}), 404
        open_path(job["file"], reveal=(action == "reveal"))
        return jsonify({"ok": True})
    if action == "remove":
        if job["status"] in ("queued", "downloading", "processing"):
            job["status"] = "cancelled"
            proc = job.get("_proc")
            if proc:
                proc.terminate()
        with jobs_lock:
            jobs.pop(job_id, None)
        return jsonify({"ok": True})
    return jsonify({"error": "Unknown action"}), 400


@app.route("/api/open-folder", methods=["POST"])
def open_folder():
    open_path(download_dir())
    return jsonify({"ok": True})


def make_server():
    from werkzeug.serving import make_server as _make_server
    return _make_server(HOST, PORT, app, threaded=True)


if __name__ == "__main__":
    update_ytdlp_in_background()
    print(f"{APP_NAME} is running at http://{HOST}:{PORT}")
    make_server().serve_forever()
