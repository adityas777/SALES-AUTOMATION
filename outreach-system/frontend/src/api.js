const API_BASE = "http://localhost:8000/api";

async function request(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
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
};
