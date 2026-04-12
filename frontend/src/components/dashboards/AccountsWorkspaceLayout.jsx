import { Link, NavLink, useNavigate } from "react-router-dom";
import { CircleDollarSign, LogOut, KeyRound } from "lucide-react";
import { clearSession, getSessionUser } from "../../lib/auth";
import { useHospitalSettings } from "../../context/HospitalSettingsContext";

const links = [
  { to: "/dashboard/finance", label: "Accounts", icon: CircleDollarSign },
  { to: "/dashboard/account", label: "Account", icon: KeyRound },
];

export default function AccountsWorkspaceLayout({ title, subtitle, children }) {
  const navigate = useNavigate();
  const user = getSessionUser();
  const { hospitalName } = useHospitalSettings();

  const handleLogout = () => {
    clearSession();
    navigate("/");
  };

  return (
    <div className="min-h-screen bg-slate-100 text-slate-900">
      <div className="flex min-h-screen">
        <aside className="hidden w-72 bg-slate-900 p-6 text-white md:flex md:flex-col">
          <Link to="/dashboard/finance" className="mb-8 block">
            <p className="text-xs uppercase tracking-[0.2em] text-teal-300">MedX Accounts</p>
            <p className="mt-1 text-2xl font-extrabold">Command Desk</p>
          </Link>

          <nav className="space-y-2 flex-1">
            {links.map((item) => {
              const Icon = item.icon;
              return (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.to === "/dashboard/finance"}
                  className={({ isActive }) =>
                    `flex items-center gap-3 rounded-xl px-4 py-3 text-sm font-semibold transition ${
                      isActive ? "bg-teal-600 text-white" : "text-slate-300 hover:bg-slate-800 hover:text-white"
                    }`
                  }
                >
                  <Icon className="h-4 w-4" />
                  {item.label}
                </NavLink>
              );
            })}
          </nav>

          <button
            type="button"
            onClick={handleLogout}
            className="mt-6 inline-flex items-center justify-center gap-2 rounded-xl border border-red-400/40 px-4 py-2 text-sm font-semibold text-red-300 hover:bg-red-500/10"
          >
            <LogOut className="h-4 w-4" /> Exit
          </button>
        </aside>

        <main className="flex-1">
          <header className="border-b border-slate-200 bg-white px-5 py-4 sm:px-8 flex items-center justify-between">
            <div>
              <h1 className="text-xl sm:text-2xl font-extrabold tracking-tight">{title}</h1>
              <p className="text-sm text-slate-600">{subtitle}</p>
            </div>
            <div className="text-right">
              <p className="text-xs uppercase tracking-[0.14em] text-slate-500">Hospital</p>
              <p className="text-sm font-semibold text-teal-700">{hospitalName || user?.hospital_name || "MedX"}</p>
            </div>
          </header>
          <section className="p-5 sm:p-8">{children}</section>
        </main>
      </div>
    </div>
  );
}
