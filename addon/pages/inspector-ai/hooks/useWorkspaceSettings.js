/* global React */

const WORKSPACE_SETTINGS_KEY = "inspector-ai-settings";
const DEFAULT_SETTINGS = {
  autoAnalyzeContext: true,
  showTimeline: true,
  showSuggestions: true,
  maxHistoryItems: 50,
  theme: "auto",
  fontSize: "medium",
};

function loadSettings() {
  try {
    const raw = localStorage.getItem(WORKSPACE_SETTINGS_KEY);
    return raw ? {...DEFAULT_SETTINGS, ...JSON.parse(raw)} : {...DEFAULT_SETTINGS};
  } catch { return {...DEFAULT_SETTINGS}; }
}

function saveSettings(settings) {
  try {
    localStorage.setItem(WORKSPACE_SETTINGS_KEY, JSON.stringify(settings));
  } catch { /* ignore */ }
}

export default function useWorkspaceSettings() {
  const [settings, setSettingsState] = React.useState(loadSettings);

  const updateSettings = React.useCallback((updates) => {
    setSettingsState((prev) => {
      const next = {...prev, ...updates};
      saveSettings(next);
      return next;
    });
  }, []);

  const resetSettings = React.useCallback(() => {
    saveSettings(DEFAULT_SETTINGS);
    setSettingsState({...DEFAULT_SETTINGS});
  }, []);

  return {
    settings,
    updateSettings,
    resetSettings,
    autoAnalyzeContext: settings.autoAnalyzeContext,
    showTimeline: settings.showTimeline,
    showSuggestions: settings.showSuggestions,
    maxHistoryItems: settings.maxHistoryItems,
    theme: settings.theme,
    fontSize: settings.fontSize,
  };
}
