import { useState } from "react";
import { api } from "../lib/api";
import { KeyRound, Loader2, ShieldCheck } from "lucide-react";

export default function AccountSecurity() {
  const [form, setForm] = useState({ current_password: "", new_password: "" });
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setMessage("");
    try {
      await api.post("/auth/change-password", form);
      setForm({ current_password: "", new_password: "" });
      setMessage("Password updated successfully.");
    } catch (err) {
      setMessage(err?.response?.data?.detail || "Password update failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="px-4 py-10 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-2xl rounded-2xl border border-slate-200 bg-white p-8 shadow-sm">
        <div className="flex items-center gap-3 mb-6">
          <div className="rounded-xl bg-cyan-100 p-2 text-cyan-700"><ShieldCheck className="h-5 w-5" /></div>
          <h1 className="text-2xl font-extrabold">Account Security</h1>
        </div>
        <form onSubmit={submit} className="space-y-4">
          <input type="password" placeholder="Current Password" className="w-full rounded-xl border p-3" value={form.current_password} onChange={(e) => setForm({ ...form, current_password: e.target.value })} required />
          <input type="password" placeholder="New Password (min 8 chars)" className="w-full rounded-xl border p-3" value={form.new_password} onChange={(e) => setForm({ ...form, new_password: e.target.value })} required />
          <button disabled={loading} className="rounded-xl bg-slate-900 text-white px-5 py-3 font-semibold inline-flex items-center gap-2">
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <KeyRound className="h-4 w-4" />} Change Password
          </button>
          {message ? <p className="text-sm font-semibold text-slate-700">{message}</p> : null}
        </form>
      </div>
    </section>
  );
}
