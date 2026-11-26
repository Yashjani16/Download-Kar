"""Download Kar Desktop launcher.

Starts the local download server and shows a menu-bar (macOS) / system-tray (Windows)
icon with Open, Downloads folder and Quit. If the app is already running, it just opens
the existing window in the browser.
"""
import json
import os
import sys
import threading
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


def open_ui(*_args) -> None:
    webbrowser.open(URL)


def open_downloads(*_args) -> None:
    server.open_path(server.download_dir())


def main() -> None:
    if already_running():
        open_ui()
        return

    try:
        httpd = server.make_server()
    except OSError:
        print(f"Port {server.PORT} is busy. Close the other program using it and try again.")
        sys.exit(1)

    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    server.update_ytdlp_in_background()

    # Open the window when the user launches the app (always on macOS, where the app has
    # no Dock icon; on Windows the Start-menu shortcut passes --open, while the sign-in
    # autostart does not) and on the very first run.
    first_run_flag = os.path.join(server.data_dir(), ".welcomed")
    if sys.platform == "darwin" or "--open" in sys.argv or not os.path.exists(first_run_flag):
        open_ui()
        open(first_run_flag, "w").close()

    if "--no-tray" in sys.argv:
        print(f"{server.APP_NAME} is running at {URL}")
        threading.Event().wait()
        return

    import pystray
    from PIL import Image

    icon_image = Image.open(os.path.join(server.BASE_DIR, "static", "icon.png"))

    def quit_app(icon, _item):
        icon.stop()
        httpd.shutdown()

    menu = pystray.Menu(
        pystray.MenuItem("Open Download Kar", open_ui, default=True),
        pystray.MenuItem("Open Downloads folder", open_downloads),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit Download Kar", quit_app),
    )
    pystray.Icon("download-kar", icon_image, "Download Kar", menu).run()


if __name__ == "__main__":
    main()
