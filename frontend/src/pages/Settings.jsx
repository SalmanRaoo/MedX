import { useEffect, useMemo, useState } from "react";
import Sidebar from "../components/Sidebar";
import { api } from "../lib/api";
import { useHospitalSettings } from "../context/HospitalSettingsContext";
import { Building2, Image as ImageIcon, Loader2, MapPin, Phone, Save, Settings2, Stethoscope } from "lucide-react";

function NumberInput({ label, value, onChange, min = "0", step = "0.01" }) {
  return (
    <label className="block space-y-1">
      <span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">{label}</span>
      <input
        type="number"
        min={min}
        step={step}
        value={value}
        onChange={onChange}
        className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-teal-500"
      />
    </label>
  );
}

export default function Settings() {
  const sessionUser = useMemo(() => {
    try {
      return JSON.parse(localStorage.getItem("medx_user") || "{}");
    } catch {
      return {};
    }
  }, []);
  const isSuperAdmin = String(sessionUser?.role_name || "").toUpperCase() === "SUPER_ADMIN";

  const { refreshSettings } = useHospitalSettings();
  const [targetHospitalId, setTargetHospitalId] = useState("");

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const [metadata, setMetadata] = useState({
    hospital_name: "",
    address: "",
    contact_number: "",
    logo_url: "",
  });
  const [patientRegistrationFee, setPatientRegistrationFee] = useState("0");
  const [doctorConsultationFee, setDoctorConsultationFee] = useState("0");
  const [labTests, setLabTests] = useState({
    CBC: "0",
    LFT: "0",
    RFT: "0",
  });
  const [radiologyServices, setRadiologyServices] = useState([]);

  const fetchSettings = async () => {
    setLoading(true);
    setError("");
    try {
      const params = {};
      if (isSuperAdmin && targetHospitalId) params.hospital_id = Number(targetHospitalId);
      const { data } = await api.get("/settings", { params });
      const hospitalMeta = data?.hospital_metadata || {};
      const pricing = data?.service_pricing || {};
      const fees = data?.staff_fees || {};

      setMetadata({
        hospital_name: hospitalMeta.hospital_name || "",
        address: hospitalMeta.address || "",
        contact_number: hospitalMeta.contact_number || "",
        logo_url: hospitalMeta.logo_url || "",
      });
      setPatientRegistrationFee(String(pricing.patient_registration_fee ?? 0));
      setDoctorConsultationFee(String(fees.doctor_consultation_fee_default ?? 0));

      const nextLab = pricing.lab_tests || {};
      setLabTests({
        CBC: String(nextLab.CBC ?? nextLab.cbc ?? 0),
        LFT: String(nextLab.LFT ?? nextLab.lft ?? 0),
        RFT: String(nextLab.RFT ?? nextLab.rft ?? 0),
      });
      setRadiologyServices(
        (pricing.radiology_services || []).map((item) => ({
          service_id: item.service_id,
          modality: item.modality,
          scan_name: item.scan_name,
          body_part: item.body_part,
          service_fee: String(item.service_fee ?? 0),
        }))
      );
    } catch (err) {
      setError(err?.response?.data?.detail || "Unable to load master settings.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSettings();
  }, [targetHospitalId]);

  const onSave = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError("");
    setSuccess("");
    try {
      const params = {};
      if (isSuperAdmin && targetHospitalId) params.hospital_id = Number(targetHospitalId);
      await api.put(
        "/settings",
        {
          hospital_metadata: {
            hospital_name: metadata.hospital_name,
            address: metadata.address,
            contact_number: metadata.contact_number,
            logo_url: metadata.logo_url,
          },
          service_pricing: {
            patient_registration_fee: Number(patientRegistrationFee || 0),
            lab_tests: {
              CBC: Number(labTests.CBC || 0),
              LFT: Number(labTests.LFT || 0),
              RFT: Number(labTests.RFT || 0),
            },
            radiology_services: radiologyServices.map((s) => ({
              service_id: Number(s.service_id),
              service_fee: Number(s.service_fee || 0),
            })),
          },
          staff_fees: {
            doctor_consultation_fee_default: Number(doctorConsultationFee || 0),
          },
        },
        { params }
      );
      setSuccess("Master control settings updated successfully.");
      await fetchSettings();
      await refreshSettings();
    } catch (err) {
      setError(err?.response?.data?.detail || "Unable to save settings.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex h-screen bg-slate-50 overflow-hidden font-sans">
      <Sidebar />
      <div className="flex-1 flex flex-col">
        <header className="h-20 border-b bg-white px-8 flex items-center justify-between">
          <div>
            <h1 className="text-xl font-black uppercase tracking-tight text-slate-900">Admin Master Control</h1>
            <p className="text-xs text-slate-500">Global hospital values for pricing, identity, and consultation defaults</p>
          </div>
          {isSuperAdmin ? (
            <label className="block space-y-1">
              <span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Target Hospital ID</span>
              <input
                type="number"
                min="1"
                value={targetHospitalId}
                onChange={(e) => setTargetHospitalId(e.target.value)}
                className="rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-teal-500"
                placeholder="Current if empty"
              />
            </label>
          ) : null}
        </header>

        <main className="flex-1 overflow-y-auto p-8">
          {loading ? (
            <div className="rounded-[32px] border border-slate-200 bg-white p-10 shadow-sm flex items-center gap-3 text-slate-600">
              <Loader2 className="h-5 w-5 animate-spin" /> Loading settings...
            </div>
          ) : (
            <form onSubmit={onSave} className="space-y-6">
              {error ? <p className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</p> : null}
              {success ? <p className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{success}</p> : null}

              <section className="rounded-[32px] border border-slate-200 bg-white p-6 shadow-sm">
                <h2 className="text-lg font-bold flex items-center gap-2"><Building2 className="h-5 w-5 text-teal-700" /> Hospital Metadata</h2>
                <div className="mt-4 grid gap-4 md:grid-cols-2">
                  <label className="block space-y-1">
                    <span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Hospital Name</span>
                    <input
                      value={metadata.hospital_name}
                      onChange={(e) => setMetadata((p) => ({ ...p, hospital_name: e.target.value }))}
                      className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-teal-500"
                    />
                  </label>
                  <label className="block space-y-1">
                    <span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Contact Number</span>
                    <div className="relative">
                      <Phone className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                      <input
                        value={metadata.contact_number}
                        onChange={(e) => setMetadata((p) => ({ ...p, contact_number: e.target.value }))}
                        className="w-full rounded-xl border border-slate-300 py-2 pl-9 pr-3 text-sm outline-none focus:border-teal-500"
                      />
                    </div>
                  </label>
                  <label className="block space-y-1 md:col-span-2">
                    <span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Address</span>
                    <div className="relative">
                      <MapPin className="absolute left-3 top-3 h-4 w-4 text-slate-400" />
                      <textarea
                        rows={2}
                        value={metadata.address}
                        onChange={(e) => setMetadata((p) => ({ ...p, address: e.target.value }))}
                        className="w-full rounded-xl border border-slate-300 py-2 pl-9 pr-3 text-sm outline-none focus:border-teal-500"
                      />
                    </div>
                  </label>
                  <label className="block space-y-1 md:col-span-2">
                    <span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Logo URL</span>
                    <div className="relative">
                      <ImageIcon className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                      <input
                        value={metadata.logo_url}
                        onChange={(e) => setMetadata((p) => ({ ...p, logo_url: e.target.value }))}
                        className="w-full rounded-xl border border-slate-300 py-2 pl-9 pr-3 text-sm outline-none focus:border-teal-500"
                        placeholder="https://..."
                      />
                    </div>
                  </label>
                </div>
              </section>

              <section className="rounded-[32px] border border-slate-200 bg-white p-6 shadow-sm">
                <h2 className="text-lg font-bold flex items-center gap-2"><Settings2 className="h-5 w-5 text-teal-700" /> Service Pricing</h2>
                <div className="mt-4 grid gap-4 md:grid-cols-2">
                  <NumberInput
                    label="Patient Registration Fee"
                    value={patientRegistrationFee}
                    onChange={(e) => setPatientRegistrationFee(e.target.value)}
                  />
                </div>

                <div className="mt-4 rounded-2xl border border-slate-200 p-4">
                  <p className="text-sm font-bold">Lab Test Pricing</p>
                  <div className="mt-3 grid gap-3 md:grid-cols-3">
                    <NumberInput label="CBC" value={labTests.CBC} onChange={(e) => setLabTests((p) => ({ ...p, CBC: e.target.value }))} />
                    <NumberInput label="LFT" value={labTests.LFT} onChange={(e) => setLabTests((p) => ({ ...p, LFT: e.target.value }))} />
                    <NumberInput label="RFT" value={labTests.RFT} onChange={(e) => setLabTests((p) => ({ ...p, RFT: e.target.value }))} />
                  </div>
                </div>

                <div className="mt-4 rounded-2xl border border-slate-200 p-4">
                  <p className="text-sm font-bold">Radiology Pricing</p>
                  <div className="mt-3 overflow-auto rounded-xl border border-slate-200">
                    <table className="min-w-full text-sm">
                      <thead className="bg-slate-50">
                        <tr>
                          <th className="px-3 py-2 text-left">Modality</th>
                          <th className="px-3 py-2 text-left">Scan</th>
                          <th className="px-3 py-2 text-left">Body Part</th>
                          <th className="px-3 py-2 text-left">Fee</th>
                        </tr>
                      </thead>
                      <tbody>
                        {radiologyServices.map((item, idx) => (
                          <tr key={item.service_id} className="border-t border-slate-100">
                            <td className="px-3 py-2">{item.modality}</td>
                            <td className="px-3 py-2">{item.scan_name}</td>
                            <td className="px-3 py-2">{item.body_part}</td>
                            <td className="px-3 py-2 w-48">
                              <input
                                type="number"
                                min="0"
                                step="0.01"
                                value={item.service_fee}
                                onChange={(e) =>
                                  setRadiologyServices((prev) =>
                                    prev.map((r, i) => (i === idx ? { ...r, service_fee: e.target.value } : r))
                                  )
                                }
                                className="w-full rounded-lg border border-slate-300 px-2 py-1.5 text-sm outline-none focus:border-teal-500"
                              />
                            </td>
                          </tr>
                        ))}
                        {radiologyServices.length === 0 ? (
                          <tr><td colSpan={4} className="px-3 py-6 text-center text-slate-500">No radiology services found.</td></tr>
                        ) : null}
                      </tbody>
                    </table>
                  </div>
                </div>
              </section>

              <section className="rounded-[32px] border border-slate-200 bg-white p-6 shadow-sm">
                <h2 className="text-lg font-bold flex items-center gap-2"><Stethoscope className="h-5 w-5 text-teal-700" /> Staff Fees</h2>
                <div className="mt-4 grid gap-4 md:grid-cols-2">
                  <NumberInput
                    label="Default Doctor Consultation Fee"
                    value={doctorConsultationFee}
                    onChange={(e) => setDoctorConsultationFee(e.target.value)}
                  />
                </div>
              </section>

              <button
                type="submit"
                disabled={saving}
                className="inline-flex items-center gap-2 rounded-xl bg-teal-600 px-5 py-3 text-sm font-bold text-white hover:bg-teal-700 disabled:opacity-70"
              >
                {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                {saving ? "Saving..." : "Save Master Control"}
              </button>
            </form>
          )}
        </main>
      </div>
    </div>
  );
}
