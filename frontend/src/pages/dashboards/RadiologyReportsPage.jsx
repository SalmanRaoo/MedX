import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { FileText, LogOut, Printer, ScanLine, Search } from "lucide-react";
import { api } from "../../lib/api";
import { clearSession, getSessionUser } from "../../lib/auth";

export default function RadiologyReportsPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const user = getSessionUser();

  const routeRecordId = Number(searchParams.get("record_id") || 0);
  const routeMrn = (searchParams.get("patient_mrn") || "").trim();

  const [records, setRecords] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [recordDetail, setRecordDetail] = useState(null);

  const [searchText, setSearchText] = useState("");
  const [filterMrn, setFilterMrn] = useState(routeMrn);
  const [filterScanId, setFilterScanId] = useState(routeRecordId > 0 ? String(routeRecordId) : "");

  const [signatureName, setSignatureName] = useState(user?.full_name || user?.email || "");
  const [manualImpression, setManualImpression] = useState("");

  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [sharing, setSharing] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const loadRecords = async () => {
    setLoading(true);
    setError("");
    try {
      const params = { limit: 400 };
      if (filterMrn.trim()) params.patient_mrn = filterMrn.trim();
      if (filterScanId && Number(filterScanId) > 0) params.imaging_record_id = Number(filterScanId);

      const { data } = await api.get("/radiology/imaging-records", { params });
      const items = data?.items || [];
      setRecords(items);
      setSelectedId((prev) => {
        if (routeRecordId > 0 && items.find((r) => Number(r.imaging_record_id) === Number(routeRecordId))) {
          return routeRecordId;
        }
        if (prev && items.find((r) => Number(r.imaging_record_id) === Number(prev))) return prev;
        return items.length ? items[0].imaging_record_id : null;
      });
      if (!items.length) {
        setRecordDetail(null);
      }
    } catch (err) {
      setError(err?.response?.data?.detail || "Unable to load radiology reports.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadRecords();
  }, []);

  useEffect(() => {
    if (routeRecordId > 0) setSelectedId(routeRecordId);
  }, [routeRecordId]);

  useEffect(() => {
    if (!selectedId) {
      setRecordDetail(null);
      return;
    }
    let active = true;
    const fetchDetail = async () => {
      try {
        setError("");
        const params = {};
        if (filterMrn.trim()) params.patient_mrn = filterMrn.trim();
        const { data } = await api.get(`/radiology/imaging-records/${selectedId}`, { params });
        if (!active) return;
        setRecordDetail(data || null);
        const notes = data?.record?.doctor_notes || "";
        setManualImpression(notes);
      } catch (err) {
        if (err?.response?.status === 404 && filterMrn.trim()) {
          try {
            const { data } = await api.get(`/radiology/imaging-records/${selectedId}`);
            if (!active) return;
            setRecordDetail(data || null);
            const notes = data?.record?.doctor_notes || "";
            setManualImpression(notes);
            return;
          } catch (fallbackErr) {
            if (!active) return;
            setRecordDetail(null);
            setError(fallbackErr?.response?.data?.detail || "Unable to load radiology report details.");
            return;
          }
        }
        if (!active) return;
        setRecordDetail(null);
        setError(err?.response?.data?.detail || "Unable to load radiology report details.");
      }
    };
    fetchDetail();
    return () => {
      active = false;
    };
  }, [selectedId, filterMrn]);

  const filteredRecords = useMemo(() => {
    const q = searchText.trim().toLowerCase();
    if (!q) return records;
    return records.filter((r) => {
      const blob = `${r.imaging_record_id || ""} ${r.patient_mrn_snapshot || ""} ${r.patient_name_snapshot || ""} ${r.modality || ""} ${r.body_part || ""}`.toLowerCase();
      return blob.includes(q);
    });
  }, [records, searchText]);

  const finalizeReport = async () => {
    if (!recordDetail?.record) return;
    if (!signatureName.trim()) {
      setError("Radiologist signature is required.");
      return;
    }
    setSaving(true);
    setError("");
    setSuccess("");
    try {
      await api.post(`/radiology/imaging-records/${recordDetail.record.imaging_record_id}/finalize`, {
        radiologist_signature_name: signatureName.trim(),
        manual_impression: manualImpression.trim() || null,
        status: "FINALIZED",
      });
      setSuccess("Radiology report finalized and signed.");
      await loadRecords();
      const params = {};
      if (filterMrn.trim()) params.patient_mrn = filterMrn.trim();
      const { data } = await api.get(`/radiology/imaging-records/${recordDetail.record.imaging_record_id}`, { params });
      setRecordDetail(data || null);
    } catch (err) {
      setError(err?.response?.data?.detail || "Unable to finalize radiology report.");
    } finally {
      setSaving(false);
    }
  };

  const shareReport = async () => {
    if (!recordDetail?.record?.imaging_record_id) return;
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
      setSuccess("Radiology report shared to Patient and Doctor dashboards.");
    } catch (err) {
      setError(err?.response?.data?.detail || "Unable to share radiology report.");
    } finally {
      setSharing(false);
    }
  };

  const printReport = () => {
    const record = recordDetail?.record;
    if (!record) return;
    const hospital = recordDetail?.hospital || {};
    const win = window.open("", "_blank", "width=1100,height=900");
    if (!win) return;

    win.document.write(`
      <html>
        <head>
          <title>MedX Radiology Report</title>
          <style>
            @page { size: A4; margin: 12mm; }
            body { font-family: Segoe UI, Arial, sans-serif; color: #0f172a; margin:0; }
            .sheet { border:1px solid #cbd5e1; border-radius:16px; overflow:hidden; }
            .head { display:flex; justify-content:space-between; color:white; background:linear-gradient(120deg,#0f172a,#0f766e); padding:14px 16px; }
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
              <div><strong>${hospital.hospital_name || user?.hospital_name || "MedX"}</strong><br/>Radiology Diagnostic Report</div>
              <div>${new Date().toLocaleString()}</div>
            </div>
            <div class="content">
              <div class="grid">
                <div class="k">Patient MRN</div><div>${record.patient_mrn_snapshot || "-"}</div>
                <div class="k">Scan ID</div><div>#${record.imaging_record_id || "-"}</div>
                <div class="k">Patient Name</div><div>${record.patient_name_snapshot || "-"}</div>
                <div class="k">Modality</div><div>${record.modality || "-"}</div>
                <div class="k">Body Part</div><div>${record.body_part || "-"}</div>
                <div class="k">Study Title</div><div>${record.study_title || "-"}</div>
              </div>

              <div class="viewer">
                ${record.scan_image_data_url ? `<img src="${record.scan_image_data_url}" alt="Radiology scan" />` : "<p style='color:#94a3b8'>No image uploaded</p>"}
              </div>

              <div class="badge">AI Result: ${record.ai_result || "N/A"} (${record.ai_confidence || "N/A"})</div>
              <p style="margin-top:10px; font-size:13px;"><strong>Radiologist Manual Impression:</strong> ${record.doctor_notes || "-"}</p>

              <div class="sign">
                <p><strong>Radiologist Signature:</strong> ${record.doctor_signature_name || "-"}</p>
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

  const handleLogout = () => {
    clearSession();
    navigate("/");
  };

  const record = recordDetail?.record;

  return (
    <div className="min-h-screen bg-slate-100 text-slate-900">
      <div className="flex min-h-screen">
        <aside className="no-print hidden w-72 bg-slate-900 p-6 text-white md:flex md:flex-col">
          <Link to="/dashboard/radiology" className="mb-8 block">
            <p className="text-xs uppercase tracking-[0.2em] text-cyan-300">MedX Radiology</p>
            <p className="mt-1 text-2xl font-extrabold">Imaging Suite</p>
          </Link>

          <div className="rounded-2xl border border-cyan-700/40 bg-slate-800/70 p-4 text-sm">
            <p className="font-semibold">{user?.hospital_name || "MedX"}</p>
            <p className="mt-1 text-slate-300">Separate radiology reporting workspace with print-ready A4 output.</p>
          </div>

          <nav className="mt-6 flex-1 space-y-2">
            <Link to="/dashboard/radiology" className="flex items-center gap-3 rounded-xl px-4 py-3 text-sm font-semibold text-slate-300 hover:bg-slate-800">
              <ScanLine className="h-4 w-4" /> Radiology Dashboard
            </Link>
            <Link to="/dashboard/radiology/reports" className="flex items-center gap-3 rounded-xl bg-cyan-600 px-4 py-3 text-sm font-semibold text-white">
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
          <header className="no-print rounded-[32px] border border-slate-200 bg-white p-6 shadow-sm">
            <h1 className="text-3xl font-black tracking-tight">Radiology Reports</h1>
            <p className="mt-1 text-slate-600">Fetch by MRN + Scan ID, finalize with radiologist impression, and print professional reports.</p>
          </header>

          {error ? <p className="no-print rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</p> : null}
          {success ? <p className="no-print rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{success}</p> : null}

          <div className="grid gap-5 xl:grid-cols-[0.9fr_1.4fr]">
            <section className="no-print rounded-[32px] border border-slate-200 bg-white p-6 shadow-sm">
              <h2 className="text-lg font-bold">Report Finder</h2>
              <div className="mt-3 grid gap-2 sm:grid-cols-2">
                <input
                  value={filterMrn}
                  onChange={(e) => setFilterMrn(e.target.value)}
                  placeholder="Patient MRN"
                  className="rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-cyan-500"
                />
                <input
                  value={filterScanId}
                  onChange={(e) => setFilterScanId(e.target.value)}
                  placeholder="Scan ID"
                  className="rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-cyan-500"
                />
              </div>
              <button
                type="button"
                onClick={loadRecords}
                className="mt-2 rounded-xl border border-cyan-600 px-3 py-2 text-sm font-semibold text-cyan-700 hover:bg-cyan-50"
              >
                Fetch Reports
              </button>

              <div className="relative mt-3">
                <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                <input
                  value={searchText}
                  onChange={(e) => setSearchText(e.target.value)}
                  placeholder="Search loaded reports"
                  className="w-full rounded-xl border border-slate-300 py-2 pl-9 pr-3 text-sm outline-none focus:border-cyan-500"
                />
              </div>

              <div className="mt-3 max-h-[70vh] space-y-2 overflow-auto pr-1">
                {loading ? <p className="text-sm text-slate-500">Loading reports...</p> : null}
                {!loading && filteredRecords.length === 0 ? <p className="text-sm text-slate-500">No radiology reports found.</p> : null}
                {filteredRecords.map((r) => (
                  <button
                    key={r.imaging_record_id}
                    type="button"
                    onClick={() => setSelectedId(r.imaging_record_id)}
                    className={`w-full rounded-xl border p-3 text-left text-sm ${
                      Number(selectedId) === Number(r.imaging_record_id)
                        ? "border-cyan-500 bg-cyan-50"
                        : "border-slate-200 hover:bg-slate-50"
                    }`}
                  >
                    <p className="font-semibold">#{r.imaging_record_id} | {r.patient_mrn_snapshot || "-"}</p>
                    <p className="text-slate-600">{r.patient_name_snapshot || "-"}</p>
                    <p className="text-xs text-slate-500">{r.modality || "-"} - {r.body_part || "-"}</p>
                  </button>
                ))}
              </div>
            </section>

            <section className="report-print-shell rounded-[32px] border border-slate-200 bg-white p-6 shadow-sm">
              {!record ? <p className="text-sm text-slate-500">Select a scan report from left panel.</p> : null}
              {record ? (
                <div className="space-y-4">
                  <h2 className="text-lg font-bold">Radiology Diagnostic Report</h2>
                  <div className="grid gap-2 text-sm sm:grid-cols-2">
                    <p><span className="font-semibold">Scan ID:</span> #{record.imaging_record_id}</p>
                    <p><span className="font-semibold">Patient MRN:</span> {record.patient_mrn_snapshot || "-"}</p>
                    <p><span className="font-semibold">Patient Name:</span> {record.patient_name_snapshot || "-"}</p>
                    <p><span className="font-semibold">Modality:</span> {record.modality || "-"}</p>
                    <p><span className="font-semibold">Body Part:</span> {record.body_part || "-"}</p>
                    <p><span className="font-semibold">Status:</span> {record.status || "-"}</p>
                  </div>

                  <div className="rounded-[24px] border border-slate-800 bg-slate-950 p-3">
                    <div className="relative flex min-h-80 items-center justify-center overflow-hidden rounded-xl bg-slate-900">
                      {record.scan_image_data_url ? (
                        <img src={record.scan_image_data_url} alt="Radiology scan" className="max-h-[480px] w-auto object-contain" />
                      ) : (
                        <p className="text-sm text-slate-400">No scan image available.</p>
                      )}
                      <div className="absolute inset-x-3 bottom-3 rounded-lg bg-slate-950/85 px-3 py-2 text-sm font-semibold text-cyan-100">
                        AI: {record.ai_result || "N/A"} ({record.ai_confidence || "N/A"})
                      </div>
                    </div>
                  </div>

                  <div className="no-print rounded-xl border border-slate-200 p-3 space-y-3">
                    <label className="block space-y-1">
                      <span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Radiologist Signature</span>
                      <input
                        value={signatureName}
                        onChange={(e) => setSignatureName(e.target.value)}
                        className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-cyan-500"
                      />
                    </label>
                    <label className="block space-y-1">
                      <span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Manual Impression / Notes</span>
                      <textarea
                        value={manualImpression}
                        onChange={(e) => setManualImpression(e.target.value)}
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
                        {saving ? "Finalizing..." : "Finalize Report"}
                      </button>
                      <button
                        type="button"
                        onClick={printReport}
                        className="inline-flex items-center gap-2 rounded-xl border border-cyan-600 px-4 py-2 text-sm font-semibold text-cyan-700 hover:bg-cyan-50"
                      >
                        <Printer className="h-4 w-4" /> Print Radiology Report
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
                  </div>

                  <div className="rounded-xl border border-slate-200 p-3 text-sm">
                    <p><span className="font-semibold">Radiologist Signature:</span> {record.doctor_signature_name || "-"}</p>
                    <p><span className="font-semibold">Signed At:</span> {record.doctor_signature_at || "-"}</p>
                    <p><span className="font-semibold">Manual Impression:</span> {record.doctor_notes || "-"}</p>
                  </div>
                </div>
              ) : null}
            </section>
          </div>
        </main>
      </div>
    </div>
  );
}
