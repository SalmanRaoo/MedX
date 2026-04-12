import { useEffect, useState } from "react";
import Sidebar from "../components/Sidebar";
import { api } from "../lib/api";

function isMedxSuperAdmin(row) {
  const role = String(row?.role || row?.role_name || "").toUpperCase();
  const email = String(row?.email || "").toLowerCase();
  const name = String(row?.full_name || "").toLowerCase();
  return role === "SUPER_ADMIN" || email === "superadmin@medx.local" || name.includes("medx super admin");
}

function formatAccessAction(actionType) {
  const key = String(actionType || "").toUpperCase();
  if (key === "FORCE_LOGOUT") return "FORCE LOGOUT";
  if (key === "BLOCK_PERMANENT") return "BLOCK PERMANENT";
  if (key === "UNBLOCK") return "UNBLOCK";
  if (key.startsWith("UNBLOCK_")) return key.replaceAll("_", " ");
  return key || "-";
}

export default function AdminUserAccessPage() {
  const [staff, setStaff] = useState([]);
  const [blocked, setBlocked] = useState([]);
  const [events, setEvents] = useState([]);
  const [status, setStatus] = useState("");
  const [busyUserId, setBusyUserId] = useState(null);

  const load = async () => {
    try {
      const [staffRes, blockedRes, eventRes] = await Promise.all([
        api.get("/staff/"),
        api.get("/admin/users/blocked"),
        api.get("/admin/users/access-events"),
      ]);
      const staffItems = staffRes.data?.items || [];
      const blockedItems = blockedRes.data?.items || [];
      const hiddenUserIds = new Set(
        [...staffItems, ...blockedItems]
          .filter((item) => isMedxSuperAdmin(item))
          .map((item) => item.user_id)
          .filter((id) => !!id)
      );

      setStaff(staffItems.filter((item) => !isMedxSuperAdmin(item) && !hiddenUserIds.has(item.user_id)));
      setBlocked(blockedItems.filter((item) => !isMedxSuperAdmin(item) && !hiddenUserIds.has(item.user_id)));
      setEvents(
        (eventRes.data?.items || []).filter(
          (item) => !hiddenUserIds.has(item.target_user_id) && !hiddenUserIds.has(item.actor_user_id)
        )
      );
    } catch (err) {
      setStatus(err?.response?.data?.detail || "Unable to load user access control data");
    }
  };

  useEffect(() => {
    load();
  }, []);

  const forceLogout = async (userId) => {
    setBusyUserId(userId);
    try {
      await api.post(`/admin/users/${userId}/force-logout`, { reason: "Admin manual logout" });
      setStatus(`User ${userId} logged out.`);
      await load();
    } finally {
      setBusyUserId(null);
    }
  };

  const blockUser = async (userId) => {
    setBusyUserId(userId);
    try {
      await api.post(`/admin/users/${userId}/block-permanent`, { reason: "Admin permanent block" });
      setStatus(`User ${userId} blocked.`);
      await load();
    } finally {
      setBusyUserId(null);
    }
  };

  const unblockUser = async (userId) => {
    setBusyUserId(userId);
    try {
      await api.post(`/admin/users/${userId}/unblock`, { reason: "Admin unblock" });
      setStatus(`User ${userId} unblocked.`);
      await load();
    } finally {
      setBusyUserId(null);
    }
  };

  return (
    <div className="flex h-screen bg-slate-50 overflow-hidden font-sans">
      <Sidebar />
      <div className="flex-1 overflow-y-auto p-8 space-y-6">
        <header className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h1 className="text-3xl font-extrabold">User Access Control</h1>
          <p className="text-slate-600">Force logout, permanently block, and unblock hospital users.</p>
          {status ? <p className="text-sm text-cyan-700 mt-2">{status}</p> : null}
        </header>

        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm overflow-auto">
          <h2 className="text-xl font-bold mb-3">Staff Actions</h2>
          <table className="w-full text-sm">
            <thead><tr className="text-left text-slate-500"><th>Name</th><th>Role</th><th>User ID</th><th>Action</th></tr></thead>
            <tbody>
              {staff.map((s) => (
                <tr key={s.staff_id} className="border-t">
                  <td className="py-2">{s.full_name}</td>
                  <td>{s.role}</td>
                  <td>{s.user_id || "-"}</td>
                  <td>
                    {s.user_id ? (
                      <div className="flex gap-2">
                        <button
                          onClick={() => forceLogout(s.user_id)}
                          disabled={busyUserId === s.user_id}
                          className="rounded border px-2 py-1 disabled:opacity-60"
                        >
                          Logout
                        </button>
                        <button
                          onClick={() => blockUser(s.user_id)}
                          disabled={busyUserId === s.user_id}
                          className="rounded border px-2 py-1 text-rose-700 disabled:opacity-60"
                        >
                          Block Permanent
                        </button>
                      </div>
                    ) : "-"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm overflow-auto">
          <h2 className="text-xl font-bold mb-3">Blocked Users</h2>
          <table className="w-full text-sm">
            <thead><tr className="text-left text-slate-500"><th>User ID</th><th>Email</th><th>Status</th><th>Action</th></tr></thead>
            <tbody>
              {blocked.length === 0 ? (
                <tr className="border-t">
                  <td className="py-3 text-slate-500" colSpan={4}>No blocked users in this hospital.</td>
                </tr>
              ) : blocked.map((b) => (
                <tr key={`${b.user_id}-${b.hospital_id}`} className="border-t">
                  <td className="py-2">{b.user_id}</td>
                  <td>{b.email}</td>
                  <td>{b.is_active === 0 ? "BLOCKED" : "ACTIVE"}</td>
                  <td>
                    <button
                      onClick={() => unblockUser(b.user_id)}
                      disabled={busyUserId === b.user_id}
                      className="rounded border px-2 py-1 disabled:opacity-60"
                    >
                      Unblock User
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm overflow-auto">
          <h2 className="text-xl font-bold mb-3">Access Action History</h2>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-slate-500">
                <th>When</th>
                <th>Action</th>
                <th>Logged Out / Target User</th>
                <th>Performed By</th>
                <th>Reason</th>
              </tr>
            </thead>
            <tbody>
              {events.length === 0 ? (
                <tr className="border-t">
                  <td className="py-3 text-slate-500" colSpan={5}>No access actions recorded yet.</td>
                </tr>
              ) : events.map((e) => (
                <tr key={e.action_id} className="border-t">
                  <td className="py-2">{e.created_at}</td>
                  <td>{formatAccessAction(e.action_type)}</td>
                  <td>
                    <p className="font-medium text-slate-800">{e.target_email || "-"}</p>
                    <p className="text-xs text-slate-500">User ID: {e.target_user_id || "-"}</p>
                  </td>
                  <td>
                    <p className="font-medium text-slate-800">{e.actor_email || "-"}</p>
                    <p className="text-xs text-slate-500">User ID: {e.actor_user_id || "-"}</p>
                  </td>
                  <td>{e.reason || "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      </div>
    </div>
  );
}
