import { Link, useNavigate } from "react-router-dom";
import { FlaskConical, FileText, LogOut, WandSparkles, ArrowRight, ScanLine } from "lucide-react";
import { clearSession, getSessionUser } from "../../lib/auth";

export default function LabDashboard() {
  const navigate = useNavigate();
  const user = getSessionUser();

  const handleLogout = () => {
    clearSession();
    navigate("/");
  };

  return (
    <div className="min-h-screen bg-slate-100 text-slate-900">
      <div className="flex min-h-screen">
        <aside className="hidden w-72 bg-slate-900 p-6 text-white md:flex md:flex-col">
          <Link to="/dashboard/lab" className="mb-8 block">
            <p className="text-xs uppercase tracking-[0.2em] text-teal-300">MedX Laboratory</p>
            <p className="mt-1 text-2xl font-extrabold">Technician Desk</p>
          </Link>

          <div className="rounded-2xl border border-teal-700/40 bg-slate-800/70 p-4 text-sm">
            <p className="font-semibold">{user?.hospital_name || "MedX"}</p>
            <p className="mt-1 text-slate-300">Main lab dashboard now uses quick actions only.</p>
          </div>

          <nav className="mt-6 flex-1 space-y-2">
            <Link to="/dashboard/lab" className="flex items-center gap-3 rounded-xl bg-teal-600 px-4 py-3 text-sm font-semibold text-white">
              <FlaskConical className="h-4 w-4" /> Lab Home
            </Link>
            <Link to="/dashboard/lab/generate" className="flex items-center gap-3 rounded-xl px-4 py-3 text-sm font-semibold text-slate-300 hover:bg-slate-800">
              <WandSparkles className="h-4 w-4" /> Smart Lab Form
            </Link>
            <Link to="/dashboard/lab/reports" className="flex items-center gap-3 rounded-xl px-4 py-3 text-sm font-semibold text-slate-300 hover:bg-slate-800">
              <FileText className="h-4 w-4" /> Report Management
            </Link>
            <Link to="/dashboard/radiology" className="flex items-center gap-3 rounded-xl px-4 py-3 text-sm font-semibold text-slate-300 hover:bg-slate-800">
              <ScanLine className="h-4 w-4" /> Radiology Suite
            </Link>
          </nav>

          <button
            type="button"
            onClick={handleLogout}
            className="mt-6 inline-flex items-center justify-center gap-2 rounded-xl border border-red-400/40 px-4 py-2 text-sm font-semibold text-red-300 hover:bg-red-500/10"
          >
            <LogOut className="h-4 w-4" /> Logout
          </button>
        </aside>

        <main className="flex-1 space-y-5 p-5 sm:p-8">
          <header className="rounded-[32px] border border-slate-200 bg-white p-6 shadow-sm">
            <h1 className="text-3xl font-black tracking-tight">Laboratory Dashboard</h1>
            <p className="mt-1 text-slate-600">All forms are removed from this page. Use the actions below to generate and manage reports.</p>
          </header>

          <section className="grid gap-5 md:grid-cols-3">
            <article className="rounded-[32px] border border-slate-200 bg-white p-6 shadow-sm">
              <p className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Action 1</p>
              <h2 className="mt-1 text-xl font-black">Open Smart Lab Form</h2>
              <p className="mt-2 text-sm text-slate-600">Select any of the 8 AI lab models, fill required clinical features, attach standard markers, and generate report.</p>
              <Link
                to="/dashboard/lab/generate"
                className="mt-4 inline-flex items-center gap-2 rounded-xl bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-teal-700"
              >
                Open Generator <ArrowRight className="h-4 w-4" />
              </Link>
            </article>

            <article className="rounded-[32px] border border-slate-200 bg-white p-6 shadow-sm">
              <p className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Action 2</p>
              <h2 className="mt-1 text-xl font-black">Manage Completed Reports</h2>
              <p className="mt-2 text-sm text-slate-600">Review finalized entries, open professional result view, and print reports for records.</p>
              <Link
                to="/dashboard/lab/reports"
                className="mt-4 inline-flex items-center gap-2 rounded-xl border border-teal-600 px-4 py-2 text-sm font-semibold text-teal-700 hover:bg-teal-50"
              >
                Open Report Management <ArrowRight className="h-4 w-4" />
              </Link>
            </article>

            <article className="rounded-[32px] border border-slate-200 bg-white p-6 shadow-sm">
              <p className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Action 3</p>
              <h2 className="mt-1 text-xl font-black">Open Radiology Suite</h2>
              <p className="mt-2 text-sm text-slate-600">Capture imaging metadata for X-Ray, Ultrasound, MRI and trigger dedicated AI actions.</p>
              <Link
                to="/dashboard/radiology"
                className="mt-4 inline-flex items-center gap-2 rounded-xl border border-cyan-600 px-4 py-2 text-sm font-semibold text-cyan-700 hover:bg-cyan-50"
              >
                Open Radiology Suite <ArrowRight className="h-4 w-4" />
              </Link>
            </article>
          </section>
        </main>
      </div>
    </div>
  );
}
