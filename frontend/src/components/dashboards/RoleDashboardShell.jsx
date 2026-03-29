import { Link, useNavigate } from "react-router-dom";
import { LogOut, KeyRound } from "lucide-react";
import { clearSession } from "../../lib/auth";

export default function RoleDashboardShell({ title, subtitle, cards = [] }) {
  const user = JSON.parse(localStorage.getItem("medx_user") || "{}");
  const navigate = useNavigate();

  const handleExit = () => {
    clearSession();
    navigate("/");
  };

  return (
    <section className="px-4 py-10 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-7xl space-y-6">
        <header className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-extrabold tracking-tight">{title}</h1>
            <p className="text-slate-600 mt-1">{subtitle}</p>
            <p className="text-xs mt-2 uppercase tracking-[0.14em] text-cyan-700">{user.hospital_name || "Hospital"}</p>
          </div>
          <div className="flex gap-2">
            <Link to="/dashboard/account" className="rounded-lg border px-4 py-2 text-sm font-semibold text-slate-700 inline-flex items-center gap-2"><KeyRound className="h-4 w-4" />Account</Link>
            <button type="button" onClick={handleExit} className="rounded-lg border px-4 py-2 text-sm font-semibold text-slate-700 inline-flex items-center gap-2"><LogOut className="h-4 w-4" />Exit</button>
          </div>
        </header>

        <div className="grid gap-5 md:grid-cols-3">
          {cards.map((c) => (
            <article key={c.title} className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <h3 className="text-lg font-bold">{c.title}</h3>
              <p className="text-sm text-slate-600 mt-2">{c.text}</p>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}
