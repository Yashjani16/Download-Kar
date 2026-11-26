// Download Kar: standalone replacement for the Ghost Downloader desktop bridge.
// Exposes the same surface background.ts used for desktop-bridge, but every task is
// downloaded by the browser itself through chrome.downloads — no desktop app needed.
import type {CommandResult, DesktopConnectionState, TaskSummary} from "../shared/types";
import {fileExtension} from "../shared/utils";

const TRACKED_KEY = "dkTrackedDownloads";
const DESKTOP_JOBS_KEY = "dkDesktopJobs";
const DESKTOP_URL = "http://127.0.0.1:48123";
const DESKTOP_APP_ID = "download-kar-desktop";
const DESKTOP_TASK_PREFIX = "desktop:";
const DESKTOP_SEEN_KEY = "dkDesktopSeen";
// Filled in at build time (GitHub Actions sets it to this repo's Releases page).
declare const __DK_RELEASES_URL__: string;
const RELEASES_URL = typeof __DK_RELEASES_URL__ === "string" ? __DK_RELEASES_URL__ : "";
const POLL_MS = 1000;
const MAX_TRACKED = 300;

type TrackedDownload = { id: number; createdAt: number; url: string; filename: string };
type DesktopJobRef = { id: string; url: string; title: string; format: string; createdAt: number };
type DesktopJob = {
  id: string; url: string; title: string; format: string; status: string; progress: number;
  downloaded: number; total: number; speed: number; filename: string; error: string | null;
  created: number; file_exists: boolean;
};

const DESKTOP_STATUS: Record<string, string> = {
  queued: "waiting", downloading: "running", processing: "running",
  done: "completed", error: "failed", cancelled: "failed",
};

export type LocalBridgeSnapshot = {
  connectionState: DesktopConnectionState;
  connectionMessage: string;
  desktopVersion: string;
  token: string;
  serverUrl: string;
  tasks: TaskSummary[];
};

export interface LocalBridgeOptions {
  onTaskSnapshotChanged?: (tasks: TaskSummary[]) => void;
}

