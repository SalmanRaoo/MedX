import { useEffect, useState } from "react";
import { Building2, Clock3, Mail, Phone, AlertCircle, Loader2 } from "lucide-react";
import { publicApi } from "../lib/api";

export default function HospitalContacts() {
  const [hospitals, setHospitals] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    publicApi.get("/public/hospitals/contacts")
      .then((res) => setHospitals(res.data?.items || []))
      .catch(() => setHospitals([]))
      .finally(() => setLoading(false));
  }, []);

  return (
    <section className="px-4 py-16 sm:px-6 lg:px-8">
      <div className="mx-auto w-full max-w-7xl">
        <div className="mb-8 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h1 className="text-3xl font-extrabold tracking-tight text-slate-900">Hospital Contact Directory</h1>
          <p className="mt-2 text-sm text-slate-600">Public directory of MedX-connected hospitals. Contact profiles are updated by each hospital admin from their settings panel.</p>
        </div>

        {loading ? (
          <div className="py-20 text-center"><Loader2 className="mx-auto h-8 w-8 animate-spin text-cyan-700" /></div>
        ) : hospitals.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-10 text-center">
            <AlertCircle className="mx-auto mb-3 h-8 w-8 text-slate-400" />
            <p className="text-sm font-semibold text-slate-600">No hospital contact profiles available yet.</p>
          </div>
        ) : (
          <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">
            {hospitals.map((h) => (
              <article key={h.setting_id || h.hospital_id} className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm hover:shadow-md transition-shadow">
                <h3 className="text-lg font-bold text-slate-900">{h.hospital_name || "Hospital"}</h3>
                <p className="mt-2 text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Hospital ID: {h.hospital_id}</p>
                <div className="mt-5 space-y-3 text-sm text-slate-700">
                  <p className="flex gap-2"><Phone className="mt-0.5 h-4 w-4 text-cyan-700" />{h.phone_contact || "N/A"}</p>
                  <p className="flex gap-2"><Mail className="mt-0.5 h-4 w-4 text-cyan-700" />{h.email_contact || "N/A"}</p>
                  <p className="flex gap-2"><AlertCircle className="mt-0.5 h-4 w-4 text-red-600" />Emergency: {h.emergency_line || "N/A"}</p>
                  <p className="flex gap-2"><Clock3 className="mt-0.5 h-4 w-4 text-cyan-700" />{h.opd_hours || "N/A"}</p>
                  <p className="flex gap-2"><Building2 className="mt-0.5 h-4 w-4 text-cyan-700" />{h.address || "N/A"}</p>
                </div>
              </article>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
