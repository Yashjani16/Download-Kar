import {
    Body1Strong,
    Button,
    Card,
    Field,
    Input,
    makeStyles,
    MessageBar,
    MessageBarBody,
    Select,
    SpinButton,
    Switch,
    Tag,
    TagGroup,
} from "@fluentui/react-components";
import type {SpinButtonOnChangeData, SwitchOnChangeData} from "@fluentui/react-components";
import {AddRegular, ArrowClockwiseRegular, ClipboardPasteRegular, PlugConnectedRegular,} from "@fluentui/react-icons";
import {useCallback, useEffect, useRef, useState} from "react";

import {DEFAULT_SERVER_URL, EXTENSION_VERSION} from "../../shared/constants";
import {
    BYPASS_SHORTCUT_KEY,
    MIN_TAKE_SIZE_KB_KEY,
    SHOULD_AUTO_SELECT_PORT_KEY,
    SKIP_EXTENSIONS_KEY,
    SKIP_DOMAINS_KEY,
    SHOULD_OPEN_POPUP_ON_SENT_KEY,
    SHOULD_TAKE_UNKNOWN_SIZE_KEY,
} from "../../background/constants";
import {MEDIA_BUTTON_STYLE_KEY, type MediaButtonStyle, type ThemePreference} from "../../shared/types";
import {
  type BypassShortcut,
  DEFAULT_BYPASS_SHORTCUT,
  parseBypassShortcut,
  toBypassShortcut,
  toShortcutLabel,
} from "../../shared/bypass-shortcut";

