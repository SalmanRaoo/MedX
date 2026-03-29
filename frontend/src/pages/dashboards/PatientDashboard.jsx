import { useEffect, useMemo, useState } from "react";
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
        const res = isPatientRole
          ? await api.get("/patient/my-feed")
          : await api.get("/patient/care-feed", { params: { patient_id: Number(patientId) } });

        if (!active) return;
        setFeed({
          patient: res.data.patient || null,
          medications: res.data.medications || [],
          clinical_updates: res.data.clinical_updates || [],
        });
      } catch (err) {
        if (!active) return;
        setError(err?.response?.data?.detail || "Unable to load patient care feed.");
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
      { title: "Patient", text: feed.patient?.full_name || "-" },
    ],
    [feed]
  );

  return (
    <>
      <RoleDashboardShell
        title="Patient Dashboard"
        subtitle="See diagnosis, procedures, and medications added by doctors."
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

          <div className="grid gap-5 lg:grid-cols-2">
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
          </div>
        </div>
      </section>
    </>
  );
}
