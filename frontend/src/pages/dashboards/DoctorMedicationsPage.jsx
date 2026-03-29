import { useEffect, useMemo, useState } from "react";
import { api } from "../../lib/api";
import DoctorWorkspaceLayout from "../../components/dashboards/DoctorWorkspaceLayout";

export default function DoctorMedicationsPage() {
  const [patients, setPatients] = useState([]);
  const [patientQuery, setPatientQuery] = useState("");
  const [loadingPatients, setLoadingPatients] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const [form, setForm] = useState({
    patient_id: "",
    medication_name: "",
    dosage: "",
    frequency: "",
    duration_days: "",
    instructions: "",
  });

  useEffect(() => {
    let active = true;
    const loadPatients = async () => {
      try {
        const res = await api.get("/patients/", { params: { limit: 300 } });
        if (!active) return;
        setPatients(res.data.items || []);
      } catch {
        if (!active) return;
        setError("Unable to load patients.");
      } finally {
        if (active) setLoadingPatients(false);
      }
    };
    loadPatients();
    return () => {
      active = false;
    };
  }, []);

  const canSubmit = useMemo(() => form.patient_id && form.medication_name.trim(), [form]);

  const filteredPatients = useMemo(() => {
    const q = patientQuery.trim().toLowerCase();
    if (!q) return patients;
    return patients.filter((p) => {
      const name = String(p.full_name || "").toLowerCase();
      const mrn = String(p.patient_mrn || "").toLowerCase();
      return name.includes(q) || mrn.includes(q);
    });
  }, [patients, patientQuery]);

  const onChange = (e) => setForm((prev) => ({ ...prev, [e.target.name]: e.target.value }));

  const onSubmit = async (e) => {
    e.preventDefault();
    if (!canSubmit) return;

    setSubmitting(true);
    setError("");
    setSuccess("");

    try {
      await api.post("/doctor/medications", {
        patient_id: Number(form.patient_id),
        medication_name: form.medication_name.trim(),
        dosage: form.dosage || null,
        frequency: form.frequency || null,
        duration_days: form.duration_days ? Number(form.duration_days) : null,
        instructions: form.instructions || null,
      });

      setSuccess("Medication sent to pharmacy queue and patient care feed.");
      setForm({
        patient_id: "",
        medication_name: "",
        dosage: "",
        frequency: "",
        duration_days: "",
        instructions: "",
      });
    } catch (err) {
      setError(err?.response?.data?.detail || "Unable to create medication order.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <DoctorWorkspaceLayout title="Doctor Medications" subtitle="Create medication orders for pharmacy and patient.">
      <div className="max-w-3xl rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <form className="space-y-4" onSubmit={onSubmit}>
          {error ? <p className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</p> : null}
          {success ? <p className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-700">{success}</p> : null}

          <label className="block space-y-1">
            <span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Search Patient</span>
            <input
              value={patientQuery}
              onChange={(e) => setPatientQuery(e.target.value)}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-cyan-500"
              placeholder="Search by name or MRN"
            />
          </label>

          <label className="block space-y-1">
            <span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Patient</span>
            <select
              name="patient_id"
              value={form.patient_id}
              onChange={onChange}
              disabled={loadingPatients}
              className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-cyan-500"
              required
            >
              <option value="">{loadingPatients ? "Loading patients..." : "Select patient"}</option>
              {filteredPatients.map((p) => (
                <option key={p.patient_id} value={p.patient_id}>
                  {p.full_name} (MRN: {p.patient_mrn})
                </option>
              ))}
            </select>
          </label>

          <Input label="Medication Name" name="medication_name" value={form.medication_name} onChange={onChange} required />
          <Input label="Dosage" name="dosage" value={form.dosage} onChange={onChange} placeholder="e.g., 500mg" />
          <Input label="Frequency" name="frequency" value={form.frequency} onChange={onChange} placeholder="e.g., Twice daily" />
          <Input label="Duration (Days)" name="duration_days" value={form.duration_days} onChange={onChange} type="number" min="1" />

          <label className="block space-y-1">
            <span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Instructions</span>
            <textarea
              name="instructions"
              value={form.instructions}
              onChange={onChange}
              rows={4}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-cyan-500"
              placeholder="Special instruction for pharmacy and patient"
            />
          </label>

          <button
            type="submit"
            disabled={!canSubmit || submitting}
            className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-cyan-700 disabled:cursor-not-allowed disabled:opacity-70"
          >
            {submitting ? "Saving..." : "Send Medication"}
          </button>
        </form>
      </div>
    </DoctorWorkspaceLayout>
  );
}

function Input({ label, ...props }) {
  return (
    <label className="block space-y-1">
      <span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">{label}</span>
      <input
        {...props}
        className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-cyan-500"
      />
    </label>
  );
}
