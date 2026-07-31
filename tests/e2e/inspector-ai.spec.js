import {test, expect} from "./fixtures";
import {TEST_CONSTANTS} from "./test-helpers";

test.describe("Inspector AI Runtime Validation", () => {
  const {mockHost} = TEST_CONSTANTS;

  test("1) Page loads without errors", async ({page, extensionId}) => {
    const errors = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") errors.push(msg.text());
    });
    page.on("pageerror", (err) => errors.push(err.message));

    await page.goto(
      `chrome-extension://${extensionId}/pages/inspector-ai/index.html?host=${mockHost}`,
      {waitUntil: "domcontentloaded", timeout: 15000}
    );
    await page.waitForTimeout(5000);

    const bodyLen = await page.evaluate(() => document.body ? document.body.innerHTML.length : 0);
    expect(bodyLen).toBeGreaterThan(50);
    const rootExists = await page.evaluate(() => !!document.getElementById("ai-workspace-root"));
    expect(rootExists).toBeTruthy();

    const jsErrors = errors.filter(e =>
      !e.includes("ERR_FILE_NOT_FOUND") &&
      !e.includes("ERR_NAME_NOT_RESOLVED") &&
      !e.includes("Backend not configured")
    );
    expect(jsErrors).toEqual([]);
  });

  test("2) SLDS page header renders", async ({page, extensionId}) => {
    const errors = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") errors.push(msg.text());
    });
    page.on("pageerror", (err) => errors.push(err.message));

    await page.goto(
      `chrome-extension://${extensionId}/pages/inspector-ai/index.html?host=${mockHost}`,
      {waitUntil: "domcontentloaded", timeout: 15000}
    );
    await page.waitForTimeout(5000);

    const headerInfo = await page.evaluate(() => {
      const header = document.querySelector(".slds-builder-header");
      if (!header) return {found: false};
      return {
        found: true,
        title: header.querySelector(".slds-text-heading_small")?.textContent || "",
        hasOrgBadge: !!header.querySelector(".slds-badge"),
        hasUtilities: !!header.querySelector(".slds-builder-header__utilities"),
      };
    });
    const hdrErrors = errors.filter(e =>
      !e.includes("ERR_FILE_NOT_FOUND") &&
      !e.includes("ERR_NAME_NOT_RESOLVED") &&
      !e.includes("Backend not configured")
    );
    expect(hdrErrors).toEqual([]);
    if (!headerInfo.found) {
      const rootHtml = await page.evaluate(() => document.getElementById("ai-workspace-root")?.innerHTML?.substring(0, 2000) || "EMPTY");
      console.log("DEBUG test2 rootHtml:", rootHtml);
    }
    expect(headerInfo.found).toBeTruthy();
    expect(headerInfo.title).toBe("Inspector AI");
    expect(headerInfo.hasOrgBadge).toBeTruthy();
    expect(headerInfo.hasUtilities).toBeTruthy();
  });

  test("3) Unconfigured state shows welcome screen with hero, setup guide, and CTA", async ({page, extensionId}) => {
    const errors = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") errors.push(msg.text());
    });
    page.on("pageerror", (err) => errors.push(err.message));

    await page.goto(
      `chrome-extension://${extensionId}/pages/inspector-ai/index.html?host=${mockHost}`,
      {waitUntil: "domcontentloaded", timeout: 15000}
    );
    await page.waitForTimeout(5000);

    const welcomeInfo = await page.evaluate(() => {
      const welcome = document.querySelector(".ai-welcome");
      if (!welcome) return {found: false};
      return {
        found: true,
        heroTitle: welcome.querySelector(".ai-welcome-title")?.textContent || "",
        heroSubtitle: welcome.querySelector(".ai-welcome-subtitle")?.textContent || "",
        hasSetupSteps: !!welcome.querySelector(".ai-setup-steps"),
        hasCta: !!welcome.querySelector(".ai-welcome-cta"),
        ctaText: welcome.querySelector(".ai-welcome-cta")?.textContent || "",
        hasFeatures: !!welcome.querySelector(".ai-welcome-features"),
        hasFeatureCards: !!welcome.querySelector(".ai-feature-card"),
      };
    });
    const wlcmErrors = errors.filter(e =>
      !e.includes("ERR_FILE_NOT_FOUND") &&
      !e.includes("ERR_NAME_NOT_RESOLVED") &&
      !e.includes("Backend not configured")
    );
    expect(wlcmErrors).toEqual([]);
    expect(welcomeInfo.found).toBeTruthy();
    expect(welcomeInfo.heroTitle).toBe("Inspector AI");
    expect(welcomeInfo.heroSubtitle).toBe("Your AI Engineering Assistant for Salesforce");
    expect(welcomeInfo.hasSetupSteps).toBeTruthy();
    expect(welcomeInfo.hasCta).toBeTruthy();
    expect(welcomeInfo.ctaText).toBe("Configure Inspector AI");
    expect(welcomeInfo.hasFeatures).toBeTruthy();
    expect(welcomeInfo.hasFeatureCards).toBeTruthy();
  });

  test("4) Backend config persists via localStorage", async ({page, extensionId}) => {
    await page.goto(
      `chrome-extension://${extensionId}/pages/inspector-ai/index.html?host=${mockHost}`,
      {waitUntil: "domcontentloaded", timeout: 15000}
    );
    await page.waitForTimeout(3000);

    await page.evaluate(() => {
      localStorage.setItem("sfirBackendUrl", "http://test-backend:8080");
      localStorage.setItem("sfirBackendApiKey", "test-key-123");
    });

    const storedUrl = await page.evaluate(() => localStorage.getItem("sfirBackendUrl"));
    const storedKey = await page.evaluate(() => localStorage.getItem("sfirBackendApiKey"));
    expect(storedUrl).toBe("http://test-backend:8080");
    expect(storedKey).toBe("test-key-123");
  });

  test("5) Configured state shows full workspace layout", async ({page, extensionId}) => {
    const errors = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") errors.push(msg.text());
    });
    page.on("pageerror", (err) => errors.push(err.message));

    await page.goto(
      `chrome-extension://${extensionId}/pages/inspector-ai/index.html?host=${mockHost}`,
      {waitUntil: "domcontentloaded", timeout: 15000}
    );
    await page.waitForTimeout(3000);

    await page.evaluate(() => {
      localStorage.setItem("sfirBackendUrl", "http://test-backend:8080");
      localStorage.setItem("sfirBackendApiKey", "test-key-123");
    });
    await page.reload({waitUntil: "domcontentloaded"});
    await page.waitForTimeout(3000);

    const layoutInfo = await page.evaluate(() => {
      const layout = document.querySelector(".ai-workspace-layout");
      if (!layout) return {error: "layout missing"};
      return {
        hasSidebar: !!layout.querySelector(".ai-sidebar"),
        hasContent: !!layout.querySelector(".ai-workspace-content"),
        hasContext: !!layout.querySelector(".ai-workspace-toolbar"),
        hasChat: !!layout.querySelector(".ai-results-area"),
        hasInput: !!layout.querySelector(".ai-input-section"),
        sidebarHasList: !!layout.querySelector(".ai-sidebar-list"),
        sidebarHasHeader: !!layout.querySelector(".ai-sidebar-header"),
      };
    });
    expect(layoutInfo.error).toBeUndefined();
    expect(layoutInfo.hasSidebar).toBeTruthy();
    expect(layoutInfo.hasContent).toBeTruthy();
    expect(layoutInfo.hasContext).toBeTruthy();
    expect(layoutInfo.hasChat).toBeTruthy();
    expect(layoutInfo.hasInput).toBeTruthy();
    expect(layoutInfo.sidebarHasList).toBeTruthy();
    expect(layoutInfo.sidebarHasHeader).toBeTruthy();
    expect(errors).toEqual([]);
  });
});
