import { Link } from "react-router-dom";
import RoleDashboardShell from "../../components/dashboards/RoleDashboardShell";

export default function ReceptionDashboard() {
  return (
    <>
      <RoleDashboardShell
        title="Reception Dashboard"
        subtitle="Front-desk control for patient onboarding and admissions."
        cards={[
          { title: "Patient Intake", text: "Register new patients and issue portal credentials." },
          { title: "Admissions", text: "Enter admitted patient details and cost." },
          { title: "Service Desk", text: "Handle patient and visitor requests." },
        ]}
      />

      <section className="px-4 pb-10 sm:px-6 lg:px-8 -mt-2">
        <div className="mx-auto max-w-7xl grid gap-4 md:grid-cols-2">
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm flex items-center justify-between gap-4 flex-wrap">
            <div>
              <h3 className="text-lg font-bold">Patient Intake</h3>
              <p className="text-sm text-slate-600">Register patients and print credential receipt.</p>
            </div>
            <Link to="/dashboard/reception/patients" className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-cyan-700">
              Add Patients
            </Link>
          </div>

          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm flex items-center justify-between gap-4 flex-wrap">
            <div>
              <h3 className="text-lg font-bold">Admission Desk</h3>
              <p className="text-sm text-slate-600">Enter admitted patient details, bed and cost.</p>
            </div>
            <Link to="/dashboard/reception/admissions" className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-cyan-700">
              Admit Patients
            </Link>
          </div>
        </div>
      </section>
    </>
  );
}
