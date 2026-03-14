class ApiError extends Error {
  constructor(message, status, payload) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.payload = payload;
  }
}

const DASHBOARD_SNAPSHOT_KEY = "mission-control.dashboard.snapshot";

function saveDashboardSnapshot(payload) {
  try {
    localStorage.setItem(
      DASHBOARD_SNAPSHOT_KEY,
      JSON.stringify({
        cachedAt: new Date().toISOString(),
        payload,
      }),
    );
  } catch {
    // Ignore storage failures so the product still works in constrained browsers.
  }
}

function loadDashboardSnapshot() {
  try {
    const raw = localStorage.getItem(DASHBOARD_SNAPSHOT_KEY);
    if (!raw) {
      return null;
    }
    const parsed = JSON.parse(raw);
    if (!parsed?.payload) {
      return null;
    }
    return {
      ...parsed.payload,
      runtime: {
        ...(parsed.payload.runtime || {}),
        offlineSnapshot: true,
        cachedAt: parsed.cachedAt || "",
      },
    };
  } catch {
    return null;
  }
}

async function request(path, options = {}) {
  try {
    const response = await fetch(path, {
      credentials: "include",
      ...options,
      headers: {
        ...(options.body ? { "Content-Type": "application/json" } : {}),
        ...(options.headers || {}),
      },
    });
    const text = await response.text();
    const payload = text ? JSON.parse(text) : {};
    if (!response.ok) {
      throw new ApiError(payload.message || payload.error || `Request failed: ${response.status}`, response.status, payload);
    }
    if (path === "/api/dashboard") {
      saveDashboardSnapshot(payload);
    }
    return payload;
  } catch (error) {
    if (path === "/api/dashboard") {
      const snapshot = loadDashboardSnapshot();
      if (snapshot) {
        return snapshot;
      }
    }
    throw error;
  }
}

export function getSession() {
  return request("/api/auth/session");
}

export function loginWithPassword(username, password) {
  return request("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ mode: "password", username, password }),
  });
}

export function loginWithToken(token) {
  return request("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ mode: "token", token }),
  });
}

export function logout() {
  return request("/api/auth/logout", {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export function getDashboard() {
  return request("/api/dashboard");
}

export function getConversationTranscript(agentId, sessionId) {
  return request(`/api/conversations/transcript?agentId=${encodeURIComponent(agentId)}&sessionId=${encodeURIComponent(sessionId)}`);
}

export function postAction(path, payload) {
  return request(path, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export { ApiError };
