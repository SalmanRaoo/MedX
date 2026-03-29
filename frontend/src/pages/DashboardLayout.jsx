import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import Sidebar from "../components/Sidebar";
import { api } from "../lib/api";
import {
  Search, UserPlus, X, ShieldCheck, Users,
  Activity, BrainCircuit, Loader2, CheckCircle, Building2
} from "lucide-react";

export default function DashboardLayout() {
  const navigate = useNavigate();
  const user = JSON.parse(localStorage.getItem("medx_user") || "{}");
  const [stats, setStats] = useState({ patients: 0, staff: 0, ai: 0 });
  const [usersList, setUsersList] = useState([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [dbStatus, setDbStatus] = useState("Checking...");
  const [toast, setToast] = useState({ show: false, message: "" });

  const [form, setForm] = useState({
    full_name: "",
    email: "",
    password: "",
    role_name: "DOCTOR",
    phone_number: "",
    department_name: "",
    department_location: "",
    license_number: "",
  });
  const [isSubmitting, setIsSubmitting] = useState(false);

  const showToast = (msg) => {
    setToast({ show: true, message: msg });
    setTimeout(() => setToast({ show: false, message: "" }), 3000);
  };

  const fetchHospitalData = async () => {
    try {
      if (!localStorage.getItem("medx_token")) {
        navigate("/login");
        return;
      }

      const [staffRes, patRes, aiRes] = await Promise.all([
        api.get("/staff/"),
        api.get("/patients/"),
        api.get("/ai_diagnoses/"),
      ]);

      const staff = staffRes.data?.items || [];
      const patients = patRes.data?.items || [];
      const ai = aiRes.data?.items || [];

      setUsersList(staff);
      setStats({ staff: staff.length, patients: patients.length, ai: ai.length });
      setDbStatus(staff.length === 0 ? "Empty" : "Optimal");
    } catch {
      setDbStatus("Offline");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchHospitalData();
  }, []);

  const getRoleBadge = (role) => {
    const roles = {
      DOCTOR: "bg-blue-100 text-blue-700 border-blue-200",
      ADMIN: "bg-purple-100 text-purple-700 border-purple-200",
      RECEPTIONIST: "bg-teal-100 text-teal-700 border-teal-200",
      NURSE: "bg-emerald-100 text-emerald-700 border-emerald-200",
    };
    return roles[(role || "").toUpperCase()] || "bg-slate-100 text-slate-700 border-slate-200";
  };

  const handleRegisterStaff = async (e) => {
    e.preventDefault();
    setIsSubmitting(true);
    try {
      await api.post("/admin/users/create", form);
      setIsModalOpen(false);
      setForm({
        full_name: "",
        email: "",
        password: "",
        role_name: "DOCTOR",
        phone_number: "",
        department_name: "",
        department_location: "",
        license_number: "",
      });
      showToast("Staff account created with login credentials");
      fetchHospitalData();
    } catch (err) {
      showToast(err?.response?.data?.detail || "Registration failed");
    } finally {
      setIsSubmitting(false);
    }
  };

  const filteredUsers = usersList.filter(
    (u) =>
      u.full_name?.toLowerCase().includes(searchQuery.toLowerCase()) ||
      u.role?.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="flex h-screen bg-slate-50 overflow-hidden font-sans">
      <Sidebar />
      <div className="flex-1 flex flex-col relative">
        {toast.show && (
          <div className="fixed top-8 right-8 z-[200] bg-slate-900 text-white px-6 py-4 rounded-2xl shadow-2xl flex items-center">
            <CheckCircle className="w-5 h-5 mr-3 text-teal-400" />
            <span className="font-bold text-sm tracking-tight">{toast.message}</span>
          </div>
        )}

        <header className="h-20 bg-white border-b flex items-center justify-between px-8 shadow-sm">
          <div className="flex-1 max-w-xl relative">
            <Search className="absolute left-4 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
            <input type="text" placeholder="Search staff..." className="w-full pl-12 pr-4 py-3 bg-slate-50 border border-slate-200 rounded-xl text-sm outline-none" value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)} />
          </div>
          <div className="ml-6 flex items-center gap-3 rounded-xl border border-slate-200 px-3 py-2">
            <Building2 className="h-4 w-4 text-slate-500" />
            <div>
              <p className="text-xs font-bold text-slate-500">{user.hospital_name || "Hospital"}</p>
              <p className="text-[10px] uppercase tracking-[0.12em] text-cyan-700">Admin Dashboard</p>
            </div>
          </div>
        </header>

        <main className="flex-1 overflow-y-auto p-8 space-y-8">
          <div className="flex justify-between items-end">
            <div>
              <h1 className="text-3xl font-black text-slate-900 tracking-tight">Admin Control Center</h1>
              <p className="text-slate-400 text-sm mt-1">Manage staff accounts, departments, and enterprise operations.</p>
            </div>
            <button onClick={() => setIsModalOpen(true)} className="bg-teal-600 text-white px-6 py-3 rounded-xl font-bold flex items-center hover:bg-teal-700 shadow-xl">
              <UserPlus className="h-4 w-4 mr-2" /> Register Staff
            </button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
            <MetricCard label="Total Patients" value={stats.patients} icon={<Users className="text-blue-500" />} />
            <MetricCard label="Medical Staff" value={stats.staff} icon={<Activity className="text-teal-500" />} />
            <MetricCard label="AI Diagnostics" value={stats.ai} icon={<BrainCircuit className="text-purple-500" />} />
            <MetricCard label="System Status" value={dbStatus} icon={<ShieldCheck className="text-green-500" />} isStatus />
          </div>

          <div className="bg-white rounded-[32px] border border-slate-100 shadow-xl overflow-hidden">
            <div className="p-6 border-b bg-slate-50/50">
              <h3 className="font-black text-slate-800 uppercase tracking-widest text-[10px]">Hospital Staff Directory</h3>
            </div>
            <table className="w-full text-left">
              <thead className="bg-white text-[10px] font-black text-slate-400 uppercase tracking-widest">
                <tr><th className="px-8 py-5">Name</th><th className="px-8 py-5">Role</th><th className="px-8 py-5">Department</th><th className="px-8 py-5 text-right">Status</th></tr>
              </thead>
              <tbody className="divide-y text-sm">
                {isLoading ? (
                  <tr><td colSpan="4" className="py-24 text-center"><Loader2 className="animate-spin mx-auto text-teal-600" /></td></tr>
                ) : filteredUsers.map((userRow) => (
                  <tr key={userRow.staff_id} className="hover:bg-slate-50 transition-colors">
                    <td className="px-8 py-5 font-bold text-slate-700">{userRow.full_name}</td>
                    <td className="px-8 py-5"><span className={`px-3 py-1 rounded-full border text-[10px] font-black uppercase tracking-widest ${getRoleBadge(userRow.role)}`}>{userRow.role}</span></td>
                    <td className="px-8 py-5 text-slate-500">{userRow.department_id ? `#${userRow.department_id}` : "-"}</td>
                    <td className="px-8 py-5 text-right"><span className="px-3 py-1 bg-green-50 text-green-600 rounded-full text-[10px] font-black uppercase tracking-widest border border-green-100">Active</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </main>
      </div>

      {isModalOpen && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-900/40 backdrop-blur-md p-4">
          <div className="bg-white rounded-[32px] shadow-2xl w-full max-w-2xl overflow-hidden">
            <div className="px-10 py-8 bg-slate-900 text-white flex justify-between items-center">
              <div><h2 className="text-xl font-black tracking-tight">Register Staff Member</h2><p className="text-slate-400 text-[10px] font-bold uppercase tracking-widest mt-1">Creates Login + Profile</p></div>
              <button onClick={() => setIsModalOpen(false)}><X className="text-white" /></button>
            </div>
            <form onSubmit={handleRegisterStaff} className="p-8 grid md:grid-cols-2 gap-4">
              <input type="text" placeholder="Full Name" className="p-3 bg-slate-50 border rounded-xl" value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} required />
              <input type="email" placeholder="Email (login)" className="p-3 bg-slate-50 border rounded-xl" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} required />
              <input type="password" placeholder="Temporary Password" className="p-3 bg-slate-50 border rounded-xl" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} required />
              <select className="p-3 bg-slate-50 border rounded-xl" value={form.role_name} onChange={(e) => setForm({ ...form, role_name: e.target.value })}>
                <option value="DOCTOR">Doctor</option><option value="ADMIN">Admin</option><option value="NURSE">Nurse</option><option value="RECEPTIONIST">Receptionist</option><option value="PHARMACY">Pharmacy</option><option value="LAB">Lab</option><option value="FINANCE">Finance</option><option value="OPERATIONS">Operations</option>
              </select>
              <input type="text" placeholder="Phone Number" className="p-3 bg-slate-50 border rounded-xl" value={form.phone_number} onChange={(e) => setForm({ ...form, phone_number: e.target.value })} />
              <input type="text" placeholder="License Number (optional)" className="p-3 bg-slate-50 border rounded-xl" value={form.license_number} onChange={(e) => setForm({ ...form, license_number: e.target.value })} />
              <input type="text" placeholder="Department" className="p-3 bg-slate-50 border rounded-xl" value={form.department_name} onChange={(e) => setForm({ ...form, department_name: e.target.value })} />
              <input type="text" placeholder="Department Location" className="p-3 bg-slate-50 border rounded-xl" value={form.department_location} onChange={(e) => setForm({ ...form, department_location: e.target.value })} />
              <button disabled={isSubmitting} className="md:col-span-2 w-full py-4 bg-teal-600 text-white font-black rounded-xl shadow-xl hover:bg-teal-700">
                {isSubmitting ? "Processing..." : "Create Staff Account"}
              </button>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

function MetricCard({ label, value, icon, isStatus }) {
  return (
    <div className="bg-white p-8 rounded-[32px] border border-slate-100 shadow-sm flex flex-col justify-between">
      <div className="p-4 bg-slate-50 rounded-2xl w-fit mb-6">{icon}</div>
      <div>
        <p className="text-slate-400 text-[10px] font-black uppercase tracking-widest mb-1">{label}</p>
        <h3 className="text-3xl font-black text-slate-900 tracking-tighter">
          {isStatus && <span className="inline-block w-3 h-3 bg-green-500 rounded-full mr-3 animate-pulse" />}
          {value}
        </h3>
      </div>
    </div>
  );
}
