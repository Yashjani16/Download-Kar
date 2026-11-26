// Downloads cat-catch (https://github.com/xifangczy/cat-catch, GPL-3.0) into ../upstream at
// the exact commit Download Kar was tested with, then applies Download Kar's small changes.
// build.mjs runs this automatically when ../upstream is missing.
import {execFileSync} from "node:child_process";
import {existsSync, mkdirSync, readFileSync, rmSync, writeFileSync} from "node:fs";
import path from "node:path";
import {fileURLToPath} from "node:url";

const CAT_CATCH_REPO = "https://github.com/xifangczy/cat-catch.git";
const CAT_CATCH_COMMIT = "97f6005bf06230338001d4b0458a959b722cb384";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const upstreamDir = path.resolve(__dirname, "../../upstream");

// [file, original text, Download Kar replacement]
const PATCHES = [
  [
    "js/init.js",
    "    M3u8Mp4: false,",
    "    M3u8Mp4: true,  // Download Kar: save HLS as MP4 by default",
  ],
  [
    "js/init.js",
    "    M3u8Ffmpeg: true,",
    "    M3u8Ffmpeg: false,  // Download Kar: never send files to an online FFmpeg site by default",
  ],
  [
    "js/init.js",
    '        chrome.action.setIcon({ path: G.enable ? "/img/icon.png" : "/img/icon-disable.png" });',
    "        // Download Kar: keep our own toolbar icon.",
  ],
];

function git(...args) {
  execFileSync("git", args, { cwd: upstreamDir, stdio: "inherit" });
}

export function fetchUpstream() {
  if (existsSync(path.join(upstreamDir, "catch-script"))) {
    return;
  }
  console.log(`Fetching cat-catch ${CAT_CATCH_COMMIT.slice(0, 7)} into ${upstreamDir}`);
  rmSync(upstreamDir, { recursive: true, force: true });
  mkdirSync(upstreamDir, { recursive: true });
  git("init", "-q");
  git("fetch", "-q", "--depth", "1", CAT_CATCH_REPO, CAT_CATCH_COMMIT);
  git("checkout", "-q", "FETCH_HEAD");
  rmSync(path.join(upstreamDir, ".git"), { recursive: true, force: true });

  for (const [file, original, replacement] of PATCHES) {
    const target = path.join(upstreamDir, file);
    const text = readFileSync(target, "utf8");
    if (!text.includes(original)) {
      throw new Error(`cat-catch patch failed: "${original.trim()}" not found in ${file}`);
    }
    writeFileSync(target, text.replace(original, replacement));
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  fetchUpstream();
}
