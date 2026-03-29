import { useEffect, useState } from "react";
import Sidebar from "../components/Sidebar";
import { api } from "../lib/api";

export default function AdminUserAccessPage() {
  const [staff, setStaff] = useState([]);
  const [blocked, setBlocked] = useState([]);
  const [events, setEvents] = useState([]);
  const [status, setStatus] = useState("");

  const load = async () => {
    try {
      const [staffRes, blockedRes, eventRes] = await Promise.all([
        api.get("/staff/"),
        api.get("/admin/users/blocked"),
        api.get("/admin/users/access-events"),
      ]);
      setStaff(staffRes.data?.items || []);
      setBlocked(blockedRes.data?.items || []);
      setEvents(eventRes.data?.items || []);
    } catch (err) {
      setStatus(err?.response?.data?.detail || "Unable to load user access control data");
    }
  };

  useEffect(() => {
    load();
  }, []);

  const forceLogout = async (userId) => {
    await api.post(`/admin/users/${userId}/force-logout`, { reason: "Admin manual logout" });
    setStatus(`User ${userId} logged out.`);
    await load();
  };

  const blockUser = async (userId) => {
    await api.post(`/admin/users/${userId}/block-permanent`, { reason: "Admin permanent block" });
    setStatus(`User ${userId} blocked.`);
    await load();
  };

  const unblockUser = async (userId) => {
    await api.post(`/admin/users/${userId}/unblock`, { reason: "Admin unblock" });
    setStatus(`User ${userId} unblocked.`);
    await load();
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
                        <button onClick={() => forceLogout(s.user_id)} className="rounded border px-2 py-1">Logout</button>
                        <button onClick={() => blockUser(s.user_id)} className="rounded border px-2 py-1 text-rose-700">Block Permanent</button>
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
              {blocked.map((b) => (
                <tr key={`${b.user_id}-${b.hospital_id}`} className="border-t">
                  <td className="py-2">{b.user_id}</td>
                  <td>{b.email}</td>
                  <td>{b.is_active === 0 ? "BLOCKED" : "ACTIVE"}</td>
                  <td><button onClick={() => unblockUser(b.user_id)} className="rounded border px-2 py-1">Unblock</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm overflow-auto">
          <h2 className="text-xl font-bold mb-3">Access Action History</h2>
          <table className="w-full text-sm">
            <thead><tr className="text-left text-slate-500"><th>When</th><th>Action</th><th>Target User</th><th>Reason</th></tr></thead>
            <tbody>
              {events.map((e) => (
                <tr key={e.action_id} className="border-t">
                  <td className="py-2">{e.created_at}</td>
                  <td>{e.action_type}</td>
                  <td>{e.target_user_id}</td>
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
