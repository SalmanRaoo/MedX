import { useEffect, useMemo, useState } from "react";
import { CreditCard, FilePlus2, Search } from "lucide-react";
import { api } from "../../lib/api";
import ReceptionWorkspaceLayout from "../../components/dashboards/ReceptionWorkspaceLayout";

function InputField({ label, ...props }) {
  return (
    <label className="block space-y-1">
      <span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">{label}</span>
      <input
        {...props}
        className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-teal-500"
      />
    </label>
  );
}

export default function ReceptionRadiologyBillingHub() {
  const [patients, setPatients] = useState([]);
  const [services, setServices] = useState([]);
  const [orders, setOrders] = useState([]);

  const [patientSearch, setPatientSearch] = useState("");
  const [testSearch, setTestSearch] = useState("");
  const [modality, setModality] = useState("");
  const [patientId, setPatientId] = useState("");
  const [serviceId, setServiceId] = useState("");
  const [serviceFee, setServiceFee] = useState("");
  const [procedureTag, setProcedureTag] = useState("Radiology Scan");
  const [paymentStatus, setPaymentStatus] = useState("UNPAID");
  const [paymentMethod, setPaymentMethod] = useState("CASH");
  const [notes, setNotes] = useState("");

  const [loadingPatients, setLoadingPatients] = useState(true);
  const [loadingServices, setLoadingServices] = useState(false);
  const [loadingOrders, setLoadingOrders] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [receipt, setReceipt] = useState(null);

  const filteredPatients = useMemo(() => {
    const q = patientSearch.trim().toLowerCase();
    if (!q) return patients;
    return patients.filter((p) => {
      const blob = `${p.full_name || ""} ${p.patient_mrn || ""} ${p.phone_number || ""}`.toLowerCase();
      return blob.includes(q);
    });
  }, [patients, patientSearch]);

  const selectedPatient = useMemo(
    () => patients.find((p) => String(p.patient_id) === String(patientId)) || null,
    [patients, patientId]
  );

  const selectedService = useMemo(
    () => services.find((s) => String(s.service_id) === String(serviceId)) || null,
    [services, serviceId]
  );

  const modalityOptions = useMemo(() => {
    const set = new Set(services.map((s) => s.modality).filter(Boolean));
    return Array.from(set);
  }, [services]);

  const loadPatients = async () => {
    setLoadingPatients(true);
    try {
      const { data } = await api.get("/patients/", { params: { limit: 500 } });
      const items = data?.items || [];
      setPatients(items);
      if (!patientId && items.length) {
        setPatientId(String(items[0].patient_id));
      }
    } catch (err) {
      setError(err?.response?.data?.detail || "Unable to load patients.");
    } finally {
      setLoadingPatients(false);
    }
  };

  const loadServices = async () => {
    setLoadingServices(true);
    try {
      const params = {};
      if (modality) params.modality = modality;
      if (testSearch.trim()) params.q = testSearch.trim();
      const { data } = await api.get("/reception/radiology-services", { params });
      const items = data?.items || [];
      setServices(items);
      setServiceId((prev) => {
        if (prev && items.find((s) => String(s.service_id) === String(prev))) return prev;
        return items.length ? String(items[0].service_id) : "";
      });
    } catch (err) {
      setError(err?.response?.data?.detail || "Unable to load radiology services.");
    } finally {
      setLoadingServices(false);
    }
  };

  const loadOrders = async () => {
    setLoadingOrders(true);
    try {
      const { data } = await api.get("/reception/radiology-billing/orders", { params: { limit: 200 } });
      setOrders(data?.items || []);
    } catch (err) {
      setError(err?.response?.data?.detail || "Unable to load billing orders.");
    } finally {
      setLoadingOrders(false);
    }
  };

  useEffect(() => {
    loadPatients();
    loadOrders();
  }, []);

  useEffect(() => {
    loadServices();
  }, [modality, testSearch]);

  useEffect(() => {
    if (!selectedService) {
      setServiceFee("");
      return;
    }
    setServiceFee(String(Number(selectedService.service_fee || 0)));
  }, [selectedService?.service_id]);

  const registerOrder = async () => {
    setError("");
    setSuccess("");
    if (!selectedPatient) {
      setError("Please select a patient.");
      return;
    }
    if (!selectedService) {
      setError("Please select a scan service.");
      return;
    }

    setSaving(true);
    try {
      const { data } = await api.post("/reception/radiology-billing/register", {
        patient_id: Number(selectedPatient.patient_id),
        patient_mrn: selectedPatient.patient_mrn,
        service_id: Number(selectedService.service_id),
        service_fee: Number(serviceFee || selectedService.service_fee || 0),
        procedure_tag: procedureTag || "Radiology Scan",
        payment_status: paymentStatus,
        payment_method: paymentMethod,
        notes: notes || null,
      });
      setReceipt(data?.receipt || null);
      setSuccess("Radiology service registered. Accounts ledger updated via invoice/payment status.");
      setNotes("");
      await loadOrders();
    } catch (err) {
      setError(err?.response?.data?.detail || "Unable to register radiology billing.");
    } finally {
      setSaving(false);
    }
  };

  const togglePaymentStatus = async (item) => {
    const current = String(item.payment_status || "UNPAID").toUpperCase();
    const next = current === "PAID" ? "UNPAID" : "PAID";
    setError("");
    setSuccess("");
    try {
      await api.post(`/reception/radiology-billing/${item.billing_id}/payment-status`, {
        payment_status: next,
        payment_method: paymentMethod,
      });
      setSuccess(`Payment status updated to ${next}.`);
      await loadOrders();
    } catch (err) {
      setError(err?.response?.data?.detail || "Unable to update payment status.");
    }
  };

  const printReceipt = async () => {
    if (!receipt) return;
    let settingsMeta = {};
    try {
      const { data } = await api.get("/settings");
      settingsMeta = data?.hospital_metadata || {};
    } catch {
      settingsMeta = {};
    }
    const hospitalName = settingsMeta.hospital_name || receipt.hospital_name || "MedX Radiology Desk";
    const hospitalAddress = settingsMeta.address || receipt.hospital_address || "";
    const hospitalLogo = settingsMeta.logo_url || receipt.hospital_logo_url || "";

    const popup = window.open("", "_blank", "width=450,height=900");
    if (!popup) return;

    popup.document.write(`
      <html>
        <head>
          <title>Radiology Payment Receipt</title>
          <style>
            @page { size: 80mm auto; margin: 4mm; }
            body { margin: 0; font-family: "Consolas", "Courier New", monospace; color: #0f172a; background: #fff; }
            .ticket { width: 78mm; margin: 0 auto; padding: 8px 6px; }
            .center { text-align: center; }
            .hr { border-top: 1px dashed #334155; margin: 8px 0; }
            .row { display: flex; justify-content: space-between; gap: 10px; font-size: 12px; margin: 4px 0; }
            .k { color: #334155; }
            .v { font-weight: 700; text-align: right; }
            .total { font-size: 14px; font-weight: 700; padding: 6px 0; }
            .logo { width:30px; height:30px; border-radius:999px; object-fit:cover; margin:0 auto 4px; }
          </style>
        </head>
        <body>
          <div class="ticket">
            <div class="center">
              ${hospitalLogo ? `<img src="${hospitalLogo}" alt="Hospital Logo" class="logo" />` : ""}
              <div style="font-size:16px;font-weight:700;">${hospitalName}</div>
              <div style="font-size:10px;">${hospitalAddress || ""}</div>
              <div style="font-size:11px;">Thermal Billing Receipt</div>
            </div>
            <div class="hr"></div>
            <div class="row"><span class="k">Receipt</span><span class="v">${receipt.receipt_no || "-"}</span></div>
            <div class="row"><span class="k">Date</span><span class="v">${receipt.created_at || "-"}</span></div>
            <div class="row"><span class="k">Patient MRN</span><span class="v">${receipt.patient_mrn || "-"}</span></div>
            <div class="row"><span class="k">Patient</span><span class="v">${receipt.patient_name || "-"}</span></div>
            <div class="row"><span class="k">Scan</span><span class="v">${receipt.scan_type || "-"}</span></div>
            <div class="row"><span class="k">Procedure Tag</span><span class="v">${receipt.procedure_tag || "-"}</span></div>
            <div class="row"><span class="k">Modality</span><span class="v">${receipt.modality || "-"}</span></div>
            <div class="row"><span class="k">Body Part</span><span class="v">${receipt.body_part || "-"}</span></div>
            <div class="hr"></div>
            <div class="row total"><span>Total Due</span><span>PKR ${Number(receipt.total_amount_due || 0).toFixed(2)}</span></div>
            <div class="row"><span class="k">Payment</span><span class="v">${receipt.payment_status || "-"}</span></div>
            <div class="row"><span class="k">Invoice</span><span class="v">${receipt.invoice_number || "-"}</span></div>
            <div class="hr"></div>
            <div class="center" style="font-size:11px;">Thank you</div>
          </div>
        </body>
      </html>
    `);
    popup.document.close();
    popup.focus();
    popup.print();
  };

  return (
    <ReceptionWorkspaceLayout
      title="Reception Radiology & Billing Hub"
      subtitle="Create X-Ray, MRI, Ultrasound, and CT Scan service orders with immediate invoice generation."
    >
      <div className="space-y-5">
          <header className="rounded-[32px] border border-slate-200 bg-white p-6 shadow-sm">
            <div className="flex items-center gap-3">
              <span className="inline-flex h-11 w-11 items-center justify-center rounded-2xl bg-teal-100 text-teal-700">
                <CreditCard className="h-6 w-6" />
              </span>
              <div>
                <h1 className="text-3xl font-black tracking-tight">Reception Radiology & Billing Hub</h1>
                <p className="mt-1 text-slate-600">Radiology order registration with integrated billing and procedure tagging.</p>
              </div>
            </div>
          </header>

          {error ? <p className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</p> : null}
          {success ? <p className="rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{success}</p> : null}

          <div className="grid gap-5 xl:grid-cols-[1.12fr_1fr]">
            <section className="rounded-[32px] border border-slate-200 bg-white p-6 shadow-sm">
              <h2 className="text-lg font-bold">Service Registration</h2>

              <div className="mt-4 grid gap-3 sm:grid-cols-2">
                <label className="block space-y-1 sm:col-span-2">
                  <span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Search Patient</span>
                  <div className="relative">
                    <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                    <input
                      value={patientSearch}
                      onChange={(e) => setPatientSearch(e.target.value)}
                      placeholder="MRN, name, phone"
                      className="w-full rounded-xl border border-slate-300 py-2 pl-9 pr-3 text-sm outline-none focus:border-teal-500"
                    />
                  </div>
                </label>

                <label className="block space-y-1 sm:col-span-2">
                  <span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Patient</span>
                  <select
                    value={patientId}
                    onChange={(e) => setPatientId(e.target.value)}
                    className="w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-teal-500"
                  >
                    <option value="">Select patient</option>
                    {filteredPatients.map((p) => (
                      <option key={p.patient_id} value={p.patient_id}>
                        {p.full_name} ({p.patient_mrn})
                      </option>
                    ))}
                  </select>
                </label>

                <label className="block space-y-1">
                  <span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Modality</span>
                  <select
                    value={modality}
                    onChange={(e) => setModality(e.target.value)}
                    className="w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-teal-500"
                  >
                    <option value="">All</option>
                    {["X_RAY", "MRI", "ULTRASOUND", "CT_SCAN"].map((m) => (
                      <option key={m} value={m}>{m}</option>
                    ))}
                    {modalityOptions
                      .filter((m) => !["X_RAY", "MRI", "ULTRASOUND", "CT_SCAN"].includes(m))
                      .map((m) => <option key={m} value={m}>{m}</option>)}
                  </select>
                </label>

                <InputField
                  label="Search Report Type / Test"
                  value={testSearch}
                  onChange={(e) => setTestSearch(e.target.value)}
                  placeholder="CT Scan - Abdomen, MRI - Brain"
                />

                <InputField
                  label="Procedure Tag"
                  value={procedureTag}
                  onChange={(e) => setProcedureTag(e.target.value)}
                  placeholder="Radiology Scan"
                />

                <InputField
                  label="Price (PKR)"
                  type="number"
                  min="0"
                  step="0.01"
                  value={serviceFee}
                  onChange={(e) => setServiceFee(e.target.value)}
                  placeholder="0"
                />

                <label className="block space-y-1 sm:col-span-2">
                  <span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Radiology Service</span>
                  <select
                    value={serviceId}
                    onChange={(e) => setServiceId(e.target.value)}
                    className="w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-teal-500"
                  >
                    <option value="">Select service</option>
                    {services.map((s) => (
                      <option key={s.service_id} value={s.service_id}>
                        {s.scan_name} ({s.modality}) - PKR {Number(s.service_fee || 0).toFixed(2)}
                      </option>
                    ))}
                  </select>
                </label>

                <label className="block space-y-1">
                  <span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Payment Status</span>
                  <select
                    value={paymentStatus}
                    onChange={(e) => setPaymentStatus(e.target.value)}
                    className="w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-teal-500"
                  >
                    <option value="UNPAID">UNPAID</option>
                    <option value="PAID">PAID</option>
                  </select>
                </label>

                <label className="block space-y-1">
                  <span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Payment Method</span>
                  <select
                    value={paymentMethod}
                    onChange={(e) => setPaymentMethod(e.target.value)}
                    className="w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-teal-500"
                  >
                    <option value="CASH">CASH</option>
                    <option value="CARD">CARD</option>
                    <option value="BANK">BANK</option>
                    <option value="ONLINE">ONLINE</option>
                  </select>
                </label>

                <label className="block space-y-1 sm:col-span-2">
                  <span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Order Notes</span>
                  <textarea
                    value={notes}
                    onChange={(e) => setNotes(e.target.value)}
                    rows={3}
                    className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-teal-500"
                  />
                </label>
              </div>

              <div className="mt-3 rounded-2xl border border-slate-200 bg-slate-50 p-3 text-sm">
                <p><span className="font-semibold">Patient MRN:</span> {selectedPatient?.patient_mrn || "-"}</p>
                <p><span className="font-semibold">Scan Type:</span> {selectedService?.scan_name || "-"}</p>
                <p><span className="font-semibold">Procedure Tag:</span> {procedureTag || "-"}</p>
                <p><span className="font-semibold">Total Due:</span> PKR {Number(serviceFee || selectedService?.service_fee || 0).toFixed(2)}</p>
              </div>

              <div className="mt-4 flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={registerOrder}
                  disabled={saving || loadingPatients || loadingServices}
                  className="inline-flex items-center gap-2 rounded-xl bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-teal-700 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  <FilePlus2 className="h-4 w-4" />
                  {saving ? "Registering..." : "Register Service + Invoice"}
                </button>
                {receipt ? (
                  <button
                    type="button"
                    onClick={printReceipt}
                    className="inline-flex items-center gap-2 rounded-xl border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50"
                  >
                    <CreditCard className="h-4 w-4" /> Print Receipt
                  </button>
                ) : null}
              </div>
            </section>

            <section className="rounded-[32px] border border-slate-200 bg-white p-6 shadow-sm">
              <h2 className="text-lg font-bold">Recent Radiology Billings</h2>
              {loadingOrders ? <p className="mt-3 text-sm text-slate-500">Loading billing orders...</p> : null}
              {!loadingOrders && orders.length === 0 ? <p className="mt-3 text-sm text-slate-500">No billing orders found.</p> : null}

              <div className="mt-3 space-y-2 max-h-[72vh] overflow-auto pr-1">
                {orders.map((item) => {
                  const current = String(item.payment_status || "UNPAID").toUpperCase();
                  const next = current === "PAID" ? "UNPAID" : "PAID";
                  return (
                    <div key={item.billing_id} className="rounded-2xl border border-slate-200 p-3 text-sm">
                      <p className="font-semibold text-slate-900">#{item.billing_id} | {item.patient_mrn || "-"}</p>
                      <p className="text-slate-600">{item.patient_name || "-"} | {item.scan_name || "-"}</p>
                      <p className="text-slate-600">{item.modality || "-"} | {item.body_part || "-"} | Invoice: {item.invoice_number || "-"}</p>
                      <p className="text-slate-600">Procedure Tag: {item.procedure_tag || "-"}</p>
                      <p className="text-slate-600">Amount: PKR {Number(item.net_amount || item.amount_due || 0).toFixed(2)}</p>
                      <p className={`font-semibold ${current === "PAID" ? "text-emerald-700" : "text-amber-700"}`}>Payment: {current}</p>

                      <button
                        type="button"
                        onClick={() => togglePaymentStatus(item)}
                        className="mt-2 rounded-lg border border-slate-300 px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50"
                      >
                        Toggle to {next}
                      </button>
                    </div>
                  );
                })}
              </div>
            </section>
          </div>
      </div>
    </ReceptionWorkspaceLayout>
  );
}