function isManifestUrl(url: string): boolean {
  return /\.(m3u8|mpd)(?:$|[?#])/i.test(url);
}

function safeFilename(name: string): string {
  return String(name ?? "")
    .replace(/[<>:"/\\|?*~\x00-\x1f]+/g, " ")
    .replace(/\s+/g, " ")
    .replace(/^[. ]+|[. ]+$/g, "")
    .trim()
    .slice(0, 150);
}

function basename(path: string): string {
  return path.split(/[\\/]/).pop() || path;
}

function msg(key: string, fallback: string, subs?: string[]): string {
  return chrome.i18n.getMessage(key, subs) || fallback;
}

export function createLocalBridge(options: LocalBridgeOptions = {}) {
  const tracked = new Map<number, TrackedDownload>();
  const speedSamples = new Map<number, { bytes: number; time: number; speed: number }>();
  let tasks: TaskSummary[] = [];
  const desktopRefs = new Map<string, DesktopJobRef>();
  let desktopSnapshot = new Map<string, DesktopJob>();
  let pollTimer: ReturnType<typeof setInterval> | null = null;
  let loaded = false;

  async function persist() {
    const list = [...tracked.values()].sort((a, b) => b.createdAt - a.createdAt).slice(0, MAX_TRACKED);
    const desktopList = [...desktopRefs.values()].sort((a, b) => b.createdAt - a.createdAt).slice(0, MAX_TRACKED);
    await chrome.storage.local.set({ [TRACKED_KEY]: list, [DESKTOP_JOBS_KEY]: desktopList });
  }

  async function loadPersistentState() {
    const stored = await chrome.storage.local.get([TRACKED_KEY, DESKTOP_JOBS_KEY]);
    for (const item of (stored[TRACKED_KEY] ?? []) as TrackedDownload[]) {
      if (typeof item?.id === "number") { tracked.set(item.id, item); }
    }
    for (const ref of (stored[DESKTOP_JOBS_KEY] ?? []) as DesktopJobRef[]) {
      if (typeof ref?.id === "string") { desktopRefs.set(ref.id, ref); }
    }
    loaded = true;
    await refresh();
  }

  function toSummary(item: chrome.downloads.DownloadItem, meta: TrackedDownload): TaskSummary {
    const total = item.totalBytes > 0 ? item.totalBytes : (item.fileSize > 0 ? item.fileSize : 0);
    const received = item.bytesReceived ?? 0;
    let status = "running";
    if (item.state === "complete") {
      status = "completed";
    } else if (item.state === "interrupted") {
      status = item.canResume ? "paused" : "failed";
    } else if (item.paused) {
      status = "paused";
    } else if (received === 0 && total === 0) {
      status = "waiting";
    }

    const now = Date.now();
    const sample = speedSamples.get(item.id);
    let speed = 0;
    if (status === "running") {
      if (sample && now > sample.time) {
        const instant = ((received - sample.bytes) * 1000) / (now - sample.time);
        speed = sample.speed > 0 ? sample.speed * 0.6 + instant * 0.4 : instant;
      }
      speedSamples.set(item.id, { bytes: received, time: now, speed: Math.max(0, speed) });
    } else {
      speedSamples.delete(item.id);
    }

    const name = basename(item.filename || "") || meta.filename || basename(new URL(item.finalUrl || item.url).pathname) || "download";
    const progress = status === "completed" ? 100 : total > 0 ? (received / total) * 100 : 0;
    return {
      taskId: String(item.id),
      name,
      status,
      progress,
      receivedBytes: received,
      fileSize: total,
      speed: Math.max(0, Math.round(speed)),
      createdAt: meta.createdAt,
      canPause: item.state === "in_progress" || (item.state === "interrupted" && item.canResume),
      canOpenFile: item.state === "complete" && item.exists !== false,
      canOpenFolder: item.exists !== false && Boolean(item.filename),
      shouldOpenWhenDone: false,
      fileExt: fileExtension(name),
      packName: "",
    };
  }

  async function refresh() {
    if (!loaded) { return; }
    const next: TaskSummary[] = [];
    let changedTracking = false;
    for (const meta of tracked.values()) {
      const [item] = await chrome.downloads.search({ id: meta.id });
      if (!item) {
        tracked.delete(meta.id);
        changedTracking = true;
        continue;
      }
      next.push(toSummary(item, meta));
    }
    if (changedTracking) { await persist(); }
    next.push(...(await desktopTaskSummaries()));
    tasks = next.sort((a, b) => b.createdAt - a.createdAt);
    options.onTaskSnapshotChanged?.(tasks);
    schedulePolling();
  }

  function schedulePolling() {
    const hasActive = tasks.some((t) => t.status === "running" || t.status === "waiting");
    if (hasActive && !pollTimer) {
      pollTimer = setInterval(() => void refresh(), POLL_MS);
    } else if (!hasActive && pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
  }

  function startBrowserDownload(url: string, filename: string, saveAs = false): Promise<number> {
    const cleanName = safeFilename(filename);
    const attempt = (name?: string) => new Promise<number>((resolve, reject) => {
      chrome.downloads.download({ url, ...(name ? { filename: name } : {}), ...(saveAs ? { saveAs: true } : {}) }, (downloadId) => {
        const lastError = chrome.runtime.lastError;
        if (lastError || typeof downloadId !== "number") {
          reject(new Error(lastError?.message || "Download failed to start"));
          return;
        }
        resolve(downloadId);
      });
    });
    // A filename Chrome rejects (reserved name, odd unicode) should not lose the download.
    return cleanName ? attempt(cleanName).catch(() => attempt()) : attempt();
  }

  // ------------------------------------------------------------ Download Kar Desktop

  async function desktopRequest<T>(path: string, init: RequestInit = {}, timeoutMs = 4000): Promise<T> {
    const response = await fetch(DESKTOP_URL + path, {
      ...init,
      headers: { "Content-Type": "application/json" },
      signal: AbortSignal.timeout(timeoutMs),
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) { throw new Error(body?.error || `Download Kar Desktop error ${response.status}`); }
    return body as T;
  }

  async function isDesktopRunning(): Promise<boolean> {
    try {
      const ping = await desktopRequest<{ app?: string }>("/api/ping", {}, 1500);
      if (ping.app === DESKTOP_APP_ID) {
        void chrome.storage.local.set({ [DESKTOP_SEEN_KEY]: true });
        return true;
      }
      return false;
    } catch {
      return false;
    }
  }

  // Sites where downloads already work without a login; their cookies are never sent.
  const NO_COOKIE_SITES = /(^|\.)(youtube\.com|youtu\.be|youtube-nocookie\.com)$/i;

  /** The user's cookies for this one site, in the cookies.txt format yt-dlp reads. */
  async function siteCookies(url: string): Promise<string> {
    try {
      const host = new URL(url).hostname;
      if (NO_COOKIE_SITES.test(host) || !chrome.cookies?.getAll) { return ""; }
      const cookies = await chrome.cookies.getAll({ url });
      if (cookies.length === 0) { return ""; }
      const lines = ["# Netscape HTTP Cookie File"];
      for (const c of cookies) {
        const domain = c.hostOnly ? c.domain.replace(/^\./, "") : (c.domain.startsWith(".") ? c.domain : `.${c.domain}`);
        lines.push([
          domain,
          c.hostOnly ? "FALSE" : "TRUE",
          c.path || "/",
          c.secure ? "TRUE" : "FALSE",
          String(Math.floor(c.expirationDate ?? 0)),
          c.name,
          c.value,
        ].join("\t"));
      }
      return lines.join("\n") + "\n";
    } catch {
      return "";
    }
  }

  async function sendToDesktop(url: string, title: string, format: "video" | "audio" = "video"): Promise<CommandResult> {
    if (!/^https?:/i.test(url)) {
      return { ok: false, message: msg("errorInvalidDownloadRequest", "This page can't be downloaded.") };
    }
    if (!(await isDesktopRunning())) {
      // First time only: show where to get the app. After that, just ask to open it.
      const seen = (await chrome.storage.local.get(DESKTOP_SEEN_KEY))[DESKTOP_SEEN_KEY];
      if (RELEASES_URL && !seen) { void chrome.tabs.create({ url: RELEASES_URL }); }
      return {
        ok: false,
        message: msg("dkDesktopNeeded", "Open the Download Kar desktop app to download from this site."),
      };
    }
    try {
      // The site's cookies let the app download what you can watch while logged in
      // (LinkedIn, Facebook, X, ...). They go only to the app on this computer, are used
      // for this one download and deleted afterwards.
      const cookies = await siteCookies(url);
      const result = await desktopRequest<{ job_id: string }>("/api/download", {
        method: "POST",
        body: JSON.stringify({ url, title, format, cookies }),
      });
      desktopRefs.set(result.job_id, { id: result.job_id, url, title, format, createdAt: Date.now() });
      await persist();
      await refresh();
      return { ok: true, taskId: DESKTOP_TASK_PREFIX + result.job_id, message: msg("dkSentToDesktop", "Downloading with Download Kar Desktop") };
    } catch (error) {
      return { ok: false, message: error instanceof Error ? error.message : msg("errorSendFailed", "Download failed") };
    }
  }

  async function desktopTaskSummaries(): Promise<TaskSummary[]> {
    if (desktopRefs.size === 0) { return []; }
    try {
      const { jobs } = await desktopRequest<{ jobs: DesktopJob[] }>("/api/jobs", {}, 2000);
      desktopSnapshot = new Map(jobs.map((job) => [job.id, job]));
    } catch {
      // App closed: keep the last known state; jobs it no longer knows show as failed.
    }
    const summaries: TaskSummary[] = [];
    for (const ref of desktopRefs.values()) {
      const job = desktopSnapshot.get(ref.id);
      const status = job ? (DESKTOP_STATUS[job.status] ?? "running") : "failed";
      const name = job?.filename || ref.title || job?.title || ref.url;
      summaries.push({
        taskId: DESKTOP_TASK_PREFIX + ref.id,
        name,
        status,
        progress: job ? (status === "completed" ? 100 : job.progress || 0) : 0,
        receivedBytes: job?.downloaded ?? 0,
        fileSize: job?.total ?? 0,
        speed: status === "running" ? job?.speed ?? 0 : 0,
        createdAt: ref.createdAt,
        canPause: false,
        canOpenFile: Boolean(job && status === "completed" && job.file_exists),
        canOpenFolder: Boolean(job && status === "completed" && job.file_exists),
        shouldOpenWhenDone: false,
        fileExt: fileExtension(job?.filename || "") || (ref.format === "audio" ? "mp3" : "mp4"),
        packName: "desktop",
      });
    }
    return summaries;
  }

  async function desktopTaskAction(jobId: string, action: string): Promise<CommandResult> {
    const ref = desktopRefs.get(jobId);
    if (!ref) { return { ok: true }; }
    try {
      switch (action) {
        case "open_file":
          await desktopRequest(`/api/jobs/${jobId}/open`, { method: "POST" });
          break;
        case "open_folder":
          await desktopRequest(`/api/jobs/${jobId}/reveal`, { method: "POST" });
          break;
        case "cancel":
          await desktopRequest(`/api/jobs/${jobId}/cancel`, { method: "POST" });
          break;
        case "remove":
          desktopRefs.delete(jobId);
          await persist();
          await desktopRequest(`/api/jobs/${jobId}/remove`, { method: "POST" }).catch(() => undefined);
          break;
        case "toggle_pause":
        case "redownload": {
          desktopRefs.delete(jobId);
          await persist();
          await desktopRequest(`/api/jobs/${jobId}/remove`, { method: "POST" }).catch(() => undefined);
          const result = await sendToDesktop(ref.url, ref.title, ref.format === "audio" ? "audio" : "video");
          await refresh();
          return result;
        }
        default:
          return { ok: false, message: msg("errorTaskActionFailed", "Unsupported action") };
      }
      await refresh();
      return { ok: true };
    } catch (error) {
      return { ok: false, message: error instanceof Error ? error.message : msg("errorTaskActionFailed", "Action failed") };
    }
  }

  async function addDownload(url: string, filename: string, saveAs = false): Promise<CommandResult> {
    if (!url || !/^(https?:|blob:|data:|ftp:)/i.test(url)) {
      return { ok: false, message: msg("errorInvalidDownloadRequest", "This link can't be downloaded.") };
    }
    try {
      const id = await startBrowserDownload(url, filename, saveAs);
      tracked.set(id, { id, createdAt: Date.now(), url, filename: safeFilename(filename) });
      await persist();
      await refresh();
      return { ok: true, taskId: String(id), message: msg("dkDownloadStarted", "Download started") };
    } catch (error) {
      return { ok: false, message: error instanceof Error ? error.message : msg("errorSendFailed", "Download failed") };
    }
  }

  async function createTask(payload: Record<string, any>): Promise<CommandResult> {
    const source = String(payload.source ?? "");
    const body = (payload.payload ?? {}) as Record<string, any>;

    if (source === "page_media") {
      // Sites like YouTube stream video in pieces the browser can't save; the desktop app's
      // yt-dlp downloads them from the page link instead.
      return sendToDesktop(String(body.url || body.pageUrl || ""), String(payload.title || body.pageTitle || ""));
    }

    if (source === "resource_merge") {
      const parts = Array.isArray(body.resources) ? body.resources : [];
      let started = 0;
      for (const part of parts) {
        const result = await addDownload(String(part.url ?? ""), String(part.filename ?? ""));
        if (result.ok) { started += 1; }
      }
      return started > 0
        ? { ok: true, message: msg("dkMergeSeparate", "Video and audio are downloading as separate files.") }
        : { ok: false, message: msg("errorMergeFailed", "Download failed") };
    }

    const url = String(body.url ?? "");
    if (isManifestUrl(url)) {
      return openStreamDownloader(url, String(body.headers?.referer ?? ""), String(body.filename ?? payload.title ?? ""));
    }
    return addDownload(url, String(body.filename ?? payload.title ?? ""), Boolean(payload.draft));
  }

  // HLS / DASH playlists are not single files: hand them to the bundled cat-catch stream
  // downloader page, which fetches every segment and joins them in the browser.
  async function openStreamDownloader(url: string, referer: string, title: string): Promise<CommandResult> {
    const page = /\.mpd(?:$|[?#])/i.test(url) ? "mpd.html" : "m3u8.html";
    const params = new URLSearchParams({ url });
    if (referer) { params.set("requestHeaders", JSON.stringify({ referer })); }
    if (title) { params.set("title", title.replace(/\.(m3u8|mpd)$/i, "")); }
    try {
      await chrome.tabs.create({ url: chrome.runtime.getURL(`catch-tools/${page}?${params.toString()}`) });
      return { ok: true, message: msg("dkStreamOpened", "Opened the stream downloader in a new tab.") };
    } catch (error) {
      return { ok: false, message: error instanceof Error ? error.message : msg("errorSendFailed", "Download failed") };
    }
  }

  async function taskAction(taskId: string, action: string): Promise<CommandResult> {
    if (taskId.startsWith(DESKTOP_TASK_PREFIX)) {
      return desktopTaskAction(taskId.slice(DESKTOP_TASK_PREFIX.length), action);
    }
    const id = Number(taskId);
    const [item] = await chrome.downloads.search({ id });
    const meta = tracked.get(id);
    if (!item || !meta) {
      tracked.delete(id);
      await persist();
      await refresh();
      return action === "remove" ? { ok: true } : { ok: false, message: msg("errorTaskActionFailed", "Task not found") };
    }
    try {
      switch (action) {
        case "toggle_pause":
          if (item.state === "in_progress" && !item.paused) {
            await chrome.downloads.pause(id);
          } else if (item.canResume) {
            await chrome.downloads.resume(id);
          } else {
            await addDownload(meta.url, meta.filename);
          }
          break;
        case "redownload":
          await addDownload(meta.url, meta.filename || basename(item.filename));
          break;
        case "open_file":
          try {
            await chrome.downloads.open(id);
          } catch {
            chrome.downloads.show(id);
          }
          break;
        case "open_folder":
          chrome.downloads.show(id);
          break;
        case "cancel":
          if (item.state === "in_progress") { await chrome.downloads.cancel(id); }
          break;
        case "remove":
          if (item.state === "in_progress") { await chrome.downloads.cancel(id); }
          tracked.delete(id);
          await persist();
          await chrome.downloads.erase({ id }).catch(() => undefined);
          break;
        default:
          return { ok: false, message: msg("errorTaskActionFailed", "Unsupported action") };
      }
      await refresh();
      return { ok: true };
    } catch (error) {
      return { ok: false, message: error instanceof Error ? error.message : msg("errorTaskActionFailed", "Action failed") };
    }
  }

  async function sendRequest<T extends CommandResult>(payload: Record<string, any>, _timeoutMs?: number): Promise<T> {
    if (!loaded) { await loadPersistentState(); }
    if (payload.type === "create_task") { return (await createTask(payload)) as T; }
    if (payload.type === "task_action") { return (await taskAction(String(payload.taskId), String(payload.action))) as T; }
    return { ok: false, message: msg("errorUnknownCommand", "Unknown command", [String(payload.type)]) } as T;
  }

  chrome.downloads.onChanged.addListener((delta) => {
    if (tracked.has(delta.id)) { void refresh(); }
  });
  chrome.downloads.onErased.addListener((id) => {
    if (tracked.delete(id)) { void persist().then(refresh); }
  });

  function buildSnapshot(): LocalBridgeSnapshot {
    if (loaded) { void refresh(); }
    return {
      connectionState: "connected",
      connectionMessage: "",
      desktopVersion: "",
      token: "",
      serverUrl: "",
      tasks,
    };
  }

  return {
    buildSnapshot,
    isReady: () => true,
    isDesktopRunning,
    loadPersistentState,
    sendRequest,
    sendToDesktop,
  };
}
