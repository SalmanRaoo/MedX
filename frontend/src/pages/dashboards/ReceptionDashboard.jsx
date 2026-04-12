import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import ReceptionWorkspaceLayout from "../../components/dashboards/ReceptionWorkspaceLayout";
import { api } from "../../lib/api";

export default function ReceptionDashboard() {
  const [appointments, setAppointments] = useState([]);
  const [loadingAppointments, setLoadingAppointments] = useState(false);
  const [appointmentError, setAppointmentError] = useState("");

  useEffect(() => {
    let active = true;
    const loadAppointments = async () => {
      setLoadingAppointments(true);
      setAppointmentError("");
      try {
        const { data } = await api.get("/reception/appointments", {
          params: { status: "SCHEDULED", limit: 40 },
        });
        if (!active) return;
        setAppointments(data?.items || []);
      } catch (err) {
        if (!active) return;
        setAppointments([]);
        setAppointmentError(err?.response?.data?.detail || "Unable to load appointment queue.");
      } finally {
        if (active) setLoadingAppointments(false);
      }
    };
    loadAppointments();
    return () => {
      active = false;
    };
  }, []);

  return (
    <ReceptionWorkspaceLayout
        title="Reception Dashboard"
        subtitle="Front-desk control for patient onboarding and admissions."
    >
      <section>
        <div className="grid gap-4 md:grid-cols-3">
          <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
            <p className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Patient Intake</p>
            <p className="mt-1 text-sm text-slate-600">Register new patients and issue portal credentials.</p>
          </div>
          <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
            <p className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Admissions</p>
            <p className="mt-1 text-sm text-slate-600">Enter admitted patient details, bed mapping, and cost.</p>
          </div>
          <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
            <p className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Radiology Billing</p>
            <p className="mt-1 text-sm text-slate-600">Register scan orders, issue invoices, and print receipts.</p>
          </div>
        </div>

        <div className="mt-4 grid gap-4 md:grid-cols-3">
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

          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm flex items-center justify-between gap-4 flex-wrap">
            <div>
              <h3 className="text-lg font-bold">Radiology & Billing</h3>
              <p className="text-sm text-slate-600">X-Ray, MRI, Ultrasound, CT Scan order + invoice + payment toggle.</p>
            </div>
            <Link to="/dashboard/reception/radiology-billing" className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-cyan-700">
              Open Billing Hub
            </Link>
          </div>
        </div>

        <section className="mt-6 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex items-center justify-between gap-3">
            <h3 className="text-lg font-bold">Incoming Appointments</h3>
            <p className="text-xs text-slate-500">Public and internal appointments for your hospital.</p>
          </div>
          {appointmentError ? (
            <p className="mt-3 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">{appointmentError}</p>
          ) : null}
          {loadingAppointments ? <p className="mt-3 text-sm text-slate-500">Loading appointments...</p> : null}
          {!loadingAppointments && appointments.length === 0 ? (
            <p className="mt-3 text-sm text-slate-500">No scheduled appointments right now.</p>
          ) : null}

          <div className="mt-3 max-h-72 space-y-2 overflow-auto pr-1">
            {appointments.map((a) => (
              <article key={a.appointment_id} className="rounded-xl border border-slate-200 bg-slate-50 p-3 text-sm">
                <p className="font-semibold">{a.patient_name || "-"} ({a.patient_mrn || "-"})</p>
                <p className="text-slate-600">Doctor: {a.doctor_name || `#${a.doctor_id}`}</p>
                <p className="text-slate-600">Time: {a.appointment_date || "-"}</p>
                <p className="text-xs text-slate-500">Type: {a.appointment_type || "-"} | Status: {a.status || "-"}</p>
              </article>
            ))}
          </div>
        </section>
      </section>
    </ReceptionWorkspaceLayout>
  );
}
