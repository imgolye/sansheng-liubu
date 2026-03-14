class ApiError extends Error {
  constructor(message, status, payload) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.payload = payload;
  }
}

async function request(path, options = {}) {
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
  return payload;
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
