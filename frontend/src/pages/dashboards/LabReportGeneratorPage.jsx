import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, FileText, FlaskConical, LogOut, Search, WandSparkles } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../../lib/api";
import { clearSession, getSessionUser } from "../../lib/auth";

function ToastStack({ toasts }) {
  return (
    <div className="fixed right-4 top-4 z-[100] space-y-2">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={`rounded-xl px-4 py-3 text-sm font-semibold shadow-lg ${
            t.tone === "error" ? "bg-rose-600 text-white" : "bg-teal-600 text-white"
          }`}
        >
          {t.message}
        </div>
      ))}
    </div>
  );
}

function getAge(dob) {
  if (!dob) return "";
  const d = new Date(dob);
  if (Number.isNaN(d.getTime())) return "";
  const now = new Date();
  let age = now.getFullYear() - d.getFullYear();
  const m = now.getMonth() - d.getMonth();
  if (m < 0 || (m === 0 && now.getDate() < d.getDate())) age -= 1;
  return age >= 0 ? String(age) : "";
}

function isOutOfRange(value, rr) {
  const num = Number(value);
  if (!Number.isFinite(num)) return false;
  const min = rr?.min !== undefined && rr?.min !== null ? Number(rr.min) : null;
  const max = rr?.max !== undefined && rr?.max !== null ? Number(rr.max) : null;
  if (Number.isFinite(min) && num < min) return true;
  if (Number.isFinite(max) && num > max) return true;
  return false;
}

function rrLabel(rr) {
  const min = rr?.min;
  const max = rr?.max;
  if (min !== undefined && max !== undefined) return `${min} - ${max}`;
  if (min !== undefined) return `>= ${min}`;
  if (max !== undefined) return `<= ${max}`;
  return "-";
}

function deriveInputType(feature) {
  const key = String(feature?.key || "").toLowerCase();
  const label = String(feature?.label || "").toLowerCase();
  const units = String(feature?.units || "").toLowerCase();
  const text = `${key} ${label} ${units}`;

  if (text.includes("0/1") || text.includes("binary") || text.includes("yes/no")) {
    return "Binary (0 or 1)";
  }
  if (
    ["sex", "gender", "fbs", "exang", "htn", "dm", "cad", "pe", "ane", "rbc", "pc", "pcc", "ba", "smoking", "anaemia", "high_blood_pressure"].includes(
      key
    )
  ) {
    return "Binary (0 or 1)";
  }
  if (units.includes("count") || key.includes("count") || key === "pregnancies") {
    return "Integer";
  }
  return "Numeric (decimal allowed)";
}

function deriveExampleValue(feature) {
  const inputType = deriveInputType(feature);
  if (inputType === "Binary (0 or 1)") return "0 or 1";
  if (feature?.key === "age") return "45";
  const rr = feature?.reference_range || {};
  const min = rr?.min;
  const max = rr?.max;
  if (min !== undefined && max !== undefined) {
    const mid = (Number(min) + Number(max)) / 2;
    if (Number.isFinite(mid)) return Number(mid.toFixed(2)).toString();
  }
  if (min !== undefined && Number.isFinite(Number(min))) return String(min);
  return "10";
}

