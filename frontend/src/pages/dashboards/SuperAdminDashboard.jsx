import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../../lib/api";
import { clearSession } from "../../lib/auth";

export default function SuperAdminDashboard() {
  const navigate = useNavigate();

  const [overview, setOverview] = useState(null);
  const [subs, setSubs] = useState([]);
  const [finance, setFinance] = useState(null);
  const [inventoryAlerts, setInventoryAlerts] = useState([]);
  const [aiModels, setAiModels] = useState([]);
  const [aiAccuracy, setAiAccuracy] = useState([]);
  const [aiService, setAiService] = useState(null);
  const [permissions, setPermissions] = useState([]);
  const [users, setUsers] = useState([]);
  const [contactMessages, setContactMessages] = useState([]);
  const [hospitalSettings, setHospitalSettings] = useState([]);
  const [snapshotPath, setSnapshotPath] = useState("");
  const [statusMsg, setStatusMsg] = useState("");

  const [permissionForm, setPermissionForm] = useState({
    source_role: "DOCTOR",
    target_module: "PHARMACY_STOCK",
    can_view: true,
    can_edit: false,
  });

  const [pricingForm, setPricingForm] = useState({
    doctor_consultation_fee: "",
    medicine_unit_price: "",
  });

  const loadAll = async () => {
    try {
      const [
        o,
        s,
        f,
        inv,
        models,
        accuracy,
        ping,
        perms,
        userLogs,
        msg,
        settings,
      ] = await Promise.all([
        api.get("/super-admin/overview"),
        api.get("/super-admin/subscriptions"),
        api.get("/super-admin/finance/global-revenue"),
        api.get("/super-admin/inventory/alerts", { params: { threshold: 10 } }),
        api.get("/super-admin/ai/models"),
        api.get("/super-admin/ai/accuracy"),
        api.get("/super-admin/ai/service/ping"),
        api.get("/super-admin/permissions"),
        api.get("/super-admin/logs/users"),
        api.get("/super-admin/contact-messages"),
        api.get("/super-admin/hospital-settings"),
      ]);

      setOverview(o.data);
      setSubs(s.data?.items || []);
      setFinance(f.data || null);
      setInventoryAlerts(inv.data?.items || []);
      setAiModels(models.data?.items || []);
      setAiAccuracy(accuracy.data?.items || []);
      setAiService(ping.data || null);
      setPermissions(perms.data?.items || []);
      setUsers(userLogs.data?.items || []);
      setContactMessages(msg.data?.items || []);
      setHospitalSettings(settings.data?.items || []);
    } catch (err) {
      setStatusMsg(err?.response?.data?.detail || "Unable to load super admin controls");
    }
  };

  useEffect(() => {
    loadAll();
  }, []);

  const logout = () => {
    clearSession();
    navigate("/");
  };

  const forceLogoutAll = async () => {
    await api.post("/super-admin/security/force-logout-all");
    setStatusMsg("Force logout policy applied to all active sessions.");
  };

  const pauseSubscription = async (id) => {
    await api.post(`/super-admin/subscriptions/${id}/pause`);
    await loadAll();
  };

  const resumeSubscription = async (id) => {
    await api.post(`/super-admin/subscriptions/${id}/resume`);
    await loadAll();
  };

  const activateModel = async (modelKey) => {
    await api.post("/super-admin/ai/models/activate", { model_key: modelKey });
    await loadAll();
  };

  const restartAiService = async () => {
    await api.post("/super-admin/ai/service/restart");
    const ping = await api.get("/super-admin/ai/service/ping");
    setAiService(ping.data || null);
    setStatusMsg("AI service restart signal sent.");
  };

  const createSnapshot = async () => {
    const res = await api.post("/super-admin/database/snapshot");
    setSnapshotPath(res.data?.path || "");
  };

  const savePermission = async () => {
    await api.post("/super-admin/permissions/upsert", permissionForm);
    const perms = await api.get("/super-admin/permissions");
    setPermissions(perms.data?.items || []);
    setStatusMsg("Role access mapping saved.");
  };

  const updateDoctorFee = async () => {
    if (!pricingForm.doctor_consultation_fee) return;
    await api.post("/super-admin/pricing/global-update", {
      target: "doctor_consultation_fee",
      amount: Number(pricingForm.doctor_consultation_fee),
    });
    setStatusMsg("Global doctor consultation fee updated.");
  };

  const updateMedicinePrice = async () => {
    if (!pricingForm.medicine_unit_price) return;
    await api.post("/super-admin/pricing/global-update", {
      target: "medicine_unit_price",
      amount: Number(pricingForm.medicine_unit_price),
    });
    setStatusMsg("Global medicine unit price updated.");
  };

  const blockUser = async (id) => {
    await api.post(`/super-admin/staff/${id}/block`);
    await loadAll();
  };

  const unblockUser = async (id) => {
    await api.post(`/super-admin/staff/${id}/unblock`);
    await loadAll();
  };

  return (
    <section className="px-4 py-10 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-7xl space-y-6">
        <header className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm flex items-center justify-between gap-4 flex-wrap">
          <div>
            <h1 className="text-3xl font-extrabold">Super Admin Control Center</h1>
            <p className="text-slate-600">Global System & Security Control</p>
            {statusMsg ? <p className="text-sm text-cyan-700 mt-2">{statusMsg}</p> : null}
          </div>
          <div className="flex gap-2">
            <button onClick={forceLogoutAll} className="rounded-lg border px-4 py-2 text-sm font-semibold text-rose-700">Force Logout All</button>
            <button onClick={logout} className="rounded-lg border px-4 py-2 text-sm font-semibold text-slate-700">Logout</button>
          </div>
        </header>

        <div className="grid md:grid-cols-4 gap-5">
          <Metric title="Hospitals" value={overview?.hospitals ?? "-"} />
          <Metric title="Active Subscriptions" value={overview?.active_subscriptions ?? "-"} />
          <Metric title="Expiring in 30 days" value={overview?.expiring_in_30_days ?? "-"} />
          <Metric title="Low Stock Alerts" value={inventoryAlerts.length} />
        </div>

        <Panel title="Subscription Controls">
          <Table
            headers={["Hospital", "Plan", "Cycle", "Expires", "Status", "Action"]}
            rows={subs.map((s) => [
              s.hospital_name,
              s.plan_name,
              s.billing_cycle,
              new Date(s.expires_at).toLocaleDateString(),
              s.status,
              <div key={s.subscription_id} className="flex gap-2">
                <button onClick={() => pauseSubscription(s.subscription_id)} className="rounded border px-2 py-1">Pause</button>
                <button onClick={() => resumeSubscription(s.subscription_id)} className="rounded border px-2 py-1">Resume</button>
              </div>,
            ])}
          />
        </Panel>

        <Panel title="AI & Model Governance">
          <div className="grid md:grid-cols-3 gap-4">
            <div className="rounded-xl border p-4">
              <p className="font-bold mb-2">Model Selection</p>
              {aiModels.map((m) => (
                <button key={m.model_key} onClick={() => activateModel(m.model_key)} className={`block w-full text-left rounded border px-3 py-2 mb-2 ${m.is_active ? "bg-cyan-50 border-cyan-400" : ""}`}>
                  {m.model_name} ({m.model_key}) {m.is_active ? "- Active" : ""}
                </button>
              ))}
            </div>
            <div className="rounded-xl border p-4">
              <p className="font-bold mb-2">Accuracy Monitoring</p>
              {aiAccuracy.slice(0, 6).map((m) => (
                <p key={m.metric_id} className="text-sm">{m.model_key} | {m.metric_name}: <strong>{m.metric_value}</strong></p>
              ))}
            </div>
            <div className="rounded-xl border p-4">
              <p className="font-bold mb-2">AI Service Control</p>
              <p className="text-sm mb-2">Service: {aiService?.status || "unknown"}</p>
              <div className="flex gap-2">
                <button onClick={loadAll} className="rounded border px-3 py-2 text-sm">Ping</button>
                <button onClick={restartAiService} className="rounded border px-3 py-2 text-sm">Restart</button>
              </div>
            </div>
          </div>
        </Panel>

        <Panel title="Enterprise Financial Oversight">
          <div className="grid md:grid-cols-2 gap-4">
            <div className="rounded-xl border p-4">
              <p className="font-bold">Global Revenue</p>
              <p className="text-sm">Payments: {finance?.payments_collected ?? 0}</p>
              <p className="text-sm">Subscriptions: {finance?.subscriptions_collected ?? 0}</p>
              <p className="text-sm font-bold">Combined: {finance?.combined_total ?? 0}</p>
            </div>
            <div className="rounded-xl border p-4 space-y-2">
              <p className="font-bold">Pricing Control</p>
              <input value={pricingForm.doctor_consultation_fee} onChange={(e) => setPricingForm((p) => ({ ...p, doctor_consultation_fee: e.target.value }))} className="w-full rounded border px-3 py-2 text-sm" placeholder="Global doctor consultation fee" />
              <button onClick={updateDoctorFee} className="rounded border px-3 py-2 text-sm">Update Doctor Fee</button>
              <input value={pricingForm.medicine_unit_price} onChange={(e) => setPricingForm((p) => ({ ...p, medicine_unit_price: e.target.value }))} className="w-full rounded border px-3 py-2 text-sm" placeholder="Global medicine unit price" />
              <button onClick={updateMedicinePrice} className="rounded border px-3 py-2 text-sm">Update Medicine Price</button>
            </div>
          </div>
        </Panel>

        <Panel title="Infrastructure & Audit">
          <div className="grid md:grid-cols-2 gap-4">
            <div className="rounded-xl border p-4">
              <p className="font-bold mb-2">Database Snapshots</p>
              <button onClick={createSnapshot} className="rounded border px-3 py-2 text-sm">Create Snapshot</button>
              {snapshotPath ? <p className="text-xs mt-2 break-all">{snapshotPath}</p> : null}
            </div>
            <div className="rounded-xl border p-4">
              <p className="font-bold mb-2">Hospital Identity Settings</p>
              <p className="text-sm">Records: {hospitalSettings.length}</p>
            </div>
          </div>
          <div className="mt-4 grid md:grid-cols-2 gap-4">
            <div className="rounded-xl border p-4">
              <p className="font-bold mb-2">Inventory Alerts (&lt;10)</p>
              {inventoryAlerts.slice(0, 8).map((a) => (
                <p key={a.batch_id} className="text-sm">Hospital {a.hospital_id}: {a.medicine_name} ({a.quantity})</p>
              ))}
            </div>
            <div className="rounded-xl border p-4">
              <p className="font-bold mb-2">Public Contact Messages</p>
              {contactMessages.slice(0, 8).map((m) => (
                <p key={m.contact_message_id} className="text-sm">{m.name}: {m.subject || "No subject"}</p>
              ))}
            </div>
          </div>
        </Panel>

        <Panel title="User Lifecycle & Access Levels">
          <div className="grid md:grid-cols-2 gap-4 mb-4">
            <div className="rounded-xl border p-4 space-y-2">
              <p className="font-bold">Role Permission Mapping</p>
              <input value={permissionForm.source_role} onChange={(e) => setPermissionForm((p) => ({ ...p, source_role: e.target.value.toUpperCase() }))} className="w-full rounded border px-3 py-2 text-sm" placeholder="Source role (e.g. DOCTOR)" />
              <input value={permissionForm.target_module} onChange={(e) => setPermissionForm((p) => ({ ...p, target_module: e.target.value.toUpperCase() }))} className="w-full rounded border px-3 py-2 text-sm" placeholder="Target module (e.g. PHARMACY_STOCK)" />
              <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={permissionForm.can_view} onChange={(e) => setPermissionForm((p) => ({ ...p, can_view: e.target.checked }))} />Can View</label>
              <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={permissionForm.can_edit} onChange={(e) => setPermissionForm((p) => ({ ...p, can_edit: e.target.checked }))} />Can Edit</label>
              <button onClick={savePermission} className="rounded border px-3 py-2 text-sm">Save Permission</button>
            </div>
            <div className="rounded-xl border p-4 overflow-auto">
              <p className="font-bold mb-2">Current Permission Matrix</p>
              {permissions.slice(0, 20).map((p) => (
                <p key={p.permission_id} className="text-sm">{p.source_role}{" -> "}{p.target_module} (view:{p.can_view} edit:{p.can_edit})</p>
              ))}
            </div>
          </div>

          <Table
            headers={["User ID", "Email", "Active", "Created", "Action"]}
            rows={users.slice(0, 50).map((u) => [
              u.user_id,
              u.email,
              u.is_active,
              u.created_at,
              <div key={u.user_id} className="flex gap-2">
                <button onClick={() => blockUser(u.user_id)} className="rounded border px-2 py-1">Block</button>
                <button onClick={() => unblockUser(u.user_id)} className="rounded border px-2 py-1">Unblock</button>
              </div>,
            ])}
          />
        </Panel>
      </div>
    </section>
  );
}

function Metric({ title, value }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <p className="text-xs uppercase tracking-[0.14em] text-slate-500 font-bold">{title}</p>
      <p className="text-3xl font-extrabold mt-2">{value}</p>
    </div>
  );
}

function Panel({ title, children }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm overflow-auto">
      <h2 className="text-xl font-bold mb-4">{title}</h2>
      {children}
    </div>
  );
}

function Table({ headers, rows }) {
  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="text-left text-slate-500 border-b">
          {headers.map((h) => (
            <th key={h} className="py-2 pr-3">{h}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={i} className="border-b">
            {r.map((c, idx) => (
              <td key={idx} className="py-2 pr-3 align-top">{c}</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}



