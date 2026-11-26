import {Button, Caption1, Card, makeStyles, tokens} from "@fluentui/react-components";
import {ArrowDownloadRegular, MusicNote2Regular} from "@fluentui/react-icons";
import {useEffect, useState} from "react";

// Download Kar: one-click hand-off of the current page to the Download Kar desktop app,
// which uses yt-dlp for YouTube, Instagram, TikTok and 1000+ other sites.

const DESKTOP_PING_URL = "http://127.0.0.1:48123/api/ping";

const useStyles = makeStyles({
  card: {
    margin: "8px 12px 0",
    padding: "10px 12px",
    gap: "6px",
  },
  top: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: "8px",
  },
  title: {
    fontWeight: tokens.fontWeightSemibold,
  },
  status: {
    display: "flex",
    alignItems: "center",
    gap: "4px",
    color: tokens.colorNeutralForeground3,
    whiteSpace: "nowrap",
  },
  dot: {
    width: "7px",
    height: "7px",
    borderRadius: "50%",
  },
  buttons: {
    display: "flex",
    gap: "8px",
  },
});

export function DesktopBar({
  onDownload,
}: {
  onDownload: (format: "video" | "audio") => Promise<void>;
}) {
  const styles = useStyles();
  const [isRunning, setRunning] = useState<boolean | null>(null);
  const [busy, setBusy] = useState<"video" | "audio" | null>(null);

  useEffect(() => {
    let cancelled = false;
    const check = () => {
      fetch(DESKTOP_PING_URL, { signal: AbortSignal.timeout(1500) })
        .then((r) => r.json())
        .then((body) => { if (!cancelled) { setRunning(body?.app === "download-kar-desktop"); } })
        .catch(() => { if (!cancelled) { setRunning(false); } });
    };
    check();
    const timer = window.setInterval(check, 4000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, []);

  const run = async (format: "video" | "audio") => {
    setBusy(format);
    try {
      await onDownload(format);
    } finally {
      setBusy(null);
    }
  };

  return (
    <Card appearance="filled-alternative" className={styles.card}>
      <div className={styles.top}>
        <Caption1 className={styles.title}>{chrome.i18n.getMessage("dkDesktopBarTitle")}</Caption1>
        <Caption1 className={styles.status}>
          <span
            className={styles.dot}
            style={{ backgroundColor: isRunning ? tokens.colorPaletteGreenForeground1 : tokens.colorNeutralForeground4 }}
          />
          {isRunning === null ? "" : chrome.i18n.getMessage(isRunning ? "dkDesktopRunning" : "dkDesktopOff")}
        </Caption1>
      </div>
      <div className={styles.buttons}>
        <Button
          size="small"
          appearance="primary"
          icon={<ArrowDownloadRegular />}
          disabled={busy !== null}
          onClick={() => void run("video")}
        >
          {chrome.i18n.getMessage("dkDesktopVideo")}
        </Button>
        <Button
          size="small"
          icon={<MusicNote2Regular />}
          disabled={busy !== null}
          onClick={() => void run("audio")}
        >
          {chrome.i18n.getMessage("dkDesktopAudio")}
        </Button>
      </div>
      <Caption1 className={styles.status}>{chrome.i18n.getMessage("dkDesktopBarHint")}</Caption1>
    </Card>
  );
}
