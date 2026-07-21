import { Link } from "react-router-dom";
import { useEffect, useMemo, useState } from "react";
import { api } from "../../lib/api";
import DoctorWorkspaceLayout from "../../components/dashboards/DoctorWorkspaceLayout";

export default function DoctorDashboard() {
  const [recentResults, setRecentResults] = useState([]);
  const [doctorAppointments, setDoctorAppointments] = useState([]);

  const [patients, setPatients] = useState([]);
  const [patientSearch, setPatientSearch] = useState("");
  const [patientId, setPatientId] = useState("");

  const [tests, setTests] = useState([]);
  const [testSearch, setTestSearch] = useState("");

  const [requestType, setRequestType] = useState("LAB");
  const [testCode, setTestCode] = useState("");
  const [radiologyConfig, setRadiologyConfig] = useState({ modalities: [] });
  const [radiologyModality, setRadiologyModality] = useState("");
  const [radiologyName, setRadiologyName] = useState("");
  const [radiologyBodyPart, setRadiologyBodyPart] = useState("");
  const [priority, setPriority] = useState("ROUTINE");
  const [notes, setNotes] = useState("");

  const [patientRequests, setPatientRequests] = useState({ lab_requests: [], radiology_requests: [] });
  const [sharedReports, setSharedReports] = useState([]);
  const [preConsultation, setPreConsultation] = useState(null);
  const [loadingPreConsultation, setLoadingPreConsultation] = useState(false);
  const [bedAvailability, setBedAvailability] = useState({ items: [], totals: {} });
  const [transferBedId, setTransferBedId] = useState("");
  const [transferring, setTransferring] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const [recentRes, testRes, radConfigRes, bedRes, apptRes] = await Promise.all([
          api.get("/doctor/recent-results", { params: { limit: 12 } }),
          api.get("/lab/master-tests", { params: { limit: 5000 } }),
          api.get("/radiology/config"),
          api.get("/doctor/bed-availability"),
          api.get("/doctor/appointments", { params: { status: "SCHEDULED", limit: 25 } }),
        ]);
        if (!active) return;
        setRecentResults(recentRes.data.items || []);
        setDoctorAppointments(apptRes.data.items || []);
        const testItems = testRes.data.items || [];
        setTests(testItems);
        if (testItems.length) setTestCode(testItems[0].code);
        const modalities = radConfigRes?.data?.modalities || [];
        setRadiologyConfig({ modalities });
        if (modalities.length) {
          const first = modalities[0];
          setRadiologyModality(first.code || "");
          setRadiologyBodyPart((first.body_parts || [])[0]?.code || "");
        }
        setBedAvailability(bedRes?.data || { items: [], totals: {} });
      } catch {
        if (!active) return;
        setRecentResults([]);
        setDoctorAppointments([]);
      }
    };
    load();
    return () => {
      active = false;
    };
  }, []);

  const loadBedAvailability = async () => {
    try {
      const { data } = await api.get("/doctor/bed-availability");
      setBedAvailability(data || { items: [], totals: {} });
    } catch {
      // keep previous snapshot
    }
  };

  useEffect(() => {
    let active = true;
    const t = setTimeout(async () => {
      try {
        const res = await api.get("/lab/patient-search", { params: { q: patientSearch, limit: 200 } });
        if (!active) return;
        const items = res.data.items || [];
        setPatients(items);
        if (items.length && !items.find((p) => String(p.patient_id) === String(patientId))) {
          setPatientId(String(items[0].patient_id));
        }
      } catch {
        if (!active) return;
        setPatients([]);
      }
    }, 220);

    return () => {
      active = false;
      clearTimeout(t);
    };
  }, [patientSearch]);

  const filteredTests = useMemo(() => {
    const q = testSearch.trim().toLowerCase();
    if (!q) return tests;
    return tests.filter((t) => {
      const aliases = (t.aliases || []).join(" ").toLowerCase();
      return `${t.code} ${t.name} ${t.department} ${aliases}`.toLowerCase().includes(q);
    });
  }, [tests, testSearch]);

  const selectedRadiologyModality = useMemo(
    () => (radiologyConfig.modalities || []).find((m) => m.code === radiologyModality) || null,
    [radiologyConfig.modalities, radiologyModality]
  );

  useEffect(() => {
    const bodyParts = selectedRadiologyModality?.body_parts || [];
    if (!bodyParts.length) {
      setRadiologyBodyPart("");
      return;
    }
    if (!bodyParts.find((bp) => bp.code === radiologyBodyPart)) {
      setRadiologyBodyPart(bodyParts[0].code);
    }
  }, [selectedRadiologyModality, radiologyBodyPart]);

  useEffect(() => {
    if (!patientId) {
      setPatientRequests({ lab_requests: [], radiology_requests: [] });
      setSharedReports([]);
      setPreConsultation(null);
      return;
    }
    let active = true;
    const loadRequests = async () => {
      try {
        const [res, sharedRes] = await Promise.all([
          api.get(`/doctor/patients/${patientId}/requests`),
          api.get("/reports/shared", { params: { patient_id: Number(patientId), audience: "DOCTOR", limit: 120 } }),
        ]);
        if (!active) return;
        setPatientRequests({
          lab_requests: res.data.lab_requests || [],
          radiology_requests: res.data.radiology_requests || [],
        });
        setSharedReports(sharedRes.data.items || []);
      } catch {
        if (!active) return;
        setPatientRequests({ lab_requests: [], radiology_requests: [] });
        setSharedReports([]);
      }
    };
    loadRequests();
    return () => {
      active = false;
    };
  }, [patientId]);

  useEffect(() => {
    if (!patientId) {
      setPreConsultation(null);
      return;
    }
    let active = true;
    const loadPreConsultation = async () => {
      setLoadingPreConsultation(true);
      try {
        const { data } = await api.get("/nurse/vitals", { params: { patient_id: Number(patientId), limit: 1 } });
        if (!active) return;
        const latest = (data?.items || [])[0] || null;
        setPreConsultation(latest);
      } catch {
        if (!active) return;
        setPreConsultation(null);
      } finally {
        if (active) setLoadingPreConsultation(false);
      }
    };
    loadPreConsultation();
    return () => {
      active = false;
    };
  }, [patientId]);

  useEffect(() => {
    const token = localStorage.getItem("medx_token");
    if (!token) return;
    const ws = new WebSocket(`ws://localhost:8000/ws/bed-sync?token=${encodeURIComponent(token)}`);
    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (["bed_status_changed", "bed_transfer", "unit_config_updated"].includes(msg?.event)) {
          loadBedAvailability();
        }
      } catch {
        // ignore invalid ws payload
      }
    };
    return () => ws.close();
  }, []);

  const onCreateRequest = async () => {
    if (!patientId) {
      setError("Please select patient.");
      return;
    }

    if (requestType === "LAB" && !testCode) {
      setError("Please select lab test.");
      return;
    }

    const selectedBodyPartObj =
      (selectedRadiologyModality?.body_parts || []).find((bp) => bp.code === radiologyBodyPart) || null;
    const derivedRadName = `${selectedRadiologyModality?.label || radiologyModality || "Radiology"} ${
      selectedBodyPartObj?.label || radiologyBodyPart || ""
    }`
      .trim()
      .replace(/\s+/g, " ");
    const finalRadiologyName = (radiologyName || "").trim() || derivedRadName;

    if (requestType === "RADIOLOGY" && !finalRadiologyName) {
      setError("Please select radiology modality/body part or enter test title.");
      return;
    }

    setSaving(true);
    setError("");
    try {
      await api.post("/doctor/requests", {
        patient_id: Number(patientId),
        request_type: requestType,
        test_code: requestType === "LAB" ? testCode : undefined,
        test_name: requestType === "RADIOLOGY" ? finalRadiologyName : undefined,
        body_part: requestType === "RADIOLOGY" ? radiologyBodyPart || null : undefined,
        priority,
        notes: notes.trim() || null,
      });

      setNotes("");
      if (requestType === "RADIOLOGY") {
        setRadiologyName("");
      }

      const res = await api.get(`/doctor/patients/${patientId}/requests`);
      setPatientRequests({
        lab_requests: res.data.lab_requests || [],
        radiology_requests: res.data.radiology_requests || [],
      });
    } catch (err) {
      setError(err?.response?.data?.detail || "Unable to create request.");
    } finally {
      setSaving(false);
    }
  };

  const freeBedOptions = useMemo(() => {
    const options = [];
    (bedAvailability.items || []).forEach((unit) => {
      (unit.free_bed_options || []).forEach((bed) => {
        options.push({
          value: String(bed.bed_id),
          label: `${unit.ward_name} (${unit.unit_type}) - ${bed.bed_number}`,
        });
      });
    });
    return options;
  }, [bedAvailability]);

  useEffect(() => {
    if (!freeBedOptions.length) {
      setTransferBedId("");
      return;
    }
    if (!freeBedOptions.find((o) => o.value === transferBedId)) {
      setTransferBedId(freeBedOptions[0].value);
    }
  }, [freeBedOptions, transferBedId]);

  const onTransferToWard = async () => {
    if (!patientId) {
      setError("Please select patient before transfer.");
      return;
    }
    if (!transferBedId) {
      setError("No free bed selected.");
      return;
    }
    setTransferring(true);
    setError("");
    try {
      await api.post("/doctor/transfer-to-ward", {
        patient_id: Number(patientId),
        bed_id: Number(transferBedId),
      });
      await Promise.all([loadBedAvailability(), api.get(`/doctor/patients/${patientId}/requests`).then((res) => {
        setPatientRequests({
          lab_requests: res.data.lab_requests || [],
          radiology_requests: res.data.radiology_requests || [],
        });
      })]);
    } catch (err) {
      setError(err?.response?.data?.detail || "Unable to transfer patient.");
    } finally {
      setTransferring(false);
    }
  };

  return (
    <DoctorWorkspaceLayout
      title="Doctor Dashboard"
      subtitle="Manage patient care workflow and create lab/radiology requests per patient."
    >
      <div className="grid gap-4 md:grid-cols-3">
        <Card
          title="Add Medication"
          text="Create medication orders that are visible to pharmacy and patient."
          to="/dashboard/doctor/medications"
          cta="Open Medications"
        />
        <Card
          title="Add Diagnosis"
          text="Record diagnosis and share it directly with patient care feed."
          to="/dashboard/doctor/clinical"
          cta="Open Clinical Updates"
        />
        <Card
          title="Add Procedure"
          text="Record procedures and publish to patient care timeline."
          to="/dashboard/doctor/clinical"
          cta="Open Clinical Updates"
        />
        <Card
          title="Symptoms AI"
          text="Select symptoms, run the disease predictor model, and review confidence."
          to="/dashboard/doctor/symptoms"
          cta="Open Symptoms AI"
        />
        <Card
          title="AI Imaging Lab"
          text="Upload chest X-ray or brain MRI and run specialized imaging AI models."
          to="/dashboard/doctor/ai-imaging-lab"
          cta="Open Imaging Lab"
        />
        <Card
          title="Imaging Reports"
          text="Review imaging-only reports with scan preview and final doctor signature."
          to="/dashboard/doctor/imaging-reports"
          cta="Open Imaging Reports"
        />
        <Card
          title="My Patients"
          text="View all your patients with previous diagnosis, medications, and admission/OPD details."
          to="/dashboard/doctor/patients"
          cta="Open My Patients"
        />
      </div>

      <section className="mt-6 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex items-center justify-between gap-3">
          <h3 className="text-lg font-bold">My Incoming Appointments</h3>
          <p className="text-xs text-slate-500">Appointments booked for your profile in this hospital.</p>
        </div>
        {doctorAppointments.length === 0 ? <p className="mt-3 text-sm text-slate-500">No scheduled appointments right now.</p> : null}
        <div className="mt-3 grid gap-3 md:grid-cols-2">
          {doctorAppointments.map((a) => (
            <article key={a.appointment_id} className="rounded-xl border border-slate-200 p-3 text-sm">
              <p className="font-semibold">{a.patient_name || "-"} ({a.patient_mrn || "-"})</p>
              <p className="text-slate-600">Time: {a.appointment_date || "-"}</p>
              <p className="text-slate-600">Type: {a.appointment_type || "-"}</p>
              <p className="text-xs text-slate-500">Status: {a.status || "-"}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="mt-6 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <h3 className="text-lg font-bold">Patient Lab / Radiology Requests</h3>
        {error ? <p className="mt-2 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</p> : null}

        <div className="mt-3 grid gap-3 md:grid-cols-4">
          <label className="space-y-1 md:col-span-2">
            <span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Search Patient</span>
            <input
              value={patientSearch}
              onChange={(e) => setPatientSearch(e.target.value)}
              placeholder="MRN or patient name"
              className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-cyan-500"
            />
          </label>

          <label className="space-y-1">
            <span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Patient</span>
            <select
              value={patientId}
              onChange={(e) => setPatientId(e.target.value)}
              className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-cyan-500"
            >
              <option value="">Select patient</option>
              {patients.map((p) => (
                <option key={p.patient_id} value={p.patient_id}>{p.full_name} ({p.patient_mrn})</option>
              ))}
            </select>
          </label>

          <label className="space-y-1">
            <span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Request Type</span>
            <select
              value={requestType}
              onChange={(e) => setRequestType(e.target.value)}
              className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-cyan-500"
            >
              <option value="LAB">LAB</option>
              <option value="RADIOLOGY">RADIOLOGY</option>
            </select>
          </label>
        </div>

        {requestType === "LAB" ? (
          <div className="mt-3 grid gap-3 md:grid-cols-2">
            <label className="space-y-1">
              <span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Search Report Type / Test</span>
              <input
                value={testSearch}
                onChange={(e) => setTestSearch(e.target.value)}
                placeholder="Search test by code/name"
                className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-cyan-500"
              />
            </label>
            <label className="space-y-1">
              <span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Lab Test</span>
              <select
                value={testCode}
                onChange={(e) => setTestCode(e.target.value)}
                className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-cyan-500"
              >
                {filteredTests.map((t) => (
                  <option key={t.code} value={t.code}>{t.code} - {t.name}</option>
                ))}
              </select>
            </label>
          </div>
        ) : (
          <div className="mt-3 grid gap-3 md:grid-cols-2">
            <label className="space-y-1">
              <span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Modality</span>
              <select
                value={radiologyModality}
                onChange={(e) => setRadiologyModality(e.target.value)}
                className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-cyan-500"
              >
                {(radiologyConfig.modalities || []).map((m) => (
                  <option key={m.code} value={m.code}>
                    {m.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="space-y-1">
              <span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Body Part</span>
              <select
                value={radiologyBodyPart}
                onChange={(e) => setRadiologyBodyPart(e.target.value)}
                className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-cyan-500"
              >
                {(selectedRadiologyModality?.body_parts || []).map((bp) => (
                  <option key={bp.code} value={bp.code}>
                    {bp.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="space-y-1 md:col-span-2">
              <span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Study Title (Optional)</span>
              <input
                value={radiologyName}
                onChange={(e) => setRadiologyName(e.target.value)}
                placeholder="If empty, system auto-generates from modality + body part"
                className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-cyan-500"
              />
            </label>
          </div>
        )}

        <div className="mt-3 grid gap-3 md:grid-cols-3">
          <label className="space-y-1">
            <span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Priority</span>
            <select
              value={priority}
              onChange={(e) => setPriority(e.target.value)}
              className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-cyan-500"
            >
              <option value="ROUTINE">ROUTINE</option>
              <option value="URGENT">URGENT</option>
              <option value="STAT">STAT</option>
            </select>
          </label>

          <label className="space-y-1 md:col-span-2">
            <span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Notes</span>
            <input
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Clinical notes for lab/radiology"
              className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-cyan-500"
            />
          </label>
        </div>

        <button
          type="button"
          onClick={onCreateRequest}
          disabled={saving}
          className="mt-4 rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-cyan-700 disabled:opacity-60"
        >
          {saving ? "Saving..." : "Create Request"}
        </button>

        <div className="mt-4 grid gap-3 md:grid-cols-3">
          <article className="rounded-xl border border-slate-200 p-3 md:col-span-3">
            <p className="font-semibold">Pre-Consultation Summary (Nurse Vitals)</p>
            {loadingPreConsultation ? <p className="mt-2 text-sm text-slate-500">Loading latest vitals...</p> : null}
            {!loadingPreConsultation && !preConsultation ? (
              <p className="mt-2 text-sm text-slate-500">No vitals recorded yet for selected patient.</p>
            ) : null}
            {preConsultation ? (
              <div className="mt-2 grid gap-2 text-sm text-slate-700 md:grid-cols-3">
                <p><span className="font-semibold">Recorded At:</span> {preConsultation.recorded_at || "-"}</p>
                <p><span className="font-semibold">BP:</span> {preConsultation.blood_pressure_systolic || "-"} / {preConsultation.blood_pressure_diastolic || "-"}</p>
                <p><span className="font-semibold">Pulse:</span> {preConsultation.pulse_rate || "-"}</p>
                <p><span className="font-semibold">Temperature:</span> {preConsultation.body_temperature || "-"}</p>
                <p><span className="font-semibold">SpO2:</span> {preConsultation.oxygen_saturation || "-"}</p>
                <p><span className="font-semibold">Respiratory:</span> {preConsultation.respiratory_rate || "-"}</p>
                <p><span className="font-semibold">Weight:</span> {preConsultation.weight_kg || "-"}</p>
                <p><span className="font-semibold">BMI:</span> {preConsultation.bmi || "-"}</p>
                <p><span className="font-semibold">Chief Complaint:</span> {preConsultation.chief_complaint || "-"}</p>
              </div>
            ) : null}
          </article>

          <article className="rounded-xl border border-slate-200 p-3">
            <p className="font-semibold">Lab Requests For Selected Patient</p>
            <div className="mt-2 max-h-52 space-y-2 overflow-auto text-sm">
              {patientRequests.lab_requests.length === 0 ? <p className="text-slate-500">No lab requests.</p> : null}
              {patientRequests.lab_requests.map((r) => (
                <div key={r.request_id} className="rounded-lg border border-slate-100 bg-slate-50 p-2">
                  <p className="font-medium">{r.test_name || `Test #${r.test_id}`}</p>
                  <p className="text-xs text-slate-600">Status: {r.status}</p>
                </div>
              ))}
            </div>
          </article>

          <article className="rounded-xl border border-slate-200 p-3">
            <p className="font-semibold">Radiology Requests For Selected Patient</p>
            <div className="mt-2 max-h-52 space-y-2 overflow-auto text-sm">
              {patientRequests.radiology_requests.length === 0 ? <p className="text-slate-500">No radiology requests.</p> : null}
              {patientRequests.radiology_requests.map((r) => (
                <div key={r.radiology_request_id} className="rounded-lg border border-slate-100 bg-slate-50 p-2">
                  <p className="font-medium">{r.test_name}</p>
                  <p className="text-xs text-slate-600">Body Part: {r.body_part || "-"}</p>
                  <p className="text-xs text-slate-600">Priority: {r.priority || "-"}</p>
                  <p className="text-xs text-slate-600">Status: {r.status}</p>
                </div>
              ))}
            </div>
          </article>

          <article className="rounded-xl border border-slate-200 p-3">
            <p className="font-semibold">Shared Reports (Lab + Imaging)</p>
            <div className="mt-2 max-h-52 space-y-2 overflow-auto text-sm">
              {sharedReports.length === 0 ? <p className="text-slate-500">No shared reports yet.</p> : null}
              {sharedReports.map((r) => (
                <div key={r.shared_report_id} className="rounded-lg border border-slate-100 bg-slate-50 p-2">
                  <p className="font-medium">{r.title || `${r.report_type} #${r.source_record_id}`}</p>
                  <p className="text-xs text-slate-600">{r.summary || "-"}</p>
                  <div className="mt-1">
                    {r.report_type === "LAB_RECORD" ? (
                      <Link
                        to={`/dashboard/doctor/lab-reports?record_id=${r.source_record_id}`}
                        className="text-xs font-semibold text-cyan-700 hover:underline"
                      >
                        Open Lab Report
                      </Link>
                    ) : (
                      <Link
                        to={`/dashboard/doctor/imaging-reports?record_id=${r.source_record_id}`}
                        className="text-xs font-semibold text-cyan-700 hover:underline"
                      >
                        Open Imaging Report
                      </Link>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </article>
        </div>
      </section>

      <section className="mt-6 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <h3 className="text-lg font-bold">Bed Availability & Transfer To Ward</h3>
        <p className="mt-1 text-xs text-slate-500">Live sync enabled. Free = green, Occupied = red, Cleaning = yellow.</p>
        <div className="mt-3 grid gap-3 md:grid-cols-4">
          <article className="rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-sm">
            <p className="font-semibold text-emerald-800">Free Beds</p>
            <p className="text-lg font-black text-emerald-700">{bedAvailability?.totals?.free_beds || 0}</p>
          </article>
          <article className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm">
            <p className="font-semibold text-rose-800">Occupied</p>
            <p className="text-lg font-black text-rose-700">{bedAvailability?.totals?.occupied_beds || 0}</p>
          </article>
          <article className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm">
            <p className="font-semibold text-amber-800">Cleaning</p>
            <p className="text-lg font-black text-amber-700">{bedAvailability?.totals?.cleaning_beds || 0}</p>
          </article>
          <article className="rounded-xl border border-slate-200 bg-slate-50 p-3 text-sm">
            <p className="font-semibold text-slate-700">Total Beds</p>
            <p className="text-lg font-black text-slate-900">{bedAvailability?.totals?.total_beds || 0}</p>
          </article>
        </div>

        <div className="mt-4 grid gap-3 md:grid-cols-3">
          <label className="space-y-1 md:col-span-2">
            <span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Select Free Bed</span>
            <select
              value={transferBedId}
              onChange={(e) => setTransferBedId(e.target.value)}
              className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-cyan-500"
            >
              {freeBedOptions.length === 0 ? <option value="">No free bed available</option> : null}
              {freeBedOptions.map((opt) => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
          </label>
          <button
            type="button"
            onClick={onTransferToWard}
            disabled={transferring || !patientId || !transferBedId}
            className="self-end rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-cyan-700 disabled:opacity-60"
          >
            {transferring ? "Transferring..." : "Transfer To Ward"}
          </button>
        </div>

        <div className="mt-4 grid gap-3 md:grid-cols-2">
          {(bedAvailability.items || []).map((u) => (
            <article key={`${u.unit_type}-${u.ward_name}`} className="rounded-xl border border-slate-200 p-3 text-sm">
              <p className="font-semibold">{u.ward_name} ({u.unit_type})</p>
              <p className="text-xs text-slate-600">Free {u.free_beds} | Occupied {u.occupied_beds} | Cleaning {u.cleaning_beds}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="mt-6 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <h3 className="text-lg font-bold">Recent Lab Results</h3>
        {recentResults.length === 0 ? <p className="mt-2 text-sm text-slate-500">No recent results yet.</p> : null}
        <div className="mt-3 grid gap-3 md:grid-cols-2">
          {recentResults.map((r) => (
            <article key={r.diagnosis_id} className="rounded-xl border border-slate-200 p-3 text-sm">
              <p className="font-semibold">{r.patient_name} ({r.patient_mrn})</p>
              <p>{r.disease_category}: {r.prediction_result}</p>
              <p className="text-slate-600">Confidence: {r.confidence_score || "N/A"}</p>
              <p className="text-xs text-slate-500 mt-1">{r.created_at}</p>
            </article>
          ))}
        </div>
      </section>
    </DoctorWorkspaceLayout>
  );
}

function Card({ title, text, to, cta }) {
  return (
    <article className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <h3 className="text-lg font-bold">{title}</h3>
      <p className="mt-2 text-sm text-slate-600">{text}</p>
      <Link to={to} className="mt-4 inline-flex rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-cyan-700">
        {cta}
      </Link>
    </article>
  );
}
