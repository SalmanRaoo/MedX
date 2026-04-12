import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import Sidebar from "../components/Sidebar";
import { api } from "../lib/api";
import {
  Users, UserRound, Search, Loader2,
  Database, Phone, Mail, Calendar, HeartPulse
} from "lucide-react";

export default function StaffPatients() {
  const [activeTab, setActiveTab] = useState("staff");
  const [staff, setStaff] = useState([]);
  const [patients, setPatients] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");

  const fetchData = async () => {
    try {
      const [staffRes, patientRes] = await Promise.all([
        api.get("/staff/"),
        api.get("/patients/"),
      ]);

      const visibleStaff = (staffRes.data?.items || []).filter(
        (member) => String(member.role || "").toUpperCase() !== "SUPER_ADMIN"
      );
      setStaff(visibleStaff);
      setPatients(patientRes.data?.items || []);
    } catch (err) {
      console.error("Data fetch failed");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const listToDisplay = activeTab === "staff" ? staff : patients;
  const filteredList = listToDisplay.filter((item) =>
    item.full_name?.toLowerCase().includes(searchQuery.toLowerCase()) ||
    item.role?.toLowerCase().includes(searchQuery.toLowerCase()) ||
    item.patient_mrn?.toLowerCase().includes(searchQuery.toLowerCase()) ||
    item.phone_number?.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const getBadgeStyle = (role) => {
    if (activeTab === "patients") return "bg-blue-50 text-blue-600 border-blue-100";
    const styles = {
      DOCTOR: "bg-purple-50 text-purple-700 border-purple-100",
      ADMIN: "bg-slate-900 text-white border-slate-800",
      RECEPTIONIST: "bg-teal-50 text-teal-700 border-teal-100",
      RADIOLOGIST: "bg-indigo-50 text-indigo-700 border-indigo-100",
      ACCOUNTANT: "bg-amber-50 text-amber-700 border-amber-100",
    };
    return styles[String(role || "").toUpperCase()] || "bg-slate-50 text-slate-600 border-slate-100";
  };

  const getHistoryLink = (item) => {
    if (activeTab === "staff") return `/dashboard/staff-history/${item.staff_id}`;
    return `/dashboard/patient-history/${item.patient_id}`;
  };

  return (
    <div className="flex h-screen bg-slate-50 overflow-hidden font-sans">
      <Sidebar />
      <div className="flex-1 flex flex-col">
        <header className="h-20 bg-white border-b flex items-center justify-between px-10 shadow-sm">
          <div className="flex items-center space-x-2">
            <div className="bg-teal-600 p-2 rounded-xl"><Users className="text-white w-5 h-5" /></div>
            <h1 className="text-xl font-black text-slate-900 uppercase tracking-tighter">Directory</h1>
          </div>
          <div className="flex-1 max-w-md mx-10 relative">
            <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
            <input
              type="text"
              placeholder={`Search ${activeTab}...`}
              className="w-full pl-12 pr-4 py-3 bg-slate-50 border rounded-2xl outline-none focus:ring-2 focus:ring-teal-500/10 transition-all text-sm"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>
          <div className="text-right">
            <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest leading-none mb-1">Total Records</p>
            <p className="text-lg font-black text-slate-900 leading-none">{activeTab === "staff" ? staff.length : patients.length}</p>
          </div>
        </header>

        <main className="flex-1 overflow-y-auto p-10 space-y-8">
          <div className="flex p-1.5 bg-slate-200/50 rounded-2xl w-fit">
            <button onClick={() => setActiveTab("staff")} className={`px-8 py-3 rounded-xl font-black text-[10px] uppercase tracking-[0.15em] transition-all ${activeTab === "staff" ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-700"}`}>Medical Staff</button>
            <button onClick={() => setActiveTab("patients")} className={`px-8 py-3 rounded-xl font-black text-[10px] uppercase tracking-[0.15em] transition-all ${activeTab === "patients" ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-700"}`}>Patient Database</button>
          </div>

          <div className="grid grid-cols-1 xl:grid-cols-2 2xl:grid-cols-3 gap-6">
            {isLoading ? (
              <div className="col-span-full py-20 text-center"><Loader2 className="animate-spin mx-auto text-teal-600 w-10 h-10" /></div>
            ) : filteredList.length === 0 ? (
              <div className="col-span-full py-20 text-center bg-white rounded-[32px] border border-dashed border-slate-200">
                <Database className="mx-auto text-slate-200 w-12 h-12 mb-4" />
                <p className="text-slate-400 font-black text-[10px] uppercase tracking-widest">No active records found in {activeTab}</p>
              </div>
            ) : filteredList.map((item) => (
              <Link key={activeTab === "staff" ? item.staff_id : item.patient_id} to={getHistoryLink(item)} className="bg-white p-8 rounded-[32px] border border-slate-100 shadow-xl shadow-slate-200/30 hover:translate-y-[-4px] transition-all group block">
                <div className="flex justify-between items-start mb-6">
                  <div className={`p-4 rounded-2xl ${activeTab === "staff" ? "bg-teal-50 text-teal-600" : "bg-blue-50 text-blue-600"}`}>
                    {activeTab === "staff" ? <UserRound className="w-6 h-6" /> : <HeartPulse className="w-6 h-6" />}
                  </div>
                  <span className={`px-3 py-1 rounded-full border text-[9px] font-black uppercase tracking-widest ${getBadgeStyle(item.role)}`}>
                    {activeTab === "staff" ? item.role : "Registered"}
                  </span>
                </div>

                <h3 className="text-xl font-black text-slate-900 mb-1 group-hover:text-teal-600 transition-colors">{item.full_name}</h3>
                <p className="text-slate-400 text-[10px] font-bold uppercase tracking-widest mb-6">ID: #{activeTab === "staff" ? item.staff_id : item.patient_id}</p>

                <div className="space-y-3 pt-6 border-t border-slate-50">
                  <div className="flex items-center text-sm font-bold text-slate-600"><Phone className="w-4 h-4 mr-3 text-slate-300" />{item.phone_number || "No Contact"}</div>
                  {activeTab === "patients" && (<div className="flex items-center text-sm font-bold text-slate-600"><Calendar className="w-4 h-4 mr-3 text-slate-300" />Born: {item.dob || "N/A"}</div>)}
                  {activeTab === "staff" && (<div className="flex items-center text-sm font-bold text-slate-600 italic"><Mail className="w-4 h-4 mr-3 text-slate-300" />Click to view full history</div>)}
                </div>
              </Link>
            ))}
          </div>
        </main>
      </div>
    </div>
  );
}
