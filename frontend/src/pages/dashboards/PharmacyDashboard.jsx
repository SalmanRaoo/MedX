import { useEffect, useState } from "react";
import RoleDashboardShell from "../../components/dashboards/RoleDashboardShell";
import { api } from "../../lib/api";

export default function PharmacyDashboard() {
  const [queue, setQueue] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    const loadQueue = async () => {
      try {
        const res = await api.get("/pharmacy/medication-queue", { params: { limit: 200 } });
        if (!active) return;
        setQueue(res.data.items || []);
      } catch (err) {
        if (!active) return;
        setError(err?.response?.data?.detail || "Unable to load medication queue");
      } finally {
        if (active) setLoading(false);
      }
    };
    loadQueue();
    return () => {
      active = false;
    };
  }, []);

  return (
    <>
      <RoleDashboardShell
        title="Pharmacy Dashboard"
        subtitle="Medication orders sent by doctors."
        cards={[
          { title: "Total Queue", text: String(queue.length) },
          { title: "Pending Orders", text: String(queue.filter((q) => q.pharmacy_status === "PENDING").length) },
          { title: "Last Sync", text: loading ? "Loading..." : "Live" },
        ]}
      />

      <section className="px-4 pb-10 sm:px-6 lg:px-8 -mt-2">
        <div className="mx-auto max-w-7xl rounded-2xl border border-slate-200 bg-white p-5 shadow-sm overflow-x-auto">
          <h3 className="text-lg font-bold mb-3">Medication Queue</h3>
          {error ? <p className="text-sm text-rose-700">{error}</p> : null}
          {!error && queue.length === 0 && !loading ? <p className="text-sm text-slate-600">No medication orders yet.</p> : null}
          {queue.length > 0 ? (
            <table className="min-w-full text-sm">
              <thead className="text-left text-slate-500">
                <tr>
                  <th className="py-2 pr-3">Patient</th>
                  <th className="py-2 pr-3">Medication</th>
                  <th className="py-2 pr-3">Dosage</th>
                  <th className="py-2 pr-3">Frequency</th>
                  <th className="py-2 pr-3">Status</th>
                </tr>
              </thead>
              <tbody>
                {queue.map((row) => (
                  <tr key={row.medication_order_id} className="border-t border-slate-100">
                    <td className="py-2 pr-3">{row.patient_name || row.patient_id}</td>
                    <td className="py-2 pr-3">{row.medication_name}</td>
                    <td className="py-2 pr-3">{row.dosage || "-"}</td>
                    <td className="py-2 pr-3">{row.frequency || "-"}</td>
                    <td className="py-2 pr-3">{row.pharmacy_status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : null}
        </div>
      </section>
    </>
  );
}
