import RoleDashboardShell from "../../components/dashboards/RoleDashboardShell";
export default function NurseDashboard() {
  return <RoleDashboardShell title="Nurse Dashboard" subtitle="Ward operations, vitals, and bedside tasks." cards={[{ title: "Assigned Wards", text: "Monitor active patients and room occupancy." }, { title: "Vitals Queue", text: "Record and review scheduled vitals rounds." }, { title: "Escalation Alerts", text: "Instantly escalate abnormal trends to doctors." }]} />;
}
