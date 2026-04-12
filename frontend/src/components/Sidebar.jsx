import { Link, useLocation, useNavigate } from "react-router-dom";
import {
  LayoutDashboard,
  Users,
  Settings,
  LogOut,
  ShieldCheck,
  KeyRound,
  UserX,
  CircleDollarSign,
  Truck,
  Building2,
} from "lucide-react";

export default function Sidebar() {
  const location = useLocation();
  const navigate = useNavigate();
  const role = (() => {
    try {
      return String(JSON.parse(localStorage.getItem("medx_user") || "{}")?.role_name || "").toUpperCase();
    } catch {
      return "";
    }
  })();
  const canAccessAccounts = role === "SUPER_ADMIN" || role === "ACCOUNTANT";
  const canAccessOperations = role === "SUPER_ADMIN" || role === "ADMIN" || role === "OPERATIONS";

  const handleLogout = () => {
    localStorage.removeItem("medx_token");
    localStorage.removeItem("medx_user");
    navigate("/");
  };

  const isActive = (path) =>
    location.pathname === path
      ? "bg-teal-600 text-white shadow-lg shadow-teal-600/20 translate-x-1"
      : "text-slate-400 hover:bg-white/5 hover:text-white";

  return (
    <div className="w-72 bg-slate-900 h-screen flex flex-col shadow-2xl z-50 relative border-r border-white/5">
      <div className="h-24 flex items-center px-10 mb-4">
        <Link to="/dashboard/admin" className="flex items-center group">
          <div className="bg-teal-500 p-2.5 rounded-2xl shadow-lg group-hover:rotate-12 transition-transform">
            <ShieldCheck className="h-6 w-6 text-white" />
          </div>
          <span className="ml-4 font-black text-2xl tracking-tighter text-white uppercase">MedX</span>
        </Link>
      </div>

      <nav className="flex-1 px-6 space-y-3 font-sans">
        <p className="px-4 text-[10px] font-black text-slate-500 uppercase tracking-[0.2em] mb-4">Core Management</p>

        <SidebarLink to="/dashboard/admin" icon={<LayoutDashboard className="h-5 w-5" />} label="Admin Overview" activeClass={isActive("/dashboard/admin")} />
        <SidebarLink to="/dashboard/staff-patients" icon={<Users className="h-5 w-5" />} label="Staff & Patients" activeClass={isActive("/dashboard/staff-patients")} />
        <SidebarLink to="/dashboard/user-access" icon={<UserX className="h-5 w-5" />} label="User Access" activeClass={isActive("/dashboard/user-access")} />
        {canAccessAccounts ? (
          <>
            <SidebarLink to="/dashboard/finance" icon={<CircleDollarSign className="h-5 w-5" />} label="Accounts" activeClass={isActive("/dashboard/finance")} />
            <SidebarLink to="/dashboard/fleet" icon={<Truck className="h-5 w-5" />} label="Fleet" activeClass={isActive("/dashboard/fleet")} />
          </>
        ) : null}
        {canAccessOperations ? (
          <SidebarLink to="/dashboard/operations" icon={<Building2 className="h-5 w-5" />} label="Operations" activeClass={isActive("/dashboard/operations")} />
        ) : null}

        <div className="pt-8 px-4 text-[10px] font-black text-slate-500 uppercase tracking-[0.2em] mb-4">Infrastructure</div>
        <SidebarLink to="/dashboard/settings" icon={<Settings className="h-5 w-5" />} label="System Settings" activeClass={isActive("/dashboard/settings")} />
        <SidebarLink to="/dashboard/account" icon={<KeyRound className="h-5 w-5" />} label="Account Security" activeClass={isActive("/dashboard/account")} />
      </nav>

      <div className="p-8 border-t border-white/5">
        <button onClick={handleLogout} className="flex items-center w-full px-6 py-4 text-red-400 hover:bg-red-500/10 rounded-2xl font-black text-[10px] uppercase tracking-widest transition-all active:scale-95">
          <LogOut className="h-5 w-5 mr-4" />
          <span>Secure Sign Out</span>
        </button>
      </div>
    </div>
  );
}

function SidebarLink({ to, icon, label, activeClass }) {
  return (
    <Link to={to} className={`flex items-center px-6 py-4 rounded-2xl font-bold text-sm transition-all duration-300 ${activeClass}`}>
      <span className="mr-4">{icon}</span>
      <span className="tracking-tight">{label}</span>
    </Link>
  );
}
