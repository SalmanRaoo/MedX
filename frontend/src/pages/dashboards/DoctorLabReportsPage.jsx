import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Printer, Search } from "lucide-react";
import { api } from "../../lib/api";
import DoctorWorkspaceLayout from "../../components/dashboards/DoctorWorkspaceLayout";

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

export default function DoctorLabReportsPage() {
  const [searchParams] = useSearchParams();
  const queryRecordId = Number(searchParams.get("record_id") || 0);

  const [reports, setReports] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    const loadReports = async () => {
      setLoading(true);
      setError("");
      try {
        const { data } = await api.get("/doctor/lab-reports", {
          params: {
            status: "COMPLETED",
            limit: 2000,
          },
        });
        if (!active) return;
        const items = (data?.items || []).map((r) => ({
          shared_report_id: Number(r.record_id),
          source_record_id: Number(r.record_id),
          patient_name: r.patient_name || r.patient_full_name_snapshot || "-",
          patient_mrn: r.patient_mrn || r.patient_mrn_snapshot || "-",
          title: `Lab Report: ${r.test_type || "LAB"}`,
          summary: `Specimen: ${r.specimen_type || "-"} | Status: ${r.status || "-"}`,
          created_at: r.created_at || r.updated_at || "-",
          report: r,
        }));
        setReports(items);
        setSelectedId((prev) => {
          if (queryRecordId > 0) {
            const byRecordId = items.find((r) => Number(r.source_record_id) === queryRecordId);
            if (byRecordId) return byRecordId.shared_report_id;
          }
          if (prev && items.find((r) => r.shared_report_id === prev)) return prev;
          return items.length ? items[0].shared_report_id : null;
        });
      } catch (err) {
        if (!active) return;
        setReports([]);
        setSelectedId(null);
        setError(err?.response?.data?.detail || "Unable to load lab reports.");
      } finally {
        if (active) setLoading(false);
      }
    };
    loadReports();
    return () => {
      active = false;
    };
  }, [queryRecordId]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return reports;
    return reports.filter((r) => {
      const blob = `${r.title || ""} ${r.summary || ""} ${r.patient_name || ""} ${r.patient_mrn || ""} ${r.source_record_id || ""}`.toLowerCase();
      return blob.includes(q);
    });
  }, [reports, search]);

  const selected = useMemo(
    () => filtered.find((r) => r.shared_report_id === selectedId) || filtered[0] || null,
    [filtered, selectedId]
  );

  const printSelected = () => {
    if (!selected?.report) return;
    const report = selected.report;
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

    const win = window.open("", "_blank", "width=1100,height=900");
    if (!win) return;

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
          <p><span class="k">Patient:</span> ${report.patient_full_name_snapshot || selected.patient_name || "-"}</p>
          <p><span class="k">MRN:</span> ${report.patient_mrn_snapshot || selected.patient_mrn || "-"}</p>
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

  return (
    <DoctorWorkspaceLayout
      title="Lab Reports"
      subtitle="Doctor-only lab report view sourced from reports shared to doctor dashboards."
    >
      {error ? <p className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</p> : null}

      <div className="mt-4 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="grid gap-3 md:grid-cols-1">
          <label className="space-y-1">
            <span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Search Reports</span>
            <div className="relative">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search patient, MRN, test, summary, record id"
                className="w-full rounded-lg border border-slate-300 py-2 pl-9 pr-3 text-sm outline-none focus:border-cyan-500"
              />
            </div>
          </label>
        </div>
      </div>

      <div className="mt-5 grid gap-5 xl:grid-cols-[0.9fr_1.4fr]">
        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <h3 className="text-lg font-bold">Lab Reports</h3>
          <p className="mt-1 text-xs text-slate-500">Showing completed lab reports across all patients in your hospital.</p>
          {loading ? <p className="mt-2 text-sm text-slate-500">Loading...</p> : null}
          {!loading && filtered.length === 0 ? <p className="mt-2 text-sm text-slate-500">No lab reports available.</p> : null}
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
                <p className="font-semibold">{r.title || `LAB_RECORD #${r.source_record_id}`}</p>
                <p className="text-slate-600">{r.summary || "-"}</p>
                <p className="text-xs text-slate-500">MRN: {r.patient_mrn || "-"} | Record #{r.source_record_id || "-"}</p>
              </button>
            ))}
          </div>
        </section>

        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          {!selected ? <p className="text-sm text-slate-500">Select a lab report.</p> : null}
          {selected ? (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-lg font-bold">Lab Report Detail</h3>
                <button
                  type="button"
                  onClick={printSelected}
                  className="inline-flex items-center gap-2 rounded-lg border border-cyan-600 px-4 py-2 text-sm font-semibold text-cyan-700 hover:bg-cyan-50"
                >
                  <Printer className="h-4 w-4" /> Print
                </button>
              </div>

              <div className="grid gap-2 text-sm sm:grid-cols-2">
                <p><span className="font-semibold">Patient:</span> {selected.patient_name || "-"}</p>
                <p><span className="font-semibold">MRN:</span> {selected.patient_mrn || "-"}</p>
                <p><span className="font-semibold">Shared At:</span> {selected.created_at || "-"}</p>
                <p><span className="font-semibold">Record ID:</span> {selected.source_record_id || "-"}</p>
              </div>

              <div className="rounded-xl border border-slate-200 p-3 text-sm">
                <p><span className="font-semibold">Test Type:</span> {selected.report?.test_type || "-"}</p>
                <p><span className="font-semibold">Specimen:</span> {selected.report?.specimen_type || "-"}</p>
                <p><span className="font-semibold">Status:</span> {selected.report?.status || "-"}</p>
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
                    {normalizeLabMarkers(selected.report?.markers_json || {}).length === 0 ? (
                      <tr className="border-t border-slate-100">
                        <td className="px-3 py-2 text-slate-500" colSpan={5}>No marker data.</td>
                      </tr>
                    ) : null}
                  </tbody>
                </table>
              </div>

              <div className="rounded-xl border border-slate-200 p-3">
                <p className="text-sm font-bold">AI Insight</p>
                <div className="mt-2 space-y-1 text-sm">
                  {Object.keys(selected.report?.ai_outputs_json || {}).length === 0 ? (
                    <p className="text-slate-500">No AI output for this report.</p>
                  ) : (
                    Object.entries(selected.report?.ai_outputs_json || {}).map(([k, v]) => {
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
            </div>
          ) : null}
        </section>
      </div>
    </DoctorWorkspaceLayout>
  );
}
