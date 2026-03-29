import { Navigate, useLocation } from "react-router-dom";
import { clearSession, getSessionUser, isTokenValid } from "../lib/auth";

export function ProtectedRoute({ children }) {
  const location = useLocation();
  if (!isTokenValid()) {
    clearSession();
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  return children;
}

export function RoleRoute({ allowedRoles = [], children }) {
  const location = useLocation();
  const user = getSessionUser();

  if (!isTokenValid()) {
    clearSession();
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }

  const role = (user?.role_name || "").toUpperCase();
  const allowed = allowedRoles.map((r) => r.toUpperCase());
  if (!allowed.includes(role)) {
    return <Navigate to="/dashboard" replace />;
  }

  return children;
}

export function GuestRoute({ children }) {
  if (isTokenValid()) return <Navigate to="/dashboard" replace />;
  return children;
}
