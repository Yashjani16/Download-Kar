"""Download Kar Desktop launcher.

One program, three roles:
  (no flags)   what you get when you open the app: makes sure the background service is
               running, then shows the Download Kar window.
  --server     the background service: the local download server the browser extension
               talks to, plus the menu-bar (macOS) / system-tray (Windows) icon. Windows
               starts this at sign-in.
  --window     just the Download Kar window (used by the tray icon's "Open" item).

The window and the service are separate processes, so closing the window never stops
downloads, and the extension keeps working while the window is closed.
"""
import json
import os
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser

import server

URL = f"http://{server.HOST}:{server.PORT}"


def already_running() -> bool:
    try:
        with urllib.request.urlopen(URL + "/api/ping", timeout=1.5) as response:
            return json.load(response).get("app") == server.APP_ID
    except Exception:
        return False


def self_command(*args: str) -> list:
    if server.IS_FROZEN:
        return [sys.executable, *args]
    return [sys.executable, os.path.abspath(__file__), *args]


def spawn(*args: str) -> None:
    """Start another copy of this program in the background, detached from this one."""
    kwargs = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if server.SYSTEM == "Windows":
        kwargs["creationflags"] = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(self_command(*args), **kwargs)


def ensure_server() -> bool:
    if already_running():
        return True
    spawn("--server")
    for _ in range(60):  # up to ~15 s on a slow first start
        time.sleep(0.25)
        if already_running():
            return True
    return False


def open_in_browser() -> None:
    webbrowser.open(URL)


def show_window() -> None:
    """The Download Kar window (native WebKit on macOS, Edge WebView2 on Windows)."""
    if os.environ.get("DK_BROWSER_UI") == "1":
        open_in_browser()
        return
    try:
        import webview
    except Exception:
        open_in_browser()
        return
    try:
        webview.create_window(
            "Download Kar", URL, width=980, height=780, min_size=(560, 520),
            background_color="#F4F1EB", text_select=True,
        )
        webview.start()
    except Exception:
        # No usable web view on this computer (e.g. WebView2 missing): use the browser.
        open_in_browser()


def open_window_from_tray(*_args) -> None:
    spawn("--window")


def open_downloads(*_args) -> None:
    server.open_path(server.download_dir())


def run_server() -> None:
    if already_running():
        return
    try:
        httpd = server.make_server()
    except OSError:
        print(f"Port {server.PORT} is busy. Close the other program using it and try again.")
        sys.exit(1)

    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    server.update_ytdlp_in_background()

    if "--no-tray" in sys.argv:
        print(f"{server.APP_NAME} is running at {URL}")
        threading.Event().wait()
        return

    try:
        import pystray
        from PIL import Image
    except Exception:
        threading.Event().wait()
        return

    if server.SYSTEM == "Darwin":
        # Background service: menu-bar icon only, no Dock icon.
        try:
            from AppKit import NSApplication
            NSApplication.sharedApplication().setActivationPolicy_(1)  # Accessory
        except Exception:
            pass

    icon_image = Image.open(os.path.join(server.BASE_DIR, "static", "icon.png"))

    def quit_app(icon, _item):
        icon.stop()
        httpd.shutdown()

    menu = pystray.Menu(
        pystray.MenuItem("Open Download Kar", open_window_from_tray, default=True),
        pystray.MenuItem("Open Downloads folder", open_downloads),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit Download Kar", quit_app),
    )
    pystray.Icon("download-kar", icon_image, "Download Kar", menu).run()


def main() -> None:
    if "--server" in sys.argv:
        run_server()
        return
    if "--window" in sys.argv:
        show_window()
        return
    # Opened by the user: start the background service if needed, then show the window.
    if not ensure_server():
        print("Download Kar couldn't start its background service.")
        sys.exit(1)
    show_window()


if __name__ == "__main__":
    main()
