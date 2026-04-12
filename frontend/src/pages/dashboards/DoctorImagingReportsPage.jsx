import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Printer } from "lucide-react";
import { api } from "../../lib/api";
import { getSessionUser } from "../../lib/auth";
import DoctorWorkspaceLayout from "../../components/dashboards/DoctorWorkspaceLayout";

export default function DoctorImagingReportsPage() {
  const [searchParams] = useSearchParams();
  const user = getSessionUser();
  const queryRecordId = Number(searchParams.get("record_id") || 0);

  const [records, setRecords] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [recordDetail, setRecordDetail] = useState(null);
  const [search, setSearch] = useState("");
  const [signatureName, setSignatureName] = useState(user?.full_name || user?.email || "");
  const [impression, setImpression] = useState("");
  const [saving, setSaving] = useState(false);
  const [sharing, setSharing] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const load = async () => {
    setError("");
    try {
      const { data } = await api.get("/radiology/imaging-records", { params: { limit: 400 } });
      const items = data?.items || [];
      setRecords(items);
      setSelectedId((prev) => {
        if (queryRecordId > 0) return queryRecordId;
        if (prev) return prev;
        return items.length ? items[0].imaging_record_id : null;
      });
    } catch (err) {
      setError(err?.response?.data?.detail || "Unable to load imaging records.");
    }
  };

  useEffect(() => {
    load();
  }, []);

  useEffect(() => {
    if (queryRecordId > 0) setSelectedId(queryRecordId);
  }, [queryRecordId]);

  useEffect(() => {
    if (!selectedId) return;
    let active = true;
    const fetchDetail = async () => {
      try {
        const { data } = await api.get(`/radiology/imaging-records/${selectedId}`);
        if (!active) return;
        setRecordDetail(data || null);
        const record = data?.record;
        if (record?.doctor_notes) setImpression(record.doctor_notes);
      } catch (err) {
        if (!active) return;
        setError(err?.response?.data?.detail || "Unable to load imaging report details.");
      }
    };
    fetchDetail();
    return () => {
      active = false;
    };
  }, [selectedId]);

  const filteredRecords = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return records;
    return records.filter((r) => {
      const blob = `${r.patient_mrn_snapshot || ""} ${r.patient_name_snapshot || ""} ${r.modality || ""} ${r.body_part || ""} ${r.imaging_record_id || ""}`.toLowerCase();
      return blob.includes(q);
    });
  }, [records, search]);

  const finalizeReport = async () => {
    if (!recordDetail?.record) return;
    if (!signatureName.trim()) {
      setError("Doctor signature name is required.");
      return;
    }
    setSaving(true);
    setError("");
    setSuccess("");
    try {
      await api.post(`/radiology/imaging-records/${recordDetail.record.imaging_record_id}/finalize`, {
        doctor_signature_name: signatureName.trim(),
        final_impression: impression.trim() || null,
      });
      setSuccess("Imaging report finalized and signed.");
      await load();
      const { data } = await api.get(`/radiology/imaging-records/${recordDetail.record.imaging_record_id}`);
      setRecordDetail(data || null);
    } catch (err) {
      setError(err?.response?.data?.detail || "Unable to finalize imaging report.");
    } finally {
      setSaving(false);
    }
  };

  const shareReport = async () => {
    if (!recordDetail?.record) return;
    setSharing(true);
    setError("");
    setSuccess("");
    try {
      await api.post("/reports/share", {
        report_type: "IMAGING_RECORD",
        source_record_id: recordDetail.record.imaging_record_id,
        share_to_patient: true,
        share_to_doctor: true,
      });
      setSuccess("Imaging report shared to Patient and Doctor dashboards.");
    } catch (err) {
      setError(err?.response?.data?.detail || "Unable to share imaging report.");
    } finally {
      setSharing(false);
    }
  };

  const onPrint = () => {
    const record = recordDetail?.record;
    if (!record) return;
    const hospital = recordDetail?.hospital || {};
    const win = window.open("", "_blank", "width=1100,height=900");
    if (!win) return;

    win.document.write(`
      <html>
        <head>
          <title>MedX Imaging Report</title>
          <style>
            @page { size: A4; margin: 12mm; }
            body { font-family: Segoe UI, Arial, sans-serif; color: #0f172a; margin:0; }
            .sheet { border:1px solid #cbd5e1; border-radius:16px; overflow:hidden; }
            .head { display:flex; justify-content:space-between; color:white; background:linear-gradient(120deg,#0f172a,#155e75); padding:14px 16px; }
            .content { padding:16px; }
            .grid { display:grid; grid-template-columns: 190px 1fr 190px 1fr; gap:8px 10px; font-size:13px; }
            .k { font-weight:700; color:#334155; }
            .viewer { margin-top:12px; border:1px solid #334155; border-radius:12px; background:#020617; min-height:260px; display:flex; align-items:center; justify-content:center; overflow:hidden; }
            .viewer img { max-height:420px; width:auto; object-fit:contain; }
            .badge { margin-top:10px; padding:8px 10px; border-radius:8px; background:#e0f2fe; border:1px solid #bae6fd; font-weight:700; color:#0c4a6e; }
            .sign { margin-top:18px; border-top:1px dashed #94a3b8; padding-top:10px; font-size:13px; }
          </style>
        </head>
        <body>
          <div class="sheet">
            <div class="head">
              <div><strong>MedX Radiology Suite</strong><br/>AI Imaging Report</div>
              <div>${new Date().toLocaleString()}</div>
            </div>
            <div class="content">
              <div class="grid">
                <div class="k">Hospital</div><div>${hospital.hospital_name || user?.hospital_name || "MedX"}</div>
                <div class="k">Patient MRN</div><div>${record.patient_mrn_snapshot || "-"}</div>
                <div class="k">Patient Name</div><div>${record.patient_name_snapshot || "-"}</div>
                <div class="k">Modality</div><div>${record.modality || "-"}</div>
                <div class="k">Body Part</div><div>${record.body_part || "-"}</div>
                <div class="k">Study Title</div><div>${record.study_title || "-"}</div>
                <div class="k">Status</div><div>${record.status || "-"}</div>
              </div>

              <div class="viewer">
                ${record.scan_image_data_url ? `<img src="${record.scan_image_data_url}" alt="Imaging scan" />` : "<p style='color:#94a3b8'>No image</p>"}
              </div>

              <div class="badge">AI Finding: ${record.ai_result || "N/A"} (${record.ai_confidence || "N/A"})</div>
              <p style="margin-top:10px; font-size:13px;"><strong>Doctor Impression:</strong> ${record.doctor_notes || "-"}</p>

              <div class="sign">
                <p><strong>Doctor Signature:</strong> ${record.doctor_signature_name || "-"}</p>
                <p><strong>Signed At:</strong> ${record.doctor_signature_at || "-"}</p>
              </div>
            </div>
          </div>
        </body>
      </html>
    `);
    win.document.close();
    win.focus();
    win.print();
  };

  const record = recordDetail?.record;

  return (
    <DoctorWorkspaceLayout
      title="Imaging Reports"
      subtitle="Radiology-only report workflow with scan image, AI findings, and doctor signature."
    >
      {error ? <p className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</p> : null}
      {success ? <p className="mt-3 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{success}</p> : null}

      <div className="mt-4 grid gap-5 xl:grid-cols-[0.9fr_1.4fr]">
        <section className="rounded-[32px] border border-slate-200 bg-white p-6 shadow-sm">
          <h2 className="text-lg font-bold">Imaging Records</h2>
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by MRN, patient, modality, body part"
            className="mt-3 w-full rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-cyan-500"
          />
          <div className="mt-3 max-h-[70vh] space-y-2 overflow-auto pr-1">
            {filteredRecords.length === 0 ? <p className="text-sm text-slate-500">No imaging records found.</p> : null}
            {filteredRecords.map((r) => (
              <button
                key={r.imaging_record_id}
                type="button"
                onClick={() => setSelectedId(r.imaging_record_id)}
                className={`w-full rounded-xl border p-3 text-left text-sm ${
                  selectedId === r.imaging_record_id ? "border-cyan-500 bg-cyan-50" : "border-slate-200 hover:bg-slate-50"
                }`}
              >
                <p className="font-semibold">{r.patient_name_snapshot || "-"} ({r.patient_mrn_snapshot || "-"})</p>
                <p className="text-slate-600">{r.modality} - {r.body_part}</p>
                <p className="text-xs text-slate-500">ID #{r.imaging_record_id}</p>
              </button>
            ))}
          </div>
        </section>

        <section className="rounded-[32px] border border-slate-200 bg-white p-6 shadow-sm">
          {!record ? <p className="text-sm text-slate-500">Select an imaging record.</p> : null}
          {record ? (
            <div className="space-y-4">
              <h2 className="text-lg font-bold">Imaging Report View</h2>
              <div className="grid gap-2 text-sm sm:grid-cols-2">
                <p><span className="font-semibold">MRN:</span> {record.patient_mrn_snapshot}</p>
                <p><span className="font-semibold">Name:</span> {record.patient_name_snapshot || "-"}</p>
                <p><span className="font-semibold">Modality:</span> {record.modality}</p>
                <p><span className="font-semibold">Body Part:</span> {record.body_part}</p>
                <p><span className="font-semibold">Study:</span> {record.study_title || "-"}</p>
                <p><span className="font-semibold">Status:</span> {record.status}</p>
              </div>

              <div className="rounded-[24px] border border-slate-800 bg-slate-950 p-3">
                <div className="relative flex min-h-80 items-center justify-center overflow-hidden rounded-xl bg-slate-900">
                  {record.scan_image_data_url ? (
                    <img src={record.scan_image_data_url} alt="Imaging scan" className="max-h-[480px] w-auto object-contain" />
                  ) : (
                    <p className="text-sm text-slate-400">No scan image available.</p>
                  )}
                  <div className="absolute inset-x-3 bottom-3 rounded-lg bg-slate-950/85 px-3 py-2 text-sm font-semibold text-cyan-100">
                    {record.ai_result || "N/A"} ({record.ai_confidence || "N/A"})
                  </div>
                </div>
              </div>

              <div className="rounded-xl border border-slate-200 p-3 text-sm">
                <p className="font-semibold">AI Findings JSON</p>
                <pre className="mt-2 max-h-44 overflow-auto rounded-lg bg-slate-100 p-2 text-xs text-slate-700">
                  {JSON.stringify(record.ai_findings_json || {}, null, 2)}
                </pre>
              </div>

              <div className="rounded-xl border border-slate-200 p-3 space-y-3">
                <p className="font-semibold text-sm">Doctor Final Signature</p>
                <label className="block space-y-1">
                  <span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Doctor Signature Name</span>
                  <input
                    value={signatureName}
                    onChange={(e) => setSignatureName(e.target.value)}
                    className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-cyan-500"
                  />
                </label>
                <label className="block space-y-1">
                  <span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Final Impression</span>
                  <textarea
                    value={impression}
                    onChange={(e) => setImpression(e.target.value)}
                    rows={4}
                    className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-cyan-500"
                  />
                </label>
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={finalizeReport}
                    disabled={saving}
                    className="rounded-xl bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-cyan-700 disabled:opacity-60"
                  >
                    {saving ? "Finalizing..." : "Finalize & Sign"}
                  </button>
                  <button
                    type="button"
                    onClick={onPrint}
                    className="inline-flex items-center gap-2 rounded-xl border border-cyan-600 px-4 py-2 text-sm font-semibold text-cyan-700 hover:bg-cyan-50"
                  >
                    <Printer className="h-4 w-4" /> Print Report
                  </button>
                  <button
                    type="button"
                    onClick={shareReport}
                    disabled={sharing}
                    className="rounded-xl border border-emerald-600 px-4 py-2 text-sm font-semibold text-emerald-700 hover:bg-emerald-50 disabled:opacity-60"
                  >
                    {sharing ? "Sharing..." : "Send To Patient + Doctor"}
                  </button>
                </div>
                <p className="text-xs text-slate-600">
                  Signed by: <span className="font-semibold">{record.doctor_signature_name || "-"}</span> | At:{" "}
                  <span className="font-semibold">{record.doctor_signature_at || "-"}</span>
                </p>
              </div>
            </div>
          ) : null}
        </section>
      </div>
    </DoctorWorkspaceLayout>
  );
}