export default function LabReportGeneratorPage() {
  const navigate = useNavigate();
  const user = getSessionUser();

  const [config, setConfig] = useState({
    models: [],
    model_feature_mapping: {},
    unified_features: [],
    symptom_options: [],
    specimen_types: [],
    standard_marker_sets: {},
  });

  const [patients, setPatients] = useState([]);
  const [patientSearch, setPatientSearch] = useState("");
  const [patientId, setPatientId] = useState("");

  const [selectedTestType, setSelectedTestType] = useState("");
  const [testTypeSearch, setTestTypeSearch] = useState("");
  const [clinicalInputs, setClinicalInputs] = useState({});
  const [selectedSymptoms, setSelectedSymptoms] = useState([]);
  const [symptomQuery, setSymptomQuery] = useState("");

  const [specimenType, setSpecimenType] = useState("Serum");
  const [collectionTimestamp, setCollectionTimestamp] = useState(new Date().toISOString().slice(0, 16));
  const [clinicalNotes, setClinicalNotes] = useState("");
  const [patientAge, setPatientAge] = useState("");

  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [toasts, setToasts] = useState([]);

  const addToast = (message, tone = "success") => {
    const id = Date.now() + Math.random();
    setToasts((prev) => [...prev, { id, message, tone }]);
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 3500);
  };

  const currentPatient = useMemo(
    () => patients.find((p) => String(p.patient_id) === String(patientId)) || null,
    [patients, patientId]
  );

  const modelByCode = useMemo(() => {
    const map = {};
    (config.models || []).forEach((m) => {
      map[m.code] = m;
    });
    return map;
  }, [config.models]);

  const selectedModelSpec = useMemo(() => modelByCode[selectedTestType] || null, [modelByCode, selectedTestType]);

  const filteredTestTypes = useMemo(() => {
    const q = testTypeSearch.trim().toLowerCase();
    const all = config.models || [];
    if (!q) return all;
    return all.filter((m) => {
      const blob = `${m.code || ""} ${m.label || ""} ${m.department || ""}`.toLowerCase();
      return blob.includes(q);
    });
  }, [config.models, testTypeSearch]);

  const requiredFeatureKeys = useMemo(() => {
    if (!selectedModelSpec) return [];
    if (selectedModelSpec.input_mode === "symptoms") return [];
    return config.model_feature_mapping?.[selectedTestType] || [];
  }, [selectedModelSpec, config.model_feature_mapping, selectedTestType]);

  const requiredFeatureMeta = useMemo(() => {
    const map = {};
    (config.unified_features || []).forEach((f) => {
      map[f.key] = f;
    });
    return requiredFeatureKeys.map((k) => map[k] || { key: k, label: k, units: "", description: "", reference_range: {} });
  }, [requiredFeatureKeys, config.unified_features]);

  const hasSymptomsModel = useMemo(
    () => selectedModelSpec?.input_mode === "symptoms",
    [selectedModelSpec]
  );

  const filteredSymptoms = useMemo(() => {
    const all = config.symptom_options || [];
    const q = symptomQuery.trim().toLowerCase();
    if (!q) return all;
    return all.filter((s) => String(s).toLowerCase().includes(q));
  }, [config.symptom_options, symptomQuery]);

  useEffect(() => {
    let active = true;
    const init = async () => {
      try {
        const { data } = await api.get("/lab/smart-form-config");
        if (!active) return;
        const next = data || {
          models: [],
          model_feature_mapping: {},
          unified_features: [],
          symptom_options: [],
          specimen_types: [],
          standard_marker_sets: {},
        };
        setConfig(next);
        if ((next.models || []).length) {
          setSelectedTestType(next.models[0].code);
        }
        if ((next.specimen_types || []).length) {
          setSpecimenType(next.specimen_types[0]);
        }
      } catch (err) {
        if (!active) return;
        setError(err?.response?.data?.detail || "Unable to load Smart Lab Form config.");
      }
    };
    init();
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    setClinicalInputs({});
    setSelectedSymptoms([]);
    setSymptomQuery("");
  }, [selectedTestType]);

  useEffect(() => {
    const derived = getAge(currentPatient?.dob);
    setPatientAge(derived);
  }, [currentPatient?.patient_id, currentPatient?.dob]);

  useEffect(() => {
    if (!requiredFeatureKeys.includes("age")) return;
    setClinicalInputs((prev) => {
      if (prev.age && String(prev.age).trim() !== "") return prev;
      if (!patientAge) return prev;
      return { ...prev, age: patientAge };
    });
  }, [requiredFeatureKeys, patientAge]);

  useEffect(() => {
    let active = true;
    const t = setTimeout(async () => {
      try {
        const { data } = await api.get("/lab/patient-search", { params: { q: patientSearch, limit: 150 } });
        if (!active) return;
        const items = data?.items || [];
        setPatients(items);
        if (items.length && !items.find((p) => String(p.patient_id) === String(patientId))) {
          setPatientId(String(items[0].patient_id));
        }
      } catch (err) {
        if (!active) return;
        setError(err?.response?.data?.detail || "Unable to search patients.");
      }
    }, 220);
    return () => {
      active = false;
      clearTimeout(t);
    };
  }, [patientSearch, patientId]);

  const toggleSymptom = (symptom) => {
    setSelectedSymptoms((prev) => (prev.includes(symptom) ? prev.filter((s) => s !== symptom) : [...prev, symptom]));
  };

  const updateClinicalInput = (key, value) => {
    setClinicalInputs((prev) => ({ ...prev, [key]: value }));
  };

  const validate = () => {
    if (!patientId) return "Please select a patient.";
    if (!selectedTestType) return "Please select test type.";
    if (!specimenType) return "Please select specimen type.";
    if (!collectionTimestamp) return "Collection timestamp is required.";

    for (const f of requiredFeatureMeta) {
      const v = clinicalInputs[f.key];
      if (v === "" || v === null || v === undefined) {
        return `${f.label || f.key} is required.`;
      }
      if (Number.isNaN(Number(v))) {
        return `${f.label || f.key} must be numeric.`;
      }
    }
    if (hasSymptomsModel && selectedSymptoms.length === 0) {
      return "Select at least one symptom for General Disease model.";
    }
    return "";
  };

  const onGenerate = async () => {
    const msg = validate();
    if (msg) {
      setError(msg);
      return;
    }

    setSaving(true);
    setError("");
    try {
      const { data } = await api.post("/lab/smart-records", {
        patient_id: Number(patientId),
        patient_age: patientAge === "" ? null : Number(patientAge),
        selected_models: [selectedTestType],
        specimen_type: specimenType,
        collection_timestamp: collectionTimestamp,
        clinical_notes: clinicalNotes,
        clinical_inputs: clinicalInputs,
        selected_symptoms: selectedSymptoms,
        standard_markers: [],
      });

      const recordId = data?.record?.record_id;
      if (!recordId) throw new Error("Record ID missing after save.");

      addToast("Unified lab form submitted. Combined report is ready.");
      navigate(`/dashboard/lab/reports?record_id=${recordId}`);
    } catch (err) {
      setError(err?.response?.data?.detail || err?.message || "Unable to generate report.");
      addToast("Report generation failed.", "error");
    } finally {
      setSaving(false);
    }
  };

  const handleLogout = () => {
    clearSession();
    navigate("/");
  };

  return (
    <div className="min-h-screen bg-slate-100 text-slate-900">
      <div className="flex min-h-screen">
        <aside className="hidden w-72 bg-slate-900 p-6 text-white md:flex md:flex-col">
          <Link to="/dashboard/lab" className="mb-8 block">
            <p className="text-xs uppercase tracking-[0.2em] text-teal-300">MedX Laboratory</p>
            <p className="mt-1 text-2xl font-extrabold">Technician Desk</p>
          </Link>
          <div className="rounded-2xl border border-teal-700/40 bg-slate-800/70 p-4 text-sm">
            <p className="font-semibold">{user?.hospital_name || "MedX"}</p>
            <p className="mt-1 text-slate-300">One unified form for all AI models and printable reporting.</p>
          </div>
          <nav className="mt-6 flex-1 space-y-2">
            <Link to="/dashboard/lab" className="flex items-center gap-3 rounded-xl px-4 py-3 text-sm font-semibold text-slate-300 hover:bg-slate-800">
              <FlaskConical className="h-4 w-4" /> Lab Home
            </Link>
            <Link to="/dashboard/lab/generate" className="flex items-center gap-3 rounded-xl bg-teal-600 px-4 py-3 text-sm font-semibold text-white">
              <WandSparkles className="h-4 w-4" /> Smart Lab Form
            </Link>
            <Link to="/dashboard/lab/reports" className="flex items-center gap-3 rounded-xl px-4 py-3 text-sm font-semibold text-slate-300 hover:bg-slate-800">
              <FileText className="h-4 w-4" /> Report Management
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
            <h1 className="text-3xl font-black tracking-tight">Unified Lab Input Form</h1>
            <p className="mt-1 text-slate-600">Fill one form, run one or more models, and print one combined report.</p>
          </header>

          {error ? <p className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</p> : null}

          <section className="rounded-[32px] border border-slate-200 bg-white p-6 shadow-sm space-y-4">
            <h2 className="text-lg font-bold">Patient Metadata</h2>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <label className="block space-y-1 lg:col-span-2">
                <span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Search Patient (MRN / Name)</span>
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                  <input
                    value={patientSearch}
                    onChange={(e) => setPatientSearch(e.target.value)}
                    className="w-full rounded-xl border border-slate-300 py-2 pl-9 pr-3 text-sm outline-none focus:border-teal-500"
                    placeholder="MRN or patient name"
                  />
                </div>
              </label>
              <label className="block space-y-1">
                <span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Patient</span>
                <select
                  value={patientId}
                  onChange={(e) => setPatientId(e.target.value)}
                  className="w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-teal-500"
                >
                  <option value="">Select patient</option>
                  {patients.map((p) => (
                    <option key={p.patient_id} value={p.patient_id}>
                      {p.full_name} (MRN: {p.patient_mrn})
                    </option>
                  ))}
                </select>
              </label>
              <label className="block space-y-1">
                <span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Collection Timestamp</span>
                <input
                  type="datetime-local"
                  value={collectionTimestamp}
                  onChange={(e) => setCollectionTimestamp(e.target.value)}
                  className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-teal-500"
                />
              </label>
            </div>

            <div className="grid gap-3 sm:grid-cols-5">
              <div className="rounded-xl border border-slate-200 bg-slate-50 p-3 text-sm">
                <p className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Name</p>
                <p className="mt-1 font-semibold">{currentPatient?.full_name || "-"}</p>
              </div>
              <div className="rounded-xl border border-slate-200 bg-slate-50 p-3 text-sm">
                <p className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">MRN</p>
                <p className="mt-1 font-semibold">{currentPatient?.patient_mrn || "-"}</p>
              </div>
              <div className="rounded-xl border border-slate-200 bg-slate-50 p-3 text-sm">
                <p className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Gender</p>
                <p className="mt-1 font-semibold">{currentPatient?.gender || "-"}</p>
              </div>
              <div className="rounded-xl border border-slate-200 bg-slate-50 p-3 text-sm">
                <p className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Age</p>
                <input
                  type="number"
                  min="0"
                  max="130"
                  value={patientAge}
                  onChange={(e) => setPatientAge(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-2 py-1.5 font-semibold outline-none focus:border-teal-500"
                />
              </div>
              <label className="block space-y-1">
                <span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Specimen</span>
                <select
                  value={specimenType}
                  onChange={(e) => setSpecimenType(e.target.value)}
                  className="w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-teal-500"
                >
                  {(config.specimen_types || []).map((s) => (
                    <option key={s} value={s}>
                      {s}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            <label className="block space-y-1">
              <span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Clinical Notes</span>
              <textarea
                value={clinicalNotes}
                onChange={(e) => setClinicalNotes(e.target.value)}
                rows={3}
                className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-teal-500"
                placeholder="Relevant clinical context..."
              />
            </label>
          </section>

          <section className="rounded-[32px] border border-slate-200 bg-white p-6 shadow-sm space-y-4">
            <h2 className="text-lg font-bold">Test Type</h2>
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="block space-y-1">
                <span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Search Test Type</span>
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                  <input
                    value={testTypeSearch}
                    onChange={(e) => setTestTypeSearch(e.target.value)}
                    className="w-full rounded-xl border border-slate-300 py-2 pl-9 pr-3 text-sm outline-none focus:border-teal-500"
                    placeholder="Search by code, test name, department"
                  />
                </div>
              </label>
              <label className="block space-y-1">
                <span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Select Test Type</span>
                {filteredTestTypes.length > 0 ? (
                  <select
                    value={selectedTestType}
                    onChange={(e) => setSelectedTestType(e.target.value)}
                    className="w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-teal-500"
                  >
                    {filteredTestTypes.map((m) => (
                      <option key={m.code} value={m.code}>
                        {m.label} ({m.code})
                      </option>
                    ))}
                  </select>
                ) : (
                  <div className="w-full rounded-xl border border-slate-300 bg-slate-50 px-3 py-2 text-sm text-slate-500">
                    No test types found.
                  </div>
                )}
              </label>
            </div>
            {selectedModelSpec ? (
              <p className="text-xs text-slate-600">
                Selected: <span className="font-semibold">{selectedModelSpec.label}</span> ({selectedModelSpec.department || "Department"})
              </p>
            ) : null}
          </section>

          {selectedModelSpec && (requiredFeatureMeta.length > 0 || hasSymptomsModel) && (
            <section className="rounded-[32px] border border-slate-200 bg-white p-6 shadow-sm space-y-5">
              <h2 className="text-lg font-bold">Model Input Form</h2>

              {requiredFeatureMeta.length > 0 ? (
                <div className="space-y-3">
                  <p className="text-sm font-semibold text-slate-700">Required Numeric Features</p>
                  <div className="overflow-auto rounded-xl border border-slate-200">
                    <table className="min-w-full text-sm">
                      <thead className="bg-slate-50">
                        <tr>
                          <th className="px-3 py-2 text-left">Key</th>
                          <th className="px-3 py-2 text-left">Marker</th>
                          <th className="px-3 py-2 text-left">Result Input</th>
                          <th className="px-3 py-2 text-left">Input Type</th>
                          <th className="px-3 py-2 text-left">Example</th>
                          <th className="px-3 py-2 text-left">Reference Range</th>
                          <th className="px-3 py-2 text-left">Units</th>
                          <th className="px-3 py-2 text-left">Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {requiredFeatureMeta.map((f) => {
                          const value = clinicalInputs[f.key] ?? "";
                          const critical = isOutOfRange(value, f.reference_range);
                          return (
                            <tr key={f.key} className={`border-t ${critical ? "bg-rose-50 text-rose-700" : "border-slate-100"}`}>
                              <td className="px-3 py-2 font-semibold">{f.key}</td>
                              <td className="px-3 py-2">
                                <div className="font-semibold text-slate-900">{f.label || f.key}</div>
                                {f.description ? <div className="text-xs text-slate-500">{f.description}</div> : null}
                              </td>
                              <td className="px-3 py-2">
                                <input
                                  type="number"
                                  step="any"
                                  value={value}
                                  onChange={(e) => updateClinicalInput(f.key, e.target.value)}
                                  className={`w-full min-w-28 rounded-lg border px-3 py-2 text-sm outline-none ${
                                    critical
                                      ? "border-rose-400 bg-rose-50 text-rose-700"
                                      : "border-slate-300 bg-white text-slate-900 focus:border-teal-500"
                                  }`}
                                  placeholder={`e.g. ${deriveExampleValue(f)}`}
                                />
                              </td>
                              <td className="px-3 py-2">{deriveInputType(f)}</td>
                              <td className="px-3 py-2">{deriveExampleValue(f)}</td>
                              <td className="px-3 py-2">{rrLabel(f.reference_range)}</td>
                              <td className="px-3 py-2">{f.units || "-"}</td>
                              <td className="px-3 py-2">
                                {critical ? (
                                  <span className="inline-flex items-center gap-1 text-xs font-semibold text-rose-700">
                                    <AlertTriangle className="h-3 w-3" />
                                    Outside Range
                                  </span>
                                ) : (
                                  <span className="text-xs font-semibold text-emerald-700">Normal</span>
                                )}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              ) : null}

              {hasSymptomsModel ? (
                <div className="space-y-3">
                  <p className="text-sm font-semibold text-slate-700">Symptoms (for General Disease model)</p>
                  <input
                    value={symptomQuery}
                    onChange={(e) => setSymptomQuery(e.target.value)}
                    className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-teal-500"
                    placeholder="Search symptom (e.g. fever, chest pain)"
                  />
                  <div className="max-h-72 overflow-auto rounded-xl border border-slate-200">
                    <table className="min-w-full text-sm">
                      <thead className="bg-slate-50">
                        <tr>
                          <th className="px-3 py-2 text-left">Symptom</th>
                          <th className="px-3 py-2 text-left">Selected</th>
                        </tr>
                      </thead>
                      <tbody>
                        {filteredSymptoms.length === 0 ? (
                          <tr className="border-t border-slate-100">
                            <td className="px-3 py-2 text-slate-500" colSpan={2}>No symptoms found.</td>
                          </tr>
                        ) : (
                          filteredSymptoms.map((s) => {
                            const active = selectedSymptoms.includes(s);
                            return (
                              <tr key={s} className={`border-t ${active ? "bg-teal-50" : "border-slate-100"}`}>
                                <td className="px-3 py-2 font-semibold text-slate-800">{s}</td>
                                <td className="px-3 py-2">
                                  <button
                                    type="button"
                                    onClick={() => toggleSymptom(s)}
                                    className={`rounded-lg border px-3 py-1 text-xs font-semibold transition ${
                                      active
                                        ? "border-teal-500 bg-teal-600 text-white"
                                        : "border-slate-300 bg-white text-slate-700 hover:bg-slate-50"
                                    }`}
                                  >
                                    {active ? "Selected" : "Select"}
                                  </button>
                                </td>
                              </tr>
                            );
                          })
                        )}
                      </tbody>
                    </table>
                  </div>
                  <p className="text-xs text-slate-600">Selected symptoms: {selectedSymptoms.length}</p>
                </div>
              ) : null}
            </section>
          )}

          <section className="rounded-[32px] border border-slate-200 bg-white p-6 shadow-sm">
            <button
              type="button"
              onClick={onGenerate}
              disabled={saving}
              className="rounded-xl bg-slate-900 px-5 py-2.5 text-sm font-semibold text-white hover:bg-teal-700 disabled:opacity-60"
            >
              {saving ? "Generating..." : "Generate Report"}
            </button>
          </section>
        </main>
      </div>

      <ToastStack toasts={toasts} />
    </div>
  );
}
