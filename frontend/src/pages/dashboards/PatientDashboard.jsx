import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import RoleDashboardShell from "../../components/dashboards/RoleDashboardShell";
import { api } from "../../lib/api";
import { getSessionUser } from "../../lib/auth";

export default function PatientDashboard() {
  const sessionUser = getSessionUser();
  const role = (sessionUser?.role_name || "").toUpperCase();
  const isPatientRole = role === "PATIENT";

  const [patients, setPatients] = useState([]);
  const [patientId, setPatientId] = useState("");
  const [feed, setFeed] = useState({ medications: [], clinical_updates: [], patient: null });
  const [sharedReports, setSharedReports] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (isPatientRole) return;
    let active = true;
    const loadPatients = async () => {
      try {
        const res = await api.get("/patients/", { params: { limit: 300 } });
        if (!active) return;
        const items = res.data.items || [];
        setPatients(items);
        if (items.length > 0) {
          setPatientId(String(items[0].patient_id));
        }
      } catch {
        if (!active) return;
        setError("Unable to load patients.");
      }
    };
    loadPatients();
    return () => {
      active = false;
    };
  }, [isPatientRole]);

  useEffect(() => {
    let active = true;
    const loadFeed = async () => {
      if (!isPatientRole && !patientId) return;
      setLoading(true);
      setError("");
      try {
        const [feedRes, sharedRes] = await Promise.all([
          isPatientRole
            ? api.get("/patient/my-feed")
            : api.get("/patient/care-feed", { params: { patient_id: Number(patientId) } }),
          isPatientRole
            ? api.get("/reports/shared", { params: { audience: "PATIENT", limit: 100 } })
            : api.get("/reports/shared", { params: { patient_id: Number(patientId), audience: "PATIENT", limit: 100 } }),
        ]);

        if (!active) return;
        setFeed({
          patient: feedRes.data.patient || null,
          medications: feedRes.data.medications || [],
          clinical_updates: feedRes.data.clinical_updates || [],
        });
        setSharedReports(sharedRes.data.items || []);
      } catch (err) {
        if (!active) return;
        setError(err?.response?.data?.detail || "Unable to load patient dashboard data.");
      } finally {
        if (active) setLoading(false);
      }
    };
    loadFeed();
    return () => {
      active = false;
    };
  }, [patientId, isPatientRole]);

  const cards = useMemo(
    () => [
      { title: "Medication Orders", text: String(feed.medications.length) },
      { title: "Diagnosis/Procedure", text: String(feed.clinical_updates.length) },
      { title: "Published Reports", text: String(sharedReports.length) },
      { title: "Patient", text: feed.patient?.full_name || "-" },
    ],
    [feed, sharedReports]
  );

  return (
    <>
      <RoleDashboardShell
        title="Patient Dashboard"
        subtitle="See diagnosis, procedures, medications, and laboratory AI reports instantly."
        cards={cards}
      />

      <section className="px-4 pb-10 sm:px-6 lg:px-8 -mt-2">
        <div className="mx-auto max-w-7xl space-y-5">
          {!isPatientRole ? (
            <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <label className="block space-y-1">
                <span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Patient</span>
                <select
                  value={patientId}
                  onChange={(e) => setPatientId(e.target.value)}
                  className="w-full max-w-md rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-cyan-500"
                >
                  {patients.map((p) => (
                    <option key={p.patient_id} value={p.patient_id}>
                      {p.full_name} (MRN: {p.patient_mrn})
                    </option>
                  ))}
                </select>
              </label>
            </div>
          ) : null}

          {error ? <p className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</p> : null}

          <div className="grid gap-5 lg:grid-cols-3">
            <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <h3 className="text-lg font-bold">Medications</h3>
              {loading ? <p className="text-sm text-slate-500 mt-3">Loading...</p> : null}
              {!loading && feed.medications.length === 0 ? <p className="text-sm text-slate-500 mt-3">No medications yet.</p> : null}
              <div className="mt-3 space-y-3">
                {feed.medications.map((m) => (
                  <article key={m.medication_order_id} className="rounded-lg border border-slate-100 p-3">
                    <p className="font-semibold">{m.medication_name}</p>
                    <p className="text-sm text-slate-600">{m.dosage || "-"} | {m.frequency || "-"} | {m.duration_days || "-"} days</p>
                    <p className="text-sm text-slate-600 mt-1">{m.instructions || "No instructions"}</p>
                  </article>
                ))}
              </div>
            </section>

            <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <h3 className="text-lg font-bold">Diagnosis / Procedures</h3>
              {loading ? <p className="text-sm text-slate-500 mt-3">Loading...</p> : null}
              {!loading && feed.clinical_updates.length === 0 ? <p className="text-sm text-slate-500 mt-3">No clinical updates yet.</p> : null}
              <div className="mt-3 space-y-3">
                {feed.clinical_updates.map((u) => (
                  <article key={u.update_id} className="rounded-lg border border-slate-100 p-3">
                    <p className="font-semibold">{u.update_type}: {u.title}</p>
                    <p className="text-sm text-slate-600 mt-1">{u.details || "No details"}</p>
                  </article>
                ))}
              </div>
            </section>

            <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <h3 className="text-lg font-bold">Published Reports (Lab + Imaging)</h3>
              {loading ? <p className="text-sm text-slate-500 mt-3">Loading...</p> : null}
              {!loading && sharedReports.length === 0 ? <p className="text-sm text-slate-500 mt-3">No shared reports yet.</p> : null}
              <div className="mt-3 space-y-3">
                {sharedReports.slice(0, 5).map((r) => (
                  <article key={r.shared_report_id} className="rounded-lg border border-slate-100 p-3">
                    <p className="font-semibold">{r.title || `${r.report_type} #${r.source_record_id}`}</p>
                    <p className="text-sm text-slate-600">{r.summary || "-"}</p>
                    <p className="text-xs text-slate-500 mt-1">{r.created_at}</p>
                  </article>
                ))}
              </div>
              <div className="mt-4">
                <Link
                  to="/dashboard/patient/reports"
                  className="inline-flex rounded-lg border border-cyan-600 px-4 py-2 text-sm font-semibold text-cyan-700 hover:bg-cyan-50"
                >
                  Open Full Reports Page
                </Link>
              </div>
            </section>
          </div>
        </div>
      </section>
    </>
  );
}
