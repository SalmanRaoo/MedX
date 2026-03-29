import { useEffect, useMemo, useState } from "react";
import { api } from "../../lib/api";
import DoctorWorkspaceLayout from "../../components/dashboards/DoctorWorkspaceLayout";

export default function DoctorClinicalPage() {
  const [patients, setPatients] = useState([]);
  const [patientQuery, setPatientQuery] = useState("");
  const [loadingPatients, setLoadingPatients] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const [form, setForm] = useState({
    patient_id: "",
    update_type: "DIAGNOSIS",
    title: "",
    details: "",
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

  const canSubmit = useMemo(() => form.patient_id && form.update_type && form.title.trim(), [form]);

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
      await api.post("/doctor/clinical-updates", {
        patient_id: Number(form.patient_id),
        update_type: form.update_type,
        title: form.title.trim(),
        details: form.details || null,
      });
      setSuccess(`${form.update_type} sent to patient care feed.`);
      setForm({ patient_id: "", update_type: "DIAGNOSIS", title: "", details: "" });
    } catch (err) {
      setError(err?.response?.data?.detail || "Unable to save clinical update.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <DoctorWorkspaceLayout title="Diagnosis & Procedure" subtitle="Share diagnosis and procedures to patient timeline.">
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

          <label className="block space-y-1">
            <span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Type</span>
            <select
              name="update_type"
              value={form.update_type}
              onChange={onChange}
              className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-cyan-500"
            >
              <option value="DIAGNOSIS">Diagnosis</option>
              <option value="PROCEDURE">Procedure</option>
            </select>
          </label>

          <label className="block space-y-1">
            <span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Title</span>
            <input
              name="title"
              value={form.title}
              onChange={onChange}
              required
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-cyan-500"
              placeholder="Short title"
            />
          </label>

          <label className="block space-y-1">
            <span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Details</span>
            <textarea
              name="details"
              value={form.details}
              onChange={onChange}
              rows={5}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-cyan-500"
              placeholder="Enter clinical details"
            />
          </label>

          <button
            type="submit"
            disabled={!canSubmit || submitting}
            className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-cyan-700 disabled:cursor-not-allowed disabled:opacity-70"
          >
            {submitting ? "Saving..." : "Save Update"}
          </button>
        </form>
      </div>
    </DoctorWorkspaceLayout>
  );
}
