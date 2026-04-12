import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api } from "../lib/api";
import { getToken } from "../lib/auth";

const HospitalSettingsContext = createContext(null);

export function HospitalSettingsProvider({ children }) {
  const [settings, setSettings] = useState(null);
  const [loading, setLoading] = useState(false);

  const refreshSettings = useCallback(async () => {
    if (!getToken()) {
      setSettings(null);
      return null;
    }
    setLoading(true);
    try {
      const { data } = await api.get("/settings");
      setSettings(data || null);
      return data || null;
    } catch {
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshSettings();
  }, [refreshSettings]);

  useEffect(() => {
    const onStorage = () => {
      if (!getToken()) {
        setSettings(null);
        return;
      }
      refreshSettings();
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, [refreshSettings]);

  const value = useMemo(
    () => ({
      settings,
      loading,
      refreshSettings,
      hospitalName: settings?.hospital_metadata?.hospital_name || null,
      hospitalAddress: settings?.hospital_metadata?.address || null,
      hospitalLogoUrl: settings?.hospital_metadata?.logo_url || null,
      hospitalContactNumber: settings?.hospital_metadata?.contact_number || null,
    }),
    [settings, loading, refreshSettings]
  );

  return <HospitalSettingsContext.Provider value={value}>{children}</HospitalSettingsContext.Provider>;
}

export function useHospitalSettings() {
  const ctx = useContext(HospitalSettingsContext);
  if (!ctx) {
    return {
      settings: null,
      loading: false,
      refreshSettings: async () => null,
      hospitalName: null,
      hospitalAddress: null,
      hospitalLogoUrl: null,
      hospitalContactNumber: null,
    };
  }
  return ctx;
}
