import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Activity, ArrowLeft, LockKeyhole, Mail, Loader2, Building2 } from "lucide-react";
import { publicApi } from "../lib/api";

export default function Login() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [selectedHospitalId, setSelectedHospitalId] = useState("");
  const [hospitals, setHospitals] = useState([]);
  const [requireHospitalSelection, setRequireHospitalSelection] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const canSubmit = useMemo(() => {
    if (!email || !password) return false;
    if (requireHospitalSelection && !selectedHospitalId) return false;
    return true;
  }, [email, password, requireHospitalSelection, selectedHospitalId]);

  const handleLogin = async (e) => {
    e.preventDefault();
    if (!canSubmit) return;

    setLoading(true);
    setError("");

    try {
      const payload = {
        email,
        password,
        selected_hospital_id: requireHospitalSelection ? Number(selectedHospitalId) : null,
      };

      const res = await publicApi.post("/auth/login", payload);

      if (res.data.require_hospital_selection) {
        setHospitals(res.data.hospitals || []);
        setRequireHospitalSelection(true);
        setLoading(false);
        return;
      }

      localStorage.setItem("medx_token", res.data.access_token);
      localStorage.setItem("medx_user", JSON.stringify(res.data.user));
      navigate("/dashboard");
    } catch (err) {
      setError(err?.response?.data?.detail || "Unable to login");
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="relative flex min-h-screen items-center justify-center overflow-hidden px-4 py-10 sm:px-6 lg:px-8">
      <div className="hero-glow" />
      <div className="w-full max-w-md rounded-3xl border border-slate-200 bg-white p-8 shadow-xl">
        <Link to="/" className="mb-6 inline-flex items-center gap-2 text-sm font-semibold text-slate-500 hover:text-cyan-700">
          <ArrowLeft className="h-4 w-4" /> Back to home
        </Link>

        <div className="mb-7">
          <div className="mb-4 inline-flex rounded-xl bg-cyan-600 p-3 text-white">
            <Activity className="h-6 w-6" />
          </div>
          <h1 className="text-2xl font-extrabold tracking-tight text-slate-900">Staff Sign In</h1>
          <p className="mt-1 text-sm text-slate-600">Multi-hospital secure login with tenant selection.</p>
        </div>

        <form onSubmit={handleLogin} className="space-y-5">
          {error && <p className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm font-medium text-rose-700">{error}</p>}

          <label className="block space-y-1">
            <span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Email</span>
            <div className="flex items-center rounded-lg border border-slate-300 px-3">
              <Mail className="h-4 w-4 text-slate-400" />
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full border-0 px-2 py-3 outline-none"
                placeholder="you@hospital.com"
              />
            </div>
          </label>

          <label className="block space-y-1">
            <span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Password</span>
            <div className="flex items-center rounded-lg border border-slate-300 px-3">
              <LockKeyhole className="h-4 w-4 text-slate-400" />
              <input
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full border-0 px-2 py-3 outline-none"
                placeholder="Enter your password"
              />
            </div>
          </label>

          {requireHospitalSelection && (
            <label className="block space-y-1">
              <span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Select Hospital</span>
              <div className="flex items-center rounded-lg border border-slate-300 px-3">
                <Building2 className="h-4 w-4 text-slate-400" />
                <select
                  value={selectedHospitalId}
                  onChange={(e) => setSelectedHospitalId(e.target.value)}
                  className="w-full border-0 bg-transparent px-2 py-3 outline-none"
                  required
                >
                  <option value="">Choose hospital</option>
                  {hospitals.map((h) => (
                    <option key={h.hospital_id} value={h.hospital_id}>
                      {h.hospital_name} ({h.role_name})
                    </option>
                  ))}
                </select>
              </div>
            </label>
          )}

          <button
            type="submit"
            disabled={loading || !canSubmit}
            className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-slate-900 px-5 py-3 text-sm font-semibold text-white transition hover:bg-cyan-700 disabled:cursor-not-allowed disabled:opacity-70"
          >
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            {loading ? "Signing in" : requireHospitalSelection ? "Continue" : "Sign In"}
          </button>
        </form>
      </div>
    </section>
  );
}
