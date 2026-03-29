export default function About() {
  return (
    <section className="px-4 py-16 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-6xl space-y-8 rounded-2xl border border-slate-200 bg-white p-8 shadow-sm">
        <div>
          <h1 className="text-3xl font-extrabold tracking-tight">About MedX Project</h1>
          <p className="mt-3 text-slate-700">MedX is a Final Year Project focused on building a production-style multi-hospital health technology platform. The product combines ERP operations, AI decision support, SaaS subscription management, and role-based dashboard experiences.</p>
        </div>

        <div className="grid gap-6 md:grid-cols-2">
          <article className="rounded-xl border border-slate-200 bg-slate-50 p-5">
            <h2 className="text-xl font-bold">Mission</h2>
            <p className="mt-2 text-slate-700">Deliver safer and faster healthcare operations with a secure multi-tenant architecture where every hospital has isolated data and configurable workflows.</p>
          </article>
          <article className="rounded-xl border border-slate-200 bg-slate-50 p-5">
            <h2 className="text-xl font-bold">Architecture</h2>
            <p className="mt-2 text-slate-700">Backend uses a tenant-aware SQL schema and role-checked APIs. Frontend provides public product pages plus role dashboards for hospital teams.</p>
          </article>
        </div>

        <div>
          <h2 className="text-xl font-bold">Detailed Scope</h2>
          <ul className="mt-3 list-disc pl-6 text-slate-700 space-y-2">
            <li>Multi-hospital onboarding and subscription plans with expiry tracking.</li>
            <li>Public pricing, hospital contacts, and MedX support contact portals.</li>
            <li>Super-admin business observability across all purchased subscriptions.</li>
            <li>Hospital admin functions for staff lifecycle, department mapping, and settings management.</li>
            <li>AI report generation from operational report content with delivery to doctor/patient and printable hardcopy support.</li>
            <li>Role-based dashboards for Super Admin, Admin, Doctor, Nurse, Reception, Lab, Pharmacy, Finance, Operations, and Patient.</li>
          </ul>
        </div>

        <div className="rounded-xl border border-cyan-200 bg-cyan-50 p-5">
          <h2 className="text-xl font-bold text-cyan-900">Project Value</h2>
          <p className="mt-2 text-cyan-900/90">This project demonstrates real-world software engineering concerns: security boundaries, user-role orchestration, operational observability, and productized healthcare workflows.</p>
        </div>
      </div>
    </section>
  );
}
