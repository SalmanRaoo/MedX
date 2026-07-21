import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../../lib/api";
import { clearSession } from "../../lib/auth";

function formatDate(value) {
  if (!value) return "-";
  const dt = new Date(value);
  if (Number.isNaN(dt.getTime())) return String(value);
  return dt.toLocaleDateString();
}

function extractData(result, fallback) {
  if (result?.status !== "fulfilled") return fallback;
  return result.value?.data ?? fallback;
}

function extractError(result) {
  if (result?.status !== "rejected") return "";
  return (
    result.reason?.response?.data?.detail
    || result.reason?.message
    || "Request failed"
  );
}

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
    const labels = [
      "overview",
      "subscriptions",
      "finance",
      "inventory",
      "ai models",
      "ai accuracy",
      "ai ping",
      "permissions",
      "user logs",
      "contact messages",
      "hospital settings",
    ];

    const results = await Promise.allSettled([
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

    const [o, s, f, inv, models, accuracy, ping, perms, userLogs, msg, settings] = results;

    setOverview(extractData(o, null));
    setSubs(extractData(s, { items: [] })?.items || []);
    setFinance(extractData(f, null));
    setInventoryAlerts(extractData(inv, { items: [] })?.items || []);
    setAiModels(extractData(models, { items: [] })?.items || []);
    setAiAccuracy(extractData(accuracy, { items: [] })?.items || []);
    setAiService(extractData(ping, null));
    setPermissions(extractData(perms, { items: [] })?.items || []);
    setUsers(extractData(userLogs, { items: [] })?.items || []);
    setContactMessages(extractData(msg, { items: [] })?.items || []);
    setHospitalSettings(extractData(settings, { items: [] })?.items || []);

    const failed = results
      .map((result, idx) => {
        const err = extractError(result);
        return err ? `${labels[idx]}: ${err}` : "";
      })
      .filter(Boolean);

    if (failed.length) {
      setStatusMsg(`Loaded with warnings. First issue: ${failed[0]}`);
    }
  };

  useEffect(() => {
    loadAll().catch((err) => {
      setStatusMsg(err?.response?.data?.detail || "Unable to load super admin controls");
    });
  }, []);

  const logout = () => {
    clearSession();
    navigate("/");
  };

  const forceLogoutAll = async () => {
    try {
      await api.post("/super-admin/security/force-logout-all");
      setStatusMsg("Force logout policy applied to all active sessions.");
    } catch (err) {
      setStatusMsg(err?.response?.data?.detail || "Unable to force logout all sessions.");
    }
  };

  const pauseSubscription = async (id) => {
    if (!id) return;
    try {
      await api.post(`/super-admin/subscriptions/${id}/pause`);
      await loadAll();
      setStatusMsg(`Subscription #${id} paused.`);
    } catch (err) {
      setStatusMsg(err?.response?.data?.detail || "Unable to pause subscription.");
    }
  };

  const resumeSubscription = async (id) => {
    if (!id) return;
    try {
      await api.post(`/super-admin/subscriptions/${id}/resume`);
      await loadAll();
      setStatusMsg(`Subscription #${id} resumed.`);
    } catch (err) {
      setStatusMsg(err?.response?.data?.detail || "Unable to resume subscription.");
    }
  };

  const activateModel = async (modelKey) => {
    try {
      await api.post("/super-admin/ai/models/activate", { model_key: modelKey });
      await loadAll();
      setStatusMsg(`Model ${modelKey} activated.`);
    } catch (err) {
      setStatusMsg(err?.response?.data?.detail || "Unable to activate model.");
    }
  };

  const restartAiService = async () => {
    try {
      await api.post("/super-admin/ai/service/restart");
      const ping = await api.get("/super-admin/ai/service/ping");
      setAiService(ping.data || null);
      setStatusMsg("AI service restart signal sent.");
    } catch (err) {
      setStatusMsg(err?.response?.data?.detail || "Unable to restart AI service.");
    }
  };

  const createSnapshot = async () => {
    try {
      const res = await api.post("/super-admin/database/snapshot");
      setSnapshotPath(res.data?.path || "");
      setStatusMsg("Database snapshot created.");
    } catch (err) {
      setStatusMsg(err?.response?.data?.detail || "Unable to create database snapshot.");
    }
  };

  const savePermission = async () => {
    try {
      await api.post("/super-admin/permissions/upsert", permissionForm);
      const perms = await api.get("/super-admin/permissions");
      setPermissions(perms.data?.items || []);
      setStatusMsg("Role access mapping saved.");
    } catch (err) {
      setStatusMsg(err?.response?.data?.detail || "Unable to save role permission mapping.");
    }
  };

  const updateDoctorFee = async () => {
    const amount = Number(pricingForm.doctor_consultation_fee);
    if (!pricingForm.doctor_consultation_fee || Number.isNaN(amount)) {
      setStatusMsg("Enter a valid doctor consultation fee.");
      return;
    }
    try {
      await api.post("/super-admin/pricing/global-update", {
        target: "doctor_consultation_fee",
        amount,
      });
      setStatusMsg("Global doctor consultation fee updated.");
    } catch (err) {
      setStatusMsg(err?.response?.data?.detail || "Unable to update doctor consultation fee.");
    }
  };

  const updateMedicinePrice = async () => {
    const amount = Number(pricingForm.medicine_unit_price);
    if (!pricingForm.medicine_unit_price || Number.isNaN(amount)) {
      setStatusMsg("Enter a valid medicine unit price.");
      return;
    }
    try {
      await api.post("/super-admin/pricing/global-update", {
        target: "medicine_unit_price",
        amount,
      });
      setStatusMsg("Global medicine unit price updated.");
    } catch (err) {
      setStatusMsg(err?.response?.data?.detail || "Unable to update medicine unit price.");
    }
  };

  const blockUser = async (id) => {
    try {
      await api.post(`/super-admin/staff/${id}/block`);
      await loadAll();
      setStatusMsg(`User ${id} blocked.`);
    } catch (err) {
      setStatusMsg(err?.response?.data?.detail || "Unable to block user.");
    }
  };

  const unblockUser = async (id) => {
    try {
      await api.post(`/super-admin/staff/${id}/unblock`);
      await loadAll();
      setStatusMsg(`User ${id} unblocked.`);
    } catch (err) {
      setStatusMsg(err?.response?.data?.detail || "Unable to unblock user.");
    }
  };

  return (
    <section className="px-4 py-10 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-7xl space-y-6">
        <header className="flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <div>
            <h1 className="text-3xl font-extrabold">Super Admin Control Center</h1>
            <p className="text-slate-600">Global System & Security Control</p>
            {statusMsg ? <p className="mt-2 text-sm text-cyan-700">{statusMsg}</p> : null}
          </div>
          <div className="flex flex-wrap gap-2">
            <Link to="/dashboard/super-admin/pricing" className="rounded-lg border px-4 py-2 text-sm font-semibold text-slate-700">
              Pricing Page Plans
            </Link>
            <Link to="/dashboard/super-admin/blocked" className="rounded-lg border px-4 py-2 text-sm font-semibold text-slate-700">
              Blocked Users
            </Link>
            <button onClick={forceLogoutAll} className="rounded-lg border px-4 py-2 text-sm font-semibold text-rose-700">Force Logout All</button>
            <button onClick={logout} className="rounded-lg border px-4 py-2 text-sm font-semibold text-slate-700">Logout</button>
          </div>
        </header>

        <div className="grid gap-5 md:grid-cols-4">
          <Metric title="Hospitals" value={overview?.hospitals ?? "-"} />
          <Metric title="Active Subscriptions" value={overview?.active_subscriptions ?? "-"} />
          <Metric title="Expiring in 30 days" value={overview?.expiring_in_30_days ?? "-"} />
          <Metric title="Low Stock Alerts" value={inventoryAlerts.length} />
        </div>

        <Panel title="Subscription Controls">
          <Table
            headers={["Hospital", "Code", "Plan", "Cycle", "Start Date", "End Date", "Suspend Date", "Status", "Action"]}
            rows={subs.map((s) => {
              const currentStatus = String(s.status || "").toUpperCase();
              return [
                s.hospital_name || "-",
                s.hospital_code || "-",
                s.plan_name || "No subscription",
                s.billing_cycle ? String(s.billing_cycle).toUpperCase() : "-",
                formatDate(s.started_at),
                formatDate(s.expires_at),
                formatDate(s.suspended_at),
                currentStatus || "-",
                s.subscription_id ? (
                  <div key={`sub-act-${s.subscription_id}`} className="flex gap-2">
                    <button
                      onClick={() => pauseSubscription(s.subscription_id)}
                      disabled={currentStatus !== "ACTIVE"}
                      className="rounded border px-2 py-1 disabled:opacity-50"
                    >
                      Pause
                    </button>
                    <button
                      onClick={() => resumeSubscription(s.subscription_id)}
                      disabled={currentStatus !== "PAUSED"}
                      className="rounded border px-2 py-1 disabled:opacity-50"
                    >
                      Resume
                    </button>
                  </div>
                ) : (
                  <span key={`sub-na-${s.hospital_id || s.hospital_code || "na"}`} className="text-xs text-slate-500">No subscription</span>
                ),
              ];
            })}
          />
        </Panel>

        <Panel title="AI & Model Governance">
          <div className="grid gap-4 md:grid-cols-3">
            <div className="rounded-xl border p-4">
              <p className="mb-2 font-bold">Model Selection</p>
              {aiModels.map((m) => (
                <button
                  key={m.model_key}
                  onClick={() => activateModel(m.model_key)}
                  className={`mb-2 block w-full rounded border px-3 py-2 text-left ${m.is_active ? "border-cyan-400 bg-cyan-50" : ""}`}
                >
                  {m.model_name} ({m.model_key}) {m.is_active ? "- Active" : ""}
                </button>
              ))}
            </div>
            <div className="rounded-xl border p-4">
              <p className="mb-2 font-bold">Accuracy Monitoring</p>
              {aiAccuracy.slice(0, 6).map((m) => (
                <p key={m.metric_id} className="text-sm">{m.model_key} | {m.metric_name}: <strong>{m.metric_value}</strong></p>
              ))}
            </div>
            <div className="rounded-xl border p-4">
              <p className="mb-2 font-bold">AI Service Control</p>
              <p className="mb-2 text-sm">Service: {aiService?.status || "unknown"}</p>
              <div className="flex gap-2">
                <button onClick={loadAll} className="rounded border px-3 py-2 text-sm">Ping</button>
                <button onClick={restartAiService} className="rounded border px-3 py-2 text-sm">Restart</button>
              </div>
            </div>
          </div>
        </Panel>

        <Panel title="Enterprise Financial Oversight">
          <div className="grid gap-4 md:grid-cols-2">
            <div className="rounded-xl border p-4">
              <p className="font-bold">Global Revenue</p>
              <p className="text-sm">Payments: {finance?.payments_collected ?? 0}</p>
              <p className="text-sm">Subscriptions: {finance?.subscriptions_collected ?? 0}</p>
              <p className="text-sm font-bold">Combined: {finance?.combined_total ?? 0}</p>
            </div>
            <div className="space-y-2 rounded-xl border p-4">
              <p className="font-bold">Pricing Control</p>
              <input
                value={pricingForm.doctor_consultation_fee}
                onChange={(e) => setPricingForm((p) => ({ ...p, doctor_consultation_fee: e.target.value }))}
                className="w-full rounded border px-3 py-2 text-sm"
                placeholder="Global doctor consultation fee"
              />
              <button onClick={updateDoctorFee} className="rounded border px-3 py-2 text-sm">Update Doctor Fee</button>
              <input
                value={pricingForm.medicine_unit_price}
                onChange={(e) => setPricingForm((p) => ({ ...p, medicine_unit_price: e.target.value }))}
                className="w-full rounded border px-3 py-2 text-sm"
                placeholder="Global medicine unit price"
              />
              <button onClick={updateMedicinePrice} className="rounded border px-3 py-2 text-sm">Update Medicine Price</button>
            </div>
          </div>
        </Panel>

        <Panel title="Infrastructure & Audit">
          <div className="grid gap-4 md:grid-cols-2">
            <div className="rounded-xl border p-4">
              <p className="mb-2 font-bold">Database Snapshots</p>
              <button onClick={createSnapshot} className="rounded border px-3 py-2 text-sm">Create Snapshot</button>
              {snapshotPath ? <p className="mt-2 break-all text-xs">{snapshotPath}</p> : null}
            </div>
            <div className="rounded-xl border p-4">
              <p className="mb-2 font-bold">Hospital Identity Settings</p>
              <p className="text-sm">Records: {hospitalSettings.length}</p>
            </div>
          </div>
          <div className="mt-4 grid gap-4 md:grid-cols-2">
            <div className="rounded-xl border p-4">
              <p className="mb-2 font-bold">Inventory Alerts (&lt;10)</p>
              {inventoryAlerts.slice(0, 8).map((a) => (
                <p key={a.batch_id} className="text-sm">Hospital {a.hospital_id}: {a.medicine_name} ({a.quantity})</p>
              ))}
            </div>
            <div className="rounded-xl border p-4">
              <p className="mb-2 font-bold">Public Contact Messages</p>
              {contactMessages.slice(0, 8).map((m) => (
                <p key={m.contact_message_id} className="text-sm">{m.name}: {m.subject || "No subject"}</p>
              ))}
            </div>
          </div>
        </Panel>

        <Panel title="User Lifecycle & Access Levels">
          <div className="mb-4 grid gap-4 md:grid-cols-2">
            <div className="space-y-2 rounded-xl border p-4">
              <p className="font-bold">Role Permission Mapping</p>
              <input
                value={permissionForm.source_role}
                onChange={(e) => setPermissionForm((p) => ({ ...p, source_role: e.target.value.toUpperCase() }))}
                className="w-full rounded border px-3 py-2 text-sm"
                placeholder="Source role (e.g. DOCTOR)"
              />
              <input
                value={permissionForm.target_module}
                onChange={(e) => setPermissionForm((p) => ({ ...p, target_module: e.target.value.toUpperCase() }))}
                className="w-full rounded border px-3 py-2 text-sm"
                placeholder="Target module (e.g. PHARMACY_STOCK)"
              />
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={permissionForm.can_view}
                  onChange={(e) => setPermissionForm((p) => ({ ...p, can_view: e.target.checked }))}
                />
                Can View
              </label>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={permissionForm.can_edit}
                  onChange={(e) => setPermissionForm((p) => ({ ...p, can_edit: e.target.checked }))}
                />
                Can Edit
              </label>
              <button onClick={savePermission} className="rounded border px-3 py-2 text-sm">Save Permission</button>
            </div>
            <div className="overflow-auto rounded-xl border p-4">
              <p className="mb-2 font-bold">Current Permission Matrix</p>
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
      <p className="text-xs font-bold uppercase tracking-[0.14em] text-slate-500">{title}</p>
      <p className="mt-2 text-3xl font-extrabold">{value}</p>
    </div>
  );
}

function Panel({ title, children }) {
  return (
    <div className="overflow-auto rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
      <h2 className="mb-4 text-xl font-bold">{title}</h2>
      {children}
    </div>
  );
}

function Table({ headers, rows }) {
  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="border-b text-left text-slate-500">
          {headers.map((h) => (
            <th key={h} className="py-2 pr-3">{h}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.length === 0 ? (
          <tr>
            <td className="py-3 text-slate-500" colSpan={headers.length}>No records found.</td>
          </tr>
        ) : rows.map((r, i) => (
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
