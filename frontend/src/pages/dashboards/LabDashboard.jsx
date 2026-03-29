import RoleDashboardShell from "../../components/dashboards/RoleDashboardShell";
export default function LabDashboard() {
  return <RoleDashboardShell title="Lab Dashboard" subtitle="Sample processing, test status, and report release." cards={[{ title: "Pending Samples", text: "View queued test samples." }, { title: "Result Validation", text: "Approve and release final lab reports." }, { title: "Turnaround Time", text: "Monitor SLA against test categories." }]} />;
}
