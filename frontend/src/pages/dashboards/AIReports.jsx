import { useState } from "react";
import { api } from "../../lib/api";
import { FileText, Loader2, Printer } from "lucide-react";

export default function AIReports() {
  const [form, setForm] = useState({
    report_title: "",
    source_context: "",
    patient_id: "",
    doctor_id: "",
  });
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const res = await api.post("/ai/reports/generate", {
        report_title: form.report_title,
        source_context: form.source_context,
        patient_id: form.patient_id ? Number(form.patient_id) : null,
        doctor_id: form.doctor_id ? Number(form.doctor_id) : null,
      });
      setResult(res.data);
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="px-4 py-10 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-6xl space-y-6">
        <header className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h1 className="text-3xl font-extrabold">AI Reports Center</h1>
          <p className="text-slate-600">Generate AI insights from clinical page/report data and deliver results to doctor/patient records.</p>
        </header>

        <form onSubmit={submit} className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm space-y-4">
          <input className="w-full rounded-lg border px-3 py-2.5" placeholder="Report Title" value={form.report_title} onChange={(e) => setForm({ ...form, report_title: e.target.value })} required />
          <textarea className="w-full rounded-lg border px-3 py-2.5 min-h-[160px]" placeholder="Paste report/page data here..." value={form.source_context} onChange={(e) => setForm({ ...form, source_context: e.target.value })} required />
          <div className="grid md:grid-cols-2 gap-4">
            <input className="rounded-lg border px-3 py-2.5" placeholder="Patient ID (optional)" value={form.patient_id} onChange={(e) => setForm({ ...form, patient_id: e.target.value })} />
            <input className="rounded-lg border px-3 py-2.5" placeholder="Doctor ID (optional)" value={form.doctor_id} onChange={(e) => setForm({ ...form, doctor_id: e.target.value })} />
          </div>
          <button className="rounded-xl bg-cyan-600 px-5 py-3 text-white font-semibold inline-flex items-center gap-2">
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileText className="h-4 w-4" />} Generate AI Report
          </button>
        </form>

        {result?.report ? (
          <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm print:shadow-none print:border-0" id="printable-report">
            <div className="flex justify-between items-start gap-4">
              <div>
                <h2 className="text-2xl font-bold">{result.report.report_title}</h2>
                <p className="text-xs uppercase tracking-[0.14em] text-slate-500 mt-1">Report ID: {result.report.report_id}</p>
              </div>
              <button onClick={() => window.print()} className="rounded-lg border px-4 py-2 text-sm font-semibold inline-flex items-center gap-2 print:hidden"><Printer className="h-4 w-4" />Print Hardcopy</button>
            </div>
            <div className="mt-6 grid md:grid-cols-2 gap-5">
              <div className="rounded-xl bg-slate-50 p-4">
                <h3 className="font-bold">AI Summary</h3>
                <p className="text-sm text-slate-700 mt-2">{result.report.ai_summary}</p>
              </div>
              <div className="rounded-xl bg-slate-50 p-4">
                <h3 className="font-bold">AI Recommendation</h3>
                <p className="text-sm text-slate-700 mt-2">{result.report.ai_recommendation}</p>
              </div>
            </div>
            <p className="mt-4 text-sm text-slate-600">Delivered: Doctor {result.delivery?.doctor ? "Yes" : "No"}, Patient {result.delivery?.patient ? "Yes" : "No"}</p>
          </div>
        ) : null}
      </div>
    </section>
  );
}
