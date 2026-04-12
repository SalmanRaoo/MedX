import { useEffect, useMemo, useState } from "react";
import DoctorWorkspaceLayout from "../../components/dashboards/DoctorWorkspaceLayout";
import { api } from "../../lib/api";

function titleCase(value) {
  return String(value || "")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (m) => m.toUpperCase());
}

function hasActiveAdmission(admissions = []) {
  return admissions.some((a) => {
    const status = String(a.status || "").toUpperCase();
    return status && !["DISCHARGED", "CLOSED", "COMPLETED"].includes(status);
  });
}

export default function DoctorPatientsPage() {
  const [patients, setPatients] = useState([]);
  const [patientId, setPatientId] = useState("");
  const [query, setQuery] = useState("");
  const [historyData, setHistoryData] = useState(null);
  const [loadingPatients, setLoadingPatients] = useState(true);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    const loadPatients = async () => {
      try {
        const res = await api.get("/patients/", { params: { limit: 500 } });
        if (!active) return;
        const items = res.data.items || [];
        setPatients(items);
        if (items.length) {
          setPatientId(String(items[0].patient_id));
        }
      } catch (err) {
        if (!active) return;
        setError(err?.response?.data?.detail || "Unable to load patients.");
      } finally {
        if (active) setLoadingPatients(false);
      }
    };
    loadPatients();
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!patientId) return;
    let active = true;
    const loadHistory = async () => {
      setLoadingHistory(true);
      setError("");
      try {
        const res = await api.get(`/doctor/patients/${patientId}/history`);
        if (!active) return;
        setHistoryData(res.data);
      } catch (err) {
        if (!active) return;
        setError(err?.response?.data?.detail || "Unable to load patient history.");
      } finally {
        if (active) setLoadingHistory(false);
      }
    };
    loadHistory();
    return () => {
      active = false;
    };
  }, [patientId]);

  const filteredPatients = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return patients;
    return patients.filter((p) => {
      const name = String(p.full_name || "").toLowerCase();
      const mrn = String(p.patient_mrn || "").toLowerCase();
      const phone = String(p.phone_number || "").toLowerCase();
      return name.includes(q) || mrn.includes(q) || phone.includes(q);
    });
  }, [patients, query]);

  const history = historyData?.history || {};
  const admissions = history.admissions || [];
  const appointments = history.appointments || [];
  const medications = history.medications || [];
  const clinicalUpdates = history.clinical_updates || [];
  const labRequests = history.lab_requests || [];
  const imagingRecords = history.imaging_records || [];
  const aiDiagnoses = history.ai_diagnoses || [];
  const vitals = history.vitals || [];
  const visitLogs = history.visit_logs || [];

  const latestVisit = visitLogs.length ? visitLogs[0] : null;
  const patientStatus = hasActiveAdmission(admissions)
    ? "Admitted"
    : latestVisit?.visit_type
      ? String(latestVisit.visit_type).toUpperCase()
      : appointments.length > 0
        ? "OPD"
        : "No Visit History";

  return (
    <DoctorWorkspaceLayout
      title="My Patients"
      subtitle="View all patients with previous diagnosis, medications, admission and OPD details."
    >
      <div className="grid gap-5 lg:grid-cols-[360px_1fr]">
        <aside className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search by name, MRN, phone"
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-cyan-500"
          />

          <div className="mt-3 max-h-[34rem] overflow-auto space-y-2 pr-1">
            {loadingPatients ? <p className="text-sm text-slate-500">Loading patients...</p> : null}
            {!loadingPatients && filteredPatients.length === 0 ? <p className="text-sm text-slate-500">No patients found.</p> : null}
            {filteredPatients.map((p) => {
              const selected = String(p.patient_id) === String(patientId);
              return (
                <button
                  key={p.patient_id}
                  type="button"
                  onClick={() => setPatientId(String(p.patient_id))}
                  className={`w-full rounded-xl border px-3 py-3 text-left transition ${
                    selected
                      ? "border-cyan-500 bg-cyan-50"
                      : "border-slate-200 bg-white hover:border-cyan-300"
                  }`}
                >
                  <p className="text-sm font-bold text-slate-900">{p.full_name}</p>
                  <p className="text-xs text-slate-600">MRN: {p.patient_mrn || "-"}</p>
                  <p className="text-xs text-slate-500">{p.phone_number || "No phone"}</p>
                </button>
              );
            })}
          </div>
        </aside>

        <section className="space-y-4">
          {error ? <p className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</p> : null}

          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            {loadingHistory ? <p className="text-sm text-slate-500">Loading patient history...</p> : null}
            {!loadingHistory && historyData?.patient ? (
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4 text-sm">
                <Stat label="Patient" value={historyData.patient.full_name || "-"} />
                <Stat label="MRN" value={historyData.patient.patient_mrn || "-"} />
                <Stat label="Current Status" value={patientStatus} />
                <Stat
                  label="Total Records"
                  value={String(
                    admissions.length +
                    appointments.length +
                    medications.length +
                    clinicalUpdates.length +
                    visitLogs.length +
                    labRequests.length +
                    imagingRecords.length +
                    aiDiagnoses.length +
                    vitals.length
                  )}
                />
              </div>
            ) : null}
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <HistoryCard title="Clinical Updates" items={clinicalUpdates} fields={["update_type", "title", "details", "created_at"]} />
            <HistoryCard title="Medications" items={medications} fields={["medication_name", "dosage", "frequency", "duration_days", "pharmacy_status", "created_at"]} />
            <HistoryCard title="Admissions" items={admissions} fields={["admission_date", "status", "bed_id", "admitted_by_staff_id"]} />
            <HistoryCard title="OPD Appointments" items={appointments} fields={["appointment_datetime", "status", "doctor_id", "reason"]} />
            <HistoryCard title="Lab Requests" items={labRequests} fields={["test_name", "status", "ordered_by_staff_id", "created_at"]} />
            <HistoryCard title="Imaging Records" items={imagingRecords} fields={["study_title", "modality", "body_part", "status", "created_at"]} />
            <HistoryCard title="AI Diagnoses" items={aiDiagnoses} fields={["diagnosis_text", "confidence_score", "model_name", "created_at"]} />
            <HistoryCard title="Nursing Vitals" items={vitals} fields={["blood_pressure_systolic", "blood_pressure_diastolic", "pulse_rate", "body_temperature", "respiratory_rate", "oxygen_saturation", "weight_kg", "bmi", "chief_complaint", "recorded_at"]} />
            <HistoryCard title="Reception Visit Logs" items={visitLogs} fields={["visit_type", "chief_complaint", "status", "created_at"]} />
          </div>
        </section>
      </div>
    </DoctorWorkspaceLayout>
  );
}

function Stat({ label, value }) {
  return (
    <div className="rounded-xl border border-slate-200 p-3">
      <p className="text-xs font-bold uppercase tracking-[0.1em] text-slate-500">{label}</p>
      <p className="mt-1 font-semibold text-slate-900">{value}</p>
    </div>
  );
}

function HistoryCard({ title, items, fields }) {
  return (
    <article className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <h3 className="text-base font-bold">{title} ({items.length})</h3>
      {items.length === 0 ? <p className="mt-2 text-sm text-slate-500">No records found.</p> : null}
      <div className="mt-3 space-y-2 max-h-72 overflow-auto pr-1">
        {items.map((item, idx) => (
          <div key={idx} className="rounded-lg border border-slate-200 p-3 text-sm">
            {fields.map((f) => (
              <p key={f} className="text-slate-700">
                <span className="font-semibold">{titleCase(f)}:</span> {String(item?.[f] ?? "-")}
              </p>
            ))}
          </div>
        ))}
      </div>
    </article>
  );
}


