import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import Sidebar from "../components/Sidebar";
import { api } from "../lib/api";

export default function StaffHistoryPage() {
  const { staffId } = useParams();
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .get(`/admin/staff/${staffId}/history`)
      .then((res) => setData(res.data))
      .catch((err) => setError(err?.response?.data?.detail || "Unable to load staff history"));
  }, [staffId]);

  const sections = data?.history || {};

  return (
    <div className="flex h-screen bg-slate-50 overflow-hidden font-sans">
      <Sidebar />
      <div className="flex-1 overflow-y-auto p-8 space-y-6">
        <header className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm flex justify-between items-center">
          <div>
            <h1 className="text-3xl font-extrabold">Staff Full History</h1>
            <p className="text-slate-600">All previous activity and records for this staff member.</p>
            {data?.staff ? <p className="text-sm text-cyan-700 mt-2">{data.staff.full_name} ({data.staff.role})</p> : null}
            {error ? <p className="text-sm text-rose-700 mt-2">{error}</p> : null}
          </div>
          <Link to="/dashboard/staff-patients" className="rounded-lg border px-4 py-2 text-sm font-semibold text-slate-700">Back</Link>
        </header>

        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm overflow-auto">
          <h2 className="text-xl font-bold mb-3">User Account</h2>
          <pre className="text-xs bg-slate-50 border rounded-xl p-4 overflow-auto">{JSON.stringify(data?.user || {}, null, 2)}</pre>
        </section>

        {Object.keys(sections).map((key) => (
          <section key={key} className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm overflow-auto">
            <h2 className="text-xl font-bold mb-3">{formatTitle(key)} ({(sections[key] || []).length})</h2>
            <pre className="text-xs bg-slate-50 border rounded-xl p-4 overflow-auto">{JSON.stringify(sections[key] || [], null, 2)}</pre>
          </section>
        ))}
      </div>
    </div>
  );
}

function formatTitle(key) {
  return key.replace(/_/g, " ").replace(/\b\w/g, (m) => m.toUpperCase());
}
