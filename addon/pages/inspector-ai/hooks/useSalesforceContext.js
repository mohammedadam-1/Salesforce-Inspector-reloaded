/* global React */

function getHostFromUrl() {
  const params = new URLSearchParams(location.search.slice(1));
  return params.get("host");
}

function buildContext(host) {
  if (!host) return null;
  return {
    orgId: null,
    userId: null,
    orgName: host?.split(".")?.[0]?.toUpperCase() || host,
    username: null,
    apiVersion: null,
    recordId: null,
    objectType: null,
    selectedText: null,
    pageUrl: null,
    sfHost: host,
  };
}

export default function useSalesforceContext() {
  const [context, setContext] = React.useState(() => buildContext(getHostFromUrl()));
  const [isLoading, setIsLoading] = React.useState(false);
  const [error, setError] = React.useState(null);

  const refresh = React.useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const host = getHostFromUrl();
      const ctx = buildContext(host);
      setContext(ctx);
      return ctx;
    } catch (err) {
      setError(err.message || "Failed to get context");
      return null;
    } finally {
      setIsLoading(false);
    }
  }, []);

  React.useEffect(() => {
    if (typeof chrome !== "undefined" && chrome.runtime?.onMessage) {
      const handler = (msg) => {
        if (msg.type === "ai_context_update") {
          setContext((prev) => ({...prev, ...msg.context}));
        }
      };
      chrome.runtime.onMessage.addListener(handler);
      return () => chrome.runtime.onMessage.removeListener(handler);
    }
    return undefined;
  }, []);

  return {
    context,
    isLoading,
    error,
    refresh,
    orgId: context?.orgId,
    userId: context?.userId,
    orgName: context?.orgName,
    username: context?.username,
    apiVersion: context?.apiVersion,
    recordId: context?.recordId,
    objectType: context?.objectType,
    selectedText: context?.selectedText,
    pageUrl: context?.pageUrl,
    sfHost: context?.sfHost,
  };
}
