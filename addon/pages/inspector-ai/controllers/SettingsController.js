

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
    return raw ? Object.assign({}, DEFAULT_SETTINGS, JSON.parse(raw)) : Object.assign({}, DEFAULT_SETTINGS);
  } catch {
    return Object.assign({}, DEFAULT_SETTINGS);
  }
}

function saveSettings(settings) {
  try {
    localStorage.setItem(WORKSPACE_SETTINGS_KEY, JSON.stringify(settings));
  } catch { /* ignore */ }
}

const SettingsController = {
  _settings: null,

  get settings() {
    if (!this._settings) this._settings = loadSettings();
    return this._settings;
  },

  updateSettings(updates) {
    this._settings = Object.assign({}, this.settings, updates);
    saveSettings(this._settings);
  },

  resetSettings() {
    this._settings = Object.assign({}, DEFAULT_SETTINGS);
    saveSettings(this._settings);
  },

  get showTimeline() { return this.settings.showTimeline; },
  get showSuggestions() { return this.settings.showSuggestions; },
  get autoAnalyzeContext() { return this.settings.autoAnalyzeContext; },
  get maxHistoryItems() { return this.settings.maxHistoryItems; },
};

export default SettingsController;
