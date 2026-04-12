import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, CheckCircle2, Pill, Plus, Printer, RefreshCw, Save, Search, Trash2 } from "lucide-react";
import RoleDashboardShell from "../../components/dashboards/RoleDashboardShell";
import { api } from "../../lib/api";

function toast(setter, message, tone = "success") {
  const id = Date.now() + Math.random();
  setter((prev) => [...prev, { id, message, tone }]);
  setTimeout(() => setter((prev) => prev.filter((t) => t.id !== id)), 3000);
}

function ToastStack({ toasts }) {
  return (
    <div className="fixed right-4 top-4 z-[200] space-y-2">
      {toasts.map((t) => (
        <div key={t.id} className={`rounded-xl px-4 py-2 text-sm font-semibold ${t.tone === "error" ? "bg-rose-600 text-white" : "bg-teal-600 text-white"}`}>
          {t.message}
        </div>
      ))}
    </div>
  );
}

export default function PharmacyDashboard() {
  const role = useMemo(() => {
    try {
      return String(JSON.parse(localStorage.getItem("medx_user") || "{}")?.role_name || "").toUpperCase();
    } catch {
      return "";
    }
  }, []);
  const canEditPrice = ["PHARMACY", "ADMIN", "SUPER_ADMIN"].includes(role);

  const [toasts, setToasts] = useState([]);
  const [error, setError] = useState("");

  const [mrn, setMrn] = useState("");
  const [patient, setPatient] = useState(null);
  const [prescriptions, setPrescriptions] = useState([]);
  const [qtyMap, setQtyMap] = useState({});
  const [loadingRx, setLoadingRx] = useState(false);
  const [dispensingKey, setDispensingKey] = useState("");

  const [inventory, setInventory] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [sales, setSales] = useState([]);
  const [stockSearch, setStockSearch] = useState("");
  const [stockEdits, setStockEdits] = useState({});
  const [savingId, setSavingId] = useState(0);
  const [busy, setBusy] = useState(false);

  const [newStock, setNewStock] = useState({
    medicine_name: "",
    generic_name: "",
    batch_number: "",
    expiry_date: "",
    manufacturer: "",
    unit_price: "",
    quantity_available: "",
    minimum_threshold: "50",
  });

  const loadInventory = async (q = stockSearch) => {
    const [inv, al, sal] = await Promise.all([
      api.get("/pharmacy/inventory", { params: { q, limit: 800 } }),
      api.get("/pharmacy/inventory/alerts", { params: { threshold: 50 } }),
      api.get("/pharmacy/sales", { params: { limit: 20 } }),
    ]);
    const rows = inv.data?.items || [];
    setInventory(rows);
    setAlerts(al.data?.items || []);
    setSales(sal.data?.items || []);
    setStockEdits((prev) => {
      const next = { ...prev };
      rows.forEach((r) => {
        if (!next[r.inventory_id]) next[r.inventory_id] = { quantity_available: String(r.quantity_available ?? 0), unit_price: String(r.unit_price ?? 0), minimum_threshold: String(r.minimum_threshold ?? 50) };
      });
      return next;
    });
  };

  const loadPrescriptions = async () => {
    if (!mrn.trim()) return;
    setLoadingRx(true);
    setError("");
    try {
      const res = await api.get("/pharmacy/prescriptions", { params: { patient_mrn: mrn.trim() } });
      const items = res.data?.items || [];
      setPatient(res.data?.patient || null);
      setPrescriptions(items);
      const next = {};
      items.forEach((i) => {
        next[`${i.source}-${i.source_id}`] = String(i.recommended_quantity || 1);
      });
      setQtyMap(next);
    } catch (err) {
      setError(err?.response?.data?.detail || "Unable to load prescriptions");
      setPatient(null);
      setPrescriptions([]);
    } finally {
      setLoadingRx(false);
    }
  };

  useEffect(() => {
    loadInventory().catch(() => setError("Unable to load pharmacy data"));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const totalUnits = inventory.reduce((sum, r) => sum + Number(r.quantity_available || 0), 0);
  const pendingRx = prescriptions.filter((p) => String(p.status || "").toUpperCase() !== "DISPENSED").length;

  const printLabel = (item, dispensed = null) => {
    const info = dispensed || {};
    const popup = window.open("", "_blank", "width=420,height=520");
    if (!popup) return;
    popup.document.write(`
      <html><head><title>Dosage Label</title><style>
      body{font-family:Arial;padding:12px} .box{border:2px dashed #0f766e;border-radius:12px;padding:12px;width:320px}
      .h{font-weight:700;color:#0f766e;margin-bottom:8px}.r{font-size:12px;margin:4px 0}
      </style></head><body><div class="box">
      <div class="h">MedX Pharmacy Label</div>
      <div class="r"><b>Patient:</b> ${info.patient_name || patient?.full_name || "-"}</div>
      <div class="r"><b>MRN:</b> ${info.patient_mrn || patient?.patient_mrn || "-"}</div>
      <div class="r"><b>Medicine:</b> ${info.medication_name || item.medication_name || "-"}</div>
      <div class="r"><b>Dosage:</b> ${info.dosage || item.dosage || "-"}</div>
      <div class="r"><b>Instructions:</b> ${info.instructions || item.instructions || "-"}</div>
      </div><script>window.print()</script></body></html>
    `);
    popup.document.close();
  };

  const dispense = async (item) => {
    const key = `${item.source}-${item.source_id}`;
    const quantity = Number(qtyMap[key] || 1);
    setDispensingKey(key);
    try {
      const res = await api.post("/pharmacy/dispense", { source: item.source, source_id: item.source_id, quantity });
      await Promise.all([loadPrescriptions(), loadInventory()]);
      toast(setToasts, `Dispensed. Invoice: ${res.data?.invoice_number || "-"}`);
      printLabel(item, res.data);
    } catch (err) {
      toast(setToasts, err?.response?.data?.detail || "Unable to dispense", "error");
    } finally {
      setDispensingKey("");
    }
  };

  const createStock = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await api.post("/pharmacy/inventory", {
        ...newStock,
        generic_name: newStock.generic_name || null,
        manufacturer: newStock.manufacturer || null,
        expiry_date: newStock.expiry_date || null,
        unit_price: Number(newStock.unit_price || 0),
        quantity_available: Number(newStock.quantity_available || 0),
        minimum_threshold: Number(newStock.minimum_threshold || 50),
      });
      setNewStock({ medicine_name: "", generic_name: "", batch_number: "", expiry_date: "", manufacturer: "", unit_price: "", quantity_available: "", minimum_threshold: "50" });
      await loadInventory();
      toast(setToasts, "Stock added");
    } catch (err) {
      toast(setToasts, err?.response?.data?.detail || "Unable to add stock", "error");
    } finally {
      setBusy(false);
    }
  };

  const saveRow = async (row) => {
    const edit = stockEdits[row.inventory_id] || {};
    setSavingId(row.inventory_id);
    try {
      await api.put(`/pharmacy/inventory/${row.inventory_id}`, {
        quantity_available: Number(edit.quantity_available ?? row.quantity_available ?? 0),
        minimum_threshold: Number(edit.minimum_threshold ?? row.minimum_threshold ?? 50),
        unit_price: Number(edit.unit_price ?? row.unit_price ?? 0),
      });
      await loadInventory();
      toast(setToasts, "Inventory updated");
    } catch (err) {
      toast(setToasts, err?.response?.data?.detail || "Unable to update inventory", "error");
    } finally {
      setSavingId(0);
    }
  };

  const removeExpired = async () => {
    try {
      const res = await api.delete("/pharmacy/inventory/expired");
      await loadInventory();
      toast(setToasts, `Expired removed: ${res.data?.deleted_count || 0}`);
    } catch (err) {
      toast(setToasts, err?.response?.data?.detail || "Unable to remove expired", "error");
    }
  };

  return (
    <>
      <ToastStack toasts={toasts} />
      <RoleDashboardShell title="Pharmacy Dashboard" subtitle="Dispensing desk + stock room + revenue sync." cards={[{ title: "Stock Units", text: String(totalUnits) }, { title: "Low Stock", text: String(alerts.length) }, { title: "Pending Rx", text: String(pendingRx) }]} />
      <section className="px-4 pb-10 sm:px-6 lg:px-8 -mt-2">
        <div className="mx-auto max-w-7xl space-y-6">
          {error ? <p className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</p> : null}

          <div className="rounded-[32px] border border-slate-200 bg-white p-6 shadow-sm">
            <div className="mb-4 inline-flex items-center gap-2 rounded-xl bg-teal-50 px-3 py-2 text-sm font-bold text-teal-700"><Pill className="h-4 w-4" /> Dispensing Desk (MRN)</div>
            <div className="flex gap-2">
              <div className="relative flex-1"><Search className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-slate-400" /><input value={mrn} onChange={(e) => setMrn(e.target.value)} placeholder="Enter patient MRN" className="w-full rounded-xl border border-slate-300 px-9 py-2.5 text-sm outline-none focus:border-teal-500" /></div>
              <button onClick={loadPrescriptions} className="rounded-xl bg-slate-900 px-4 py-2.5 text-sm font-semibold text-white hover:bg-teal-700">{loadingRx ? "Loading..." : "Search"}</button>
              <button onClick={loadPrescriptions} className="rounded-xl border border-slate-300 px-4 py-2.5 text-sm font-semibold text-slate-700 hover:border-teal-300 hover:text-teal-700"><RefreshCw className="h-4 w-4" /></button>
            </div>
            {patient ? <p className="mt-3 rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-700"><b>{patient.full_name}</b> ({patient.patient_mrn})</p> : null}
            <div className="mt-4 overflow-x-auto">
              {prescriptions.length === 0 ? <p className="text-sm text-slate-500">No prescriptions loaded.</p> : (
                <table className="min-w-full text-sm"><thead className="text-left text-slate-500"><tr><th className="py-2 pr-3">Medicine</th><th className="py-2 pr-3">Dose</th><th className="py-2 pr-3">Stock</th><th className="py-2 pr-3">Qty</th><th className="py-2 pr-3">Actions</th></tr></thead>
                  <tbody>{prescriptions.map((i) => { const k = `${i.source}-${i.source_id}`; const inStock = Boolean(i.in_stock); return (
                    <tr key={k} className="border-t border-slate-100">
                      <td className="py-2 pr-3"><p className="font-semibold">{i.medication_name}</p><p className="text-xs text-slate-500">{i.instructions || "-"}</p></td>
                      <td className="py-2 pr-3">{i.dosage || "-"}</td>
                      <td className="py-2 pr-3"><span className={`inline-flex items-center gap-1 rounded-full px-2 py-1 text-xs font-semibold ${inStock ? "bg-emerald-100 text-emerald-700" : "bg-rose-100 text-rose-700"}`}>{inStock ? <CheckCircle2 className="h-3.5 w-3.5" /> : <AlertTriangle className="h-3.5 w-3.5" />}{inStock ? "In Stock" : "Out"}</span></td>
                      <td className="py-2 pr-3"><input type="number" min="1" value={qtyMap[k] || "1"} onChange={(e) => setQtyMap((p) => ({ ...p, [k]: e.target.value }))} className="w-20 rounded-lg border border-slate-300 px-2 py-1 text-sm" /></td>
                      <td className="py-2 pr-3"><div className="flex gap-2"><button onClick={() => dispense(i)} disabled={!inStock || dispensingKey === k} className="rounded-lg bg-slate-900 px-3 py-1.5 text-xs font-semibold text-white hover:bg-teal-700 disabled:opacity-60">{dispensingKey === k ? "..." : "Dispense"}</button><button onClick={() => printLabel(i)} className="inline-flex items-center gap-1 rounded-lg border border-slate-300 px-3 py-1.5 text-xs font-semibold text-slate-700"><Printer className="h-3.5 w-3.5" />Label</button></div></td>
                    </tr>
                  ); })}</tbody>
                </table>
              )}
            </div>
          </div>

          <div className="grid gap-6 xl:grid-cols-[1.2fr_1fr]">
            <div className="rounded-[32px] border border-slate-200 bg-white p-6 shadow-sm">
              <form onSubmit={createStock} className="grid gap-3 md:grid-cols-2">
                <Input label="Medicine" value={newStock.medicine_name} onChange={(v) => setNewStock((p) => ({ ...p, medicine_name: v }))} required />
                <Input label="Generic Name" value={newStock.generic_name} onChange={(v) => setNewStock((p) => ({ ...p, generic_name: v }))} />
                <Input label="Batch" value={newStock.batch_number} onChange={(v) => setNewStock((p) => ({ ...p, batch_number: v }))} required />
                <Input label="Expiry" type="date" value={newStock.expiry_date} onChange={(v) => setNewStock((p) => ({ ...p, expiry_date: v }))} />
                <Input label="Manufacturer" value={newStock.manufacturer} onChange={(v) => setNewStock((p) => ({ ...p, manufacturer: v }))} />
                <Input label="Unit Price" type="number" step="0.01" min="0" value={newStock.unit_price} onChange={(v) => setNewStock((p) => ({ ...p, unit_price: v }))} required />
                <Input label="Quantity" type="number" min="0" value={newStock.quantity_available} onChange={(v) => setNewStock((p) => ({ ...p, quantity_available: v }))} required />
                <Input label="Low Threshold" type="number" min="0" value={newStock.minimum_threshold} onChange={(v) => setNewStock((p) => ({ ...p, minimum_threshold: v }))} />
                <div className="md:col-span-2 flex flex-wrap gap-2"><button disabled={busy} className="inline-flex items-center gap-2 rounded-xl bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-teal-700"><Plus className="h-4 w-4" />{busy ? "Saving..." : "Add Stock"}</button><button type="button" onClick={removeExpired} className="inline-flex items-center gap-2 rounded-xl border border-rose-300 px-4 py-2 text-sm font-semibold text-rose-700 hover:bg-rose-50"><Trash2 className="h-4 w-4" />Delete Expired</button></div>
              </form>

              <div className="mt-5 flex gap-2"><input value={stockSearch} onChange={(e) => setStockSearch(e.target.value)} placeholder="Search inventory" className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm" /><button onClick={() => loadInventory(stockSearch)} className="rounded-xl border border-slate-300 px-3 py-2 text-sm font-semibold text-slate-700">Search</button></div>
              <div className="mt-4 overflow-x-auto">
                <table className="min-w-full text-sm"><thead className="text-left text-slate-500"><tr><th className="py-2 pr-3">Medicine</th><th className="py-2 pr-3">Batch</th><th className="py-2 pr-3">Qty</th><th className="py-2 pr-3">Price</th><th className="py-2 pr-3">Threshold</th><th className="py-2 pr-3">Save</th></tr></thead>
                  <tbody>{inventory.map((r) => { const e = stockEdits[r.inventory_id] || {}; return (
                    <tr key={r.inventory_id} className="border-t border-slate-100">
                      <td className="py-2 pr-3">{r.medicine_name}</td>
                      <td className="py-2 pr-3">{r.batch_number}</td>
                      <td className="py-2 pr-3"><input type="number" min="0" value={e.quantity_available ?? r.quantity_available} onChange={(ev) => setStockEdits((p) => ({ ...p, [r.inventory_id]: { ...p[r.inventory_id], quantity_available: ev.target.value } }))} className="w-24 rounded-lg border border-slate-300 px-2 py-1" /></td>
                      <td className="py-2 pr-3"><input type="number" min="0" step="0.01" disabled={!canEditPrice} value={e.unit_price ?? r.unit_price} onChange={(ev) => setStockEdits((p) => ({ ...p, [r.inventory_id]: { ...p[r.inventory_id], unit_price: ev.target.value } }))} className="w-24 rounded-lg border border-slate-300 px-2 py-1 disabled:bg-slate-100" /></td>
                      <td className="py-2 pr-3"><input type="number" min="0" value={e.minimum_threshold ?? r.minimum_threshold} onChange={(ev) => setStockEdits((p) => ({ ...p, [r.inventory_id]: { ...p[r.inventory_id], minimum_threshold: ev.target.value } }))} className="w-24 rounded-lg border border-slate-300 px-2 py-1" /></td>
                      <td className="py-2 pr-3"><button onClick={() => saveRow(r)} disabled={savingId === r.inventory_id} className="inline-flex items-center gap-1 rounded-lg border border-slate-300 px-2 py-1 text-xs font-semibold text-slate-700"><Save className="h-3.5 w-3.5" />{savingId === r.inventory_id ? "..." : "Save"}</button></td>
                    </tr>
                  ); })}</tbody>
                </table>
              </div>
            </div>

            <div className="space-y-6">
              <div className="rounded-[32px] border border-slate-200 bg-white p-6 shadow-sm">
                <h3 className="mb-3 text-sm font-bold uppercase tracking-[0.12em] text-amber-700">Low Stock Alerts</h3>
                {alerts.length === 0 ? <p className="text-sm text-slate-500">No alerts.</p> : alerts.slice(0, 10).map((a) => <p key={a.inventory_id} className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm">{a.medicine_name} | Qty {a.quantity_available}</p>)}
              </div>
              <div className="rounded-[32px] border border-slate-200 bg-white p-6 shadow-sm">
                <h3 className="mb-3 text-sm font-bold uppercase tracking-[0.12em] text-emerald-700">Pharmacy Revenue Feed</h3>
                {sales.length === 0 ? <p className="text-sm text-slate-500">No sales yet.</p> : sales.map((s) => <p key={s.sale_id} className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm">{s.patient_mrn || "-"} | PKR {Number(s.total_amount || 0).toFixed(2)}</p>)}
              </div>
            </div>
          </div>
        </div>
      </section>
    </>
  );
}

function Input({ label, value, onChange, ...props }) {
  return (
    <label className="block space-y-1">
      <span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">{label}</span>
      <input {...props} value={value} onChange={(e) => onChange(e.target.value)} className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm" />
    </label>
  );
}
