/* ──────────────────────────────────────────────
   OrgContext — Org State Manager
   ──────────────────────────────────────────────
   Manages org connection state, caching, and switching.
   Uses chrome.storage.session for ephemeral data.
   ────────────────────────────────────────────── */

const STORAGE_KEY = "ai_org_context";

export class OrgContext {
  constructor() {
    this._orgs = [];
    this._activeOrgId = null;
    this._listeners = new Set();
    this._loaded = false;
  }

  async init() {
    try {
      const data = await this._getStorage();
      if (data) {
        this._orgs = data.orgs || [];
        this._activeOrgId = data.activeOrgId || null;
      }
    } catch (e) {
      console.warn("OrgContext.init failed:", e);
    }
    this._loaded = true;
    this._notify();
  }

  get orgs() {
    return this._orgs;
  }

  get activeOrg() {
    return this._orgs.find((o) => o.id === this._activeOrgId) || this._orgs[0] || null;
  }

  get isConnected() {
    return this.activeOrg?.status === "connected";
  }

  get apiVersion() {
    return this.activeOrg?.apiVersion || "62.0";
  }

  async addOrg(org) {
    const existing = this._orgs.findIndex((o) => o.id === org.id);
    if (existing >= 0) {
      this._orgs[existing] = { ...this._orgs[existing], ...org };
    } else {
      this._orgs.push(org);
    }
    await this._persist();
    this._notify();
  }

  async removeOrg(orgId) {
    this._orgs = this._orgs.filter((o) => o.id !== orgId);
    if (this._activeOrgId === orgId) {
      this._activeOrgId = this._orgs[0]?.id || null;
    }
    await this._persist();
    this._notify();
  }

  async setActiveOrg(orgId) {
    this._activeOrgId = orgId;
    await this._persist();
    this._notify();
  }

  async updateOrgStatus(orgId, status) {
    const org = this._orgs.find((o) => o.id === orgId);
    if (org) {
      org.status = status;
      await this._persist();
      this._notify();
    }
  }

  onChange(fn) {
    this._listeners.add(fn);
    return () => this._listeners.delete(fn);
  }

  _notify() {
    for (const fn of this._listeners) {
      try { fn(this); } catch (e) { console.warn("OrgContext listener error:", e); }
    }
  }

  async _getStorage() {
    return new Promise((resolve) => {
      if (typeof chrome !== "undefined" && chrome.storage?.session) {
        chrome.storage.session.get(STORAGE_KEY, (result) => {
          resolve(result[STORAGE_KEY] || null);
        });
      } else {
        const raw = sessionStorage.getItem(STORAGE_KEY);
        resolve(raw ? JSON.parse(raw) : null);
      }
    });
  }

  async _persist() {
    const data = { orgs: this._orgs, activeOrgId: this._activeOrgId };
    return new Promise((resolve) => {
      if (typeof chrome !== "undefined" && chrome.storage?.session) {
        chrome.storage.session.set({ [STORAGE_KEY]: data }, resolve);
      } else {
        try { sessionStorage.setItem(STORAGE_KEY, JSON.stringify(data)); } catch (e) { /* ignore */ }
        resolve();
      }
    });
  }
}

export const orgContext = new OrgContext();
