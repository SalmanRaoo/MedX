import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Activity, BedDouble, LogOut, Save, Search, Stethoscope } from "lucide-react";
import { api } from "../../lib/api";
import { clearSession, getSessionUser } from "../../lib/auth";
import { useHospitalSettings } from "../../context/HospitalSettingsContext";

function InputField({ label, ...props }) {
  return (
    <label className="block space-y-1">
      <span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">{label}</span>
      <input
        {...props}
        className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-teal-500"
      />
    </label>
  );
}

export default function NurseDashboard() {
  const navigate = useNavigate();
  const user = getSessionUser();
  const { hospitalName } = useHospitalSettings();
  const formRef = useRef(null);

  const [patients, setPatients] = useState([]);
  const [searchText, setSearchText] = useState("");
  const [patientId, setPatientId] = useState("");
  const [vitalsHistory, setVitalsHistory] = useState([]);
  const [wardBeds, setWardBeds] = useState([]);
  const [wardSummary, setWardSummary] = useState({ free: 0, occupied: 0, cleaning: 0 });
  const [wardName, setWardName] = useState("");

  const [loadingPatients, setLoadingPatients] = useState(true);
  const [loadingVitals, setLoadingVitals] = useState(false);
  const [loadingBeds, setLoadingBeds] = useState(false);
  const [saving, setSaving] = useState(false);
  const [savingBedId, setSavingBedId] = useState(null);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const [form, setForm] = useState({
    blood_pressure_systolic: "",
    blood_pressure_diastolic: "",
    heart_rate: "",
    body_temperature: "",
    respiratory_rate: "",
    oxygen_saturation: "",
    weight_kg: "",
    height_cm: "",
    bmi: "",
    chief_complaint: "",
    observation_notes: "",
  });

  const currentPatient = useMemo(
    () => patients.find((p) => String(p.patient_id) === String(patientId)) || null,
    [patients, patientId]
  );

  const loadVitals = async (pid) => {
    if (!pid) {
      setVitalsHistory([]);
      return;
    }
    setLoadingVitals(true);
    try {
      const { data } = await api.get("/nurse/vitals", { params: { patient_id: Number(pid), limit: 80 } });
      setVitalsHistory(data?.items || []);
    } catch (err) {
      setError(err?.response?.data?.detail || "Unable to load vitals history.");
    } finally {
      setLoadingVitals(false);
    }
  };

  const loadWardBeds = async (ward = "") => {
    setLoadingBeds(true);
    try {
      const { data } = await api.get("/nurse/ward-beds", {
        params: ward ? { ward_name: ward } : {},
      });
      setWardBeds(data?.items || []);
      setWardSummary(data?.summary || { free: 0, occupied: 0, cleaning: 0 });
      if (data?.ward_name) setWardName(data.ward_name);
    } catch (err) {
      setError(err?.response?.data?.detail || "Unable to load ward beds.");
    } finally {
      setLoadingBeds(false);
    }
  };

  useEffect(() => {
    let active = true;
    const timer = setTimeout(async () => {
      try {
        const { data } = await api.get("/nurse/patient-search", {
          params: { q: searchText, limit: 220 },
        });
        if (!active) return;
        const items = data?.items || [];
        setPatients(items);
        if (items.length && !items.find((p) => String(p.patient_id) === String(patientId))) {
          setPatientId(String(items[0].patient_id));
        }
      } catch (err) {
        if (!active) return;
        setError(err?.response?.data?.detail || "Unable to search patients.");
      } finally {
        if (active) setLoadingPatients(false);
      }
    }, 200);

    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [searchText, patientId]);

  useEffect(() => {
    loadVitals(patientId);
  }, [patientId]);

  useEffect(() => {
    loadWardBeds("");
  }, []);

  useEffect(() => {
    const token = localStorage.getItem("medx_token");
    if (!token) return;
    const ws = new WebSocket(`ws://localhost:8000/ws/bed-sync?token=${encodeURIComponent(token)}`);
    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (["bed_status_changed", "bed_transfer", "unit_config_updated"].includes(msg?.event)) {
          loadWardBeds(wardName || "");
        }
      } catch {
        // ignore invalid payload
      }
    };
    return () => ws.close();
  }, [wardName]);

  useEffect(() => {
    const w = Number(form.weight_kg);
    const hCm = Number(form.height_cm);
    if (!Number.isFinite(w) || !Number.isFinite(hCm) || w <= 0 || hCm <= 0) return;
    const hM = hCm / 100;
    const bmi = w / (hM * hM);
    if (!Number.isFinite(bmi)) return;
    setForm((prev) => ({ ...prev, bmi: bmi.toFixed(2) }));
  }, [form.weight_kg, form.height_cm]);

  const onChange = (e) => {
    setForm((prev) => ({ ...prev, [e.target.name]: e.target.value }));
  };

  const onEnterNext = (e) => {
    if (e.key !== "Enter") return;
    const tag = String(e.target.tagName || "").toLowerCase();
    if (tag === "textarea") return;
    e.preventDefault();
    const formEl = formRef.current;
    if (!formEl) return;
    const focusables = Array.from(formEl.querySelectorAll("input, select, textarea, button"))
      .filter((el) => !el.disabled && el.type !== "hidden");
    const idx = focusables.indexOf(e.target);
    if (idx >= 0 && idx < focusables.length - 1) {
      focusables[idx + 1].focus();
    }
  };

  const onSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setSuccess("");
    if (!currentPatient) {
      setError("Please select a patient.");
      return;
    }

    setSaving(true);
    try {
      await api.post("/nurse/vitals", {
        patient_id: Number(currentPatient.patient_id),
        patient_mrn: currentPatient.patient_mrn,
        blood_pressure_systolic: form.blood_pressure_systolic || null,
        blood_pressure_diastolic: form.blood_pressure_diastolic || null,
        heart_rate: form.heart_rate || null,
        body_temperature: form.body_temperature || null,
        respiratory_rate: form.respiratory_rate || null,
        oxygen_saturation: form.oxygen_saturation || null,
        weight_kg: form.weight_kg || null,
        bmi: form.bmi || null,
        chief_complaint: form.chief_complaint || null,
        observation_notes: form.observation_notes || null,
      });

      setSuccess("Vitals saved and synced to doctor consultation view.");
      setForm((prev) => ({
        ...prev,
        chief_complaint: "",
        observation_notes: "",
      }));
      await loadVitals(currentPatient.patient_id);
    } catch (err) {
      setError(err?.response?.data?.detail || "Unable to save vitals.");
    } finally {
      setSaving(false);
    }
  };

  const handleLogout = () => {
    clearSession();
    navigate("/");
  };

  const updateBedStatus = async (bed, status) => {
    setError("");
    setSuccess("");
    if (status === "OCCUPIED" && !currentPatient) {
      setError("Select a patient before occupying a bed.");
      return;
    }
    setSavingBedId(bed.bed_id);
    try {
      await api.post(`/operations/beds/${bed.bed_id}/status`, {
        status,
        patient_id: status === "OCCUPIED" ? Number(currentPatient.patient_id) : null,
      });
      setSuccess(`Bed ${bed.bed_number} marked ${status}.`);
      await loadWardBeds(wardName || "");
    } catch (err) {
      setError(err?.response?.data?.detail || "Unable to update bed status.");
    } finally {
      setSavingBedId(null);
    }
  };

  return (
    <div className="min-h-screen bg-slate-100 text-slate-900">
      <div className="flex min-h-screen">
        <aside className="hidden w-72 bg-slate-900 p-6 text-white md:flex md:flex-col">
          <Link to="/dashboard/nurse" className="mb-8 block">
            <p className="text-xs uppercase tracking-[0.2em] text-teal-300">MedX Nursing</p>
            <p className="mt-1 text-2xl font-extrabold">Vitals Station</p>
          </Link>

          <div className="rounded-2xl border border-teal-700/40 bg-slate-800/70 p-4 text-sm">
            <p className="font-semibold">{hospitalName || user?.hospital_name || "MedX"}</p>
            <p className="mt-1 text-slate-300">Clinical intake vitals and nursing notes linked with patient MRN.</p>
          </div>

          <nav className="mt-6 flex-1 space-y-2">
            <Link to="/dashboard/nurse" className="flex items-center gap-3 rounded-xl bg-teal-600 px-4 py-3 text-sm font-semibold text-white">
              <Stethoscope className="h-4 w-4" /> Nurse Dashboard
            </Link>
            <Link to="/dashboard/account" className="flex items-center gap-3 rounded-xl px-4 py-3 text-sm font-semibold text-slate-300 hover:bg-slate-800">
              <Activity className="h-4 w-4" /> Account Security
            </Link>
          </nav>

          <button
            type="button"
            onClick={handleLogout}
            className="mt-6 inline-flex items-center justify-center gap-2 rounded-xl border border-red-400/40 px-4 py-2 text-sm font-semibold text-red-300 hover:bg-red-500/10"
          >
            <LogOut className="h-4 w-4" /> Logout
          </button>
        </aside>

        <main className="flex-1 space-y-5 p-5 sm:p-8">
          <header className="rounded-[32px] border border-slate-200 bg-white p-6 shadow-sm">
            <div className="flex items-center gap-3">
              <span className="inline-flex h-11 w-11 items-center justify-center rounded-2xl bg-teal-100 text-teal-700">
                <Stethoscope className="h-6 w-6" />
              </span>
              <div>
                <h1 className="text-3xl font-black tracking-tight">Nurse Clinical Intake</h1>
                <p className="mt-1 text-slate-600">Capture vitals and nursing notes for doctor consultation in real time.</p>
              </div>
            </div>
          </header>

          {error ? <p className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</p> : null}
          {success ? <p className="rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{success}</p> : null}

          <div className="grid gap-5 xl:grid-cols-[1.15fr_1fr]">
            <section className="rounded-[32px] border border-slate-200 bg-white p-6 shadow-sm">
              <h2 className="text-lg font-bold">Patient & Vitals Entry</h2>

              <div className="mt-4 grid gap-3 sm:grid-cols-2">
                <label className="block space-y-1 sm:col-span-2">
                  <span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Search Patient (MRN / Name)</span>
                  <div className="relative">
                    <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                    <input
                      value={searchText}
                      onChange={(e) => setSearchText(e.target.value)}
                      placeholder="Type MRN or name"
                      className="w-full rounded-xl border border-slate-300 py-2 pl-9 pr-3 text-sm outline-none focus:border-teal-500"
                    />
                  </div>
                </label>

                <label className="block space-y-1 sm:col-span-2">
                  <span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Patient</span>
                  <select
                    value={patientId}
                    onChange={(e) => setPatientId(e.target.value)}
                    className="w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-teal-500"
                  >
                    <option value="">Select patient</option>
                    {patients.map((p) => (
                      <option key={p.patient_id} value={p.patient_id}>
                        {p.full_name} ({p.patient_mrn})
                      </option>
                    ))}
                  </select>
                </label>
              </div>

              <div className="mt-3 rounded-2xl border border-slate-200 bg-slate-50 p-3 text-sm">
                <p><span className="font-semibold">Patient:</span> {currentPatient?.full_name || "-"}</p>
                <p><span className="font-semibold">MRN:</span> {currentPatient?.patient_mrn || "-"}</p>
                <p><span className="font-semibold">Gender:</span> {currentPatient?.gender || "-"}</p>
              </div>

              <form ref={formRef} onSubmit={onSubmit} onKeyDown={onEnterNext} className="mt-4 grid gap-3 sm:grid-cols-2">
                <InputField label="BP Systolic (mmHg)" name="blood_pressure_systolic" value={form.blood_pressure_systolic} onChange={onChange} />
                <InputField label="BP Diastolic (mmHg)" name="blood_pressure_diastolic" value={form.blood_pressure_diastolic} onChange={onChange} />
                <InputField label="Heart Rate (bpm)" name="heart_rate" value={form.heart_rate} onChange={onChange} />
                <InputField label="Temperature (°C)" name="body_temperature" value={form.body_temperature} onChange={onChange} />
                <InputField label="Respiratory Rate (/min)" name="respiratory_rate" value={form.respiratory_rate} onChange={onChange} />
                <InputField label="SpO2 (%)" name="oxygen_saturation" value={form.oxygen_saturation} onChange={onChange} />
                <InputField label="Weight (kg)" name="weight_kg" value={form.weight_kg} onChange={onChange} />
                <InputField label="Height (cm)" name="height_cm" value={form.height_cm} onChange={onChange} />
                <InputField label="BMI" name="bmi" value={form.bmi} onChange={onChange} />

                <label className="block space-y-1 sm:col-span-2">
                  <span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Chief Complaint</span>
                  <textarea
                    name="chief_complaint"
                    value={form.chief_complaint}
                    onChange={onChange}
                    rows={2}
                    className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-teal-500"
                  />
                </label>

                <label className="block space-y-1 sm:col-span-2">
                  <span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Observation Notes</span>
                  <textarea
                    name="observation_notes"
                    value={form.observation_notes}
                    onChange={onChange}
                    rows={3}
                    className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-teal-500"
                  />
                </label>

                <div className="sm:col-span-2 flex flex-wrap gap-2">
                  <button
                    type="submit"
                    disabled={saving || !currentPatient}
                    className="inline-flex items-center gap-2 rounded-xl bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-teal-700 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    <Save className="h-4 w-4" />
                    {saving ? "Saving..." : "Save Vitals"}
                  </button>
                  <p className="self-center text-xs text-slate-500">Saved vitals are immediately visible in Doctor Portal patient history.</p>
                </div>
              </form>
            </section>

            <section className="rounded-[32px] border border-slate-200 bg-white p-6 shadow-sm">
              <h2 className="text-lg font-bold">Recent Vitals History</h2>
              {loadingPatients ? <p className="mt-3 text-sm text-slate-500">Loading patients...</p> : null}
              {loadingVitals ? <p className="mt-3 text-sm text-slate-500">Loading vitals...</p> : null}
              {!loadingVitals && vitalsHistory.length === 0 ? (
                <p className="mt-3 text-sm text-slate-500">No vitals recorded for selected patient.</p>
              ) : null}

              <div className="mt-3 space-y-2 max-h-[70vh] overflow-auto pr-1">
                {vitalsHistory.map((v) => (
                  <div key={v.vitals_id} className="rounded-2xl border border-slate-200 p-3 text-sm">
                    <p className="font-semibold text-slate-900">Vitals #{v.vitals_id} | {v.recorded_at || "-"}</p>
                    <p className="text-slate-600">BP: {v.blood_pressure_systolic || "-"} / {v.blood_pressure_diastolic || "-"} | HR: {v.pulse_rate || "-"} | Temp: {v.body_temperature || "-"}</p>
                    <p className="text-slate-600">RR: {v.respiratory_rate || "-"} | SpO2: {v.oxygen_saturation || "-"} | Weight: {v.weight_kg || "-"} | BMI: {v.bmi || "-"}</p>
                    <p className="text-slate-600">Complaint: {v.chief_complaint || "-"}</p>
                    <p className="text-slate-600">Observation: {v.observation_notes || "-"}</p>
                  </div>
                ))}
              </div>
            </section>
          </div>

          <section className="rounded-[32px] border border-slate-200 bg-white p-6 shadow-sm">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="text-lg font-bold">Ward Bed Board</h2>
                <p className="text-xs text-slate-500">Live bed status sync: green Free, red Occupied, yellow Cleaning/Maintenance.</p>
              </div>
              <div className="flex items-center gap-2 text-xs font-semibold">
                <span className="rounded-full bg-emerald-100 px-2 py-1 text-emerald-700">Free: {wardSummary.free || 0}</span>
                <span className="rounded-full bg-rose-100 px-2 py-1 text-rose-700">Occupied: {wardSummary.occupied || 0}</span>
                <span className="rounded-full bg-amber-100 px-2 py-1 text-amber-700">Cleaning: {wardSummary.cleaning || 0}</span>
              </div>
            </div>
            {wardName ? <p className="mt-2 text-xs text-slate-500">Assigned Ward: {wardName}</p> : null}
            {loadingBeds ? <p className="mt-3 text-sm text-slate-500">Loading bed board...</p> : null}
            <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
              {wardBeds.map((bed) => {
                const status = String(bed.status || "").toUpperCase();
                const tileClass =
                  status === "FREE"
                    ? "border-emerald-200 bg-emerald-50 text-emerald-800"
                    : status === "OCCUPIED"
                    ? "border-rose-200 bg-rose-50 text-rose-800"
                    : "border-amber-200 bg-amber-50 text-amber-800";
                return (
                  <article key={bed.bed_id} className={`rounded-2xl border p-3 ${tileClass}`}>
                    <div className="flex items-center justify-between">
                      <p className="text-sm font-bold">{bed.bed_number}</p>
                      <BedDouble className="h-4 w-4" />
                    </div>
                    <p className="mt-1 text-xs">Status: {status || "-"}</p>
                    <p className="mt-1 text-xs">Patient: {bed.patient_name || "-"}</p>
                    <div className="mt-2 grid grid-cols-2 gap-2">
                      <button
                        type="button"
                        onClick={() => updateBedStatus(bed, "OCCUPIED")}
                        disabled={savingBedId === bed.bed_id}
                        className="rounded-lg border border-slate-300 bg-white px-2 py-1 text-xs font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-60"
                      >
                        Occupy
                      </button>
                      <button
                        type="button"
                        onClick={() => updateBedStatus(bed, "FREE")}
                        disabled={savingBedId === bed.bed_id}
                        className="rounded-lg border border-slate-300 bg-white px-2 py-1 text-xs font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-60"
                      >
                        Free
                      </button>
                    </div>
                  </article>
                );
              })}
              {!loadingBeds && wardBeds.length === 0 ? (
                <p className="text-sm text-slate-500">No bed records found for this ward.</p>
              ) : null}
            </div>
          </section>
        </main>
      </div>
    </div>
  );
}
