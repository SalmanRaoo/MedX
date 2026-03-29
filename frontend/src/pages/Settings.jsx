import { useState, useEffect } from "react";
import Sidebar from "../components/Sidebar";
import { api } from "../lib/api";
import {
  Save, Building2, MapPin, Phone, Mail, Clock,
  ShieldCheck, Loader2, CheckCircle
} from "lucide-react";

export default function Settings() {
  const [profile, setProfile] = useState({
    hospital_name: "",
    address: "",
    phone_contact: "",
    email_contact: "",
    emergency_line: "",
    opd_hours: "",
    timezone: "Asia/Karachi",
  });

  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [toast, setToast] = useState({ show: false, message: "" });

  const showToast = (msg) => {
    setToast({ show: true, message: msg });
    setTimeout(() => setToast({ show: false, message: "" }), 3000);
  };

  const fetchProfile = async () => {
    try {
      const res = await api.get("/hospital_settings/?limit=1");
      const first = res.data?.items?.[0];
      if (first) {
        setProfile({
          hospital_name: first.hospital_name || "",
          address: first.address || "",
          phone_contact: first.phone_contact || "",
          email_contact: first.email_contact || "",
          emergency_line: first.emergency_line || "",
          opd_hours: first.opd_hours || "",
          timezone: first.timezone || "Asia/Karachi",
        });
      }
    } catch {
      // keep defaults
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchProfile();
  }, []);

  const handleSaveProfile = async (e) => {
    e.preventDefault();
    setIsSaving(true);
    try {
      await api.post("/admin/hospital-settings/upsert", profile);
      showToast("Hospital profile saved and published to Hospital Contacts page");
      fetchProfile();
    } catch (err) {
      showToast(err?.response?.data?.detail || "Failed to save profile");
    } finally {
      setIsSaving(false);
    }
  };

  if (isLoading) {
    return (
      <div className="flex h-screen items-center justify-center bg-slate-50">
        <Loader2 className="animate-spin text-teal-600 w-10 h-10" />
      </div>
    );
  }

  return (
    <div className="flex h-screen bg-slate-50 overflow-hidden font-sans">
      <Sidebar />

      <div className="flex-1 flex flex-col relative">
        {toast.show && (
          <div className="fixed top-8 right-8 z-[200] bg-slate-900 text-white px-6 py-4 rounded-2xl shadow-2xl flex items-center">
            <CheckCircle className="w-5 h-5 mr-3 text-teal-400" />
            <span className="font-bold text-sm">{toast.message}</span>
          </div>
        )}

        <header className="h-20 bg-white border-b flex items-center px-8 shadow-sm">
          <h1 className="text-xl font-black text-slate-900 uppercase tracking-tighter">Admin Hospital Settings</h1>
        </header>

        <main className="flex-1 overflow-y-auto p-12 space-y-12">
          <div className="max-w-4xl">
            <h2 className="text-3xl font-black text-slate-900 tracking-tight mb-2">Public Contact Profile</h2>
            <p className="text-slate-500 font-medium">This information appears on the public Hospital Contacts page for your hospital.</p>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-12">
            <div className="lg:col-span-2 bg-white rounded-[32px] border border-slate-100 shadow-xl p-10">
              <form onSubmit={handleSaveProfile} className="space-y-8">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                  <div className="space-y-2">
                    <label className="text-[10px] font-black text-slate-400 uppercase tracking-[0.2em] ml-1">Hospital Name</label>
                    <div className="relative"><Building2 className="absolute left-4 top-4 w-4 h-4 text-slate-400" /><input className="w-full pl-12 pr-4 py-4 bg-slate-50 border rounded-2xl outline-none" value={profile.hospital_name} onChange={(e) => setProfile({ ...profile, hospital_name: e.target.value })} /></div>
                  </div>
                  <div className="space-y-2">
                    <label className="text-[10px] font-black text-slate-400 uppercase tracking-[0.2em] ml-1">Emergency Line</label>
                    <div className="relative"><Phone className="absolute left-4 top-4 w-4 h-4 text-red-500" /><input className="w-full pl-12 pr-4 py-4 bg-slate-50 border rounded-2xl outline-none" value={profile.emergency_line} onChange={(e) => setProfile({ ...profile, emergency_line: e.target.value })} /></div>
                  </div>
                </div>

                <div className="space-y-2">
                  <label className="text-[10px] font-black text-slate-400 uppercase tracking-[0.2em] ml-1">Address</label>
                  <div className="relative"><MapPin className="absolute left-4 top-4 w-4 h-4 text-slate-400" /><textarea rows="2" className="w-full pl-12 pr-4 py-4 bg-slate-50 border rounded-2xl outline-none resize-none" value={profile.address} onChange={(e) => setProfile({ ...profile, address: e.target.value })} /></div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                  <div className="space-y-2">
                    <label className="text-[10px] font-black text-slate-400 uppercase tracking-[0.2em] ml-1">Public Email</label>
                    <div className="relative"><Mail className="absolute left-4 top-4 w-4 h-4 text-slate-400" /><input className="w-full pl-12 pr-4 py-4 bg-slate-50 border rounded-2xl outline-none" value={profile.email_contact} onChange={(e) => setProfile({ ...profile, email_contact: e.target.value })} /></div>
                  </div>
                  <div className="space-y-2">
                    <label className="text-[10px] font-black text-slate-400 uppercase tracking-[0.2em] ml-1">Phone</label>
                    <div className="relative"><Phone className="absolute left-4 top-4 w-4 h-4 text-slate-400" /><input className="w-full pl-12 pr-4 py-4 bg-slate-50 border rounded-2xl outline-none" value={profile.phone_contact} onChange={(e) => setProfile({ ...profile, phone_contact: e.target.value })} /></div>
                  </div>
                </div>

                <div className="space-y-2">
                  <label className="text-[10px] font-black text-slate-400 uppercase tracking-[0.2em] ml-1">OPD Hours</label>
                  <div className="relative"><Clock className="absolute left-4 top-4 w-4 h-4 text-slate-400" /><input className="w-full pl-12 pr-4 py-4 bg-slate-50 border rounded-2xl outline-none" value={profile.opd_hours} onChange={(e) => setProfile({ ...profile, opd_hours: e.target.value })} /></div>
                </div>

                <button disabled={isSaving} className="w-full py-5 bg-teal-600 text-white font-black rounded-2xl shadow-xl hover:bg-teal-700 flex items-center justify-center">
                  {isSaving ? <Loader2 className="animate-spin mr-2" /> : <Save className="w-5 h-5 mr-2" />}Save Hospital Contact Profile
                </button>
              </form>
            </div>

            <div className="space-y-8">
              <div className="bg-slate-900 rounded-[32px] p-8 text-white shadow-2xl">
                <ShieldCheck className="w-10 h-10 text-teal-400 mb-6" />
                <h3 className="text-xl font-black mb-2 tracking-tight">Admin Control</h3>
                <p className="text-slate-400 text-sm leading-relaxed">Only hospital admins can edit and publish this contact profile.</p>
              </div>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}
