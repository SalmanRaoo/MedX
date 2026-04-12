import { useEffect, useMemo, useState } from "react";
import { CircleDollarSign, Download, PlusCircle, ReceiptText, Wallet } from "lucide-react";
import { api } from "../../lib/api";
import AccountsWorkspaceLayout from "../../components/dashboards/AccountsWorkspaceLayout";

function money(v) {
  const n = Number(v || 0);
  return `PKR ${n.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
}

export default function FinanceDashboard() {
  const [month, setMonth] = useState(new Date().toISOString().slice(0, 7));
  const [snapshot, setSnapshot] = useState(null);
  const [revenueFeed, setRevenueFeed] = useState([]);
  const [expenses, setExpenses] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const [expenseForm, setExpenseForm] = useState({
    category: "UTILITY_BILLS",
    amount: "",
    date_incurred: new Date().toISOString().slice(0, 10),
    description: "",
  });
  const [paymentForm, setPaymentForm] = useState({
    invoice_id: "",
    amount_paid: "",
    payment_method: "CASH",
    payment_reference: "",
  });
  const [savingExpense, setSavingExpense] = useState(false);
  const [savingPayment, setSavingPayment] = useState(false);

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const [snapRes, expRes, feedRes] = await Promise.all([
        api.get("/finance/command-center", { params: { month, ledger_limit: 600 } }),
        api.get("/finance/expenses", { params: { month, limit: 400 } }),
        api.get("/finance/revenue-feed", { params: { month, limit: 600 } }),
      ]);
      setSnapshot(snapRes.data || null);
      setExpenses(expRes.data?.items || []);
      setRevenueFeed(feedRes.data?.items || []);
    } catch (err) {
      setError(err?.response?.data?.detail || "Unable to load finance dashboard.");
    } finally {
      setLoading(false);
    }
  };

  const loadRevenueFeedOnly = async () => {
    try {
      const { data } = await api.get("/finance/revenue-feed", { params: { month, limit: 600 } });
      setRevenueFeed(data?.items || []);
    } catch {
      // keep last successful feed snapshot
    }
  };

  useEffect(() => {
    load();
  }, [month]);

  useEffect(() => {
    const timer = setInterval(() => {
      loadRevenueFeedOnly();
    }, 12000);
    return () => clearInterval(timer);
  }, [month]);

  const summary = snapshot?.financial_summary || {};
  const ledger = snapshot?.patient_revenue_ledger?.items || [];

  const cards = useMemo(
    () => [
      { title: "Total Revenue", value: money(summary.total_revenue), icon: CircleDollarSign },
      { title: "Operational Spend", value: money(summary.total_operational_spend), icon: Wallet },
      { title: "Net Profit", value: money(summary.net_profit), icon: ReceiptText },
    ],
    [summary]
  );

  const addExpense = async (e) => {
    e.preventDefault();
    setSavingExpense(true);
    setError("");
    setSuccess("");
    try {
      await api.post("/finance/expenses", {
        category: expenseForm.category,
        amount: Number(expenseForm.amount),
        date_incurred: expenseForm.date_incurred,
        description: expenseForm.description || null,
      });
      setSuccess("Expense logged.");
      setExpenseForm((p) => ({ ...p, amount: "", description: "" }));
      await load();
    } catch (err) {
      setError(err?.response?.data?.detail || "Unable to save expense.");
    } finally {
      setSavingExpense(false);
    }
  };

  const recordPayment = async (e) => {
    e.preventDefault();
    setSavingPayment(true);
    setError("");
    setSuccess("");
    try {
      await api.post("/finance/payments/record", {
        invoice_id: Number(paymentForm.invoice_id),
        amount_paid: Number(paymentForm.amount_paid),
        payment_method: paymentForm.payment_method,
        payment_reference: paymentForm.payment_reference || null,
      });
      setSuccess("Payment recorded. Revenue ledger updated.");
      setPaymentForm((p) => ({ ...p, amount_paid: "", payment_reference: "" }));
      await load();
    } catch (err) {
      setError(err?.response?.data?.detail || "Unable to record payment.");
    } finally {
      setSavingPayment(false);
    }
  };

  const downloadStatement = async () => {
    setError("");
    try {
      const { data } = await api.get("/finance/monthly-statement", { params: { month } });
      const blob = new Blob([data?.csv || ""], { type: "text/csv;charset=utf-8;" });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = data?.file_name || `medx_financial_statement_${month}.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      setError(err?.response?.data?.detail || "Unable to download monthly statement.");
    }
  };

  return (
    <AccountsWorkspaceLayout
      title="Accounts & Revenue Dashboard"
      subtitle="Financial command center for billing status, revenue tracking, operational spend, and monthly statements."
    >
      {error ? <p className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</p> : null}
      {success ? <p className="mt-3 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{success}</p> : null}

      <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
        <label className="space-y-1">
          <span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Month</span>
          <input
            type="month"
            value={month}
            onChange={(e) => setMonth(e.target.value)}
            className="rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-teal-500"
          />
        </label>
        <button
          type="button"
          onClick={downloadStatement}
          className="inline-flex items-center gap-2 rounded-xl border border-teal-600 px-4 py-2 text-sm font-semibold text-teal-700 hover:bg-teal-50"
        >
          <Download className="h-4 w-4" /> Download Monthly Statement
        </button>
      </div>

      <section className="mt-5 grid gap-4 md:grid-cols-3">
        {cards.map((c) => {
          const Icon = c.icon;
          return (
            <article key={c.title} className="rounded-[32px] border border-slate-200 bg-white p-6 shadow-sm">
              <div className="inline-flex rounded-2xl bg-teal-50 p-3 text-teal-700"><Icon className="h-5 w-5" /></div>
              <p className="mt-3 text-xs font-bold uppercase tracking-[0.12em] text-slate-500">{c.title}</p>
              <p className="mt-1 text-2xl font-black tracking-tight">{c.value}</p>
            </article>
          );
        })}
      </section>

      <section className="mt-4 grid gap-3 md:grid-cols-3">
        <article className="rounded-2xl border border-slate-200 bg-white p-4 text-sm">
          <p className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Invoice Services Revenue</p>
          <p className="mt-1 text-lg font-black">{money(summary?.revenue_breakdown?.invoice_services)}</p>
        </article>
        <article className="rounded-2xl border border-slate-200 bg-white p-4 text-sm">
          <p className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Fleet Fuel Expense</p>
          <p className="mt-1 text-lg font-black">{money(summary?.spend_breakdown?.fleet_fuel)}</p>
        </article>
        <article className="rounded-2xl border border-slate-200 bg-white p-4 text-sm">
          <p className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">OT / ICU Supplies</p>
          <p className="mt-1 text-lg font-black">{money(summary?.spend_breakdown?.ot_supplies)}</p>
        </article>
      </section>

      <section className="mt-5 grid gap-5 xl:grid-cols-[0.95fr_1.35fr]">
        <article className="rounded-[32px] border border-slate-200 bg-white p-6 shadow-sm">
          <h3 className="text-lg font-bold">Expense Tracker</h3>
          <form onSubmit={addExpense} className="mt-3 space-y-3">
            <label className="block space-y-1">
              <span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Category</span>
              <select
                value={expenseForm.category}
                onChange={(e) => setExpenseForm((p) => ({ ...p, category: e.target.value }))}
                className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-teal-500"
              >
                <option value="UTILITY_BILLS">Utility Bills</option>
                <option value="EQUIPMENT_MAINTENANCE">Equipment Maintenance</option>
                <option value="SUPPLIES">Supplies</option>
                <option value="STAFF_SALARY">Staff Salary</option>
                <option value="MEDICINE_STOCK">Medicine Stock Purchase</option>
              </select>
            </label>
            <label className="block space-y-1">
              <span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Amount</span>
              <input
                type="number"
                min="0"
                step="0.01"
                value={expenseForm.amount}
                onChange={(e) => setExpenseForm((p) => ({ ...p, amount: e.target.value }))}
                className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-teal-500"
                required
              />
            </label>
            <label className="block space-y-1">
              <span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Date</span>
              <input
                type="date"
                value={expenseForm.date_incurred}
                onChange={(e) => setExpenseForm((p) => ({ ...p, date_incurred: e.target.value }))}
                className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-teal-500"
                required
              />
            </label>
            <label className="block space-y-1">
              <span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Description</span>
              <textarea
                value={expenseForm.description}
                onChange={(e) => setExpenseForm((p) => ({ ...p, description: e.target.value }))}
                rows={3}
                className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-teal-500"
              />
            </label>
            <button
              type="submit"
              disabled={savingExpense}
              className="inline-flex items-center gap-2 rounded-xl bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-teal-700 disabled:opacity-60"
            >
              <PlusCircle className="h-4 w-4" /> {savingExpense ? "Saving..." : "Log Expense"}
            </button>
          </form>

          <div className="mt-6 border-t border-slate-200 pt-4">
            <h4 className="text-sm font-bold uppercase tracking-[0.12em] text-slate-500">Record Payment</h4>
            <form onSubmit={recordPayment} className="mt-3 space-y-3">
              <input
                placeholder="Invoice ID"
                type="number"
                min="1"
                value={paymentForm.invoice_id}
                onChange={(e) => setPaymentForm((p) => ({ ...p, invoice_id: e.target.value }))}
                className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-teal-500"
                required
              />
              <input
                placeholder="Amount Paid"
                type="number"
                min="0"
                step="0.01"
                value={paymentForm.amount_paid}
                onChange={(e) => setPaymentForm((p) => ({ ...p, amount_paid: e.target.value }))}
                className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-teal-500"
                required
              />
              <select
                value={paymentForm.payment_method}
                onChange={(e) => setPaymentForm((p) => ({ ...p, payment_method: e.target.value }))}
                className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-teal-500"
              >
                <option value="CASH">Cash</option>
                <option value="CARD">Card</option>
                <option value="BANK_TRANSFER">Bank Transfer</option>
                <option value="ONLINE">Online</option>
              </select>
              <input
                placeholder="Payment reference (optional)"
                value={paymentForm.payment_reference}
                onChange={(e) => setPaymentForm((p) => ({ ...p, payment_reference: e.target.value }))}
                className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-teal-500"
              />
              <button
                type="submit"
                disabled={savingPayment}
                className="inline-flex items-center gap-2 rounded-xl border border-teal-600 px-4 py-2 text-sm font-semibold text-teal-700 hover:bg-teal-50 disabled:opacity-60"
              >
                {savingPayment ? "Recording..." : "Record Payment"}
              </button>
            </form>
          </div>
        </article>

        <article className="rounded-[32px] border border-slate-200 bg-white p-6 shadow-sm">
          <h3 className="text-lg font-bold">Real-time Revenue Feed</h3>
          <p className="mt-1 text-xs uppercase tracking-[0.12em] text-slate-500">Reception registrations and radiology billings land here as Pending until paid.</p>
          <div className="mt-3 overflow-auto rounded-xl border border-slate-200">
            <table className="min-w-full text-sm">
              <thead className="bg-slate-50">
                <tr>
                  <th className="px-3 py-2 text-left">Time</th>
                  <th className="px-3 py-2 text-left">Patient</th>
                  <th className="px-3 py-2 text-left">Service</th>
                  <th className="px-3 py-2 text-left">Fee</th>
                  <th className="px-3 py-2 text-left">State</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr><td colSpan={5} className="px-3 py-8 text-center text-slate-500">Loading...</td></tr>
                ) : revenueFeed.length === 0 ? (
                  <tr><td colSpan={5} className="px-3 py-8 text-center text-slate-500">No revenue events found.</td></tr>
                ) : (
                  revenueFeed.slice(0, 120).map((row, idx) => (
                    <tr key={`${row.invoice_id}-${row.service_type}-${idx}`} className="border-t border-slate-100">
                      <td className="px-3 py-2">
                        <p className="font-semibold">{row.invoice_number}</p>
                        <p className="text-xs text-slate-500">{row.invoice_date || "-"}</p>
                      </td>
                      <td className="px-3 py-2">
                        <p>{row.patient_name}</p>
                        <p className="text-xs text-slate-500">{row.patient_mrn}</p>
                      </td>
                      <td className="px-3 py-2">
                        <p className="font-semibold">{row.service_type}</p>
                        <p className="text-xs text-slate-500">{row.service_description}</p>
                      </td>
                      <td className="px-3 py-2">{money(row.service_fee)}</td>
                      <td className="px-3 py-2">
                        <span
                          className={`rounded-full px-2.5 py-1 text-xs font-bold ${
                            row.feed_status === "PAID" ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-700"
                          }`}
                        >
                          {row.feed_status === "PAID" ? "PAID" : "PENDING"}
                        </span>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          <h3 className="mt-6 text-lg font-bold">Patient Revenue Ledger</h3>
          <div className="mt-3 overflow-auto rounded-xl border border-slate-200">
            <table className="min-w-full text-sm">
              <thead className="bg-slate-50">
                <tr>
                  <th className="px-3 py-2 text-left">Invoice</th>
                  <th className="px-3 py-2 text-left">Patient</th>
                  <th className="px-3 py-2 text-left">Net</th>
                  <th className="px-3 py-2 text-left">Paid</th>
                  <th className="px-3 py-2 text-left">Status</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr><td colSpan={5} className="px-3 py-8 text-center text-slate-500">Loading...</td></tr>
                ) : ledger.length === 0 ? (
                  <tr><td colSpan={5} className="px-3 py-8 text-center text-slate-500">No ledger entries.</td></tr>
                ) : (
                  ledger.map((row) => (
                    <tr key={row.invoice_id} className="border-t border-slate-100">
                      <td className="px-3 py-2">
                        <p className="font-semibold">{row.invoice_number}</p>
                        <p className="text-xs text-slate-500">{row.invoice_date || "-"}</p>
                      </td>
                      <td className="px-3 py-2">
                        <p>{row.patient_name}</p>
                        <p className="text-xs text-slate-500">{row.patient_mrn}</p>
                      </td>
                      <td className="px-3 py-2">{money(row.net_amount)}</td>
                      <td className="px-3 py-2">{money(row.paid_amount)}</td>
                      <td className="px-3 py-2">
                        <span className={`rounded-full px-2.5 py-1 text-xs font-bold ${
                          row.billing_status === "PAID" ? "bg-emerald-100 text-emerald-700" : "bg-rose-100 text-rose-700"
                        }`}>
                          {row.billing_status}
                        </span>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          <div className="mt-4 overflow-auto rounded-xl border border-slate-200">
            <table className="min-w-full text-sm">
              <thead className="bg-slate-50">
                <tr>
                  <th className="px-3 py-2 text-left">Recent Expenses</th>
                  <th className="px-3 py-2 text-left">Category</th>
                  <th className="px-3 py-2 text-left">Amount</th>
                </tr>
              </thead>
              <tbody>
                {expenses.slice(0, 10).map((e) => (
                  <tr key={e.expense_id} className="border-t border-slate-100">
                    <td className="px-3 py-2 text-xs text-slate-600">{e.date_incurred}</td>
                    <td className="px-3 py-2">{e.category}</td>
                    <td className="px-3 py-2">{money(e.amount)}</td>
                  </tr>
                ))}
                {expenses.length === 0 ? (
                  <tr><td colSpan={3} className="px-3 py-6 text-center text-slate-500">No expenses recorded for this month.</td></tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </article>
      </section>
    </AccountsWorkspaceLayout>
  );
}
