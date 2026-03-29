import RoleDashboardShell from "../../components/dashboards/RoleDashboardShell";
export default function OperationsDashboard() {
  return <RoleDashboardShell title="Operations Dashboard" subtitle="Hospital-wide process quality and throughput." cards={[{ title: "Bed Utilization", text: "Track occupancy and discharge flow." }, { title: "Service Bottlenecks", text: "Identify high-delay process points." }, { title: "Quality Metrics", text: "Monitor service quality indicators." }]} />;
}
