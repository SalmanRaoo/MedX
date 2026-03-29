import RoleDashboardShell from "../../components/dashboards/RoleDashboardShell";
export default function FinanceDashboard() {
  return <RoleDashboardShell title="Finance Dashboard" subtitle="Revenue, claims, and expense control." cards={[{ title: "Receivables", text: "Track outstanding invoices and payments." }, { title: "Claims", text: "Manage insurance claim cycles." }, { title: "Expense Watch", text: "Audit cost centers and high spend areas." }]} />;
}
