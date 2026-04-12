import { useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { publicApi } from "../lib/api";

export default function SubscriptionOnboarding() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  const [form, setForm] = useState({
    hospital_code: searchParams.get("hospital_code") || "",
    full_name: "",
    email: searchParams.get("admin_email") || "",
    password: "",
    phone_number: "",
    department_name: "Administration",
  });

  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const canSubmit = useMemo(
    () => form.hospital_code && form.full_name && form.email && form.password,
    [form]
  );

  const onSubmit = async (e) => {
    e.preventDefault();
    if (!canSubmit) return;

    setLoading(true);
    setError("");
    setMessage("");

    try {
      const res = await publicApi.post("/public/subscriptions/onboard-admin", form);
      setMessage(`Admin setup completed for ${res.data.hospital_name}. You can now login.`);
      setTimeout(() => navigate("/login/staff"), 1200);
    } catch (err) {
      setError(err?.response?.data?.detail || "Unable to complete admin onboarding");
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="px-4 py-16 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-3xl rounded-2xl border border-slate-200 bg-white p-8 shadow-sm">
        <p className="text-xs uppercase tracking-[0.14em] font-bold text-cyan-700">Post-Purchase Setup</p>
        <h1 className="mt-2 text-3xl font-extrabold">Register Hospital Admin</h1>
        <p className="mt-2 text-slate-600">Complete this once after buying subscription to access your admin dashboard and database.</p>

        <form onSubmit={onSubmit} className="mt-6 space-y-4">
          {error ? <p className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</p> : null}
          {message ? <p className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-700">{message}</p> : null}

          <input className="w-full rounded-lg border px-3 py-2.5" placeholder="Hospital Code" value={form.hospital_code} onChange={(e) => setForm({ ...form, hospital_code: e.target.value })} required />
          <input className="w-full rounded-lg border px-3 py-2.5" placeholder="Admin Full Name" value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} required />
          <input type="email" className="w-full rounded-lg border px-3 py-2.5" placeholder="Admin Email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} required />
          <input type="password" className="w-full rounded-lg border px-3 py-2.5" placeholder="Admin Password (min 8 chars)" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} required />
          <input className="w-full rounded-lg border px-3 py-2.5" placeholder="Phone Number" value={form.phone_number} onChange={(e) => setForm({ ...form, phone_number: e.target.value })} />
          <input className="w-full rounded-lg border px-3 py-2.5" placeholder="Department" value={form.department_name} onChange={(e) => setForm({ ...form, department_name: e.target.value })} />

          <div className="flex gap-2">
            <button disabled={loading || !canSubmit} className="rounded-xl bg-slate-900 px-5 py-3 text-white font-semibold hover:bg-cyan-700 disabled:opacity-70">
              {loading ? "Submitting..." : "Create Admin Account"}
            </button>
            <Link to="/login/staff" className="rounded-xl border px-5 py-3 text-sm font-semibold text-slate-700">Go to Login</Link>
          </div>
        </form>
      </div>
    </section>
  );
}
