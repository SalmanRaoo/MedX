import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Loader2, Save } from "lucide-react";
import { api } from "../../lib/api";

function buildDrafts(items) {
  const next = {};
  for (const plan of items) {
    next[plan.plan_id] = {
      plan_name: plan.plan_name || "",
      monthly_price: String(plan.monthly_price ?? 0),
      yearly_price: String(plan.yearly_price ?? 0),
      is_active: Boolean(plan.is_active),
      features_text: (plan.features || []).join("\n"),
    };
  }
  return next;
}

export default function SuperAdminPricingPage() {
  const [plans, setPlans] = useState([]);
  const [drafts, setDrafts] = useState({});
  const [loading, setLoading] = useState(true);
  const [savingPlanId, setSavingPlanId] = useState(null);
  const [statusMsg, setStatusMsg] = useState("");

  const loadPlans = async () => {
    try {
      const res = await api.get("/super-admin/pricing/plans");
      const items = res.data?.items || [];
      setPlans(items);
      setDrafts(buildDrafts(items));
    } catch (err) {
      setStatusMsg(err?.response?.data?.detail || "Unable to load pricing plans.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadPlans();
  }, []);

  const setDraft = (planId, patch) => {
    setDrafts((prev) => ({
      ...prev,
      [planId]: {
        ...(prev[planId] || {}),
        ...patch,
      },
    }));
  };

  const savePlan = async (planId) => {
    const draft = drafts[planId];
    if (!draft) return;

    const monthly = Number(draft.monthly_price);
    const yearly = Number(draft.yearly_price);
    if (!draft.plan_name?.trim()) {
      setStatusMsg("Plan name is required.");
      return;
    }
    if (Number.isNaN(monthly) || monthly < 0 || Number.isNaN(yearly) || yearly < 0) {
      setStatusMsg("Monthly and yearly prices must be valid non-negative numbers.");
      return;
    }

    const features = String(draft.features_text || "")
      .split("\n")
      .map((feature) => feature.trim())
      .filter(Boolean);

    setSavingPlanId(planId);
    setStatusMsg("");
    try {
      await api.post(`/super-admin/pricing/plans/${planId}`, {
        plan_name: draft.plan_name.trim(),
        monthly_price: monthly,
        yearly_price: yearly,
        features,
        is_active: Boolean(draft.is_active),
      });
      await loadPlans();
      setStatusMsg("Pricing plan updated successfully.");
    } catch (err) {
      setStatusMsg(err?.response?.data?.detail || "Unable to update plan.");
    } finally {
      setSavingPlanId(null);
    }
  };

  return (
    <section className="px-4 py-10 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-7xl space-y-6">
        <header className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h1 className="text-3xl font-extrabold">Pricing Page Management</h1>
              <p className="text-slate-600">Update public pricing plans and their feature details.</p>
              {statusMsg ? <p className="mt-2 text-sm font-semibold text-cyan-700">{statusMsg}</p> : null}
            </div>
            <div className="flex gap-2">
              <button onClick={loadPlans} className="rounded-lg border px-4 py-2 text-sm font-semibold text-slate-700">
                Refresh
              </button>
              <Link to="/dashboard/super-admin" className="rounded-lg border px-4 py-2 text-sm font-semibold text-slate-700">
                Back
              </Link>
            </div>
          </div>
        </header>

        {loading ? (
          <div className="rounded-2xl border border-slate-200 bg-white p-10 text-center shadow-sm">
            <Loader2 className="mx-auto h-8 w-8 animate-spin text-cyan-700" />
          </div>
        ) : (
          <div className="space-y-4">
            {plans.length === 0 ? (
              <div className="rounded-2xl border border-slate-200 bg-white p-8 text-center text-slate-500 shadow-sm">
                No pricing plans found.
              </div>
            ) : (
              plans.map((plan) => {
                const draft = drafts[plan.plan_id] || {};
                const isSaving = savingPlanId === plan.plan_id;
                return (
                  <article key={plan.plan_id} className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                    <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
                      <div>
                        <p className="text-xs font-bold uppercase tracking-[0.14em] text-slate-500">{plan.plan_code}</p>
                        <p className="text-sm text-slate-500">Plan ID: {plan.plan_id}</p>
                      </div>
                      <label className="flex items-center gap-2 text-sm font-semibold text-slate-700">
                        <input
                          type="checkbox"
                          checked={Boolean(draft.is_active)}
                          onChange={(e) => setDraft(plan.plan_id, { is_active: e.target.checked })}
                        />
                        Active on public pricing page
                      </label>
                    </div>

                    <div className="grid gap-4 md:grid-cols-3">
                      <label className="block md:col-span-1">
                        <span className="mb-1 block text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Plan Name</span>
                        <input
                          value={draft.plan_name || ""}
                          onChange={(e) => setDraft(plan.plan_id, { plan_name: e.target.value })}
                          className="w-full rounded-lg border px-3 py-2.5"
                        />
                      </label>
                      <label className="block">
                        <span className="mb-1 block text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Monthly Price</span>
                        <input
                          type="number"
                          min="0"
                          step="0.01"
                          value={draft.monthly_price || ""}
                          onChange={(e) => setDraft(plan.plan_id, { monthly_price: e.target.value })}
                          className="w-full rounded-lg border px-3 py-2.5"
                        />
                      </label>
                      <label className="block">
                        <span className="mb-1 block text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Yearly Price</span>
                        <input
                          type="number"
                          min="0"
                          step="0.01"
                          value={draft.yearly_price || ""}
                          onChange={(e) => setDraft(plan.plan_id, { yearly_price: e.target.value })}
                          className="w-full rounded-lg border px-3 py-2.5"
                        />
                      </label>
                    </div>

                    <label className="mt-4 block">
                      <span className="mb-1 block text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Feature Details (one per line)</span>
                      <textarea
                        rows={4}
                        value={draft.features_text || ""}
                        onChange={(e) => setDraft(plan.plan_id, { features_text: e.target.value })}
                        className="w-full rounded-lg border px-3 py-2.5"
                      />
                    </label>

                    <div className="mt-4">
                      <button
                        onClick={() => savePlan(plan.plan_id)}
                        disabled={isSaving}
                        className="inline-flex items-center gap-2 rounded-lg border px-4 py-2 text-sm font-semibold text-slate-700 disabled:opacity-60"
                      >
                        {isSaving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                        {isSaving ? "Saving..." : "Save Plan"}
                      </button>
                    </div>
                  </article>
                );
              })
            )}
          </div>
        )}
      </div>
    </section>
  );
}
