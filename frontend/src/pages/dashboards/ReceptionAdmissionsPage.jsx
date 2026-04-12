import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../lib/api";
import ReceptionWorkspaceLayout from "../../components/dashboards/ReceptionWorkspaceLayout";
import { useHospitalSettings } from "../../context/HospitalSettingsContext";

export default function ReceptionAdmissionsPage() {
  const { settings } = useHospitalSettings();
  const [patients, setPatients] = useState([]);
  const [admissions, setAdmissions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [receipt, setReceipt] = useState(null);
  const formRef = useRef(null);

  const [form, setForm] = useState({
    patient_id: "",
    ward_name: "General",
    bed_number: "",
    admission_cost: "",
    admission_notes: "",
  });

  const fetchAll = async () => {
    try {
      const [patientsRes, admissionsRes] = await Promise.all([
        api.get("/patients/", { params: { limit: 300 } }),
        api.get("/reception/admissions", { params: { limit: 200 } }),
      ]);
      const patientItems = patientsRes.data.items || [];
      setPatients(patientItems);
      if (!form.patient_id && patientItems.length > 0) {
        setForm((p) => ({ ...p, patient_id: String(patientItems[0].patient_id) }));
      }
      setAdmissions(admissionsRes.data.items || []);
    } catch (err) {
      setError(err?.response?.data?.detail || "Unable to load admission data");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAll();
  }, []);

  const canSubmit = useMemo(() => form.patient_id && form.admission_cost !== "", [form.patient_id, form.admission_cost]);

  const onChange = (e) => setForm((prev) => ({ ...prev, [e.target.name]: e.target.value }));

  const handleEnterNext = (e) => {
    if (e.key !== "Enter") return;
    const tag = (e.target.tagName || "").toLowerCase();
    if (tag === "textarea") return;

    e.preventDefault();
    const formEl = formRef.current;
    if (!formEl) return;
    const focusables = Array.from(
      formEl.querySelectorAll("input, select, textarea, button")
    ).filter((el) => !el.disabled && el.type !== "hidden");

    const idx = focusables.indexOf(e.target);
    if (idx >= 0 && idx < focusables.length - 1) {
      focusables[idx + 1].focus();
    }
  };

  const printReceipt = async () => {
    if (!receipt) return;
    let settingsMeta = settings?.hospital_metadata || {};
    try {
      const { data } = await api.get("/settings");
      settingsMeta = data?.hospital_metadata || settingsMeta;
    } catch {
      // fallback to context / receipt snapshot
    }
    const hospitalName = settingsMeta.hospital_name || receipt.hospital_name || "MedX Hospital";
    const hospitalAddress = settingsMeta.address || receipt.hospital_address || "";
    const hospitalLogo = settingsMeta.logo_url || receipt.hospital_logo_url || "";

    const popup = window.open("", "_blank", "width=900,height=900");
    if (!popup) return;

    popup.document.write(`
      <html>
        <head>
          <title>Admission Receipt</title>
          <style>
            @page { size: A4; margin: 14mm; }
            * { box-sizing: border-box; }
            body { margin: 0; font-family: "Segoe UI", Arial, sans-serif; color: #0f172a; background: #f1f5f9; }
            .sheet { background: #fff; border: 1px solid #dbe4ff; border-radius: 16px; overflow: hidden; }
            .topbar { background: linear-gradient(120deg, #111827, #1d4ed8); color: #fff; padding: 18px 22px; display: flex; justify-content: space-between; align-items: center; gap: 14px; }
            .brand-wrap { display: flex; align-items: center; gap: 12px; }
            .brand-logo { width: 42px; height: 42px; border-radius: 10px; object-fit: cover; background: rgba(255,255,255,0.9); padding: 3px; }
            .brand h1 { margin: 0; font-size: 20px; }
            .brand p { margin: 4px 0 0; font-size: 12px; opacity: 0.9; }
            .badge { background: rgba(255,255,255,0.2); border: 1px solid rgba(255,255,255,0.35); border-radius: 999px; padding: 6px 12px; font-size: 11px; font-weight: 700; }
            .body { padding: 20px 22px; }
            .meta { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; margin-bottom: 14px; }
            .tile { border: 1px solid #e2e8f0; border-radius: 10px; padding: 10px 12px; background: #f8fafc; }
            .label { font-size: 11px; font-weight: 700; text-transform: uppercase; color: #64748b; letter-spacing: 0.08em; }
            .value { margin-top: 6px; font-size: 13px; font-weight: 700; color: #0f172a; }
            .card { border: 1px solid #e2e8f0; border-radius: 12px; padding: 14px; margin-top: 12px; }
            table { width: 100%; border-collapse: collapse; margin-top: 6px; font-size: 13px; }
            th, td { border-bottom: 1px solid #e2e8f0; padding: 8px 6px; text-align: left; }
            th { color: #475569; font-size: 11px; text-transform: uppercase; letter-spacing: 0.06em; }
            .cost { margin-top: 12px; padding: 12px; border-radius: 10px; background: #eff6ff; border: 1px solid #bfdbfe; font-weight: 700; color: #1e3a8a; }
            .foot { margin-top: 14px; font-size: 11px; color: #64748b; text-align: center; }
          </style>
        </head>
        <body>
          <div class="sheet">
            <div class="topbar">
              <div class="brand-wrap">
                ${hospitalLogo ? `<img src="${hospitalLogo}" alt="logo" class="brand-logo" />` : ""}
                <div class="brand">
                  <h1>${hospitalName}</h1>
                  <p>Reception Admission Desk</p>
                  ${hospitalAddress ? `<p>${hospitalAddress}</p>` : ""}
                </div>
              </div>
              <div class="badge">Admission Copy</div>
            </div>

            <div class="body">
              <div class="meta">
                <div class="tile">
                  <div class="label">Receipt No</div>
                  <div class="value">${receipt.receipt_no}</div>
                </div>
                <div class="tile">
                  <div class="label">Created At</div>
                  <div class="value">${receipt.created_at}</div>
                </div>
              </div>

              <div class="card">
                <table>
                  <thead>
                    <tr><th>Field</th><th>Value</th></tr>
                  </thead>
                  <tbody>
                    <tr><td>Patient Name</td><td>${receipt.patient_name}</td></tr>
                    <tr><td>Patient MRN</td><td>${receipt.patient_mrn}</td></tr>
                    <tr><td>Ward</td><td>${receipt.ward_name}</td></tr>
                    <tr><td>Bed</td><td>${receipt.bed_number}</td></tr>
                  </tbody>
                </table>

                <div class="cost">Admission Price: PKR ${Number(receipt.admission_cost || 0).toFixed(2)}</div>
              </div>

              <div class="foot">This is a computer-generated admission receipt from MedX.</div>
            </div>
          </div>
        </body>
      </html>
    `);
    popup.document.close();
    popup.focus();
    popup.print();
  };

  const onSubmit = async (e) => {
    e.preventDefault();
    if (!canSubmit) return;

    setSubmitting(true);
    setError("");
    setSuccess("");
    setReceipt(null);

    try {
      const res = await api.post("/reception/admissions/register", {
        patient_id: Number(form.patient_id),
        ward_name: form.ward_name || "General",
        bed_number: form.bed_number || null,
        admission_cost: Number(form.admission_cost || 0),
        admission_notes: form.admission_notes || null,
      });
      setReceipt(res.data.receipt || null);
      setSuccess("Admission recorded successfully.");
      setForm((p) => ({ ...p, bed_number: "", admission_cost: "", admission_notes: "" }));
      const listRes = await api.get("/reception/admissions", { params: { limit: 200 } });
      setAdmissions(listRes.data.items || []);
    } catch (err) {
      setError(err?.response?.data?.detail || "Unable to save admission.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <ReceptionWorkspaceLayout
        title="Reception Admissions"
        subtitle="Enter admitted patient details and admission cost."
    >
      <section>
        <div className="mb-4 grid gap-4 md:grid-cols-3">
          <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
            <p className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Admissions</p>
            <p className="mt-1 text-2xl font-black text-slate-900">{admissions.length}</p>
          </div>
          <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
            <p className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Ward Capture</p>
            <p className="mt-1 text-sm text-slate-600">Bed and ward assignment.</p>
          </div>
          <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
            <p className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Receipt</p>
            <p className="mt-1 text-sm text-slate-600">Printable admission receipt.</p>
          </div>
        </div>

        <div className="grid gap-5 lg:grid-cols-2">
          <article className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <h3 className="text-lg font-bold mb-3">Admit Patient</h3>
            {error ? <p className="mb-3 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</p> : null}
            {success ? <p className="mb-3 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-700">{success}</p> : null}

            <form ref={formRef} className="space-y-3" onSubmit={onSubmit} onKeyDown={handleEnterNext}>
              <label className="block space-y-1">
                <span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Patient</span>
                <select
                  name="patient_id"
                  value={form.patient_id}
                  onChange={onChange}
                  className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-cyan-500"
                >
                  {patients.map((p) => (
                    <option key={p.patient_id} value={p.patient_id}>
                      {p.full_name} (MRN: {p.patient_mrn})
                    </option>
                  ))}
                </select>
              </label>

              <Input label="Ward Name" name="ward_name" value={form.ward_name} onChange={onChange} />
              <Input label="Bed Number (Optional)" name="bed_number" value={form.bed_number} onChange={onChange} placeholder="Auto if empty" />
              <Input label="Admission Price (PKR)" name="admission_cost" value={form.admission_cost} onChange={onChange} type="number" min="0" step="0.01" required />

              <label className="block space-y-1">
                <span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Details</span>
                <textarea
                  name="admission_notes"
                  value={form.admission_notes}
                  onChange={onChange}
                  rows={4}
                  className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-cyan-500"
                />
              </label>

              <div className="flex gap-2 flex-wrap">
                <button
                  type="submit"
                  disabled={!canSubmit || submitting}
                  className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-cyan-700 disabled:cursor-not-allowed disabled:opacity-70"
                >
                  {submitting ? "Saving..." : "Save Admission"}
                </button>
                {receipt ? (
                  <button type="button" onClick={printReceipt} className="rounded-lg border px-4 py-2 text-sm font-semibold text-slate-700">
                    Print Receipt
                  </button>
                ) : null}
                <Link to="/dashboard/reception" className="rounded-lg border px-4 py-2 text-sm font-semibold text-slate-700">
                  Back
                </Link>
              </div>
            </form>
          </article>

          <article className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm overflow-x-auto">
            <h3 className="text-lg font-bold mb-3">Recent Admissions</h3>
            {loading ? <p className="text-sm text-slate-500">Loading...</p> : null}
            {!loading && admissions.length === 0 ? <p className="text-sm text-slate-500">No admissions yet.</p> : null}

            {admissions.length > 0 ? (
              <table className="min-w-full text-sm">
                <thead className="text-left text-slate-500">
                  <tr>
                    <th className="py-2 pr-3">Patient</th>
                    <th className="py-2 pr-3">Ward/Bed</th>
                    <th className="py-2 pr-3">Cost</th>
                    <th className="py-2 pr-3">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {admissions.map((a) => (
                    <tr key={a.admission_id} className="border-t border-slate-100">
                      <td className="py-2 pr-3">{a.patient_name}</td>
                      <td className="py-2 pr-3">{a.ward_name || "-"} / {a.bed_number || "-"}</td>
                      <td className="py-2 pr-3">PKR {Number(a.admission_cost || 0).toFixed(2)}</td>
                      <td className="py-2 pr-3">{a.status}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : null}
          </article>
        </div>
      </section>
    </ReceptionWorkspaceLayout>
  );
}

function Input({ label, ...props }) {
  return (
    <label className="block space-y-1">
      <span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">{label}</span>
      <input {...props} className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-cyan-500" />
    </label>
  );
}

