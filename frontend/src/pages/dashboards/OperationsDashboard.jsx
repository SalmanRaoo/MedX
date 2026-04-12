import { useEffect, useMemo, useState } from "react";
import { Activity, BedDouble, Building2, Loader2, PlusCircle } from "lucide-react";
import { api } from "../../lib/api";
import OperationsWorkspaceLayout from "../../components/dashboards/OperationsWorkspaceLayout";

function statusChip(status) {
  const s = String(status || "").toUpperCase();
  if (s === "FREE" || s === "AVAILABLE") return "bg-emerald-100 text-emerald-700 border-emerald-200";
  if (s === "OCCUPIED" || s === "SCHEDULED") return "bg-rose-100 text-rose-700 border-rose-200";
  return "bg-amber-100 text-amber-700 border-amber-200";
}

function bedTileClass(status) {
  const s = String(status || "").toUpperCase();
  if (s === "FREE") return "border-emerald-200 bg-emerald-50 text-emerald-800";
  if (s === "OCCUPIED") return "border-rose-200 bg-rose-50 text-rose-800";
  return "border-amber-200 bg-amber-50 text-amber-800";
}

export default function OperationsDashboard() {
  const [units, setUnits] = useState([]);
  const [beds, setBeds] = useState([]);
  const [patients, setPatients] = useState([]);
  const [auditItems, setAuditItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [savingUnit, setSavingUnit] = useState(false);
  const [savingBed, setSavingBed] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [wardFilter, setWardFilter] = useState("ALL");
  const [patientSearch, setPatientSearch] = useState("");
  const [bedModal, setBedModal] = useState({ open: false, bed: null, status: "FREE", patient_id: "" });
  const [unitForm, setUnitForm] = useState({
    unit_name: "",
    unit_type: "WARD",
    total_beds: 10,
    status: "AVAILABLE",
  });
  const [unitDrafts, setUnitDrafts] = useState({});

  const loadAll = async () => {
    setLoading(true);
    setError("");
    try {
      const [unitsRes, bedsRes, auditRes] = await Promise.all([
        api.get("/operations/units"),
        api.get("/operations/beds", { params: { limit: 1500 } }),
        api.get("/operations/activity-audit", { params: { limit: 60 } }),
      ]);
      const nextUnits = unitsRes.data?.items || [];
      setUnits(nextUnits);
      setBeds(bedsRes.data?.items || []);
      setAuditItems(auditRes.data?.items || []);
      const drafts = {};
      nextUnits.forEach((u) => {
        drafts[u.unit_id] = {
          unit_name: u.unit_name,
          total_beds: u.total_beds || 0,
          status: u.status || (u.unit_type === "OT" ? "AVAILABLE" : "ACTIVE"),
        };
      });
      setUnitDrafts(drafts);
    } catch (err) {
      setError(err?.response?.data?.detail || "Unable to load operations dashboard.");
    } finally {
      setLoading(false);
    }
  };

  const loadPatients = async (query = "") => {
    try {
      const { data } = await api.get("/nurse/patient-search", { params: { q: query, limit: 180 } });
      setPatients(data?.items || []);
    } catch {
      setPatients([]);
    }
  };

  useEffect(() => {
    loadAll();
    loadPatients("");
  }, []);

  useEffect(() => {
    const t = setTimeout(() => {
      loadPatients(patientSearch);
    }, 220);
    return () => clearTimeout(t);
  }, [patientSearch]);

  useEffect(() => {
    const token = localStorage.getItem("medx_token");
    if (!token) return;
    const ws = new WebSocket(`ws://localhost:8000/ws/bed-sync?token=${encodeURIComponent(token)}`);
    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (["bed_status_changed", "bed_transfer", "unit_config_updated"].includes(msg?.event)) {
          loadAll();
        }
      } catch {
        // ignore malformed ws event
      }
    };
    return () => ws.close();
  }, []);

  const wardOptions = useMemo(() => {
    const uniq = [...new Set(beds.map((b) => b.ward_name).filter(Boolean))];
    return ["ALL", ...uniq];
  }, [beds]);

  const filteredBeds = useMemo(() => {
    if (wardFilter === "ALL") return beds;
    return beds.filter((b) => b.ward_name === wardFilter);
  }, [beds, wardFilter]);

  const createUnit = async (e) => {
    e.preventDefault();
    setSavingUnit(true);
    setError("");
    setSuccess("");
    try {
      await api.post("/operations/units", {
        unit_name: unitForm.unit_name,
        unit_type: unitForm.unit_type,
        total_beds: Number(unitForm.total_beds || 0),
        status: unitForm.status,
      });
      setUnitForm({ unit_name: "", unit_type: "WARD", total_beds: 10, status: "AVAILABLE" });
      setSuccess("Operational unit created.");
      await loadAll();
    } catch (err) {
      setError(err?.response?.data?.detail || "Unable to create unit.");
    } finally {
      setSavingUnit(false);
    }
  };

  const updateUnit = async (unit) => {
    const draft = unitDrafts[unit.unit_id] || {};
    setSavingUnit(true);
    setError("");
    setSuccess("");
    try {
      await api.put(`/operations/units/${unit.unit_id}`, {
        unit_name: draft.unit_name,
        total_beds: unit.unit_type === "OT" ? undefined : Number(draft.total_beds || 0),
        status: draft.status,
      });
      setSuccess(`Unit ${unit.unit_name} updated.`);
      await loadAll();
    } catch (err) {
      setError(err?.response?.data?.detail || "Unable to update unit.");
    } finally {
      setSavingUnit(false);
    }
  };

  const openBedModal = (bed) => {
    setBedModal({
      open: true,
      bed,
      status: bed.status || "FREE",
      patient_id: bed.current_patient_id ? String(bed.current_patient_id) : "",
    });
  };

  const saveBedStatus = async () => {
    if (!bedModal.bed) return;
    setSavingBed(true);
    setError("");
    setSuccess("");
    try {
      await api.post(`/operations/beds/${bedModal.bed.bed_id}/status`, {
        status: bedModal.status,
        patient_id: bedModal.status === "OCCUPIED" ? Number(bedModal.patient_id || 0) : null,
      });
      setBedModal({ open: false, bed: null, status: "FREE", patient_id: "" });
      setSuccess("Bed status updated.");
      await loadAll();
    } catch (err) {
      setError(err?.response?.data?.detail || "Unable to update bed.");
    } finally {
      setSavingBed(false);
    }
  };

  return (
    <OperationsWorkspaceLayout
      title="Operations Unit Configuration"
      subtitle="Configure OT/ICU/Wards, manage bed occupancy grid, and monitor live operational audit activity."
    >
      {error ? <p className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</p> : null}
      {success ? <p className="mt-3 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{success}</p> : null}

      <section className="mt-4 rounded-[32px] border border-slate-200 bg-white p-6 shadow-sm">
        <h3 className="text-lg font-bold">Add Operational Unit</h3>
        <form onSubmit={createUnit} className="mt-3 grid gap-3 md:grid-cols-4">
          <input
            value={unitForm.unit_name}
            onChange={(e) => setUnitForm((p) => ({ ...p, unit_name: e.target.value }))}
            placeholder="Unit name (e.g., ICU-A)"
            className="rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-teal-500"
            required
          />
          <select
            value={unitForm.unit_type}
            onChange={(e) => setUnitForm((p) => ({ ...p, unit_type: e.target.value }))}
            className="rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-teal-500"
          >
            <option value="WARD">WARD</option>
            <option value="ICU">ICU</option>
            <option value="OT">OT</option>
          </select>
          {unitForm.unit_type !== "OT" ? (
            <input
              type="number"
              min="1"
              value={unitForm.total_beds}
              onChange={(e) => setUnitForm((p) => ({ ...p, total_beds: e.target.value }))}
              placeholder="Total beds"
              className="rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-teal-500"
            />
          ) : (
            <select
              value={unitForm.status}
              onChange={(e) => setUnitForm((p) => ({ ...p, status: e.target.value }))}
              className="rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-teal-500"
            >
              <option value="AVAILABLE">AVAILABLE</option>
              <option value="SCHEDULED">SCHEDULED</option>
            </select>
          )}
          <button
            type="submit"
            disabled={savingUnit}
            className="inline-flex items-center justify-center gap-2 rounded-xl bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-teal-700 disabled:opacity-60"
          >
            <PlusCircle className="h-4 w-4" /> {savingUnit ? "Saving..." : "Add Unit"}
          </button>
        </form>
      </section>

      <section className="mt-5 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {units.map((unit) => {
          const draft = unitDrafts[unit.unit_id] || {};
          const summary = unit.bed_summary || {};
          return (
            <article key={unit.unit_id} className="rounded-[32px] border border-slate-200 bg-white p-5 shadow-sm">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="text-lg font-black tracking-tight">{unit.unit_name}</p>
                  <p className="text-xs uppercase tracking-[0.12em] text-slate-500">{unit.unit_type}</p>
                </div>
                <span className={`rounded-full border px-3 py-1 text-xs font-bold ${statusChip(unit.status)}`}>{unit.status}</span>
              </div>
              {unit.unit_type !== "OT" ? (
                <div className="mt-3 rounded-xl border border-slate-200 bg-slate-50 p-3 text-xs">
                  <p className="text-emerald-700">Free: {summary.free_beds || 0}</p>
                  <p className="text-rose-700">Occupied: {summary.occupied_beds || 0}</p>
                  <p className="text-amber-700">Cleaning: {summary.cleaning_beds || 0}</p>
                </div>
              ) : null}
              <div className="mt-3 space-y-2">
                <input
                  value={draft.unit_name || ""}
                  onChange={(e) =>
                    setUnitDrafts((prev) => ({
                      ...prev,
                      [unit.unit_id]: { ...(prev[unit.unit_id] || {}), unit_name: e.target.value },
                    }))
                  }
                  className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-teal-500"
                />
                {unit.unit_type !== "OT" ? (
                  <input
                    type="number"
                    min="1"
                    value={draft.total_beds || 0}
                    onChange={(e) =>
                      setUnitDrafts((prev) => ({
                        ...prev,
                        [unit.unit_id]: { ...(prev[unit.unit_id] || {}), total_beds: e.target.value },
                      }))
                    }
                    className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-teal-500"
                  />
                ) : (
                  <select
                    value={draft.status || "AVAILABLE"}
                    onChange={(e) =>
                      setUnitDrafts((prev) => ({
                        ...prev,
                        [unit.unit_id]: { ...(prev[unit.unit_id] || {}), status: e.target.value },
                      }))
                    }
                    className="w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-teal-500"
                  >
                    <option value="AVAILABLE">AVAILABLE</option>
                    <option value="SCHEDULED">SCHEDULED</option>
                  </select>
                )}
                <button
                  type="button"
                  onClick={() => updateUnit(unit)}
                  className="w-full rounded-xl border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50"
                >
                  Save Unit
                </button>
              </div>
            </article>
          );
        })}
      </section>

      <section className="mt-6 rounded-[32px] border border-slate-200 bg-white p-6 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h3 className="text-lg font-bold">Bed Grid Management</h3>
          <select
            value={wardFilter}
            onChange={(e) => setWardFilter(e.target.value)}
            className="rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-teal-500"
          >
            {wardOptions.map((ward) => (
              <option key={ward} value={ward}>{ward === "ALL" ? "All Units" : ward}</option>
            ))}
          </select>
        </div>
        {loading ? (
          <div className="mt-4 text-center"><Loader2 className="mx-auto h-5 w-5 animate-spin text-teal-700" /></div>
        ) : (
          <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {filteredBeds.map((bed) => (
              <button
                key={bed.bed_id}
                type="button"
                onClick={() => openBedModal(bed)}
                className={`rounded-2xl border p-3 text-left transition hover:shadow-sm ${bedTileClass(bed.status)}`}
              >
                <div className="flex items-center justify-between">
                  <p className="text-sm font-bold">{bed.bed_number}</p>
                  <BedDouble className="h-4 w-4" />
                </div>
                <p className="mt-1 text-xs font-semibold">{bed.ward_name} ({bed.unit_type})</p>
                <p className="mt-1 text-xs">Status: {bed.status}</p>
                <p className="mt-1 text-xs">Patient: {bed.patient_name || "-"}</p>
              </button>
            ))}
          </div>
        )}
      </section>

      <section className="mt-6 rounded-[32px] border border-slate-200 bg-white p-6 shadow-sm">
        <h3 className="text-lg font-bold">Activity Audit</h3>
        <div className="mt-3 overflow-auto rounded-xl border border-slate-200">
          <table className="min-w-full text-sm">
            <thead className="bg-slate-50">
              <tr>
                <th className="px-3 py-2 text-left">Time</th>
                <th className="px-3 py-2 text-left">Module</th>
                <th className="px-3 py-2 text-left">Action</th>
                <th className="px-3 py-2 text-left">Entity</th>
              </tr>
            </thead>
            <tbody>
              {auditItems.slice(0, 30).map((a) => (
                <tr key={a.activity_id} className="border-t border-slate-100">
                  <td className="px-3 py-2 text-xs text-slate-600">{a.created_at || "-"}</td>
                  <td className="px-3 py-2">{a.module}</td>
                  <td className="px-3 py-2">{a.action}</td>
                  <td className="px-3 py-2">{a.entity_type || "-"} #{a.entity_id || "-"}</td>
                </tr>
              ))}
              {auditItems.length === 0 ? (
                <tr><td colSpan={4} className="px-3 py-6 text-center text-slate-500">No activity logs yet.</td></tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>

      {bedModal.open && bedModal.bed ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4 backdrop-blur-sm">
          <div className="w-full max-w-xl rounded-[32px] border border-slate-200 bg-white p-6 shadow-2xl">
            <h4 className="text-lg font-bold">Update Bed {bedModal.bed.bed_number}</h4>
            <p className="text-xs text-slate-500">{bedModal.bed.ward_name} | {bedModal.bed.unit_type}</p>
            <div className="mt-3 space-y-3">
              <select
                value={bedModal.status}
                onChange={(e) => setBedModal((p) => ({ ...p, status: e.target.value }))}
                className="w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-teal-500"
              >
                <option value="FREE">FREE</option>
                <option value="OCCUPIED">OCCUPIED</option>
                <option value="CLEANING">CLEANING / MAINTENANCE</option>
              </select>

              {bedModal.status === "OCCUPIED" ? (
                <>
                  <input
                    value={patientSearch}
                    onChange={(e) => setPatientSearch(e.target.value)}
                    placeholder="Search patient (MRN/Name)"
                    className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-teal-500"
                  />
                  <select
                    value={bedModal.patient_id}
                    onChange={(e) => setBedModal((p) => ({ ...p, patient_id: e.target.value }))}
                    className="w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-teal-500"
                  >
                    <option value="">Select patient</option>
                    {patients.map((p) => (
                      <option key={p.patient_id} value={p.patient_id}>{p.full_name} ({p.patient_mrn})</option>
                    ))}
                  </select>
                </>
              ) : null}
            </div>
            <div className="mt-4 flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={() => setBedModal({ open: false, bed: null, status: "FREE", patient_id: "" })}
                className="rounded-xl border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={saveBedStatus}
                disabled={savingBed}
                className="inline-flex items-center gap-2 rounded-xl bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-teal-700 disabled:opacity-60"
              >
                <Activity className="h-4 w-4" /> {savingBed ? "Saving..." : "Save Bed Status"}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </OperationsWorkspaceLayout>
  );
}