const SKIP_CATEGORIES = [
  { key: "catImages", extensions: ["jpg", "jpeg", "png", "gif", "webp", "svg", "avif", "bmp", "ico"] },
  { key: "catDocuments", extensions: ["pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "txt"] },
  { key: "catAudio", extensions: ["mp3", "flac", "wav", "aac", "ogg", "m4a", "wma"] },
];

function parseExtSet(raw: string): Set<string> {
  const result = new Set<string>();
  for (const part of raw.split(",")) {
    const ext = part.trim().replace(/^\./, "").toLowerCase();
    if (ext) { result.add(ext); }
  }
  return result;
}

const useStyles = makeStyles({
  root: {
    display: "flex",
    flexDirection: "column",
    gap: "16px",
    padding: "16px",
  },
  card: {
    gap: "16px",
    padding: "16px",
  },
  header: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: "12px",
  },
  inputRow: {
    display: "flex",
    alignItems: "center",
    gap: "8px",
  },
  input: {
    flex: 1,
  },
});

export function SettingsPage({
  desktopVersion,
  token,
  serverUrl,
  savingToken,
  savingServerUrl,
  refreshingConnection,
  requestingPairing,
  onSaveToken,
  onSaveServerUrl,
  onRefreshConnection,
  onRequestPairing,
  themePreference,
  onThemePreferenceChange,
  activePageDomain,
}: {
  desktopVersion: string;
  token: string;
  serverUrl: string;
  savingToken?: boolean;
  savingServerUrl?: boolean;
  refreshingConnection?: boolean;
  requestingPairing?: boolean;
  onSaveToken: (value: string) => Promise<boolean>;
  onSaveServerUrl: (value: string) => Promise<boolean>;
  onRefreshConnection: () => Promise<boolean>;
  onRequestPairing: () => Promise<boolean>;
  themePreference: ThemePreference;
  onThemePreferenceChange: (nextPreference: ThemePreference) => void;
  activePageDomain: string;
}) {
  const styles = useStyles();
  const [tokenDraft, setTokenDraft] = useState(token);
  const [serverUrlDraft, setServerUrlDraft] = useState(serverUrl || DEFAULT_SERVER_URL);
  const [tokenDirty, setTokenDirty] = useState(false);
  const [serverDirty, setServerDirty] = useState(false);
  const [shouldAutoSelectPort, setShouldAutoSelectPort] = useState(true);
  const [minSizeKB, setMinSizeKB] = useState(0);
  const [takeUnknownSize, setInterceptUnknown] = useState(true);
  const [skipExtensionsRaw, setSkipExtensionsRaw] = useState("");
  const [skipDomains, setSkipDomains] = useState<string[]>([]);
  const [openPopupOnSent, setOpenPopupOnSent] = useState(true);
  const [mediaButtonStyle, setMediaButtonStyle] = useState<MediaButtonStyle>("standard");
  const [bypassShortcut, setBypassShortcut] = useState<BypassShortcut>(DEFAULT_BYPASS_SHORTCUT);
  const [isRecording, setIsRecording] = useState(false);
  const [recordingDraft, setRecordingDraft] = useState<BypassShortcut | null>(null);
  const recorderRef = useRef<HTMLButtonElement>(null);

  const saveShortcut = useCallback((next: BypassShortcut) => {
    setBypassShortcut(next);
    setRecordingDraft(null);
    setIsRecording(false);
    void chrome.storage.local.set({ [BYPASS_SHORTCUT_KEY]: next });
  }, []);
  const [installType, setInstallType] = useState("");

  const installLabel = useCallback(() => {
    switch (installType) {
      case "development": return chrome.i18n.getMessage("installTypeDevelopment");
      case "admin": case "normal": return chrome.i18n.getMessage("installTypeStore");
      case "sideload": return chrome.i18n.getMessage("installTypeSideload");
      default: return installType || chrome.i18n.getMessage("installTypeUnknown");
    }
  }, [installType]);

  useEffect(() => {
    chrome.management.getSelf((info) => setInstallType(info.installType));
  }, []);

  useEffect(() => {
    chrome.storage.local.get({
      [SHOULD_AUTO_SELECT_PORT_KEY]: true,
      [MIN_TAKE_SIZE_KB_KEY]: 0,
      [SHOULD_TAKE_UNKNOWN_SIZE_KEY]: true,
      [SKIP_EXTENSIONS_KEY]: "",
      [SKIP_DOMAINS_KEY]: [],
      [SHOULD_OPEN_POPUP_ON_SENT_KEY]: true,
      [BYPASS_SHORTCUT_KEY]: null,
      [MEDIA_BUTTON_STYLE_KEY]: "standard",
    }, (result) => {
      setShouldAutoSelectPort(Boolean(result[SHOULD_AUTO_SELECT_PORT_KEY] ?? true));
      setMinSizeKB(Number(result[MIN_TAKE_SIZE_KB_KEY]) || 0);
      setInterceptUnknown(Boolean(result[SHOULD_TAKE_UNKNOWN_SIZE_KEY] ?? true));
      setSkipExtensionsRaw(String(result[SKIP_EXTENSIONS_KEY] ?? ""));
      setSkipDomains(Array.isArray(result[SKIP_DOMAINS_KEY]) ? result[SKIP_DOMAINS_KEY] : []);
      setOpenPopupOnSent(Boolean(result[SHOULD_OPEN_POPUP_ON_SENT_KEY] ?? true));
      setBypassShortcut(parseBypassShortcut(result[BYPASS_SHORTCUT_KEY]));
      setMediaButtonStyle(result[MEDIA_BUTTON_STYLE_KEY] as MediaButtonStyle);
    });
  }, []);

  useEffect(() => {
    if (!tokenDirty) {
      setTokenDraft(token);
    }
  }, [token, tokenDirty]);

  useEffect(() => {
    if (!serverDirty) {
      setServerUrlDraft(serverUrl || DEFAULT_SERVER_URL);
    }
  }, [serverDirty, serverUrl]);

  async function commitServerUrl() {
    const nextServerUrl = serverUrlDraft.trim() || DEFAULT_SERVER_URL;
    if (savingServerUrl || nextServerUrl === (serverUrl || DEFAULT_SERVER_URL)) {
      setServerDirty(false);
      return;
    }
    const ok = await onSaveServerUrl(nextServerUrl);
    if (ok) {
      setServerDirty(false);
    }
  }

  async function commitToken() {
    const nextToken = tokenDraft.trim();
    if (savingToken || nextToken === token) {
      setTokenDirty(false);
      return;
    }
    const ok = await onSaveToken(nextToken);
    if (ok) {
      setTokenDirty(false);
    }
  }

  async function pasteToken() {
    try {
      const text = await navigator.clipboard.readText();
      if (text) {
        const nextToken = text.trim();
        setTokenDraft(nextToken);
        setTokenDirty(true);
        const ok = await onSaveToken(nextToken);
        if (ok) {
          setTokenDirty(false);
        }
      }
    } catch {
      // Ignore clipboard permission failures.
    }
  }

  return (
    <div className={styles.root}>

      <Card appearance="filled-alternative" className={styles.card}>
        <Body1Strong>{chrome.i18n.getMessage("general")}</Body1Strong>


        <Field label={chrome.i18n.getMessage("openPopupOnSent")}>
          <Switch
            checked={openPopupOnSent}
            onChange={(_event, data: SwitchOnChangeData) => {
              setOpenPopupOnSent(data.checked);
              void chrome.storage.local.set({ [SHOULD_OPEN_POPUP_ON_SENT_KEY]: data.checked });
            }}
          />
        </Field>




        <Field label={chrome.i18n.getMessage("mediaButtonStyle")} hint={chrome.i18n.getMessage("mediaButtonStyleHint")}>
          <Select
            value={mediaButtonStyle}
            onChange={(event) => {
              const next = event.currentTarget.value as MediaButtonStyle;
              setMediaButtonStyle(next);
              void chrome.storage.local.set({ [MEDIA_BUTTON_STYLE_KEY]: next });
            }}
          >
            <option value="standard">{chrome.i18n.getMessage("mediaButtonStyleStandard")}</option>
            <option value="compact">{chrome.i18n.getMessage("mediaButtonStyleCompact")}</option>
          </Select>
        </Field>

        <Field label={chrome.i18n.getMessage("theme")}>
          <Select
            value={themePreference}
            onChange={(_event) => onThemePreferenceChange(_event.currentTarget.value as ThemePreference)}
          >
            <option value="system">{chrome.i18n.getMessage("followSystem")}</option>
            <option value="light">{chrome.i18n.getMessage("lightTheme")}</option>
            <option value="dark">{chrome.i18n.getMessage("darkTheme")}</option>
          </Select>
        </Field>
      </Card>

      <Card appearance="filled-alternative" className={styles.card}>
        <Body1Strong>{chrome.i18n.getMessage("about")}</Body1Strong>
        <MessageBar intent="info">
          <MessageBarBody>{chrome.i18n.getMessage("extensionVersionInfo", [EXTENSION_VERSION])}</MessageBarBody>
        </MessageBar>
        <MessageBar intent="info">
          <MessageBarBody>{chrome.i18n.getMessage("installMethodInfo", [installLabel()])}</MessageBarBody>
        </MessageBar>
        <MessageBar intent="success">
          <MessageBarBody>{chrome.i18n.getMessage("dkCredits")}</MessageBarBody>
        </MessageBar>
      </Card>
    </div>
  );
}
