import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { publicApi } from "../lib/api";
import { Check, Loader2, CreditCard, Sparkles } from "lucide-react";

export default function Pricing() {
  const navigate = useNavigate();
  const [plans, setPlans] = useState([]);
  const [loading, setLoading] = useState(true);
  const [buying, setBuying] = useState(false);
  const [message, setMessage] = useState("");
  const [purchaseDone, setPurchaseDone] = useState(false);

  const [form, setForm] = useState({
    hospital_name: "",
    hospital_code: "",
    admin_email: "",
    plan_code: "",
    billing_cycle: "monthly",
  });

  useEffect(() => {
    publicApi
      .get("/public/plans")
      .then((res) => {
        const items = res.data?.items || [];
        setPlans(items);
        if (items.length) setForm((p) => ({ ...p, plan_code: items[0].plan_code }));
      })
      .finally(() => setLoading(false));
  }, []);

  const handleBuy = async (e) => {
    e.preventDefault();
    setBuying(true);
    setMessage("");
    setPurchaseDone(false);
    try {
      const res = await publicApi.post("/public/plans/purchase", form);
      setMessage(`Purchase successful. Subscription expires on ${new Date(res.data.expires_at).toLocaleDateString()}.`);
      setPurchaseDone(true);
    } catch (err) {
      setMessage(err?.response?.data?.detail || "Purchase failed");
    } finally {
      setBuying(false);
    }
  };

  const goToOnboarding = () => {
    const query = new URLSearchParams({
      hospital_code: form.hospital_code,
      admin_email: form.admin_email,
    }).toString();
    navigate(`/subscription/onboarding?${query}`);
  };

  return (
    <section className="px-4 py-16 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-7xl space-y-8">
        <div className="rounded-2xl border border-slate-200 bg-white p-8 shadow-sm">
          <p className="text-xs font-bold uppercase tracking-[0.14em] text-cyan-700">SaaS Plans</p>
          <h1 className="text-3xl font-extrabold tracking-tight mt-2">Choose the right MedX plan</h1>
          <p className="mt-2 text-slate-600">Flexible subscription options for single-hospital and network-wide deployments.</p>
        </div>

        {loading ? (
          <div className="py-10 text-center"><Loader2 className="mx-auto h-8 w-8 animate-spin text-cyan-700" /></div>
        ) : (
          <div className="grid gap-5 md:grid-cols-3">
            {plans.map((plan) => (
              <article key={plan.plan_code} className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                <div className="flex items-center justify-between"><h3 className="text-xl font-bold">{plan.plan_name}</h3><Sparkles className="h-4 w-4 text-cyan-700" /></div>
                <p className="mt-1 text-xs font-bold uppercase tracking-[0.12em] text-slate-500">{plan.plan_code}</p>
                <p className="mt-4 text-3xl font-extrabold">${plan.monthly_price}<span className="text-sm font-semibold text-slate-500">/month</span></p>
                <p className="text-sm font-semibold text-slate-500">or ${plan.yearly_price}/year</p>
                <ul className="mt-4 space-y-2 text-sm text-slate-600">
                  {(plan.features || []).map((f) => (
                    <li key={f} className="flex items-center gap-2"><Check className="h-4 w-4 text-cyan-700" />{f}</li>
                  ))}
                </ul>
              </article>
            ))}
          </div>
        )}

        <form onSubmit={handleBuy} className="rounded-2xl border border-slate-200 bg-white p-8 shadow-sm space-y-4">
          <h2 className="text-xl font-bold flex items-center gap-2"><CreditCard className="h-5 w-5 text-cyan-700" /> Purchase Subscription</h2>
          <div className="grid gap-4 md:grid-cols-2">
            <input className="rounded-lg border px-3 py-2.5" placeholder="Hospital Name" required value={form.hospital_name} onChange={(e) => setForm({ ...form, hospital_name: e.target.value })} />
            <input className="rounded-lg border px-3 py-2.5" placeholder="Hospital Code (unique)" required value={form.hospital_code} onChange={(e) => setForm({ ...form, hospital_code: e.target.value })} />
            <input className="rounded-lg border px-3 py-2.5" type="email" placeholder="Admin Email" required value={form.admin_email} onChange={(e) => setForm({ ...form, admin_email: e.target.value })} />
            <select className="rounded-lg border px-3 py-2.5" value={form.plan_code} onChange={(e) => setForm({ ...form, plan_code: e.target.value })}>{plans.map((p) => <option key={p.plan_code} value={p.plan_code}>{p.plan_name}</option>)}</select>
            <select className="rounded-lg border px-3 py-2.5" value={form.billing_cycle} onChange={(e) => setForm({ ...form, billing_cycle: e.target.value })}><option value="monthly">Monthly</option><option value="yearly">Yearly</option></select>
          </div>
          <div className="flex gap-2 flex-wrap">
            <button disabled={buying} className="rounded-xl bg-cyan-600 px-5 py-3 text-white font-semibold hover:bg-cyan-700 disabled:opacity-70">{buying ? "Processing..." : "Purchase Subscription"}</button>
            {purchaseDone ? <button type="button" onClick={goToOnboarding} className="rounded-xl border px-5 py-3 font-semibold text-slate-700">Continue Admin Setup</button> : null}
          </div>
          {message ? <p className="text-sm font-semibold text-slate-700">{message}</p> : null}
        </form>
      </div>
    </section>
  );
}
