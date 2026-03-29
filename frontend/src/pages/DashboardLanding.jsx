import { useMemo } from "react";
import { Navigate } from "react-router-dom";
import { getSessionUser } from "../lib/auth";

export default function DashboardLanding() {
  const path = useMemo(() => {
    const role = (getSessionUser()?.role_name || "").toUpperCase();
    const map = {
      SUPER_ADMIN: "/dashboard/super-admin",
      ADMIN: "/dashboard/admin",
      DOCTOR: "/dashboard/doctor",
      NURSE: "/dashboard/nurse",
      RECEPTIONIST: "/dashboard/reception",
      PHARMACY: "/dashboard/pharmacy",
      LAB: "/dashboard/lab",
      FINANCE: "/dashboard/finance",
      OPERATIONS: "/dashboard/operations",
      PATIENT: "/dashboard/patient",
    };
    return map[role] || "/";
  }, []);

  return <Navigate to={path} replace />;
}
