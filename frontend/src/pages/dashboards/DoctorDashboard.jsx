import { Link } from "react-router-dom";
import DoctorWorkspaceLayout from "../../components/dashboards/DoctorWorkspaceLayout";

export default function DoctorDashboard() {
  return (
    <DoctorWorkspaceLayout
      title="Doctor Dashboard"
      subtitle="Manage patient care workflow: medications, diagnosis, and procedures."
    >
      <div className="grid gap-4 md:grid-cols-3">
        <Card
          title="Add Medication"
          text="Create medication orders that are visible to pharmacy and patient."
          to="/dashboard/doctor/medications"
          cta="Open Medications"
        />
        <Card
          title="Add Diagnosis"
          text="Record diagnosis and share it directly with patient care feed."
          to="/dashboard/doctor/clinical"
          cta="Open Clinical Updates"
        />
        <Card
          title="Add Procedure"
          text="Record procedures and publish to patient care timeline."
          to="/dashboard/doctor/clinical"
          cta="Open Clinical Updates"
        />
        <Card
          title="Symptoms AI"
          text="Select symptoms, run the disease predictor model, and review confidence."
          to="/dashboard/doctor/symptoms"
          cta="Open Symptoms AI"
        />
        <Card
          title="My Patients"
          text="View all your patients with previous diagnosis, medications, and admission/OPD details."
          to="/dashboard/doctor/patients"
          cta="Open My Patients"
        />
      </div>
    </DoctorWorkspaceLayout>
  );
}

function Card({ title, text, to, cta }) {
  return (
    <article className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <h3 className="text-lg font-bold">{title}</h3>
      <p className="mt-2 text-sm text-slate-600">{text}</p>
      <Link to={to} className="mt-4 inline-flex rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-cyan-700">
        {cta}
      </Link>
    </article>
  );
}
