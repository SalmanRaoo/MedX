import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Printer, Search } from "lucide-react";
import RoleDashboardShell from "../../components/dashboards/RoleDashboardShell";
import { api } from "../../lib/api";
import { getSessionUser } from "../../lib/auth";

function normalizeLabMarkers(raw) {
  if (Array.isArray(raw)) return raw;
  if (raw && typeof raw === "object") {
    const clinical = (raw.clinical_inputs || []).map((m) => ({ ...m, group: "clinical_inputs" }));
    const standard = (raw.standard_markers || []).map((m) => ({ ...m, group: "standard_markers" }));
    return [...clinical, ...standard];
  }
  return [];
}

function rrLabel(rr) {
  const min = rr?.min;
  const max = rr?.max;
  if (min !== undefined && max !== undefined) return `${min} - ${max}`;
  if (min !== undefined) return `>= ${min}`;
  if (max !== undefined) return `<= ${max}`;
  return "-";
}

export default function PatientReportsPage() {
  const user = getSessionUser();
  const role = (user?.role_name || "").toUpperCase();
  const isPatientRole = role === "PATIENT";

  const [patients, setPatients] = useState([]);
  const [patientId, setPatientId] = useState("");
  const [reports, setReports] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState("ALL");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (isPatientRole) return;
    let active = true;
    const loadPatients = async () => {
      try {
        const { data } = await api.get("/patients/", { params: { limit: 400 } });
        if (!active) return;
        const items = data?.items || [];
        setPatients(items);
        if (items.length) setPatientId(String(items[0].patient_id));
      } catch (err) {
        if (!active) return;
        setError(err?.response?.data?.detail || "Unable to load patients.");
      }
    };
    loadPatients();
    return () => {
      active = false;
    };
  }, [isPatientRole]);

  useEffect(() => {
    if (!isPatientRole && !patientId) return;
    let active = true;
    const loadReports = async () => {
      setLoading(true);
      setError("");
      try {
        const params = { audience: "PATIENT", limit: 300 };
        if (!isPatientRole) params.patient_id = Number(patientId);
        const { data } = await api.get("/reports/shared", { params });
        if (!active) return;
        const items = data?.items || [];
        setReports(items);
        setSelectedId(items.length ? items[0].shared_report_id : null);
      } catch (err) {
        if (!active) return;
        setError(err?.response?.data?.detail || "Unable to load shared reports.");
      } finally {
        if (active) setLoading(false);
      }
    };
    loadReports();
    return () => {
      active = false;
    };
  }, [isPatientRole, patientId]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return reports.filter((r) => {
      if (typeFilter !== "ALL" && r.report_type !== typeFilter) return false;
      if (!q) return true;
      const blob = `${r.title || ""} ${r.summary || ""} ${r.patient_name || ""} ${r.patient_mrn || ""}`.toLowerCase();
      return blob.includes(q);
    });
  }, [reports, search, typeFilter]);

  const selected = useMemo(
    () => filtered.find((r) => r.shared_report_id === selectedId) || filtered[0] || null,
    [filtered, selectedId]
  );

  const printSelected = () => {
    if (!selected?.report) return;
    const report = selected.report;
    const win = window.open("", "_blank", "width=1100,height=900");
    if (!win) return;

    if (selected.report_type === "IMAGING_RECORD") {
      win.document.write(`
        <html><head><title>Imaging Report</title>
        <style>
          body{font-family:Segoe UI,Arial,sans-serif;color:#0f172a;margin:0}
          .sheet{padding:16px}
          .viewer{margin-top:12px;border:1px solid #334155;border-radius:12px;background:#020617;min-height:260px;display:flex;align-items:center;justify-content:center;overflow:hidden}
          .viewer img{max-height:440px;width:auto;object-fit:contain}
          .k{font-weight:700}
        </style></head><body>
          <div class="sheet">
            <h2>MedX Imaging Report</h2>
            <p><span class="k">Patient:</span> ${report.patient_name_snapshot || "-"}</p>
            <p><span class="k">MRN:</span> ${report.patient_mrn_snapshot || "-"}</p>
            <p><span class="k">Modality:</span> ${report.modality || "-"}</p>
            <p><span class="k">Body Part:</span> ${report.body_part || "-"}</p>
            <p><span class="k">AI Finding:</span> ${report.ai_result || "N/A"} (${report.ai_confidence || "N/A"})</p>
            <p><span class="k">Doctor Notes:</span> ${report.doctor_notes || "-"}</p>
            <div class="viewer">
              ${report.scan_image_data_url ? `<img src="${report.scan_image_data_url}" alt="scan" />` : "<p style='color:#94a3b8'>No image</p>"}
            </div>
          </div>
        </body></html>
      `);
      win.document.close();
      win.focus();
      win.print();
      return;
    }

    const markerRows = normalizeLabMarkers(report.markers_json || {});
    const markersHtml = markerRows
      .map((m) => {
        const category = m.group === "clinical_inputs" ? "Clinical Inputs" : m.group === "standard_markers" ? "Standard Markers" : "Markers";
        return `<tr><td>${category}</td><td>${m.marker_name || m.key || "-"}</td><td>${m.result_value ?? "-"}</td><td>${rrLabel(m.reference_range)}</td><td>${m.units || "-"}</td></tr>`;
      })
      .join("");
    const aiHtml = Object.entries(report.ai_outputs_json || {})
      .map(([k, v]) => `<tr><td>${k}</td><td>${(v || {}).result || (v || {}).prediction || (v || {}).error || "N/A"}</td><td>${(v || {}).confidence || "-"}</td></tr>`)
      .join("");

    win.document.write(`
      <html><head><title>Lab Report</title>
      <style>
        body{font-family:Segoe UI,Arial,sans-serif;color:#0f172a;margin:0}
        .sheet{padding:16px}
        .k{font-weight:700}
        table{width:100%;border-collapse:collapse;margin-top:12px}
        th,td{border:1px solid #cbd5e1;padding:8px;text-align:left;font-size:13px}
        th{background:#f1f5f9}
      </style></head><body>
        <div class="sheet">
          <h2>MedX Laboratory Report</h2>
          <p><span class="k">Patient:</span> ${report.patient_full_name_snapshot || "-"}</p>
          <p><span class="k">MRN:</span> ${report.patient_mrn_snapshot || "-"}</p>
          <p><span class="k">Test Type:</span> ${report.test_type || "-"}</p>
          <p><span class="k">Specimen:</span> ${report.specimen_type || "-"}</p>
          <table><thead><tr><th>Category</th><th>Marker</th><th>Result</th><th>Range</th><th>Units</th></tr></thead>
          <tbody>${markersHtml || '<tr><td colspan="5">No markers</td></tr>'}</tbody></table>
          <table><thead><tr><th>Model</th><th>Prediction</th><th>Confidence</th></tr></thead>
          <tbody>${aiHtml || '<tr><td colspan="3">No AI output</td></tr>'}</tbody></table>
        </div>
      </body></html>
    `);
    win.document.close();
    win.focus();
    win.print();
  };

  const cards = useMemo(
    () => [
      { title: "Shared Reports", text: String(reports.length) },
      { title: "Lab Reports", text: String(reports.filter((r) => r.report_type === "LAB_RECORD").length) },
      { title: "Imaging Reports", text: String(reports.filter((r) => r.report_type === "IMAGING_RECORD").length) },
    ],
    [reports]
  );

  return (
    <>
      <RoleDashboardShell
        title="Patient Reports"
        subtitle="Published Lab and Imaging reports from doctor/lab workflows."
        cards={cards}
      />

      <section className="px-4 pb-10 sm:px-6 lg:px-8 -mt-2">
        <div className="mx-auto max-w-7xl space-y-5">
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="flex flex-wrap items-end gap-3">
              {!isPatientRole ? (
                <label className="space-y-1">
                  <span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Patient</span>
                  <select
                    value={patientId}
                    onChange={(e) => setPatientId(e.target.value)}
                    className="w-72 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-cyan-500"
                  >
                    {patients.map((p) => (
                      <option key={p.patient_id} value={p.patient_id}>
                        {p.full_name} (MRN: {p.patient_mrn})
                      </option>
                    ))}
                  </select>
                </label>
              ) : null}
              <label className="space-y-1">
                <span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Type</span>
                <select
                  value={typeFilter}
                  onChange={(e) => setTypeFilter(e.target.value)}
                  className="w-48 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-cyan-500"
                >
                  <option value="ALL">All</option>
                  <option value="LAB_RECORD">Lab</option>
                  <option value="IMAGING_RECORD">Imaging</option>
                </select>
              </label>
              <label className="space-y-1 grow">
                <span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Search</span>
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                  <input
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    placeholder="Search title, summary, patient, MRN"
                    className="w-full rounded-lg border border-slate-300 py-2 pl-9 pr-3 text-sm outline-none focus:border-cyan-500"
                  />
                </div>
              </label>
              <Link to="/dashboard/patient" className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50">
                Back to Dashboard
              </Link>
            </div>
            {error ? <p className="mt-3 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</p> : null}
          </div>

          <div className="grid gap-5 xl:grid-cols-[0.9fr_1.4fr]">
            <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <h3 className="text-lg font-bold">Published Reports</h3>
              {loading ? <p className="mt-2 text-sm text-slate-500">Loading...</p> : null}
              {!loading && filtered.length === 0 ? <p className="mt-2 text-sm text-slate-500">No reports available.</p> : null}
              <div className="mt-3 max-h-[65vh] space-y-2 overflow-auto pr-1">
                {filtered.map((r) => (
                  <button
                    key={r.shared_report_id}
                    type="button"
                    onClick={() => setSelectedId(r.shared_report_id)}
                    className={`w-full rounded-xl border p-3 text-left text-sm ${
                      selected?.shared_report_id === r.shared_report_id
                        ? "border-cyan-500 bg-cyan-50"
                        : "border-slate-200 hover:bg-slate-50"
                    }`}
                  >
                    <p className="font-semibold">{r.title || `${r.report_type} #${r.source_record_id}`}</p>
                    <p className="text-slate-600">{r.summary || "-"}</p>
                    <p className="text-xs text-slate-500">{r.patient_name || "-"} ({r.patient_mrn || "-"})</p>
                  </button>
                ))}
              </div>
            </section>

            <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              {!selected ? <p className="text-sm text-slate-500">Select a report.</p> : null}
              {selected ? (
                <div className="space-y-4">
                  <div className="flex items-center justify-between">
                    <h3 className="text-lg font-bold">Report Detail</h3>
                    <button
                      type="button"
                      onClick={printSelected}
                      className="inline-flex items-center gap-2 rounded-lg border border-cyan-600 px-4 py-2 text-sm font-semibold text-cyan-700 hover:bg-cyan-50"
                    >
                      <Printer className="h-4 w-4" /> Print
                    </button>
                  </div>

                  <div className="grid gap-2 text-sm sm:grid-cols-2">
                    <p><span className="font-semibold">Type:</span> {selected.report_type}</p>
                    <p><span className="font-semibold">Patient:</span> {selected.patient_name || "-"}</p>
                    <p><span className="font-semibold">MRN:</span> {selected.patient_mrn || "-"}</p>
                    <p><span className="font-semibold">Shared At:</span> {selected.created_at || "-"}</p>
                  </div>

                  {selected.report_type === "IMAGING_RECORD" ? (
                    <div className="space-y-3">
                      <div className="rounded-xl border border-slate-200 p-3 text-sm">
                        <p><span className="font-semibold">Modality:</span> {selected.report?.modality || "-"}</p>
                        <p><span className="font-semibold">Body Part:</span> {selected.report?.body_part || "-"}</p>
                        <p><span className="font-semibold">AI Finding:</span> {selected.report?.ai_result || "N/A"} ({selected.report?.ai_confidence || "N/A"})</p>
                        <p><span className="font-semibold">Doctor Notes:</span> {selected.report?.doctor_notes || "-"}</p>
                      </div>
                      <div className="rounded-xl border border-slate-800 bg-slate-950 p-3">
                        <div className="relative flex min-h-72 items-center justify-center overflow-hidden rounded-xl bg-slate-900">
                          {selected.report?.scan_image_data_url ? (
                            <img src={selected.report.scan_image_data_url} alt="Imaging scan" className="max-h-[480px] w-auto object-contain" />
                          ) : (
                            <p className="text-sm text-slate-400">No scan image available.</p>
                          )}
                        </div>
                      </div>
                    </div>
                  ) : (
                    <div className="space-y-3">
                      <div className="rounded-xl border border-slate-200 p-3 text-sm">
                        <p><span className="font-semibold">Test Type:</span> {selected.report?.test_type || "-"}</p>
                        <p><span className="font-semibold">Specimen:</span> {selected.report?.specimen_type || "-"}</p>
                      </div>
                      <div className="overflow-auto rounded-xl border border-slate-200">
                        <table className="min-w-full text-sm">
                          <thead className="bg-slate-50">
                            <tr>
                              <th className="px-3 py-2 text-left">Category</th>
                              <th className="px-3 py-2 text-left">Marker</th>
                              <th className="px-3 py-2 text-left">Result</th>
                              <th className="px-3 py-2 text-left">Range</th>
                              <th className="px-3 py-2 text-left">Units</th>
                            </tr>
                          </thead>
                          <tbody>
                            {normalizeLabMarkers(selected.report?.markers_json || {}).map((m, idx) => (
                              <tr key={`${m.key || m.marker_name || "m"}-${idx}`} className="border-t border-slate-100">
                                <td className="px-3 py-2">
                                  {m.group === "clinical_inputs" ? "Clinical Inputs" : m.group === "standard_markers" ? "Standard Markers" : "Markers"}
                                </td>
                                <td className="px-3 py-2">{m.marker_name || m.key || "-"}</td>
                                <td className="px-3 py-2">{m.result_value ?? "-"}</td>
                                <td className="px-3 py-2">{rrLabel(m.reference_range)}</td>
                                <td className="px-3 py-2">{m.units || "-"}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}
                </div>
              ) : null}
            </section>
          </div>
        </div>
      </section>
    </>
  );
}
