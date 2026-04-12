import { useEffect, useMemo, useState } from "react";
import { CalendarClock, CheckCircle2, Loader2, Stethoscope } from "lucide-react";
import { publicApi } from "../lib/api";

function todayIso() {
  const now = new Date();
  const y = now.getFullYear();
  const m = String(now.getMonth() + 1).padStart(2, "0");
  const d = String(now.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function nowTimeIso() {
  const now = new Date();
  const hh = String(now.getHours()).padStart(2, "0");
  const mm = String(now.getMinutes()).padStart(2, "0");
  return `${hh}:${mm}`;
}

export default function BookAppointment() {
  const [hospitals, setHospitals] = useState([]);
  const [doctors, setDoctors] = useState([]);

  const [form, setForm] = useState({
    hospital_id: "",
    doctor_id: "",
    patient_name: "",
    patient_phone: "",
    patient_gender: "",
    patient_dob: "",
    appointment_date: todayIso(),
    appointment_time: nowTimeIso(),
    appointment_type: "IN_PERSON",
  });

  const [loadingHospitals, setLoadingHospitals] = useState(true);
  const [loadingDoctors, setLoadingDoctors] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(null);

  useEffect(() => {
    let active = true;
    const loadHospitals = async () => {
      setLoadingHospitals(true);
      try {
        const { data } = await publicApi.get("/public/hospitals");
        if (!active) return;
        const items = data?.items || [];
        setHospitals(items);
        setForm((prev) => ({
          ...prev,
          hospital_id: items.length ? String(items[0].hospital_id) : "",
        }));
      } catch {
        if (!active) return;
        setHospitals([]);
      } finally {
        if (active) setLoadingHospitals(false);
      }
    };
    loadHospitals();
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!form.hospital_id) {
      setDoctors([]);
      setForm((prev) => ({ ...prev, doctor_id: "" }));
      return;
    }
    let active = true;
    const loadDoctors = async () => {
      setLoadingDoctors(true);
      try {
        const { data } = await publicApi.get(`/public/hospitals/${Number(form.hospital_id)}/doctors`);
        if (!active) return;
        const items = data?.items || [];
        setDoctors(items);
        setForm((prev) => ({
          ...prev,
          doctor_id: items.length ? String(items[0].doctor_id) : "",
        }));
      } catch {
        if (!active) return;
        setDoctors([]);
        setForm((prev) => ({ ...prev, doctor_id: "" }));
      } finally {
        if (active) setLoadingDoctors(false);
      }
    };
    loadDoctors();
    return () => {
      active = false;
    };
  }, [form.hospital_id]);

  const selectedHospital = useMemo(
    () => hospitals.find((h) => String(h.hospital_id) === String(form.hospital_id)) || null,
    [hospitals, form.hospital_id]
  );

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    setSuccess(null);
    setSaving(true);
    try {
      const payload = {
        hospital_id: Number(form.hospital_id),
        doctor_id: Number(form.doctor_id),
        patient_name: form.patient_name.trim(),
        patient_phone: form.patient_phone.trim(),
        patient_gender: form.patient_gender || null,
        patient_dob: form.patient_dob || null,
        appointment_date: form.appointment_date,
        appointment_time: form.appointment_time,
        appointment_type: form.appointment_type,
      };
      const { data } = await publicApi.post("/public/appointments/book", payload);
      setSuccess(data?.appointment || null);
    } catch (err) {
      setError(err?.response?.data?.detail || "Unable to book appointment.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="px-4 py-16 sm:px-6 lg:px-8">
      <div className="mx-auto w-full max-w-5xl space-y-6">
        <header className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <p className="inline-flex items-center gap-2 rounded-full bg-cyan-50 px-3 py-1 text-xs font-bold uppercase tracking-[0.12em] text-cyan-700">
            <CalendarClock className="h-3.5 w-3.5" /> Public Appointment Booking
          </p>
          <h1 className="mt-3 text-3xl font-extrabold tracking-tight text-slate-900">Book Doctor Appointment</h1>
          <p className="mt-2 text-sm text-slate-600">
            Select hospital, choose doctor, then pick your date and time slot.
          </p>
        </header>

        {success ? (
          <article className="rounded-2xl border border-emerald-200 bg-emerald-50 p-6 shadow-sm">
            <p className="inline-flex items-center gap-2 text-sm font-bold text-emerald-700">
              <CheckCircle2 className="h-4 w-4" /> Appointment booked successfully
            </p>
            <div className="mt-3 grid gap-2 text-sm text-emerald-900 sm:grid-cols-2">
              <p><span className="font-semibold">Appointment ID:</span> {success.appointment_id}</p>
              <p><span className="font-semibold">Hospital:</span> {success.hospital_name}</p>
              <p><span className="font-semibold">Doctor:</span> {success.doctor_name}</p>
              <p><span className="font-semibold">Date/Time:</span> {success.appointment_date}</p>
              <p><span className="font-semibold">Patient:</span> {success.patient_name}</p>
              <p><span className="font-semibold">MRN:</span> {success.patient_mrn}</p>
            </div>
          </article>
        ) : null}

        <form onSubmit={submit} className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          {error ? <p className="mb-4 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</p> : null}

          <div className="grid gap-4 sm:grid-cols-2">
            <label className="space-y-1">
              <span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Hospital</span>
              <select
                value={form.hospital_id}
                onChange={(e) => setForm((prev) => ({ ...prev, hospital_id: e.target.value }))}
                className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-cyan-500"
                disabled={loadingHospitals || hospitals.length === 0}
                required
              >
                {loadingHospitals ? <option>Loading hospitals...</option> : null}
                {!loadingHospitals && hospitals.length === 0 ? <option value="">No hospitals available</option> : null}
                {hospitals.map((h) => (
                  <option key={h.hospital_id} value={h.hospital_id}>
                    {h.hospital_name}
                  </option>
                ))}
              </select>
            </label>

            <label className="space-y-1">
              <span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Doctor</span>
              <select
                value={form.doctor_id}
                onChange={(e) => setForm((prev) => ({ ...prev, doctor_id: e.target.value }))}
                className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-cyan-500"
                disabled={loadingDoctors || doctors.length === 0}
                required
              >
                {loadingDoctors ? <option>Loading doctors...</option> : null}
                {!loadingDoctors && doctors.length === 0 ? <option value="">No doctors available</option> : null}
                {doctors.map((d) => (
                  <option key={d.doctor_id} value={d.doctor_id}>
                    {d.full_name} ({d.specialization || "General Medicine"})
                  </option>
                ))}
              </select>
            </label>

            <label className="space-y-1">
              <span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Patient Name</span>
              <input
                value={form.patient_name}
                onChange={(e) => setForm((prev) => ({ ...prev, patient_name: e.target.value }))}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-cyan-500"
                placeholder="Full name"
                required
              />
            </label>

            <label className="space-y-1">
              <span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Phone Number</span>
              <input
                value={form.patient_phone}
                onChange={(e) => setForm((prev) => ({ ...prev, patient_phone: e.target.value }))}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-cyan-500"
                placeholder="03xx-xxxxxxx"
                required
              />
            </label>

            <label className="space-y-1">
              <span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Date</span>
              <input
                type="date"
                min={todayIso()}
                value={form.appointment_date}
                onChange={(e) => setForm((prev) => ({ ...prev, appointment_date: e.target.value }))}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-cyan-500"
                required
              />
            </label>

            <label className="space-y-1">
              <span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Time</span>
              <input
                type="time"
                value={form.appointment_time}
                onChange={(e) => setForm((prev) => ({ ...prev, appointment_time: e.target.value }))}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-cyan-500"
                required
              />
            </label>

            <label className="space-y-1">
              <span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Appointment Type</span>
              <select
                value={form.appointment_type}
                onChange={(e) => setForm((prev) => ({ ...prev, appointment_type: e.target.value }))}
                className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-cyan-500"
              >
                <option value="IN_PERSON">In Person</option>
                <option value="VIDEO">Video</option>
              </select>
            </label>

            <label className="space-y-1">
              <span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Gender (Optional)</span>
              <select
                value={form.patient_gender}
                onChange={(e) => setForm((prev) => ({ ...prev, patient_gender: e.target.value }))}
                className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-cyan-500"
              >
                <option value="">Select</option>
                <option value="MALE">Male</option>
                <option value="FEMALE">Female</option>
                <option value="OTHER">Other</option>
              </select>
            </label>

            <label className="space-y-1 sm:col-span-2">
              <span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Date of Birth (Optional)</span>
              <input
                type="date"
                value={form.patient_dob}
                onChange={(e) => setForm((prev) => ({ ...prev, patient_dob: e.target.value }))}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-cyan-500"
              />
            </label>
          </div>

          <div className="mt-6 flex flex-wrap items-center justify-between gap-3">
            <p className="inline-flex items-center gap-2 text-xs text-slate-600">
              <Stethoscope className="h-4 w-4 text-cyan-700" />
              {selectedHospital ? `Booking at: ${selectedHospital.hospital_name}` : "Select hospital first"}
            </p>
            <button
              type="submit"
              disabled={saving || loadingHospitals || loadingDoctors || !form.hospital_id || !form.doctor_id}
              className="inline-flex items-center gap-2 rounded-lg bg-slate-900 px-5 py-2.5 text-sm font-semibold text-white hover:bg-cyan-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              {saving ? "Booking..." : "Book Appointment"}
            </button>
          </div>
        </form>
      </div>
    </section>
  );
}
