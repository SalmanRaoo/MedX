export function getToken() {
  return localStorage.getItem("medx_token");
}

function decodeJwtPayload(token) {
  try {
    const parts = token.split(".");
    if (parts.length !== 3) return null;
    const payload = parts[1].replace(/-/g, "+").replace(/_/g, "/");
    const padded = payload + "=".repeat((4 - (payload.length % 4)) % 4);
    const json = atob(padded);
    return JSON.parse(json);
  } catch {
    return null;
  }
}

export function isTokenValid(token = getToken()) {
  if (!token) return false;
  const payload = decodeJwtPayload(token);
  if (!payload || typeof payload.exp !== "number") return false;
  const nowSec = Math.floor(Date.now() / 1000);
  return payload.exp > nowSec;
}

export function getSessionUser() {
  try {
    const raw = localStorage.getItem("medx_user");
    if (raw) return JSON.parse(raw);
  } catch {
    // fallback below
  }

  const payload = decodeJwtPayload(getToken() || "");
  if (!payload) return null;
  return {
    email: payload.email,
    hospital_id: payload.hospital_id,
    role_name: payload.role_name,
  };
}

export function clearSession() {
  localStorage.removeItem("medx_token");
  localStorage.removeItem("medx_user");
}
