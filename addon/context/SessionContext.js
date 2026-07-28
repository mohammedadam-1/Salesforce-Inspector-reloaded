/* ──────────────────────────────────────────────
   SessionContext — Salesforce Session Manager
   ──────────────────────────────────────────────
   Reads Salesforce session from the page (localStorage/cookies).
   No auth flow. No token exchange. Passive extraction only.
   ────────────────────────────────────────────── */

const ORG_ID_KEY = "orgId";
const USER_ID_KEY = "userId";

export class SessionContext {
  constructor() {
    this.sessionId = null;
    this.orgId = null;
    this.userId = null;
    this.username = null;
    this._initialized = false;
  }

  async init(sfHost) {
    if (this._initialized) return;
    try {
      this.sessionId = await this._getSessionId(sfHost);
      this.orgId = await this._getOrgId(sfHost);
      this.userId = await this._getUserId(sfHost);
    } catch (e) {
      console.warn("SessionContext.init failed:", e);
    }
    this._initialized = true;
  }

  get isAuthenticated() {
    return !!this.sessionId;
  }

  async _getSessionId(sfHost) {
    return new Promise((resolve) => {
      if (typeof chrome !== "undefined" && chrome.cookies) {
        const cookieNames = ["sid", "sid_Login"];
        let found = null;
        let pending = cookieNames.length;
        for (const name of cookieNames) {
          chrome.cookies.get({ url: `https://${sfHost}`, name }, (cookie) => {
            if (cookie?.value) found = cookie.value;
            pending--;
            if (pending === 0) resolve(found);
          });
        }
        if (pending === 0) resolve(null);
      } else {
        const val = localStorage.getItem(sfHost + "_sid");
        resolve(val || null);
      }
    });
  }

  async _getOrgId(sfHost) {
    return localStorage.getItem(sfHost + "_" + ORG_ID_KEY) || null;
  }

  async _getUserId(sfHost) {
    return localStorage.getItem(sfHost + "_" + USER_ID_KEY) || null;
  }
}

export const sessionContext = new SessionContext();
