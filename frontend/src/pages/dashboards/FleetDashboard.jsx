import { useEffect, useMemo, useState } from "react";
import { Activity, Clock3, Droplets, Loader2, MapPin, PlusCircle, Truck, UserRound } from "lucide-react";
import { api } from "../../lib/api";
import FleetWorkspaceLayout from "../../components/dashboards/FleetWorkspaceLayout";

const STATUS_OPTIONS = [
  { code: "FREE", label: "Free", badge: "bg-emerald-100 text-emerald-700 border-emerald-200" },
  { code: "ON_MISSION", label: "On Trip", badge: "bg-rose-100 text-rose-700 border-rose-200" },
  { code: "IN_MAINTENANCE", label: "Maintenance", badge: "bg-amber-100 text-amber-700 border-amber-200" },
];

function money(v) {
  return `PKR ${Number(v || 0).toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
}

function badgeClassFor(status) {
  return STATUS_OPTIONS.find((s) => s.code === status)?.badge || "bg-slate-100 text-slate-700 border-slate-200";
}

function labelFor(status) {
  return STATUS_OPTIONS.find((s) => s.code === status)?.label || String(status || "Unknown");
}

function StatCard({ title, value, icon, subValue }) {
  const Icon = icon;
  return (
    <article className="rounded-[32px] border border-slate-200 bg-white p-6 shadow-sm">
      <div className="inline-flex rounded-2xl bg-teal-50 p-3 text-teal-700"><Icon className="h-5 w-5" /></div>
      <p className="mt-3 text-xs font-bold uppercase tracking-[0.12em] text-slate-500">{title}</p>
      <p className="mt-1 text-2xl font-black tracking-tight">{value}</p>
      {subValue ? <p className="mt-1 text-xs text-slate-500">{subValue}</p> : null}
    </article>
  );
}

export default function FleetDashboard() {
  const [vehicles, setVehicles] = useState([]);
  const [statusCounts, setStatusCounts] = useState({ FREE: 0, ON_MISSION: 0, IN_MAINTENANCE: 0 });
  const [summary, setSummary] = useState({ total_trips: 0, total_fuel_cost: 0, total_fuel_liters: 0 });
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [loading, setLoading] = useState(false);
  const [savingVehicle, setSavingVehicle] = useState(false);
  const [updatingFleetId, setUpdatingFleetId] = useState(null);
  const [savingTripId, setSavingTripId] = useState(null);
  const [savingFuelId, setSavingFuelId] = useState(null);
  const [historyLoadingId, setHistoryLoadingId] = useState(null);
  const [registerModalOpen, setRegisterModalOpen] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [registerForm, setRegisterForm] = useState({
    plate_number: "",
    vehicle_type: "AMBULANCE",
    model_name: "",
    assigned_driver: "",
    mission_patient_name: "",
    status: "FREE",
    destination: "",
    eta_return: "",
    notes: "",
  });
  const [drafts, setDrafts] = useState({});
  const [tripDrafts, setTripDrafts] = useState({});
  const [fuelDrafts, setFuelDrafts] = useState({});
  const [historyByFleet, setHistoryByFleet] = useState({});
  const [expandedHistory, setExpandedHistory] = useState({});

  const loadVehicles = async () => {
    setLoading(true);
    setError("");
    try {
      const { data } = await api.get("/fleet/vehicles", { params: { limit: 500 } });
      const items = data?.items || [];
      setVehicles(items);
      setStatusCounts(data?.status_counts || { FREE: 0, ON_MISSION: 0, IN_MAINTENANCE: 0 });
      setSummary(data?.summary || { total_trips: 0, total_fuel_cost: 0, total_fuel_liters: 0 });
      const nextDrafts = {};
      const nextTrips = {};
      const nextFuel = {};
      items.forEach((v) => {
        nextDrafts[v.fleet_id] = {
          status: v.status || "FREE",
          destination: v.destination || "",
          eta_return: v.eta_return || "",
          assigned_driver: v.assigned_driver || "",
          mission_patient_name: v.mission_patient_name || "",
          notes: v.notes || "",
        };
        nextTrips[v.fleet_id] = {
          destination: v.destination || "",
          patient_name: v.mission_patient_name || "",
          assigned_driver: v.assigned_driver || "",
          trip_status: "COMPLETED",
          notes: "",
        };
        nextFuel[v.fleet_id] = {
          liters: "",
          cost_amount: "",
          notes: "",
        };
      });
      setDrafts(nextDrafts);
      setTripDrafts(nextTrips);
      setFuelDrafts(nextFuel);
    } catch (err) {
      setError(err?.response?.data?.detail || "Unable to load fleet vehicles.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadVehicles();
  }, []);

  const filteredVehicles = useMemo(() => {
    if (statusFilter === "ALL") return vehicles;
    return vehicles.filter((v) => String(v.status || "").toUpperCase() === statusFilter);
  }, [statusFilter, vehicles]);

  const updateDraft = (fleetId, key, value) => {
    setDrafts((prev) => ({
      ...prev,
      [fleetId]: {
        ...(prev[fleetId] || {}),
        [key]: value,
      },
    }));
  };

  const updateTripDraft = (fleetId, key, value) => {
    setTripDrafts((prev) => ({
      ...prev,
      [fleetId]: {
        ...(prev[fleetId] || {}),
        [key]: value,
      },
    }));
  };

  const updateFuelDraft = (fleetId, key, value) => {
    setFuelDrafts((prev) => ({
      ...prev,
      [fleetId]: {
        ...(prev[fleetId] || {}),
        [key]: value,
      },
    }));
  };

  const onRegisterVehicle = async (e) => {
    e.preventDefault();
    setSavingVehicle(true);
    setError("");
    setSuccess("");
    try {
      await api.post("/fleet/vehicles", {
        plate_number: registerForm.plate_number,
        vehicle_type: registerForm.vehicle_type,
        model_name: registerForm.model_name || null,
        assigned_driver: registerForm.assigned_driver || null,
        mission_patient_name: registerForm.mission_patient_name || null,
        status: registerForm.status,
        destination: registerForm.destination || null,
        eta_return: registerForm.eta_return || null,
        notes: registerForm.notes || null,
      });
      setRegisterForm({
        plate_number: "",
        vehicle_type: "AMBULANCE",
        model_name: "",
        assigned_driver: "",
        mission_patient_name: "",
        status: "FREE",
        destination: "",
        eta_return: "",
        notes: "",
      });
      setRegisterModalOpen(false);
      setSuccess("Vehicle registered in fleet.");
      await loadVehicles();
    } catch (err) {
      setError(err?.response?.data?.detail || "Unable to register new vehicle.");
    } finally {
      setSavingVehicle(false);
    }
  };

  const onUpdateVehicle = async (fleetId) => {
    const draft = drafts[fleetId];
    if (!draft) return;
    setUpdatingFleetId(fleetId);
    setError("");
    setSuccess("");
    try {
      await api.post(`/fleet/vehicles/${fleetId}/status`, {
        status: draft.status,
        destination: draft.destination || null,
        eta_return: draft.eta_return || null,
        assigned_driver: draft.assigned_driver || null,
        mission_patient_name: draft.mission_patient_name || null,
        notes: draft.notes || null,
      });
      setSuccess(`Fleet #${fleetId} updated.`);
      await loadVehicles();
    } catch (err) {
      setError(err?.response?.data?.detail || "Unable to update fleet status.");
    } finally {
      setUpdatingFleetId(null);
    }
  };

  const onLogTrip = async (fleetId) => {
    const draft = tripDrafts[fleetId] || {};
    setSavingTripId(fleetId);
    setError("");
    try {
      await api.post(`/fleet/vehicles/${fleetId}/trips`, {
        destination: draft.destination || null,
        patient_name: draft.patient_name || null,
        assigned_driver: draft.assigned_driver || null,
        trip_status: draft.trip_status || "COMPLETED",
        notes: draft.notes || null,
      });
      setSuccess(`Trip logged for vehicle #${fleetId}.`);
      await Promise.all([loadVehicles(), loadHistory(fleetId)]);
    } catch (err) {
      setError(err?.response?.data?.detail || "Unable to log trip.");
    } finally {
      setSavingTripId(null);
    }
  };

  const onLogFuel = async (fleetId) => {
    const draft = fuelDrafts[fleetId] || {};
    setSavingFuelId(fleetId);
    setError("");
    try {
      await api.post(`/fleet/vehicles/${fleetId}/fuel-logs`, {
        liters: Number(draft.liters || 0),
        cost_amount: Number(draft.cost_amount || 0),
        notes: draft.notes || null,
      });
      setFuelDrafts((prev) => ({
        ...prev,
        [fleetId]: { liters: "", cost_amount: "", notes: "" },
      }));
      setSuccess(`Fuel log saved and synced to Accounts for vehicle #${fleetId}.`);
      await Promise.all([loadVehicles(), loadHistory(fleetId)]);
    } catch (err) {
      setError(err?.response?.data?.detail || "Unable to log fuel.");
    } finally {
      setSavingFuelId(null);
    }
  };

  const loadHistory = async (fleetId) => {
    setHistoryLoadingId(fleetId);
    try {
      const { data } = await api.get(`/fleet/vehicles/${fleetId}/history`, {
        params: { trip_limit: 10, fuel_limit: 10 },
      });
      setHistoryByFleet((prev) => ({ ...prev, [fleetId]: data || { trips: [], fuel_logs: [] } }));
    } catch {
      setHistoryByFleet((prev) => ({ ...prev, [fleetId]: { trips: [], fuel_logs: [] } }));
    } finally {
      setHistoryLoadingId(null);
    }
  };

  const toggleHistory = async (fleetId) => {
    const nextOpen = !expandedHistory[fleetId];
    setExpandedHistory((prev) => ({ ...prev, [fleetId]: nextOpen }));
    if (nextOpen && !historyByFleet[fleetId]) {
      await loadHistory(fleetId);
    }
  };

  return (
    <FleetWorkspaceLayout
      title="Ambulance & Fleet Hub"
      subtitle="Dedicated fleet command for mission dispatch, fuel tracking, and live sync to Accounts expenses."
    >
      {error ? <p className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</p> : null}
      {success ? <p className="mt-3 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{success}</p> : null}

      <section className="mt-4 grid gap-4 md:grid-cols-4">
        <StatCard title="Total Vehicles" value={vehicles.length} icon={Truck} />
        <StatCard title="Free" value={statusCounts.FREE || 0} icon={Activity} />
        <StatCard title="On Trip" value={statusCounts.ON_MISSION || 0} icon={MapPin} />
        <StatCard title="Fuel Cost Logged" value={money(summary.total_fuel_cost)} icon={Droplets} subValue={`${Number(summary.total_fuel_liters || 0).toFixed(1)} L`} />
      </section>

      <section className="mt-5 flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          {["ALL", ...STATUS_OPTIONS.map((s) => s.code)].map((status) => (
            <button
              key={status}
              type="button"
              onClick={() => setStatusFilter(status)}
              className={`rounded-xl px-4 py-2 text-sm font-semibold ${
                statusFilter === status
                  ? "bg-teal-700 text-white"
                  : "border border-slate-300 bg-white text-slate-700 hover:bg-slate-50"
              }`}
            >
              {status === "ALL" ? "All Vehicles" : labelFor(status)}
            </button>
          ))}
        </div>

        <button
          type="button"
          onClick={() => setRegisterModalOpen(true)}
          className="inline-flex items-center gap-2 rounded-xl bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-teal-700"
        >
          <PlusCircle className="h-4 w-4" /> Register New Vehicle
        </button>
      </section>

      <section className="mt-5">
        {loading ? (
          <div className="rounded-[32px] border border-slate-200 bg-white p-10 text-center">
            <Loader2 className="mx-auto h-6 w-6 animate-spin text-teal-700" />
            <p className="mt-2 text-sm text-slate-600">Loading fleet monitor...</p>
          </div>
        ) : filteredVehicles.length === 0 ? (
          <div className="rounded-[32px] border border-slate-200 bg-white p-10 text-center text-slate-600">
            No vehicles found for this status filter.
          </div>
        ) : (
          <div className="grid gap-4 md:grid-cols-2">
            {filteredVehicles.map((vehicle) => {
              const draft = drafts[vehicle.fleet_id] || {};
              const trip = tripDrafts[vehicle.fleet_id] || {};
              const fuel = fuelDrafts[vehicle.fleet_id] || {};
              const nextStatus = draft.status || vehicle.status || "FREE";
              const isMission = nextStatus === "ON_MISSION";
              const history = historyByFleet[vehicle.fleet_id] || { trips: [], fuel_logs: [] };
              const open = !!expandedHistory[vehicle.fleet_id];
              const metrics = vehicle.metrics || {};
              return (
                <article key={vehicle.fleet_id} className="rounded-[32px] border border-slate-200 bg-white p-5 shadow-sm">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-lg font-black tracking-tight">{vehicle.plate_number}</p>
                      <p className="text-sm text-slate-600">
                        {String(vehicle.vehicle_type || "-").replaceAll("_", " ")}{vehicle.model_name ? ` | ${vehicle.model_name}` : ""}
                      </p>
                    </div>
                    <span className={`rounded-full border px-3 py-1 text-xs font-bold ${badgeClassFor(vehicle.status)}`}>
                      {labelFor(vehicle.status)}
                    </span>
                  </div>

                  <div className="mt-4 grid gap-2 text-sm text-slate-700 sm:grid-cols-2">
                    <p className="flex items-center gap-2"><UserRound className="h-4 w-4 text-slate-500" /> Driver: {vehicle.assigned_driver || "-"}</p>
                    <p className="flex items-center gap-2"><UserRound className="h-4 w-4 text-slate-500" /> Patient: {vehicle.mission_patient_name || "-"}</p>
                    <p className="flex items-center gap-2"><MapPin className="h-4 w-4 text-slate-500" /> Destination: {vehicle.destination || "-"}</p>
                    <p className="flex items-center gap-2"><Clock3 className="h-4 w-4 text-slate-500" /> ETA Return: {vehicle.eta_return || "-"}</p>
                  </div>

                  <div className="mt-3 rounded-xl border border-slate-200 bg-slate-50 p-3 text-xs text-slate-700">
                    <p><span className="font-bold">Trips:</span> {metrics.total_trips || 0}</p>
                    <p><span className="font-bold">Fuel:</span> {Number(metrics.total_fuel_liters || 0).toFixed(1)} L | {money(metrics.total_fuel_cost || 0)}</p>
                    {vehicle.last_trip ? (
                      <p><span className="font-bold">Last Trip:</span> {vehicle.last_trip.destination || "-"} ({vehicle.last_trip.trip_status || "-"})</p>
                    ) : (
                      <p><span className="font-bold">Last Trip:</span> -</p>
                    )}
                  </div>

                  <div className="mt-4 space-y-2 border-t border-slate-200 pt-4">
                    <p className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Mission Status</p>
                    <div className="grid gap-2 sm:grid-cols-2">
                      <select
                        value={nextStatus}
                        onChange={(e) => updateDraft(vehicle.fleet_id, "status", e.target.value)}
                        className="rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-teal-500"
                      >
                        {STATUS_OPTIONS.map((s) => (
                          <option key={s.code} value={s.code}>{s.label}</option>
                        ))}
                      </select>
                      <input
                        value={draft.assigned_driver || ""}
                        onChange={(e) => updateDraft(vehicle.fleet_id, "assigned_driver", e.target.value)}
                        placeholder="Assigned driver"
                        className="rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-teal-500"
                      />
                      <input
                        value={draft.mission_patient_name || ""}
                        onChange={(e) => updateDraft(vehicle.fleet_id, "mission_patient_name", e.target.value)}
                        placeholder="Patient name on mission"
                        className="rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-teal-500"
                      />
                      <input
                        value={draft.destination || ""}
                        onChange={(e) => updateDraft(vehicle.fleet_id, "destination", e.target.value)}
                        placeholder={isMission ? "Mission destination" : "Destination (optional)"}
                        className="rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-teal-500"
                      />
                      <input
                        value={draft.eta_return || ""}
                        onChange={(e) => updateDraft(vehicle.fleet_id, "eta_return", e.target.value)}
                        placeholder="ETA return"
                        className="rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-teal-500"
                      />
                      <input
                        value={draft.notes || ""}
                        onChange={(e) => updateDraft(vehicle.fleet_id, "notes", e.target.value)}
                        placeholder="Status notes"
                        className="rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-teal-500"
                      />
                    </div>
                    <button
                      type="button"
                      onClick={() => onUpdateVehicle(vehicle.fleet_id)}
                      disabled={updatingFleetId === vehicle.fleet_id}
                      className="w-full rounded-xl bg-teal-700 px-4 py-2 text-sm font-semibold text-white hover:bg-teal-800 disabled:opacity-60"
                    >
                      {updatingFleetId === vehicle.fleet_id ? "Updating..." : "Save Mission Update"}
                    </button>
                  </div>

                  <div className="mt-4 grid gap-3 border-t border-slate-200 pt-4 lg:grid-cols-2">
                    <div className="rounded-xl border border-slate-200 p-3">
                      <p className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Log Trip</p>
                      <div className="mt-2 space-y-2">
                        <input
                          value={trip.destination || ""}
                          onChange={(e) => updateTripDraft(vehicle.fleet_id, "destination", e.target.value)}
                          placeholder="Destination"
                          className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-teal-500"
                        />
                        <input
                          value={trip.patient_name || ""}
                          onChange={(e) => updateTripDraft(vehicle.fleet_id, "patient_name", e.target.value)}
                          placeholder="Patient name"
                          className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-teal-500"
                        />
                        <select
                          value={trip.trip_status || "COMPLETED"}
                          onChange={(e) => updateTripDraft(vehicle.fleet_id, "trip_status", e.target.value)}
                          className="w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-teal-500"
                        >
                          <option value="ONGOING">Ongoing</option>
                          <option value="COMPLETED">Completed</option>
                          <option value="CANCELLED">Cancelled</option>
                        </select>
                        <button
                          type="button"
                          onClick={() => onLogTrip(vehicle.fleet_id)}
                          disabled={savingTripId === vehicle.fleet_id}
                          className="w-full rounded-xl border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-60"
                        >
                          {savingTripId === vehicle.fleet_id ? "Logging..." : "Save Trip Log"}
                        </button>
                      </div>
                    </div>

                    <div className="rounded-xl border border-slate-200 p-3">
                      <p className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Log Fuel (Syncs to Accounts)</p>
                      <div className="mt-2 space-y-2">
                        <input
                          type="number"
                          min="0"
                          step="0.01"
                          value={fuel.liters || ""}
                          onChange={(e) => updateFuelDraft(vehicle.fleet_id, "liters", e.target.value)}
                          placeholder="Liters"
                          className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-teal-500"
                        />
                        <input
                          type="number"
                          min="0"
                          step="0.01"
                          value={fuel.cost_amount || ""}
                          onChange={(e) => updateFuelDraft(vehicle.fleet_id, "cost_amount", e.target.value)}
                          placeholder="Cost amount"
                          className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-teal-500"
                        />
                        <input
                          value={fuel.notes || ""}
                          onChange={(e) => updateFuelDraft(vehicle.fleet_id, "notes", e.target.value)}
                          placeholder="Notes"
                          className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-teal-500"
                        />
                        <button
                          type="button"
                          onClick={() => onLogFuel(vehicle.fleet_id)}
                          disabled={savingFuelId === vehicle.fleet_id}
                          className="w-full rounded-xl border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-60"
                        >
                          {savingFuelId === vehicle.fleet_id ? "Logging..." : "Save Fuel Log"}
                        </button>
                      </div>
                    </div>
                  </div>

                  <div className="mt-4 border-t border-slate-200 pt-4">
                    <button
                      type="button"
                      onClick={() => toggleHistory(vehicle.fleet_id)}
                      className="rounded-xl border border-slate-300 px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50"
                    >
                      {open ? "Hide Trip/Fuel History" : "View Trip/Fuel History"}
                    </button>
                    {open ? (
                      <div className="mt-3 grid gap-3 lg:grid-cols-2">
                        <div className="rounded-xl border border-slate-200 p-3 text-sm">
                          <p className="font-semibold">Trip History</p>
                          {historyLoadingId === vehicle.fleet_id ? <p className="mt-2 text-xs text-slate-500">Loading...</p> : null}
                          <div className="mt-2 max-h-40 space-y-2 overflow-auto">
                            {(history.trips || []).length === 0 ? <p className="text-xs text-slate-500">No trip logs.</p> : null}
                            {(history.trips || []).map((t) => (
                              <div key={t.trip_id} className="rounded-lg border border-slate-100 bg-slate-50 p-2">
                                <p className="font-medium">{t.destination || "-"}</p>
                                <p className="text-xs text-slate-600">Patient: {t.patient_name || "-"} | {t.trip_status}</p>
                                <p className="text-xs text-slate-500">{t.started_at || "-"}</p>
                              </div>
                            ))}
                          </div>
                        </div>
                        <div className="rounded-xl border border-slate-200 p-3 text-sm">
                          <p className="font-semibold">Fuel History</p>
                          {historyLoadingId === vehicle.fleet_id ? <p className="mt-2 text-xs text-slate-500">Loading...</p> : null}
                          <div className="mt-2 max-h-40 space-y-2 overflow-auto">
                            {(history.fuel_logs || []).length === 0 ? <p className="text-xs text-slate-500">No fuel logs.</p> : null}
                            {(history.fuel_logs || []).map((f) => (
                              <div key={f.fuel_log_id} className="rounded-lg border border-slate-100 bg-slate-50 p-2">
                                <p className="font-medium">{Number(f.liters || 0).toFixed(1)} L</p>
                                <p className="text-xs text-slate-600">{money(f.cost_amount || 0)}</p>
                                <p className="text-xs text-slate-500">{f.fuel_date || "-"}</p>
                              </div>
                            ))}
                          </div>
                        </div>
                      </div>
                    ) : null}
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </section>

      {registerModalOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4 backdrop-blur-sm">
          <form
            onSubmit={onRegisterVehicle}
            className="w-full max-w-xl rounded-[32px] border border-slate-200 bg-white p-6 shadow-2xl"
          >
            <h3 className="text-xl font-black tracking-tight">Register New Vehicle</h3>
            <p className="mt-1 text-sm text-slate-600">Add ambulance or staff van with baseline mission details.</p>
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              <input
                value={registerForm.plate_number}
                onChange={(e) => setRegisterForm((p) => ({ ...p, plate_number: e.target.value }))}
                placeholder="Plate Number"
                className="rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-teal-500"
                required
              />
              <select
                value={registerForm.vehicle_type}
                onChange={(e) => setRegisterForm((p) => ({ ...p, vehicle_type: e.target.value }))}
                className="rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-teal-500"
              >
                <option value="AMBULANCE">Ambulance</option>
                <option value="STAFF_VAN">Staff Van</option>
              </select>
              <input
                value={registerForm.model_name}
                onChange={(e) => setRegisterForm((p) => ({ ...p, model_name: e.target.value }))}
                placeholder="Model"
                className="rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-teal-500"
              />
              <input
                value={registerForm.assigned_driver}
                onChange={(e) => setRegisterForm((p) => ({ ...p, assigned_driver: e.target.value }))}
                placeholder="Driver Assignment"
                className="rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-teal-500"
              />
              <input
                value={registerForm.mission_patient_name}
                onChange={(e) => setRegisterForm((p) => ({ ...p, mission_patient_name: e.target.value }))}
                placeholder="Mission patient (optional)"
                className="rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-teal-500"
              />
              <select
                value={registerForm.status}
                onChange={(e) => setRegisterForm((p) => ({ ...p, status: e.target.value }))}
                className="rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-teal-500"
              >
                {STATUS_OPTIONS.map((s) => (
                  <option key={s.code} value={s.code}>{s.label}</option>
                ))}
              </select>
              <input
                value={registerForm.destination}
                onChange={(e) => setRegisterForm((p) => ({ ...p, destination: e.target.value }))}
                placeholder="Destination (if on trip)"
                className="rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-teal-500"
              />
              <input
                value={registerForm.eta_return}
                onChange={(e) => setRegisterForm((p) => ({ ...p, eta_return: e.target.value }))}
                placeholder="ETA return"
                className="rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-teal-500"
              />
              <textarea
                value={registerForm.notes}
                onChange={(e) => setRegisterForm((p) => ({ ...p, notes: e.target.value }))}
                placeholder="Notes"
                rows={2}
                className="sm:col-span-2 rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-teal-500"
              />
            </div>
            <div className="mt-4 flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={() => setRegisterModalOpen(false)}
                className="rounded-xl border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={savingVehicle}
                className="inline-flex items-center gap-2 rounded-xl bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-teal-700 disabled:opacity-60"
              >
                {savingVehicle ? <Loader2 className="h-4 w-4 animate-spin" /> : <PlusCircle className="h-4 w-4" />}
                {savingVehicle ? "Saving..." : "Register Vehicle"}
              </button>
            </div>
          </form>
        </div>
      ) : null}
    </FleetWorkspaceLayout>
  );
}
