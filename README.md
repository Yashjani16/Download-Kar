# Download Kar

Free downloader for Windows and macOS, in two parts:

1. **Browser extension** (Chrome, Edge, Brave, Opera, Firefox): downloads videos, audio, images, files and HLS streams straight from web pages.
2. **Download Kar Desktop** (optional small app): downloads from YouTube, Instagram, TikTok, X, Facebook and 1000+ other sites using yt-dlp. The extension sends pages to it automatically.

## Features

**Extension**
- **Resources tab**: lists the videos, audio, PDFs and other files the current page loads. Click one to download it.
- **"Download this page" bar** (Resources tab): sends the page to the desktop app as a video (MP4) or audio (MP3).
- **On-page media button**: a download button over videos. On YouTube-type sites it uses the desktop app.
- **Images tab**: scan the page for images and download several at once.
- **Stream videos (m3u8 / HLS)**: a built-in stream downloader that joins the parts into one MP4.
- **Right-click menu**: download a link, image or video, or send the page to the desktop app as MP4 or MP3.
- **Tasks tab**: progress, speed, pause/resume, open file, show in folder. Includes desktop-app downloads.

**Desktop app**
- Paste links (several at once) and pick MP4 or MP3 and quality.
- Saves to `Downloads/Download Kar`.
- Lives in the menu bar (Mac) or system tray (Windows). Windows can start it at sign-in.
- Updates yt-dlp by itself, so sites keep working.

## Publishing a release (GitHub builds everything)

Every push to `main` runs the **Build and release** workflow (Actions tab, about 10–15 minutes). It publishes a GitHub Release named after the version in `app/package.json` with:
- `DownloadKar-Extension-Chrome-<version>.zip`, `DownloadKar-Extension-Firefox-<version>.zip`
- `DownloadKar-Desktop-Mac-AppleSilicon-<version>.dmg` (M1/M2/M3/M4 Macs)
- `DownloadKar-Desktop-Mac-Intel-<version>.dmg` (older Intel Macs)
- `DownloadKar-Desktop-Setup-<version>.exe` (Windows)

To ship a new version, change `"version"` in `app/package.json` (for example to `1.2.0`) and push. Share the release page. The extension it builds already points people there when the desktop app is missing.

## Installing (for users)

**Extension:** unzip the Chrome zip, open `chrome://extensions`, turn on **Developer mode**, click **Load unpacked** and pick the unzipped folder.

**Desktop app**
- **Mac:** open the `.dmg` and drag Download Kar into Applications. The first time, macOS may say it can't verify the developer. Go to **System Settings → Privacy & Security** and click **Open Anyway**. To start it automatically, add it under **System Settings → General → Login Items**.
- **Windows:** run the Setup `.exe`. If SmartScreen appears, click **More info → Run anyway**.

The apps aren't code-signed yet. Signing removes these warnings but costs money: Apple Developer Program $99/year, plus a Windows code-signing certificate.

## Building locally

```bash
# extension
cd app && npm install && npm run build          # outputs ../chromium and ../firefox

# desktop app (run without packaging; needs Python 3.10+, ffmpeg and ffprobe installed)
cd desktop && pip install -r requirements.txt && python main.py
```

## Project layout

- `app/`: extension source (TypeScript + React)
  - `src/background/local-bridge.ts`: download engine (browser downloads and the desktop-app connection)
  - `src/popup/components/DesktopBar.tsx`: the "download this page" bar
  - `public/_locales/en/messages.json`: all text shown to users
- `upstream/`: cat-catch (stream downloader pages, page tools), downloaded automatically by the build at a pinned version with Download Kar's patches (`app/scripts/fetch-upstream.mjs`)
- `desktop/`: Download Kar Desktop
  - `server.py`: local server on `127.0.0.1:48123`, runs yt-dlp
  - `main.py`: tray / menu-bar launcher
  - `templates/index.html`: the app window
  - `packaging/`: tool download script, PyInstaller spec, Windows installer script
- `.github/workflows/release.yml`: builds and publishes everything

## Security

The desktop app only listens on your own computer (`127.0.0.1`). It accepts requests only from its own window and from browser extensions. Websites you visit are refused, so a page can't start downloads or open files on your computer.

## Limitations

- DRM-protected services (Netflix, Prime Video, Hotstar, Spotify and similar) can't be downloaded.
- Chrome Web Store policy doesn't allow YouTube downloaders. Publish the extension through GitHub releases (load unpacked) rather than the Web Store, or publish a store version without the desktop-app features.

## Credits and licenses

Download Kar is free software under **GPL-3.0** (see `LICENSE`). If you share or publish it, keep it GPL-3.0, make the source available and keep these credits.

- [Ghost Downloader 3](https://github.com/XiaoYouChR/Ghost-Downloader-3) by XiaoYouChR (GPL-3.0): extension base
- [cat-catch](https://github.com/xifangczy/cat-catch) by xifangczy (GPL-3.0): media capture and stream downloader
- [ReClip](https://github.com/averygan/reclip) by averygan (MIT, see `desktop/LICENSE-RECLIP`): desktop app base
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) (Unlicense), [FFmpeg](https://ffmpeg.org) static builds from [ffmpeg-static](https://github.com/eugeneware/ffmpeg-static) (GPL), [Deno](https://deno.com) (MIT): bundled tools in the desktop app

Changes from the originals: the extension's desktop connection now uses a new local downloader and Download Kar Desktop; pairing and download interception were removed; the stream downloader saves MP4 locally instead of using an online FFmpeg service; ReClip was rebranded and given a tray launcher, bundled tools, saving to the Downloads folder, progress, cancel and a locked-down local API.
