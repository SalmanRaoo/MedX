import { Link } from "react-router-dom";
import { ArrowRight, BrainCircuit, Database, ShieldCheck, Building2, Activity, Sparkles, Stethoscope, CalendarCheck } from "lucide-react";

const capabilities = [
  { icon: BrainCircuit, title: "AI Clinical Intelligence", desc: "Narrative-to-insight AI reporting with doctor/patient delivery tracking and printable outputs." },
  { icon: Database, title: "Hospital ERP Core", desc: "Admissions, staff, pharmacy, billing, and operations under one secure tenant-aware platform." },
  { icon: ShieldCheck, title: "Multi-Tenant Security", desc: "Strong hospital data segregation, role-based access, and auditable workflows." },
  { icon: Stethoscope, title: "Care Team Workspaces", desc: "Role dashboards for doctors, nurses, reception, lab, pharmacy, and finance teams." },
  { icon: CalendarCheck, title: "Subscription & Governance", desc: "Plan purchases, expiry tracking, and super-admin visibility across all hospitals." },
  { icon: Building2, title: "Public Network Visibility", desc: "Public hospital directory with contact profiles maintained by each hospital admin." },
];

export default function Home() {
  return (
    <div>
      <section className="relative overflow-hidden px-4 pb-24 pt-20 sm:px-6 lg:px-8">
        <div className="hero-glow" />
        <div className="mx-auto grid w-full max-w-7xl items-center gap-12 lg:grid-cols-2">
          <div className="space-y-8">
            <div className="inline-flex items-center gap-2 rounded-full border border-cyan-200 bg-cyan-50 px-4 py-1.5 text-xs font-bold uppercase tracking-[0.14em] text-cyan-700">
              <Sparkles className="h-4 w-4" /> Modern Healthcare Platform
            </div>
            <div className="space-y-4">
              <h1 className="text-4xl font-extrabold leading-tight tracking-tight text-slate-900 md:text-6xl">
                Built for hospital groups.
                <span className="block text-cyan-700">Designed for clinical speed.</span>
              </h1>
              <p className="max-w-xl text-lg leading-relaxed text-slate-600">
                MedX connects hospital operations, AI reporting, subscription control, and role-based care workflows in one multi-tenant product.
              </p>
            </div>
            <div className="flex flex-col gap-3 sm:flex-row">
              <Link to="/pricing" className="inline-flex items-center justify-center gap-2 rounded-xl bg-cyan-600 px-6 py-3 text-sm font-semibold text-white shadow-lg shadow-cyan-600/25 transition hover:bg-cyan-700">View Plans <ArrowRight className="h-4 w-4" /></Link>
              <Link to="/about" className="inline-flex items-center justify-center rounded-xl border border-slate-300 bg-white px-6 py-3 text-sm font-semibold text-slate-700 transition hover:border-cyan-300 hover:text-cyan-700">Learn About MedX</Link>
            </div>
          </div>

          <div className="grid gap-4">
            <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
              <h3 className="text-sm font-bold uppercase tracking-[0.14em] text-slate-500">Use Cases</h3>
              <p className="text-sm text-slate-600 mt-3">Single hospital deployment, multi-hospital networks, and centralized health systems with shared governance.</p>
            </div>
            <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
              <h3 className="text-sm font-bold uppercase tracking-[0.14em] text-slate-500">Who Uses It</h3>
              <p className="text-sm text-slate-600 mt-3">Super Admin, Hospital Admin, Doctor, Nurse, Reception, Lab, Pharmacy, Finance, Operations, and Patient users.</p>
            </div>
          </div>
        </div>
      </section>

      <section className="border-y border-slate-200 bg-white px-4 py-20 sm:px-6 lg:px-8">
        <div className="mx-auto w-full max-w-7xl">
          <div className="mb-12"><p className="text-xs font-bold uppercase tracking-[0.14em] text-cyan-700">Capabilities</p><h2 className="mt-2 text-3xl font-extrabold tracking-tight text-slate-900">Platform Capabilities</h2></div>
          <div className="grid gap-6 md:grid-cols-3">
            {capabilities.map((item) => {
              const Icon = item.icon;
              return (
                <article key={item.title} className="rounded-2xl border border-slate-200 bg-slate-50 p-6 transition hover:-translate-y-1 hover:shadow-md">
                  <div className="mb-4 inline-flex rounded-xl bg-white p-2 text-cyan-700 shadow-sm"><Icon className="h-5 w-5" /></div>
                  <h3 className="mb-2 text-lg font-bold text-slate-900">{item.title}</h3>
                  <p className="text-sm leading-relaxed text-slate-600">{item.desc}</p>
                </article>
              );
            })}
          </div>
        </div>
      </section>
    </div>
  );
}
