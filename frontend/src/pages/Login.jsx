import { Link } from "react-router-dom";
import { Activity, ArrowRight, Building2, UserRound } from "lucide-react";

export default function Login() {
  return (
    <section className="relative flex min-h-screen items-center justify-center overflow-hidden px-4 py-10 sm:px-6 lg:px-8">
      <div className="hero-glow" />
      <div className="w-full max-w-2xl rounded-3xl border border-slate-200 bg-white p-8 shadow-xl">
        <div className="mb-8 text-center">
          <div className="mb-4 inline-flex rounded-xl bg-cyan-600 p-3 text-white">
            <Activity className="h-6 w-6" />
          </div>
          <h1 className="text-3xl font-extrabold tracking-tight text-slate-900">Log In</h1>
          <p className="mt-2 text-sm text-slate-600">Choose the portal that matches your account type.</p>
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          <Link to="/login/staff" className="group rounded-2xl border border-slate-200 bg-slate-50 p-5 transition hover:border-cyan-300 hover:bg-cyan-50">
            <div className="mb-3 inline-flex rounded-xl bg-slate-900 p-2 text-white group-hover:bg-cyan-700">
              <Building2 className="h-5 w-5" />
            </div>
            <h2 className="text-lg font-bold text-slate-900">Hospital Staff</h2>
            <p className="mt-1 text-sm text-slate-600">Admin, doctors, nurses, reception, pharmacy, and other staff.</p>
            <span className="mt-4 inline-flex items-center gap-2 text-sm font-semibold text-cyan-700">
              Continue <ArrowRight className="h-4 w-4" />
            </span>
          </Link>

          <Link to="/login/patient" className="group rounded-2xl border border-slate-200 bg-slate-50 p-5 transition hover:border-cyan-300 hover:bg-cyan-50">
            <div className="mb-3 inline-flex rounded-xl bg-slate-900 p-2 text-white group-hover:bg-cyan-700">
              <UserRound className="h-5 w-5" />
            </div>
            <h2 className="text-lg font-bold text-slate-900">Patient Portal</h2>
            <p className="mt-1 text-sm text-slate-600">Patients can view reports, medications, and care timeline.</p>
            <span className="mt-4 inline-flex items-center gap-2 text-sm font-semibold text-cyan-700">
              Continue <ArrowRight className="h-4 w-4" />
            </span>
          </Link>
        </div>
      </div>
    </section>
  );
}
