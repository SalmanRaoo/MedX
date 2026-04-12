import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { FileText, LogOut, ScanLine } from "lucide-react";
import { aiApi, api } from "../../lib/api";
import { clearSession, getSessionUser } from "../../lib/auth";

function toDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

export default function RadiologyDashboard() {
  const navigate = useNavigate();
  const user = getSessionUser();

  const [config, setConfig] = useState({ modalities: [], ai_triggers: {} });
  const [patients, setPatients] = useState([]);
  const [patientSearch, setPatientSearch] = useState("");
  const [patientId, setPatientId] = useState("");
  const [selectedModality, setSelectedModality] = useState("");
  const [selectedBodyPart, setSelectedBodyPart] = useState("");
  const [studyTitle, setStudyTitle] = useState("");
  const [technicianNotes, setTechnicianNotes] = useState("");

  const [scanFile, setScanFile] = useState(null);
  const [scanPreview, setScanPreview] = useState("");
  const [aiLoading, setAiLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [aiOutput, setAiOutput] = useState(null);
  const [records, setRecords] = useState([]);
  const [patientRequests, setPatientRequests] = useState([]);
  const [selectedRequestId, setSelectedRequestId] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const currentPatient = useMemo(
    () => patients.find((p) => String(p.patient_id) === String(patientId)) || null,
    [patients, patientId]
  );

  const currentModality = useMemo(
    () => (config.modalities || []).find((m) => m.code === selectedModality) || null,
    [config.modalities, selectedModality]
  );

  const triggerKey = `${selectedModality}::${selectedBodyPart}`;
  const activeTrigger = useMemo(() => config.ai_triggers?.[triggerKey] || null, [config.ai_triggers, triggerKey]);

  const loadRecords = async (pid) => {
    if (!pid) {
      setRecords([]);
      return;
    }
    try {
      const { data } = await api.get("/radiology/imaging-records", {
        params: { patient_id: Number(pid), limit: 60 },
      });
      setRecords(data?.items || []);
    } catch (err) {
      setError(err?.response?.data?.detail || "Unable to load imaging records.");
    }
  };

  const loadPatientRequests = async (pid) => {
    if (!pid) {
      setPatientRequests([]);
      setSelectedRequestId("");
      return;
    }
    try {
      const { data } = await api.get(`/doctor/patients/${pid}/requests`);
      const requests = data?.radiology_requests || [];
      setPatientRequests(requests);
      setSelectedRequestId((prev) => {
        if (prev && requests.find((r) => String(r.radiology_request_id) === String(prev))) return prev;
        const ordered = requests.find((r) => String(r.status || "").toUpperCase() === "ORDERED");
        return ordered ? String(ordered.radiology_request_id) : "";
      });
    } catch (err) {
      setError(err?.response?.data?.detail || "Unable to load doctor radiology requests.");
      setPatientRequests([]);
      setSelectedRequestId("");
    }
  };

  useEffect(() => {
    let active = true;
    const init = async () => {
      try {
        const { data } = await api.get("/radiology/config");
        if (!active) return;
        const next = data || { modalities: [], ai_triggers: {} };
        setConfig(next);
        if ((next.modalities || []).length) {
          const first = next.modalities[0];
          setSelectedModality(first.code);
          const firstBodyPart = (first.body_parts || [])[0]?.code || "";
          setSelectedBodyPart(firstBodyPart);
        }
      } catch (err) {
        if (!active) return;
        setError(err?.response?.data?.detail || "Unable to load radiology config.");
      }
    };
    init();
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    const options = currentModality?.body_parts || [];
    if (!options.length) {
      setSelectedBodyPart("");
      return;
    }
    if (!options.find((b) => b.code === selectedBodyPart)) {
      setSelectedBodyPart(options[0].code);
    }
  }, [currentModality, selectedBodyPart]);

  useEffect(() => {
    let active = true;
    const t = setTimeout(async () => {
      try {
        const { data } = await api.get("/lab/patient-search", { params: { q: patientSearch, limit: 180 } });
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

  useEffect(() => {
    loadRecords(patientId);
    loadPatientRequests(patientId);
  }, [patientId]);

  useEffect(() => {
    if (!selectedModality || !selectedBodyPart) return;
    setStudyTitle(`${selectedModality.replace("_", "-")} ${selectedBodyPart.replace("_", " ")}`);
  }, [selectedModality, selectedBodyPart]);

  const onFileChange = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setError("");
    setSuccess("");
    setScanFile(file);
    setAiOutput(null);
    try {
      const dataUrl = await toDataUrl(file);
      setScanPreview(dataUrl);
    } catch {
      setError("Unable to preview selected image.");
    }
  };

  const runTriggerAI = async () => {
    if (!activeTrigger) return;
    if (!scanFile) {
      setError("Please upload scan image first.");
      return;
    }
    setError("");
    setSuccess("");
    setAiLoading(true);
    try {
      const formData = new FormData();
      formData.append("file", scanFile);
      const { data } = await aiApi.post(activeTrigger.ai_path, formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setAiOutput({
        model_key: activeTrigger.ai_model_key,
        action: activeTrigger.action,
        result: data?.result || data?.prediction || "N/A",
        confidence: data?.confidence || "N/A",
        raw: data || {},
      });
      setSuccess(`${activeTrigger.action} completed.`);
    } catch (err) {
      setError(err?.response?.data?.detail || "AI processing failed.");
    } finally {
      setAiLoading(false);
    }
  };

  const saveMetadata = async () => {
    if (!currentPatient) {
      setError("Please select patient.");
      return;
    }
    if (!selectedModality || !selectedBodyPart) {
      setError("Please select modality and body part.");
      return;
    }
    setSaving(true);
    setError("");
    setSuccess("");
    try {
      await api.post("/radiology/imaging-records", {
        patient_id: Number(currentPatient.patient_id),
        patient_mrn: currentPatient.patient_mrn,
        modality: selectedModality,
        body_part: selectedBodyPart,
        study_title: studyTitle || null,
        source_page: "RADIOLOGY_DASHBOARD",
        request_id: selectedRequestId ? Number(selectedRequestId) : null,
        technician_notes: technicianNotes || null,
        ai_model_key: aiOutput?.model_key || null,
        ai_result: aiOutput?.result || null,
        ai_confidence: aiOutput?.confidence || null,
        ai_findings: aiOutput?.raw || {},
        scan_image_data_url: scanPreview || null,
        add_to_patient_record: false,
      });
      setSuccess("Radiology scan metadata saved.");
      setTechnicianNotes("");
      await loadRecords(currentPatient.patient_id);
      await loadPatientRequests(currentPatient.patient_id);
    } catch (err) {
      setError(err?.response?.data?.detail || "Unable to save radiology metadata.");
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
          <Link to="/dashboard/radiology" className="mb-8 block">
            <p className="text-xs uppercase tracking-[0.2em] text-cyan-300">MedX Radiology</p>
            <p className="mt-1 text-2xl font-extrabold">Imaging Suite</p>
          </Link>

          <div className="rounded-2xl border border-cyan-700/40 bg-slate-800/70 p-4 text-sm">
            <p className="font-semibold">{user?.hospital_name || "MedX"}</p>
            <p className="mt-1 text-slate-300">X-Ray, Ultrasound, and MRI operations with AI trigger shortcuts.</p>
          </div>

          <nav className="mt-6 flex-1 space-y-2">
            <Link to="/dashboard/radiology" className="flex items-center gap-3 rounded-xl bg-cyan-600 px-4 py-3 text-sm font-semibold text-white">
              <ScanLine className="h-4 w-4" /> Radiology Dashboard
            </Link>
            <Link to="/dashboard/radiology/reports" className="flex items-center gap-3 rounded-xl px-4 py-3 text-sm font-semibold text-slate-300 hover:bg-slate-800">
              <FileText className="h-4 w-4" /> Radiology Reports
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
            <h1 className="text-3xl font-black tracking-tight">Radiology Department Dashboard</h1>
            <p className="mt-1 text-slate-600">Multi-modality imaging workflow linked to patient MRN and AI-assisted scan tagging.</p>
          </header>

          {error ? <p className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</p> : null}
          {success ? <p className="rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{success}</p> : null}

          <section className="rounded-[32px] border border-slate-200 bg-white p-6 shadow-sm space-y-4">
            <h2 className="text-lg font-bold">Patient & Study Metadata</h2>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <label className="block space-y-1 lg:col-span-2">
                <span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Search Patient (MRN / Name)</span>
                <input
                  value={patientSearch}
                  onChange={(e) => setPatientSearch(e.target.value)}
                  placeholder="MRN or patient name"
                  className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-cyan-500"
                />
              </label>
              <label className="block space-y-1">
                <span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Patient</span>
                <select
                  value={patientId}
                  onChange={(e) => setPatientId(e.target.value)}
                  className="w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-cyan-500"
                >
                  <option value="">Select patient</option>
                  {patients.map((p) => (
                    <option key={p.patient_id} value={p.patient_id}>
                      {p.full_name} ({p.patient_mrn})
                    </option>
                  ))}
                </select>
              </label>
              <label className="block space-y-1">
                <span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Study Title</span>
                <input
                  value={studyTitle}
                  onChange={(e) => setStudyTitle(e.target.value)}
                  className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-cyan-500"
                />
              </label>
            </div>
          </section>

          <section className="rounded-[32px] border border-slate-200 bg-white p-6 shadow-sm space-y-4">
            <h2 className="text-lg font-bold">Modality Tabs</h2>
            <div className="flex flex-wrap gap-2">
              {(config.modalities || []).map((m) => (
                <button
                  key={m.code}
                  type="button"
                  onClick={() => setSelectedModality(m.code)}
                  className={`rounded-xl px-4 py-2 text-sm font-semibold ${
                    selectedModality === m.code
                      ? "bg-cyan-600 text-white"
                      : "border border-slate-300 bg-white text-slate-700 hover:bg-slate-50"
                  }`}
                >
                  {m.label}
                </button>
              ))}
            </div>

            <div className="grid gap-3 md:grid-cols-2">
              <label className="block space-y-1">
                <span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Body Part</span>
                <select
                  value={selectedBodyPart}
                  onChange={(e) => setSelectedBodyPart(e.target.value)}
                  className="w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-cyan-500"
                >
                  {(currentModality?.body_parts || []).map((b) => (
                    <option key={b.code} value={b.code}>
                      {b.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block space-y-1">
                <span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Technician Notes</span>
                <input
                  value={technicianNotes}
                  onChange={(e) => setTechnicianNotes(e.target.value)}
                  placeholder="Enter scan notes"
                  className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-cyan-500"
                />
              </label>
            </div>

            <div className="grid gap-4 lg:grid-cols-[1.2fr_1fr]">
              <div className="rounded-[32px] border border-slate-200 p-4">
                <p className="text-sm font-semibold">Upload Scan Image</p>
                <input
                  type="file"
                  accept="image/*"
                  onChange={onFileChange}
                  className="mt-2 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                />
                <div className="mt-3 rounded-2xl border border-slate-800 bg-slate-950 p-3">
                  <div className="relative flex min-h-56 items-center justify-center overflow-hidden rounded-xl bg-slate-900">
                    {scanPreview ? (
                      <img src={scanPreview} alt="Radiology preview" className="max-h-72 w-auto object-contain" />
                    ) : (
                      <p className="text-sm text-slate-400">No scan uploaded yet.</p>
                    )}
                    {aiOutput ? (
                      <div className="absolute inset-x-3 bottom-3 rounded-lg bg-slate-950/85 px-3 py-2 text-xs text-cyan-100">
                        {aiOutput.result} ({aiOutput.confidence})
                      </div>
                    ) : null}
                  </div>
                </div>
              </div>

              <div className="rounded-[32px] border border-slate-200 p-4">
                <p className="text-sm font-semibold">AI Action Panel</p>
                {activeTrigger ? (
                  <button
                    type="button"
                    onClick={runTriggerAI}
                    disabled={aiLoading}
                    className="mt-3 w-full rounded-xl bg-cyan-700 px-4 py-2 text-sm font-semibold text-white hover:bg-cyan-800 disabled:opacity-60"
                  >
                    {aiLoading ? "Processing..." : activeTrigger.action}
                  </button>
                ) : (
                  <p className="mt-3 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-600">
                    No specialized AI action for this modality + body part combination.
                  </p>
                )}

                <button
                  type="button"
                  onClick={saveMetadata}
                  disabled={saving}
                  className="mt-3 w-full rounded-xl bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-800 disabled:opacity-60"
                >
                  {saving ? "Saving..." : "Save Scan Metadata"}
                </button>

                <div className="mt-4 rounded-xl border border-slate-200 bg-slate-50 p-3">
                  <p className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Latest AI Result Preview (Before Save)</p>
                  {aiOutput ? (
                    <div className="mt-2 space-y-1 text-sm">
                      <p><span className="font-semibold">Action:</span> {aiOutput.action || "-"}</p>
                      <p><span className="font-semibold">Model:</span> {aiOutput.model_key || "-"}</p>
                      <p><span className="font-semibold">Result:</span> {aiOutput.result || "-"}</p>
                      <p><span className="font-semibold">Confidence:</span> {aiOutput.confidence || "-"}</p>
                    </div>
                  ) : (
                    <p className="mt-2 text-sm text-slate-600">Run AI first to preview findings here before saving metadata.</p>
                  )}
                </div>

                <div className="mt-4 rounded-xl border border-slate-200 bg-slate-50 p-3">
                  <p className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Doctor Radiology Requests (Selected Patient)</p>
                  {patientRequests.length === 0 ? (
                    <p className="mt-2 text-sm text-slate-600">No doctor request found for this patient.</p>
                  ) : (
                    <>
                      <label className="mt-2 block space-y-1">
                        <span className="text-xs font-semibold text-slate-600">Link Request (Optional)</span>
                        <select
                          value={selectedRequestId}
                          onChange={(e) => setSelectedRequestId(e.target.value)}
                          className="w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-cyan-500"
                        >
                          <option value="">Do not link request</option>
                          {patientRequests.map((r) => (
                            <option key={r.radiology_request_id} value={r.radiology_request_id}>
                              #{r.radiology_request_id} | {r.test_name} | {r.status}
                            </option>
                          ))}
                        </select>
                      </label>
                      <div className="mt-2 max-h-40 space-y-2 overflow-auto pr-1 text-xs">
                        {patientRequests.map((r) => (
                          <div key={r.radiology_request_id} className="rounded-lg border border-slate-200 bg-white p-2">
                            <p className="font-semibold">{r.test_name}</p>
                            <p>Body Part: {r.body_part || "-"}</p>
                            <p>Priority: {r.priority || "-"}</p>
                            <p>Status: {r.status || "-"}</p>
                          </div>
                        ))}
                      </div>
                    </>
                  )}
                </div>

                <p className="mt-3 text-xs text-slate-600">
                  Data integrity: every save is linked with patient MRN <span className="font-semibold">{currentPatient?.patient_mrn || "-"}</span>.
                </p>
              </div>
            </div>
          </section>

          <section className="rounded-[32px] border border-slate-200 bg-white p-6 shadow-sm">
            <h2 className="text-lg font-bold">Saved Imaging Records (Selected Patient)</h2>
            <div className="mt-3 overflow-auto rounded-xl border border-slate-200">
              <table className="min-w-full text-sm">
                <thead className="bg-slate-50">
                  <tr>
                    <th className="px-3 py-2 text-left">ID</th>
                    <th className="px-3 py-2 text-left">Modality</th>
                    <th className="px-3 py-2 text-left">Body Part</th>
                    <th className="px-3 py-2 text-left">AI Result</th>
                    <th className="px-3 py-2 text-left">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {records.length === 0 ? (
                    <tr>
                      <td className="px-3 py-2 text-slate-500" colSpan={5}>No imaging records yet.</td>
                    </tr>
                  ) : (
                    records.map((r) => (
                      <tr key={r.imaging_record_id} className="border-t border-slate-100">
                        <td className="px-3 py-2">{r.imaging_record_id}</td>
                        <td className="px-3 py-2">{r.modality}</td>
                        <td className="px-3 py-2">{r.body_part}</td>
                        <td className="px-3 py-2">{r.ai_result || "-"}</td>
                        <td className="px-3 py-2">{r.status}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </section>
        </main>
      </div>
    </div>
  );
}
