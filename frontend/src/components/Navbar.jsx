import { Link, useLocation } from "react-router-dom";
import { Activity, ArrowRight } from "lucide-react";

const navLinks = [
  { to: "/", label: "Home" },
  { to: "/about", label: "About" },
  { to: "/pricing", label: "Pricing" },
  { to: "/contact", label: "MedX Contact" },
  { to: "/hospital-contacts", label: "Hospitals" },
  { to: "/book-appointment", label: "Book Appointment" },
];

export default function Navbar() {
  const location = useLocation();

  return (
    <nav className="sticky top-0 z-50 border-b border-slate-200/70 bg-white/85 backdrop-blur-xl">
      <div className="mx-auto flex h-20 w-full max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
        <Link to="/" className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-cyan-600 text-white shadow-lg shadow-cyan-600/20">
            <Activity className="h-5 w-5" />
          </div>
          <div>
            <p className="text-lg font-extrabold leading-none tracking-tight">MedX</p>
            <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">Multi-Hospital ERP</p>
          </div>
        </Link>

        <div className="hidden items-center gap-6 md:flex">
          {navLinks.map((link) => {
            const isActive = location.pathname === link.to;
            return (
              <Link key={link.to} to={link.to} className={`text-sm font-semibold transition-colors ${isActive ? "text-cyan-700" : "text-slate-600 hover:text-cyan-700"}`}>
                {link.label}
              </Link>
            );
          })}
          <Link to="/login" className="inline-flex items-center gap-2 rounded-full bg-slate-900 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-cyan-700">
            Log In <ArrowRight className="h-4 w-4" />
          </Link>
        </div>
      </div>
    </nav>
  );
}

