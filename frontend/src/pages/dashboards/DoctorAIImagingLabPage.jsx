import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Brain, ImagePlus, UploadCloud } from "lucide-react";
import { aiApi, api } from "../../lib/api";
import DoctorWorkspaceLayout from "../../components/dashboards/DoctorWorkspaceLayout";

const ZONE_SPECS = {
  chest: {
    key: "chest",
    title: "Chest X-Ray Analysis",
    subtitle: "Run pneumonia model on chest radiograph.",
    modality: "X_RAY",
    bodyPart: "CHEST",
    aiPath: "/predict/pneumonia",
    aiModelKey: "pneumonia_model.h5",
  },
  brain: {
    key: "brain",
    title: "Brain MRI Analysis",
    subtitle: "Run brain tumor model on MRI scan.",
    modality: "MRI",
    bodyPart: "BRAIN",
    aiPath: "/predict/brain_tumor",
    aiModelKey: "brain_tumor_model.h5",
  },
};

function toDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

function createZoneState() {
  return {
    file: null,
    preview: "",
    aiLoading: false,
    saving: false,
    aiResult: null,
    doctorNotes: "",
  };
}

export default function DoctorAIImagingLabPage() {
  const navigate = useNavigate();
  const [patients, setPatients] = useState([]);
  const [patientSearch, setPatientSearch] = useState("");
  const [patientId, setPatientId] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [zones, setZones] = useState({
    chest: createZoneState(),
    brain: createZoneState(),
  });

  const currentPatient = useMemo(
    () => patients.find((p) => String(p.patient_id) === String(patientId)) || null,
    [patients, patientId]
  );

  const updateZone = (zoneKey, patch) => {
    setZones((prev) => ({ ...prev, [zoneKey]: { ...prev[zoneKey], ...patch } }));
  };

  useEffect(() => {
    let active = true;
    const t = setTimeout(async () => {
      try {
        const { data } = await api.get("/lab/patient-search", { params: { q: patientSearch, limit: 220 } });
        if (!active) return;
        const items = data?.items || [];
        setPatients(items);
        if (items.length && !items.find((p) => String(p.patient_id) === String(patientId))) {
          setPatientId(String(items[0].patient_id));
        }
      } catch (err) {
        if (!active) return;
        setError(err?.response?.data?.detail || "Unable to load patient list.");
      }
    }, 220);
    return () => {
      active = false;
      clearTimeout(t);
    };
  }, [patientSearch, patientId]);

  const onFileChange = async (zoneKey, e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setError("");
    setSuccess("");
    try {
      const dataUrl = await toDataUrl(file);
      updateZone(zoneKey, { file, preview: dataUrl, aiResult: null });
    } catch {
      setError("Unable to preview selected image.");
    }
  };

  const runAnalysis = async (zoneKey) => {
    const spec = ZONE_SPECS[zoneKey];
    const zone = zones[zoneKey];
    if (!zone?.file) {
      setError(`Please upload image for ${spec.title}.`);
      return;
    }

    setError("");
    setSuccess("");
    updateZone(zoneKey, { aiLoading: true });
    try {
      const formData = new FormData();
      formData.append("file", zone.file);
      const { data } = await aiApi.post(spec.aiPath, formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      updateZone(zoneKey, {
        aiResult: {
          result: data?.result || data?.prediction || "N/A",
          confidence: data?.confidence || "N/A",
          raw: data || {},
        },
      });
    } catch (err) {
      setError(err?.response?.data?.detail || `AI analysis failed for ${spec.title}.`);
    } finally {
      updateZone(zoneKey, { aiLoading: false });
    }
  };

  const addToPatientRecord = async (zoneKey) => {
    const spec = ZONE_SPECS[zoneKey];
    const zone = zones[zoneKey];
    if (!currentPatient) {
      setError("Please select patient first.");
      return;
    }
    if (!zone?.preview || !zone?.aiResult) {
      setError(`Run AI analysis first for ${spec.title}.`);
      return;
    }

    setError("");
    setSuccess("");
    updateZone(zoneKey, { saving: true });
    try {
      const { data } = await api.post("/radiology/imaging-records", {
        patient_id: Number(currentPatient.patient_id),
        patient_mrn: currentPatient.patient_mrn,
        modality: spec.modality,
        body_part: spec.bodyPart,
        study_title: `${spec.title} (${currentPatient.patient_mrn})`,
        source_page: "DOCTOR_AI_IMAGING_LAB",
        doctor_notes: zone.doctorNotes || null,
        ai_model_key: spec.aiModelKey,
        ai_result: zone.aiResult.result,
        ai_confidence: zone.aiResult.confidence,
        ai_findings: zone.aiResult.raw || {},
        scan_image_data_url: zone.preview,
        status: "COMPLETED",
        add_to_patient_record: true,
      });
      const recordId = data?.record?.imaging_record_id;
      setSuccess(`${spec.title} added to patient record${recordId ? ` (#${recordId})` : ""}.`);
      if (recordId) {
        navigate(`/dashboard/doctor/imaging-reports?record_id=${recordId}`);
      }
    } catch (err) {
      setError(err?.response?.data?.detail || "Unable to add scan to patient record.");
    } finally {
      updateZone(zoneKey, { saving: false });
    }
  };

  return (
    <DoctorWorkspaceLayout
      title="AI Imaging Lab"
      subtitle="High-priority diagnostic imaging workflow for chest X-ray and brain MRI."
    >
      {error ? <p className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</p> : null}
      {success ? <p className="mt-3 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{success}</p> : null}

      <section className="mt-4 rounded-[32px] border border-slate-200 bg-white p-6 shadow-sm">
        <h2 className="text-lg font-bold">Patient Context</h2>
        <div className="mt-3 grid gap-3 md:grid-cols-3">
          <label className="block space-y-1 md:col-span-2">
            <span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Search Patient (MRN / Name)</span>
            <input
              value={patientSearch}
              onChange={(e) => setPatientSearch(e.target.value)}
              placeholder="Search patient"
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
        </div>
      </section>

      <section className="mt-5 grid gap-5 xl:grid-cols-2">
        {Object.values(ZONE_SPECS).map((spec) => {
          const zone = zones[spec.key];
          return (
            <article key={spec.key} className="rounded-[32px] border border-slate-200 bg-white p-6 shadow-sm">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h3 className="text-xl font-black tracking-tight">{spec.title}</h3>
                  <p className="text-sm text-slate-600">{spec.subtitle}</p>
                </div>
                {spec.key === "chest" ? <ImagePlus className="h-5 w-5 text-cyan-700" /> : <Brain className="h-5 w-5 text-cyan-700" />}
              </div>

              <div className="mt-4 space-y-3">
                <label className="block space-y-1">
                  <span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Upload Scan</span>
                  <input
                    type="file"
                    accept="image/*"
                    onChange={(e) => onFileChange(spec.key, e)}
                    className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm"
                  />
                </label>
                <label className="block space-y-1">
                  <span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Doctor Notes</span>
                  <textarea
                    rows={2}
                    value={zone.doctorNotes}
                    onChange={(e) => updateZone(spec.key, { doctorNotes: e.target.value })}
                    className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-cyan-500"
                    placeholder="Optional clinical interpretation"
                  />
                </label>

                <div className="rounded-[24px] border border-slate-800 bg-slate-950 p-3">
                  <div className="relative flex min-h-72 items-center justify-center overflow-hidden rounded-xl bg-slate-900">
                    {zone.preview ? (
                      <img src={zone.preview} alt={spec.title} className="max-h-80 w-auto object-contain" />
                    ) : (
                      <div className="text-center text-slate-400">
                        <UploadCloud className="mx-auto h-8 w-8" />
                        <p className="mt-2 text-sm">Upload image to start analysis</p>
                      </div>
                    )}
                    {zone.aiResult ? (
                      <div className="absolute inset-x-3 bottom-3 rounded-lg bg-slate-950/85 px-3 py-2 text-sm font-semibold text-cyan-100">
                        {zone.aiResult.result} - {zone.aiResult.confidence}
                      </div>
                    ) : null}
                  </div>
                </div>

                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={() => runAnalysis(spec.key)}
                    disabled={zone.aiLoading}
                    className="rounded-xl bg-cyan-700 px-4 py-2 text-sm font-semibold text-white hover:bg-cyan-800 disabled:opacity-60"
                  >
                    {zone.aiLoading ? "Running AI..." : "Analyze Image"}
                  </button>
                  <button
                    type="button"
                    onClick={() => addToPatientRecord(spec.key)}
                    disabled={zone.saving || !zone.aiResult}
                    className="rounded-xl border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-60"
                  >
                    {zone.saving ? "Saving..." : "Add to Patient Record"}
                  </button>
                </div>
              </div>
            </article>
          );
        })}
      </section>
    </DoctorWorkspaceLayout>
  );
}

