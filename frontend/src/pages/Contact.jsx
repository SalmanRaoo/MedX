import { useState } from "react";
import { Building2, Mail, Phone, Send, CheckCircle2, Loader2, LifeBuoy } from "lucide-react";
import { publicApi } from "../lib/api";

export default function Contact() {
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState("");

  const [form, setForm] = useState({ name: "", email: "", subject: "General Inquiry", message: "" });
  const onChange = (key, value) => setForm((prev) => ({ ...prev, [key]: value }));

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSending(true);
    setError("");
    try {
      await publicApi.post("/contact_messages/", {
        hospital_id: null,
        name: form.name,
        email: form.email,
        subject: `[MEDX MAIN] ${form.subject}`,
        message: form.message,
      });
      setSent(true);
      setForm({ name: "", email: "", subject: "General Inquiry", message: "" });
    } catch (err) {
      setError(err?.response?.data?.detail || "Unable to send message right now.");
    } finally {
      setSending(false);
    }
  };

  return (
    <section className="px-4 py-16 sm:px-6 lg:px-8">
      <div className="mx-auto grid w-full max-w-7xl gap-8 lg:grid-cols-[1fr_1.4fr]">
        <aside className="space-y-4">
          <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
            <h1 className="text-2xl font-extrabold tracking-tight text-slate-900">MedX Main Contact</h1>
            <p className="mt-2 text-sm text-slate-600">Central support for product onboarding, technical guidance, and enterprise assistance.</p>
          </div>

          <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm space-y-3 text-sm text-slate-700">
            <p className="flex items-start gap-3"><Building2 className="mt-0.5 h-4 w-4 text-cyan-700" /><span>MedX Central Office</span></p>
            <p className="flex items-start gap-3"><Phone className="mt-0.5 h-4 w-4 text-cyan-700" /><span>+92 325 857 5683</span></p>
            <p className="flex items-start gap-3"><Mail className="mt-0.5 h-4 w-4 text-cyan-700" /><span>support@medx.health</span></p>
            <p className="flex items-start gap-3"><LifeBuoy className="mt-0.5 h-4 w-4 text-cyan-700" /><span>Support SLA: 24-48 hours</span></p>
          </div>
        </aside>

        <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8">
          {sent ? (
            <div className="flex min-h-[320px] flex-col items-center justify-center text-center">
              <div className="mb-4 rounded-full bg-emerald-100 p-3 text-emerald-700"><CheckCircle2 className="h-8 w-8" /></div>
              <h2 className="text-2xl font-bold text-slate-900">Message sent</h2>
              <p className="mt-2 text-sm text-slate-600">MedX central team received your inquiry.</p>
              <button onClick={() => setSent(false)} className="mt-6 rounded-lg border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 hover:border-cyan-400 hover:text-cyan-700">Send another message</button>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-5">
              {error && <p className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm font-medium text-rose-700">{error}</p>}
              <div className="grid gap-5 sm:grid-cols-2">
                <label className="space-y-1"><span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Name</span><input required value={form.name} onChange={(e) => onChange("name", e.target.value)} className="w-full rounded-lg border border-slate-300 px-3 py-2.5" /></label>
                <label className="space-y-1"><span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Email</span><input required type="email" value={form.email} onChange={(e) => onChange("email", e.target.value)} className="w-full rounded-lg border border-slate-300 px-3 py-2.5" /></label>
              </div>
              <label className="space-y-1 block"><span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Subject</span><input required value={form.subject} onChange={(e) => onChange("subject", e.target.value)} className="w-full rounded-lg border border-slate-300 px-3 py-2.5" /></label>
              <label className="space-y-1 block"><span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Message</span><textarea required rows={6} value={form.message} onChange={(e) => onChange("message", e.target.value)} className="w-full resize-none rounded-lg border border-slate-300 px-3 py-2.5" /></label>
              <div className="flex justify-end">
                <button type="submit" disabled={sending} className="inline-flex items-center gap-2 rounded-xl bg-cyan-600 px-5 py-3 text-sm font-semibold text-white hover:bg-cyan-700 disabled:opacity-70">{sending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}{sending ? "Sending" : "Send Message"}</button>
              </div>
            </form>
          )}
        </div>
      </div>
    </section>
  );
}
