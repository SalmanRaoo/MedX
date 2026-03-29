import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../lib/api";

export default function SuperAdminBlockedUsersPage() {
  const [blocked, setBlocked] = useState([]);
  const [msg, setMsg] = useState("");

  const load = async () => {
    try {
      const res = await api.get("/super-admin/users/blocked");
      setBlocked(res.data?.items || []);
    } catch (err) {
      setMsg(err?.response?.data?.detail || "Unable to load blocked users");
    }
  };

  useEffect(() => {
    load();
  }, []);

  const unblock = async (id) => {
    await api.post(`/super-admin/users/${id}/unblock`, { reason: "Super admin unblock" });
    setMsg(`User ${id} unblocked`);
    await load();
  };

  return (
    <section className="px-4 py-10 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-7xl space-y-6">
        <header className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm flex items-center justify-between gap-2">
          <div>
            <h1 className="text-3xl font-extrabold">Blocked Users (Global)</h1>
            <p className="text-slate-600">Super admin unblock panel across all hospitals.</p>
            {msg ? <p className="text-sm text-cyan-700 mt-2">{msg}</p> : null}
          </div>
          <Link to="/dashboard/super-admin" className="rounded-lg border px-4 py-2 text-sm font-semibold text-slate-700">Back</Link>
        </header>

        <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm overflow-auto">
          <table className="w-full text-sm">
            <thead><tr className="text-left text-slate-500"><th>User ID</th><th>Email</th><th>Hospital</th><th>Status</th><th>Action</th></tr></thead>
            <tbody>
              {blocked.map((u) => (
                <tr key={`${u.user_id}-${u.hospital_id}`} className="border-t">
                  <td className="py-2">{u.user_id}</td>
                  <td>{u.email}</td>
                  <td>{u.hospital_name || `#${u.hospital_id}`}</td>
                  <td>{u.is_active === 0 ? "BLOCKED" : "ACTIVE"}</td>
                  <td><button onClick={() => unblock(u.user_id)} className="rounded border px-2 py-1">Unblock</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}
