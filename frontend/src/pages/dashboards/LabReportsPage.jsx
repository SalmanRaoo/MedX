import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { FlaskConical, FileText, LogOut, Printer, Search, WandSparkles } from "lucide-react";
import { api } from "../../lib/api";
import { clearSession, getSessionUser } from "../../lib/auth";

function getAge(dob) {
  if (!dob) return "-";
  const d = new Date(dob);
  if (Number.isNaN(d.getTime())) return "-";
  const now = new Date();
  let age = now.getFullYear() - d.getFullYear();
  const m = now.getMonth() - d.getMonth();
  if (m < 0 || (m === 0 && now.getDate() < d.getDate())) age -= 1;
  return age >= 0 ? age : "-";
}

function rrLabel(rr) {
  const min = rr?.min;
  const max = rr?.max;
  if (min !== undefined && max !== undefined) return `${min} - ${max}`;
  if (min !== undefined) return `>= ${min}`;
  if (max !== undefined) return `<= ${max}`;
  return "-";
}

export default function LabReportsPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const user = getSessionUser();
  const queryRecordId = Number(searchParams.get("record_id") || 0);
  const queryMrn = (searchParams.get("patient_mrn") || "").trim();

  const [records, setRecords] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [recordReport, setRecordReport] = useState(null);
  const [entrySearch, setEntrySearch] = useState("");
  const [filterMrn, setFilterMrn] = useState(queryMrn);
  const [filterRecordId, setFilterRecordId] = useState(queryRecordId > 0 ? String(queryRecordId) : "");
  const [sharing, setSharing] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const params = { status: "COMPLETED", limit: 400 };
      if (filterMrn.trim()) params.patient_mrn = filterMrn.trim();
      if (filterRecordId && Number(filterRecordId) > 0) params.record_id = Number(filterRecordId);
      const { data } = await api.get("/lab/records", { params });
      const items = data?.items || [];
      setRecords(items);
      setSelectedId((prev) => {
        if (queryRecordId > 0) return queryRecordId;
        if (prev) return prev;
        return items.length ? items[0].record_id : null;
      });
    } catch (err) {
      setError(err?.response?.data?.detail || "Unable to load lab reports.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  useEffect(() => {
    if (queryRecordId > 0) {
      setSelectedId(queryRecordId);
    }
  }, [queryRecordId]);

  useEffect(() => {
    if (!selectedId) return;
    let active = true;
    const fetchReport = async () => {
      try {
        const params = {};
        if (filterMrn.trim()) params.patient_mrn = filterMrn.trim();
        const { data } = await api.get(`/lab/records/${selectedId}/report`, { params });
        if (!active) return;
        setRecordReport(data || null);
      } catch (err) {
        if (!active) return;
        setError(err?.response?.data?.detail || "Unable to load report view.");
      }
    };
    fetchReport();
    return () => {
      active = false;
    };
  }, [selectedId, filterMrn]);

  const filteredRecords = useMemo(() => {
    const q = entrySearch.trim().toLowerCase();
    if (!q) return records;
    return records.filter((e) => {
      const blob = `${e.patient_name || ""} ${e.patient_mrn || ""} ${e.test_type || ""} ${e.record_id || ""}`.toLowerCase();
      return blob.includes(q);
    });
  }, [records, entrySearch]);

  const markerRows = useMemo(() => {
    const raw = recordReport?.record?.markers_json;
    if (Array.isArray(raw)) {
      return raw.map((r) => ({ ...r, group: r.group || "markers" }));
    }
    if (raw && typeof raw === "object") {
      const clinical = (raw.clinical_inputs || []).map((r) => ({ ...r, group: "clinical_inputs" }));
      const standard = (raw.standard_markers || []).map((r) => ({ ...r, group: "standard_markers" }));
      return [...clinical, ...standard];
    }
    return [];
  }, [recordReport]);

  const onPrint = () => {
    if (!recordReport?.record) return;
    const record = recordReport.record;
    const hospital = recordReport.hospital || {};
    const ai = record.ai_outputs_json || {};
    const verifierName = user?.full_name || user?.email || "Lab Technician";

    const rowsHtml = markerRows
      .map((r) => {
        const cls = r.critical_flag ? " style='color:#be123c;font-weight:700'" : "";
        const category = r.group === "clinical_inputs" ? "Clinical Inputs" : r.group === "standard_markers" ? "Standard Markers" : "Markers";
        const modelCode = r.model_code || "-";
        return `<tr${cls}><td>${category}</td><td>${modelCode}</td><td>${r.marker_name}</td><td>${r.result_value ?? "-"}</td><td>${rrLabel(r.reference_range)}</td><td>${r.units || "-"}</td><td>${r.critical_flag ? "Yes" : "No"}</td></tr>`;
      })
      .join("");

    const aiHtml = Object.entries(ai)
      .map(([k, v]) => {
        const obj = v || {};
        if (obj.error) return `<tr><td>${k}</td><td colspan="2">Error: ${obj.error}</td></tr>`;
        return `<tr><td>${k}</td><td>${obj.result || obj.prediction || "N/A"}</td><td>${obj.confidence || "N/A"}</td></tr>`;
      })
      .join("");

    const win = window.open("", "_blank", "width=1100,height=900");
    if (!win) return;

    win.document.write(`
      <html>
        <head>
          <title>MedX Lab Record</title>
          <style>
            @page { size: A4; margin: 12mm; }
            body { font-family: Segoe UI, Arial, sans-serif; color: #0f172a; margin: 0; background: #f8fafc; }
            .sheet { border: 1px solid #cbd5e1; border-radius: 18px; overflow: hidden; }
            .header { display:flex; justify-content:space-between; align-items:center; padding:16px 18px; color:white; background: linear-gradient(120deg,#0f172a,#0f766e); }
            .brand { display:flex; align-items:center; gap:10px; }
            .logo { width:34px; height:34px; border-radius:999px; background:#2dd4bf; border:2px solid #99f6e4; }
            .content { padding: 16px 18px; }
            .grid { display:grid; grid-template-columns: 180px 1fr 180px 1fr; gap:8px 10px; font-size: 13px; }
            .k { font-weight:700; color:#334155; }
            table { width:100%; border-collapse: collapse; margin-top: 12px; font-size: 13px; }
            th, td { border:1px solid #cbd5e1; padding:8px; text-align:left; }
            th { background:#e2e8f0; }
            .section-title { margin-top: 16px; font-size: 14px; font-weight: 800; }
            .sheet-wrap { position: relative; }
            .watermark {
              position: absolute;
              inset: 0;
              display: flex;
              align-items: center;
              justify-content: center;
              pointer-events: none;
              opacity: 0.08;
              font-size: 44px;
              font-weight: 900;
              color: #0f766e;
              transform: rotate(-22deg);
              letter-spacing: 0.08em;
              text-transform: uppercase;
            }
            .sign { margin-top: 16px; border-top: 1px dashed #94a3b8; padding-top: 10px; font-size: 13px; }
          </style>
        </head>
        <body>
          <div class="sheet sheet-wrap">
            <div class="watermark">Lab Technician Verified</div>
            <div class="header">
              <div class="brand"><div class="logo"></div><div><strong>MedX Laboratory</strong><br/>Clinical Lab Report</div></div>
              <div>${new Date().toLocaleString()}</div>
            </div>
            <div class="content">
              <div class="grid">
                <div class="k">Hospital</div><div>${hospital.hospital_name || user?.hospital_name || "MedX"}</div>
                <div class="k">Address</div><div>${hospital.address || "-"}</div>
                <div class="k">Patient MRN</div><div>${record.patient_mrn || "-"}</div>
                <div class="k">Patient Name</div><div>${record.patient_name || "-"}</div>
                <div class="k">Gender</div><div>${record.patient_gender || record.patient_gender_snapshot || "-"}</div>
                <div class="k">Age</div><div>${getAge(record.patient_dob) !== "-" ? getAge(record.patient_dob) : (record.patient_age_snapshot || "-")}</div>
                <div class="k">Test Type</div><div>${record.test_type || "-"}</div>
                <div class="k">Specimen</div><div>${record.specimen_type || "-"}</div>
                <div class="k">Collection Time</div><div>${record.collection_timestamp || "-"}</div>
                <div class="k">Clinical Notes</div><div>${record.clinical_notes || "-"}</div>
              </div>

              <div class="section-title">Laboratory Markers</div>
              <table>
                <thead><tr><th>Category</th><th>Model</th><th>Marker</th><th>Result</th><th>Reference Range</th><th>Units</th><th>Critical</th></tr></thead>
                <tbody>${rowsHtml || '<tr><td colspan="7">No markers found.</td></tr>'}</tbody>
              </table>

              <div class="section-title">AI Insight</div>
              <table>
                <thead><tr><th>Model</th><th>Prediction</th><th>Confidence</th></tr></thead>
                <tbody>${aiHtml || '<tr><td colspan="3">No AI output for this report.</td></tr>'}</tbody>
              </table>

              <div class="sign">
                <p><strong>Lab Technician Verified:</strong> ${verifierName}</p>
                <p><strong>Verification Time:</strong> ${new Date().toLocaleString()}</p>
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

  const shareReport = async () => {
    if (!recordReport?.record?.record_id) return;
    setSharing(true);
    setError("");
    setSuccess("");
    try {
      await api.post("/reports/share", {
        report_type: "LAB_RECORD",
        source_record_id: recordReport.record.record_id,
        share_to_patient: true,
        share_to_doctor: true,
      });
      setSuccess("Lab report shared to Patient and Doctor dashboards.");
    } catch (err) {
      setError(err?.response?.data?.detail || "Unable to share lab report.");
    } finally {
      setSharing(false);
    }
  };

  const handleLogout = () => {
    clearSession();
    navigate("/");
  };

  return (
    <div className="min-h-screen bg-slate-100 text-slate-900">
      <div className="flex min-h-screen">
        <aside className="no-print hidden w-72 bg-slate-900 p-6 text-white md:flex md:flex-col">
          <Link to="/dashboard/lab" className="mb-8 block">
            <p className="text-xs uppercase tracking-[0.2em] text-teal-300">MedX Laboratory</p>
            <p className="mt-1 text-2xl font-extrabold">Technician Desk</p>
          </Link>

          <div className="rounded-2xl border border-teal-700/40 bg-slate-800/70 p-4 text-sm">
            <p className="font-semibold">{user?.hospital_name || "MedX"}</p>
            <p className="mt-1 text-slate-300">Professional record review and print-ready report output.</p>
          </div>

          <nav className="mt-6 flex-1 space-y-2">
            <Link to="/dashboard/lab" className="flex items-center gap-3 rounded-xl px-4 py-3 text-sm font-semibold text-slate-300 hover:bg-slate-800">
              <FlaskConical className="h-4 w-4" /> Lab Home
            </Link>
            <Link to="/dashboard/lab/generate" className="flex items-center gap-3 rounded-xl px-4 py-3 text-sm font-semibold text-slate-300 hover:bg-slate-800">
              <WandSparkles className="h-4 w-4" /> Generate Report
            </Link>
            <Link to="/dashboard/lab/reports" className="flex items-center gap-3 rounded-xl bg-teal-600 px-4 py-3 text-sm font-semibold text-white">
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
          <header className="no-print rounded-[32px] border border-slate-200 bg-white p-6 shadow-sm">
            <h1 className="text-3xl font-black tracking-tight">Report Management</h1>
            <p className="mt-1 text-slate-600">Review completed laboratory datasets and print professional reports.</p>
          </header>

          {error ? <p className="no-print rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</p> : null}
          {success ? <p className="no-print rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{success}</p> : null}

          <div className="grid gap-5 xl:grid-cols-[0.95fr_1.35fr]">
            <section className="no-print rounded-[32px] border border-slate-200 bg-white p-6 shadow-sm">
              <h2 className="text-lg font-bold">Completed Records</h2>
              <div className="mt-3 grid gap-2 sm:grid-cols-2">
                <input
                  value={filterMrn}
                  onChange={(e) => setFilterMrn(e.target.value)}
                  className="rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-teal-500"
                  placeholder="Filter by MRN"
                />
                <input
                  value={filterRecordId}
                  onChange={(e) => setFilterRecordId(e.target.value)}
                  className="rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-teal-500"
                  placeholder="Filter by Record ID"
                />
              </div>
              <button
                type="button"
                onClick={load}
                className="mt-2 rounded-xl border border-teal-600 px-3 py-2 text-sm font-semibold text-teal-700 hover:bg-teal-50"
              >
                Fetch Reports
              </button>
              <label className="mt-3 block space-y-1">
                <span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Search Test / Patient</span>
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                  <input
                    value={entrySearch}
                    onChange={(e) => setEntrySearch(e.target.value)}
                    className="w-full rounded-xl border border-slate-300 py-2 pl-9 pr-3 text-sm outline-none focus:border-teal-500"
                    placeholder="Search by test type, patient, MRN, or record id"
                  />
                </div>
              </label>
              <div className="mt-3 max-h-[70vh] space-y-2 overflow-auto pr-1">
                {!loading && filteredRecords.length === 0 ? <p className="text-sm text-slate-500">No matching records found.</p> : null}
                {filteredRecords.map((r) => (
                  <div
                    key={r.record_id}
                    className={`rounded-xl border p-3 text-sm ${
                      selectedId === r.record_id ? "border-teal-500 bg-teal-50" : "border-slate-200"
                    }`}
                  >
                    <p className="font-semibold">{r.patient_name} ({r.patient_mrn})</p>
                    <p className="text-slate-600">Test Type: {r.test_type}</p>
                    <p className="text-xs text-slate-500">Collection: {r.collection_timestamp || "-"}</p>
                    <button
                      type="button"
                      onClick={() => setSelectedId(r.record_id)}
                      className="mt-2 rounded-lg border border-slate-300 px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-100"
                    >
                      Generate Report
                    </button>
                  </div>
                ))}
              </div>
            </section>

            <section className="report-print-shell rounded-[32px] border border-slate-200 bg-white p-6 shadow-sm">
              <h2 className="text-lg font-bold">Professional Result View</h2>
              {!recordReport?.record ? <p className="mt-3 text-sm text-slate-500">Select a record to open report view.</p> : null}
              {recordReport?.record ? (
                <div className="mt-3 space-y-4">
                  <div className="grid gap-2 text-sm sm:grid-cols-2">
                    <p><span className="font-semibold">MRN:</span> {recordReport.record.patient_mrn || "-"}</p>
                    <p><span className="font-semibold">Name:</span> {recordReport.record.patient_name || "-"}</p>
                    <p><span className="font-semibold">Gender:</span> {recordReport.record.patient_gender || recordReport.record.patient_gender_snapshot || "-"}</p>
                    <p><span className="font-semibold">Age:</span> {getAge(recordReport.record.patient_dob) !== "-" ? getAge(recordReport.record.patient_dob) : (recordReport.record.patient_age_snapshot || "-")}</p>
                    <p><span className="font-semibold">Test:</span> {recordReport.record.test_type || "-"}</p>
                    <p><span className="font-semibold">Specimen:</span> {recordReport.record.specimen_type || "-"}</p>
                  </div>

                  <div className="overflow-auto rounded-xl border border-slate-200">
                    <table className="min-w-full text-sm">
                      <thead className="bg-slate-50">
                        <tr>
                          <th className="px-3 py-2 text-left">Category</th>
                          <th className="px-3 py-2 text-left">Model</th>
                          <th className="px-3 py-2 text-left">Marker</th>
                          <th className="px-3 py-2 text-left">Result</th>
                          <th className="px-3 py-2 text-left">Range</th>
                          <th className="px-3 py-2 text-left">Units</th>
                          <th className="px-3 py-2 text-left">Critical</th>
                        </tr>
                      </thead>
                      <tbody>
                        {markerRows.length === 0 ? (
                          <tr><td className="px-3 py-2" colSpan={7}>No marker data available.</td></tr>
                        ) : (
                          markerRows.map((m) => (
                            <tr key={m.key} className={`border-t ${m.critical_flag ? "bg-rose-50 text-rose-700" : "border-slate-100"}`}>
                              <td className="px-3 py-2">{m.group === "clinical_inputs" ? "Clinical Inputs" : m.group === "standard_markers" ? "Standard Markers" : "Markers"}</td>
                              <td className="px-3 py-2">{m.model_code || "-"}</td>
                              <td className="px-3 py-2">{m.marker_name}</td>
                              <td className="px-3 py-2">{m.result_value}</td>
                              <td className="px-3 py-2">{rrLabel(m.reference_range)}</td>
                              <td className="px-3 py-2">{m.units || "-"}</td>
                              <td className="px-3 py-2">{m.critical_flag ? "Yes" : "No"}</td>
                            </tr>
                          ))
                        )}
                      </tbody>
                    </table>
                  </div>

                  <div className="rounded-xl border border-slate-200 p-3">
                    <p className="text-sm font-bold">AI Insight (If Applicable)</p>
                    <div className="mt-2 space-y-1 text-sm">
                      {Object.keys(recordReport.record.ai_outputs_json || {}).length === 0 ? (
                        <p className="text-slate-500">No AI output for this report.</p>
                      ) : (
                        Object.entries(recordReport.record.ai_outputs_json || {}).map(([k, v]) => {
                          const obj = v || {};
                          return (
                            <p key={k}>
                              <span className="font-semibold">{k}:</span> {obj.result || obj.prediction || obj.error || "N/A"}
                              {obj.confidence ? ` (${obj.confidence})` : ""}
                            </p>
                          );
                        })
                      )}
                    </div>
                  </div>

                  <div className="flex gap-3">
                    <button
                      type="button"
                      onClick={() => setSelectedId(recordReport.record.record_id)}
                      className="no-print rounded-xl border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50"
                    >
                      Generate Report
                    </button>
                    <button
                      type="button"
                      onClick={onPrint}
                      className="no-print inline-flex items-center gap-2 rounded-xl border border-teal-600 px-4 py-2 text-sm font-semibold text-teal-700 hover:bg-teal-50"
                    >
                      <Printer className="h-4 w-4" /> Print Lab Report
                    </button>
                    <button
                      type="button"
                      onClick={shareReport}
                      disabled={sharing}
                      className="no-print rounded-xl border border-emerald-600 px-4 py-2 text-sm font-semibold text-emerald-700 hover:bg-emerald-50 disabled:opacity-60"
                    >
                      {sharing ? "Sharing..." : "Send To Patient + Doctor"}
                    </button>
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
