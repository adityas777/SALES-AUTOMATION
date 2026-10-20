const envApiUrl = import.meta.env.VITE_API_BASE_URL || import.meta.env.VITE_API_URL;

function resolveApiBase() {
  if (envApiUrl) {
    const trimmed = envApiUrl.trim().replace(/\/+$/, "");
    return trimmed.endsWith("/api") ? trimmed : `${trimmed}/api`;
  }
  const hostname =
    typeof window !== "undefined" && window.location.hostname
      ? window.location.hostname
      : "localhost";
  return `http://${hostname}:8000/api`;
}

export const API_BASE = resolveApiBase();

async function request(path, options = {}) {
  const isFormData = options.body instanceof FormData;
  const headers = isFormData
    ? { ...(options.headers || {}) }
    : { "Content-Type": "application/json", ...(options.headers || {}) };

  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText}: ${body}`);
  }
  return res.json();
}

export const api = {
  getCategories: () => request("/categories"),
  getLocations: () => request("/locations"),
  runCollection: (city, categories) =>
    request("/run-collection", {
      method: "POST",
      body: JSON.stringify({ city, categories }),
    }),
  getRunStatus: (runId) => request(`/run-status/${runId}`),
  getRunFeed: (runId) => request(`/run-status/${runId}/feed`),
  stopRun: (runId) => request(`/run-collection/${runId}/stop`, { method: "POST" }),
  getActiveRuns: () => request("/active-runs"),
  getStats: () => request("/stats"),
  getHandoffQueue: () => request("/handoff-queue"),
  resolveHandoff: (businessId) =>
    request(`/handoff-queue/${businessId}/resolve`, { method: "POST" }),

  // Voice Agent APIs
  getVoiceStatus: () => request("/voice/status"),
  processVoiceAudio: (
    audioBlob,
    languageCode = "en-IN",
    currentState = "IDLE",
    currentCity = "",
    currentCategories = []
  ) => {
    const formData = new FormData();
    formData.append("audio_file", audioBlob, "recording.wav");
    formData.append("language_code", languageCode);
    formData.append("current_state", currentState);
    formData.append("current_city", currentCity);
    formData.append("current_categories", JSON.stringify(currentCategories));
    return request("/voice/process-audio", {
      method: "POST",
      body: formData,
    });
  },
  parseVoiceText: (
    text,
    languageCode = "en-IN",
    currentState = "IDLE",
    currentCity = "",
    currentCategories = []
  ) =>
    request("/voice/parse-text", {
      method: "POST",
      body: JSON.stringify({
        text,
        language_code: languageCode,
        current_state: currentState,
        current_city: currentCity,
        current_categories: currentCategories,
      }),
    }),
  getSmartSummary: () => request("/voice/smart-summary"),
};
