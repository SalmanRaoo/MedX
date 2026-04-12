import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../lib/api";
import ReceptionWorkspaceLayout from "../../components/dashboards/ReceptionWorkspaceLayout";

export default function ReceptionPatientsPage() {
  const [patients, setPatients] = useState([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [receiptData, setReceiptData] = useState(null);
  const formRef = useRef(null);

  const [form, setForm] = useState({
    full_name: "",
    patient_mrn: "",
    dob: "",
    gender: "",
    phone_number: "",
    visit_type: "OPD",
    service_fee: "",
    procedure_tag: "Patient Registration",
    chief_complaint: "",
  });

  const fetchPatients = async () => {
    try {
      const [patientsRes, settingsRes] = await Promise.all([
        api.get("/patients/", { params: { limit: 200 } }),
        api.get("/settings").catch(() => ({ data: {} })),
      ]);
      setPatients(patientsRes.data.items || []);
      const defaultFee = Number(settingsRes?.data?.service_pricing?.patient_registration_fee || 0);
      setForm((prev) => (prev.service_fee === "" ? { ...prev, service_fee: String(defaultFee) } : prev));
    } catch (err) {
      setError(err?.response?.data?.detail || "Unable to load patients");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchPatients();
  }, []);

  const canSubmit = useMemo(() => form.full_name.trim(), [form.full_name]);

  const onChange = (e) => setForm((p) => ({ ...p, [e.target.name]: e.target.value }));

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

    const index = focusables.indexOf(e.target);
    if (index >= 0 && index < focusables.length - 1) {
      focusables[index + 1].focus();
    }
  };

  const printReceipt = async () => {
    if (!receiptData) return;
    let settingsMeta = {};
    try {
      const { data } = await api.get("/settings");
      settingsMeta = data?.hospital_metadata || {};
    } catch {
      settingsMeta = {};
    }

    const hospitalName = settingsMeta.hospital_name || receiptData?.receipt?.hospital_name || "MedX Hospital";
    const hospitalAddress = settingsMeta.address || receiptData?.receipt?.hospital_address || "-";
    const hospitalLogo = settingsMeta.logo_url || receiptData?.receipt?.hospital_logo_url || "";
    const popup = window.open("", "_blank", "width=900,height=900");
    if (!popup) return;

    popup.document.write(`
      <html>
        <head>
          <title>Patient Registration Receipt</title>
          <style>
            @page { size: A4; margin: 14mm; }
            * { box-sizing: border-box; }
            body { margin: 0; font-family: "Segoe UI", Arial, sans-serif; color: #0f172a; background: #eef2ff; }
            .sheet { background: #ffffff; border: 1px solid #dbe4ff; border-radius: 16px; overflow: hidden; }
            .topbar { background: linear-gradient(120deg, #0f172a, #0e7490); color: #fff; padding: 18px 22px; display: flex; justify-content: space-between; align-items: center; }
            .brand h1 { margin: 0; font-size: 20px; letter-spacing: 0.02em; }
            .brand p { margin: 4px 0 0; font-size: 12px; opacity: 0.9; }
            .logo { width:40px; height:40px; border-radius:999px; background:#ffffff; border:1px solid rgba(255,255,255,0.3); object-fit:cover; }
            .badge { background: rgba(255,255,255,0.18); border: 1px solid rgba(255,255,255,0.35); border-radius: 999px; padding: 6px 12px; font-size: 11px; font-weight: 700; }
            .body { padding: 20px 22px; }
            .meta { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; margin-bottom: 14px; }
            .meta .tile { border: 1px solid #e2e8f0; border-radius: 10px; padding: 10px 12px; background: #f8fafc; }
            .label { font-size: 11px; font-weight: 700; text-transform: uppercase; color: #64748b; letter-spacing: 0.08em; }
            .value { margin-top: 6px; font-size: 13px; font-weight: 700; color: #0f172a; }
            .card { border: 1px solid #e2e8f0; border-radius: 12px; padding: 14px; margin-top: 12px; }
            .card h3 { margin: 0 0 10px; font-size: 14px; }
            .grid { display: grid; grid-template-columns: 160px 1fr; row-gap: 8px; column-gap: 12px; font-size: 13px; }
            .key { color: #475569; font-weight: 600; }
            .cred { border: 1px dashed #0e7490; border-radius: 10px; padding: 12px; background: #ecfeff; }
            .cred .row { margin-bottom: 8px; font-size: 13px; }
            .foot { margin-top: 14px; font-size: 11px; color: #64748b; text-align: center; }
          </style>
        </head>
        <body>
          <div class="sheet">
            <div class="topbar">
              <div class="brand">
                <h1>${hospitalName}</h1>
                <p>${hospitalAddress}</p>
                <p>Patient Registration Receipt</p>
              </div>
              ${hospitalLogo ? `<img src="${hospitalLogo}" alt="Hospital Logo" class="logo" />` : ""}
              <div class="badge">Official Receipt</div>
            </div>

            <div class="body">
              <div class="meta">
                <div class="tile">
                  <div class="label">Receipt No</div>
                  <div class="value">${receiptData.receipt.receipt_no}</div>
                </div>
                <div class="tile">
                  <div class="label">Created At</div>
                  <div class="value">${receiptData.receipt.created_at}</div>
                </div>
                <div class="tile">
                  <div class="label">Hospital ID</div>
                  <div class="value">${receiptData.receipt.hospital_id}</div>
                </div>
              </div>

              <div class="card">
                <h3>Patient Details</h3>
                <div class="grid">
                  <div class="key">Patient Name</div><div>${receiptData.receipt.patient_name}</div>
                  <div class="key">Patient MRN</div><div>${receiptData.receipt.patient_mrn}</div>
                  <div class="key">Patient ID</div><div>${receiptData.receipt.patient_id}</div>
                  <div class="key">Visit Type</div><div>${receiptData.receipt.visit_type || "OPD"}</div>
                  <div class="key">Service Type</div><div>${receiptData.receipt.service_type || "PATIENT_REGISTRATION"}</div>
                  <div class="key">Procedure Tag</div><div>${receiptData.receipt.procedure_tag || "-"}</div>
                  <div class="key">Service Fee</div><div>PKR ${Number(receiptData.receipt.service_fee || 0).toFixed(2)}</div>
                  <div class="key">Invoice Number</div><div>${receiptData.receipt.invoice_number || "-"}</div>
                  <div class="key">Billing Status</div><div>${receiptData.receipt.billing_status || "-"}</div>
                  <div class="key">Chief Complaint</div><div>${receiptData.receipt.chief_complaint || "-"}</div>
                </div>
              </div>

              <div class="card">
                <h3>Portal Credentials</h3>
                <div class="cred">
                  <div class="row"><strong>Email:</strong> ${receiptData.portal_credentials.email}</div>
                  <div class="row"><strong>Temporary Password:</strong> ${receiptData.portal_credentials.temporary_password}</div>
                </div>
              </div>

              <div class="foot">Patient should change temporary password after first login.</div>
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
    setReceiptData(null);

    try {
      const res = await api.post("/reception/patients/register-portal-auto", {
        full_name: form.full_name.trim(),
        patient_mrn: form.patient_mrn.trim() || null,
        dob: form.dob || null,
        gender: form.gender || null,
        phone_number: form.phone_number || null,
        visit_type: form.visit_type || "OPD",
        service_fee: Number(form.service_fee || 0),
        procedure_tag: form.procedure_tag || "Patient Registration",
        chief_complaint: form.chief_complaint || null,
      });

      setReceiptData(res.data);
      setSuccess("Patient added and portal credentials generated.");
      setForm((p) => ({ ...p, full_name: "", patient_mrn: "", dob: "", gender: "", phone_number: "", visit_type: "OPD", procedure_tag: "Patient Registration", chief_complaint: "" }));
      await fetchPatients();
    } catch (err) {
      setError(err?.response?.data?.detail || "Unable to add patient");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <ReceptionWorkspaceLayout
        title="Reception Patient Intake"
        subtitle="Register patient and auto-generate portal credentials."
    >
      <section>
        <div className="mb-4 grid gap-4 md:grid-cols-3">
          <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
            <p className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Total Patients</p>
            <p className="mt-1 text-2xl font-black text-slate-900">{patients.length}</p>
          </div>
          <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
            <p className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Portal Account</p>
            <p className="mt-1 text-sm text-slate-600">Auto email + temporary password.</p>
          </div>
          <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
            <p className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Receipt</p>
            <p className="mt-1 text-sm text-slate-600">Includes procedure tag and billing details.</p>
          </div>
        </div>

        <div className="grid gap-5 lg:grid-cols-2">
          <article className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <h3 className="text-lg font-bold mb-3">Add Patient + Portal</h3>
            {error ? <p className="mb-3 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</p> : null}
            {success ? <p className="mb-3 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-700">{success}</p> : null}

            <form ref={formRef} className="space-y-3" onSubmit={onSubmit} onKeyDown={handleEnterNext}>
              <Input label="Full Name" name="full_name" value={form.full_name} onChange={onChange} required />
              <Input label="Patient MRN (Optional)" name="patient_mrn" value={form.patient_mrn} onChange={onChange} placeholder="Auto if empty" />
              <Input label="Date of Birth" name="dob" type="date" value={form.dob} onChange={onChange} />

              <label className="block space-y-1">
                <span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Gender</span>
                <select
                  name="gender"
                  value={form.gender}
                  onChange={onChange}
                  className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-cyan-500"
                >
                  <option value="">Select</option>
                  <option value="MALE">Male</option>
                  <option value="FEMALE">Female</option>
                  <option value="OTHER">Other</option>
                </select>
              </label>

              <Input label="Phone Number" name="phone_number" value={form.phone_number} onChange={onChange} />

              <label className="block space-y-1">
                <span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Visit Type</span>
                <select
                  name="visit_type"
                  value={form.visit_type}
                  onChange={onChange}
                  className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-cyan-500"
                >
                  <option value="OPD">OPD</option>
                  <option value="EMERGENCY">Emergency</option>
                  <option value="FOLLOW_UP">Follow Up</option>
                  <option value="WALK_IN">Walk In</option>
                </select>
              </label>

              <Input label="Price (PKR)" name="service_fee" value={form.service_fee} onChange={onChange} type="number" min="0" step="0.01" />
              <Input label="Procedure Tag" name="procedure_tag" value={form.procedure_tag} onChange={onChange} placeholder="Patient Registration" />

              <label className="block space-y-1">
                <span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Chief Complaint</span>
                <textarea
                  name="chief_complaint"
                  value={form.chief_complaint}
                  onChange={onChange}
                  rows={3}
                  className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-cyan-500"
                  placeholder="Short complaint/reason for visit"
                />
              </label>

              <div className="flex gap-2 flex-wrap">
                <button
                  type="submit"
                  disabled={!canSubmit || submitting}
                  className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-cyan-700 disabled:cursor-not-allowed disabled:opacity-70"
                >
                  {submitting ? "Saving..." : "Register Patient"}
                </button>
                {receiptData ? (
                  <button type="button" onClick={printReceipt} className="rounded-lg border px-4 py-2 text-sm font-semibold text-slate-700">
                    Print Receipt
                  </button>
                ) : null}
                <Link to="/dashboard/reception" className="rounded-lg border px-4 py-2 text-sm font-semibold text-slate-700">
                  Back
                </Link>
              </div>
            </form>

            {receiptData ? (
              <div className="mt-5 rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm">
                <p><strong>Receipt:</strong> {receiptData.receipt.receipt_no}</p>
                <p><strong>Portal Email:</strong> {receiptData.portal_credentials.email}</p>
                <p><strong>Temporary Password:</strong> {receiptData.portal_credentials.temporary_password}</p>
                <p><strong>Visit Type:</strong> {receiptData.receipt.visit_type || "OPD"}</p>
                <p><strong>Procedure Tag:</strong> {receiptData.receipt.procedure_tag || "-"}</p>
                <p><strong>Service Fee:</strong> PKR {Number(receiptData.receipt.service_fee || 0).toFixed(2)}</p>
                <p><strong>Invoice:</strong> {receiptData.receipt.invoice_number || "-"}</p>
                <p><strong>Billing Status:</strong> {receiptData.receipt.billing_status || "-"}</p>
                <p><strong>Chief Complaint:</strong> {receiptData.receipt.chief_complaint || "-"}</p>
              </div>
            ) : null}
          </article>

          <article className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm overflow-x-auto">
            <h3 className="text-lg font-bold mb-3">Recent Patients</h3>
            {loading ? <p className="text-sm text-slate-500">Loading...</p> : null}
            {!loading && patients.length === 0 ? <p className="text-sm text-slate-500">No patients yet.</p> : null}

            {patients.length > 0 ? (
              <table className="min-w-full text-sm">
                <thead className="text-left text-slate-500">
                  <tr>
                    <th className="py-2 pr-3">Name</th>
                    <th className="py-2 pr-3">MRN</th>
                    <th className="py-2 pr-3">Phone</th>
                    <th className="py-2 pr-3">DOB</th>
                  </tr>
                </thead>
                <tbody>
                  {patients.map((p) => (
                    <tr key={p.patient_id} className="border-t border-slate-100">
                      <td className="py-2 pr-3">{p.full_name}</td>
                      <td className="py-2 pr-3">{p.patient_mrn}</td>
                      <td className="py-2 pr-3">{p.phone_number || "-"}</td>
                      <td className="py-2 pr-3">{p.dob || "-"}</td>
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
      <input
        {...props}
        className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-cyan-500"
      />
    </label>
  );
}





