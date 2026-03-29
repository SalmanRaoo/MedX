import { Routes, Route } from "react-router-dom";
import DashboardLayout from "./DashboardLayout";
import StaffPatients from "./StaffPatients"; // Ensure the import name matches your file
import Settings from "./Settings";

export default function DashboardRouter() {
  return (
    <Routes>
      {/* This is your main dashboard */}
      <Route path="/" element={<DashboardLayout />} />
      
      {/* Add this specific route for your new page */}
      <Route path="/staff-patients" element={<StaffPatients />} />
      
      <Route path="/settings" element={<Settings />} />
    </Routes>
  );
}