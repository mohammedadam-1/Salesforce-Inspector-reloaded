/* global chrome */

const BK = {
  URL: "sfirBackendUrl",
  KEY: "sfirBackendApiKey",
  ORG: "sfirBackendOrgId",
};

function getBackendConfig() {
  const url = localStorage.getItem(BK.URL);
  const apiKey = localStorage.getItem(BK.KEY);
  const organizationId = localStorage.getItem(BK.ORG);
  if (!url || !apiKey) return null;
  return {url, apiKey, organizationId};
}

export function isBackendConfigured() {
  return !!getBackendConfig();
}

function getConfig() {
  const config = getBackendConfig();
  if (!config) throw new Error("Backend not configured. Configure it in Options > Backend.");
  return config;
}

function buildUrl(baseUrl, path, queryParams) {
  const cleanBase = baseUrl.replace(/\/+$/, "");
  let url = `${cleanBase}${path}`;
  if (queryParams) {
    const sp = new URLSearchParams();
    for (const [k, v] of Object.entries(queryParams)) {
      if (v !== undefined && v !== null) {
        if (Array.isArray(v)) v.forEach(x => sp.append(k, x));
        else sp.set(k, v);
      }
    }
    const qs = sp.toString();
    if (qs) url += `?${qs}`;
  }
  return url;
}

function buildHeaders(config, hasBody) {
  const hdrs = {"X-API-Key": config.apiKey, "Accept": "application/json"};
  if (config.organizationId) hdrs["X-Organization-ID"] = config.organizationId;
  if (hasBody) hdrs["Content-Type"] = "application/json";
  return hdrs;
}

async function backendRequest(method, path, queryParams, body) {
  const config = getConfig();
  const url = buildUrl(config.url, path, queryParams);
  const headers = buildHeaders(config, !!body);
  const rawBody = body ? JSON.stringify(body) : undefined;

  console.debug("[Backend] Request:", method, url, "Headers:", JSON.stringify(headers));

  try {
    const response = await fetch(url, {method, headers, body: rawBody});
    console.debug("[Backend] Response status:", response.status);

    if (!response.ok) {
      let msg = `Backend request failed (${response.status})`;
      try {
        const errData = await response.json();
        console.debug("[Backend] Error body:", JSON.stringify(errData));
        if (errData?.detail) msg = errData.detail;
        else if (errData?.error?.message) msg = errData.error.message;
      } catch (e) {
        try { msg = await response.text(); } catch (e2) {}
      }
      throw new Error(msg);
    }

    return response.json();
  } catch (e) {
    console.error("[Backend] Fetch failed:", e);
    throw e;
  }
}

export async function searchMetadata(organizationId, query, componentType, limit, offset) {
  return backendRequest("GET", "/api/v1/metadata", {
    organization_id: organizationId,
    search: query,
    component_type: componentType,
    limit,
    offset,
  });
}

export async function getMetadataComponent(componentId) {
  return backendRequest("GET", `/api/v1/metadata/${componentId}`);
}

export async function getMetadataTypes(organizationId) {
  return backendRequest("GET", "/api/v1/metadata/types", {organization_id: organizationId});
}

export async function getUpstreamDependencies(organizationId, componentKey, maxDepth) {
  return backendRequest("GET", "/api/v1/dependencies/upstream", {
    organization_id: organizationId,
    component_key: componentKey,
    max_depth: maxDepth || 5,
  });
}

export async function getDownstreamDependencies(organizationId, componentKey, maxDepth) {
  return backendRequest("GET", "/api/v1/dependencies/downstream", {
    organization_id: organizationId,
    component_key: componentKey,
    max_depth: maxDepth || 5,
  });
}

export async function analyzeChangeImpact(organizationId, componentKey, changeDescription, maxDepth) {
  return backendRequest("POST", "/api/v1/dependencies/analyze", {
    organization_id: organizationId,
    component_key: componentKey,
    change_description: changeDescription || "Modified component",
    max_depth: maxDepth || 10,
  });
}

export async function findDependencyPath(organizationId, source, target) {
  return backendRequest("GET", "/api/v1/dependencies/path", {
    organization_id: organizationId,
    source,
    target,
  });
}

export async function findSharedDependencies(organizationId, componentKeys) {
  return backendRequest("POST", "/api/v1/dependencies/shared", {
    organization_id: organizationId,
    component_keys: componentKeys,
  });
}

export async function aiChat(organizationId, query, componentIds, conversationId) {
  return backendRequest("POST", "/api/v1/ai/chat", {
    organization_id: organizationId,
    query,
    ...(componentIds?.length ? {component_ids: componentIds} : {}),
    ...(conversationId ? {conversation_id: conversationId} : {}),
  });
}

export async function aiAnalyze(organizationId, query, componentId) {
  return backendRequest("POST", "/api/v1/ai/analyze", {
    organization_id: organizationId,
    query,
    ...(componentId ? {component_id: componentId} : {}),
  });
}

export async function generateDocumentation(organizationId, componentIds) {
  return backendRequest("POST", "/api/v1/ai/document", {
    organization_id: organizationId,
    ...(componentIds?.length ? {component_ids: componentIds} : {}),
  });
}

export async function getUnusedComponents(organizationId, componentType) {
  return backendRequest("GET", "/api/v1/metadata/analysis/unused", {
    organization_id: organizationId,
    ...(componentType ? {component_type: componentType} : {}),
  });
}

export async function getDuplicateComponents(organizationId, componentType) {
  return backendRequest("GET", "/api/v1/metadata/analysis/duplicates", {
    organization_id: organizationId,
    ...(componentType ? {component_type: componentType} : {}),
  });
}

export async function listConversations(organizationId, limit) {
  return backendRequest("GET", "/api/v1/ai/conversations", {
    organization_id: organizationId,
    limit: limit || 20,
  });
}

export async function getConversation(conversationId) {
  return backendRequest("GET", `/api/v1/ai/conversations/${conversationId}`);
}

export async function triggerMetadataSync(organizationId) {
  return backendRequest("POST", "/api/v1/metadata/sync", {
    organization_id: organizationId,
    sync_type: "full",
  });
}
