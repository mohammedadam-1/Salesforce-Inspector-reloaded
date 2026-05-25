(() => {
  const bootLoading = document.getElementById("bootLoading");

  function showBootError(message) {
    if (!bootLoading) return;
    bootLoading.innerHTML = `<div style="color:#c23934;font-weight:600">${message}</div>`;
  }

  function loadStyle(href) {
    return new Promise((resolve, reject) => {
      const link = document.createElement("link");
      link.rel = "stylesheet";
      link.href = href;
      link.onload = resolve;
      link.onerror = reject;
      document.head.appendChild(link);
    });
  }

  function loadScript(src, isModule = false) {
    return new Promise((resolve, reject) => {
      const script = document.createElement("script");
      if (isModule) {
        script.type = "module";
      }
      script.src = src;
      script.onload = resolve;
      script.onerror = reject;
      document.body.appendChild(script);
    });
  }

  Promise.all([
    loadStyle("styles/slds/slds.css"),
    loadStyle("styles/sfir.css"),
    loadStyle("button.css"),
    loadStyle("schema-explorer.css"),
  ])
    .then(() => loadScript("react.js"))
    .then(() => loadScript("react-dom.js"))
    .then(() => loadScript("button.js"))
    .then(() => loadScript("schema-explorer-page.js", true))
    .catch((error) => {
      console.error("Schema Explorer bootstrap failed:", error);
      showBootError("Unable to load Schema Explorer assets.");
    });
})();
