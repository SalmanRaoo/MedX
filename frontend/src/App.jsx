import { BrowserRouter as Router, Routes, Route } from "react-router-dom";
import Navbar from "./components/Navbar";
import { GuestRoute, ProtectedRoute, RoleRoute } from "./components/RouteGuards";

import Home from "./pages/Home";
import About from "./pages/About";
import Pricing from "./pages/Pricing";
import Contact from "./pages/Contact";
import HospitalContacts from "./pages/HospitalContacts";
import BookAppointment from "./pages/BookAppointment";
import Login from "./pages/Login";
import StaffLogin from "./pages/StaffLogin";
import PatientLogin from "./pages/PatientLogin";
import SubscriptionOnboarding from "./pages/SubscriptionOnboarding";
import DashboardLanding from "./pages/DashboardLanding";
import DashboardLayout from "./pages/DashboardLayout";
import Settings from "./pages/Settings";
import StaffPatients from "./pages/StaffPatients";
import StaffHistoryPage from "./pages/StaffHistoryPage";
import PatientHistoryPage from "./pages/PatientHistoryPage";
import AdminUserAccessPage from "./pages/AdminUserAccessPage";
import AccountSecurity from "./pages/AccountSecurity";
import SuperAdminDashboard from "./pages/dashboards/SuperAdminDashboard";
import SuperAdminBlockedUsersPage from "./pages/dashboards/SuperAdminBlockedUsersPage";
import DoctorDashboard from "./pages/dashboards/DoctorDashboard";
import DoctorMedicationsPage from "./pages/dashboards/DoctorMedicationsPage";
import DoctorClinicalPage from "./pages/dashboards/DoctorClinicalPage";
import DoctorSymptomsPage from "./pages/dashboards/DoctorSymptomsPage";
import DoctorPatientsPage from "./pages/dashboards/DoctorPatientsPage";
import DoctorAIImagingLabPage from "./pages/dashboards/DoctorAIImagingLabPage";
import DoctorImagingReportsPage from "./pages/dashboards/DoctorImagingReportsPage";
import DoctorLabReportsPage from "./pages/dashboards/DoctorLabReportsPage";
import NurseDashboard from "./pages/dashboards/NurseDashboard";
import ReceptionDashboard from "./pages/dashboards/ReceptionDashboard";
import ReceptionPatientsPage from "./pages/dashboards/ReceptionPatientsPage";
import ReceptionAdmissionsPage from "./pages/dashboards/ReceptionAdmissionsPage";
import ReceptionRadiologyBillingHub from "./pages/dashboards/ReceptionRadiologyBillingHub";
import PharmacyDashboard from "./pages/dashboards/PharmacyDashboard";
import LabDashboard from "./pages/dashboards/LabDashboard";
import LabReportsPage from "./pages/dashboards/LabReportsPage";
import LabReportGeneratorPage from "./pages/dashboards/LabReportGeneratorPage";
import RadiologyDashboard from "./pages/dashboards/RadiologyDashboard";
import RadiologyReportsPage from "./pages/dashboards/RadiologyReportsPage";
import FinanceDashboard from "./pages/dashboards/FinanceDashboard";
import FleetDashboard from "./pages/dashboards/FleetDashboard";
import OperationsDashboard from "./pages/dashboards/OperationsDashboard";
import PatientDashboard from "./pages/dashboards/PatientDashboard";
import PatientReportsPage from "./pages/dashboards/PatientReportsPage";
import { HospitalSettingsProvider } from "./context/HospitalSettingsContext";

function PublicLayout({ children }) {
  return (
    <>
      <Navbar />
      {children}
    </>
  );
}

function App() {
  return (
    <HospitalSettingsProvider>
      <Router>
        <div className="min-h-screen bg-app text-slate-900">
          <Routes>
          <Route path="/" element={<PublicLayout><Home /></PublicLayout>} />
          <Route path="/about" element={<PublicLayout><About /></PublicLayout>} />
          <Route path="/pricing" element={<PublicLayout><Pricing /></PublicLayout>} />
          <Route path="/contact" element={<PublicLayout><Contact /></PublicLayout>} />
          <Route path="/hospital-contacts" element={<PublicLayout><HospitalContacts /></PublicLayout>} />
          <Route path="/book-appointment" element={<PublicLayout><BookAppointment /></PublicLayout>} />
          <Route path="/subscription/onboarding" element={<PublicLayout><SubscriptionOnboarding /></PublicLayout>} />

          <Route path="/login" element={<GuestRoute><Login /></GuestRoute>} />
          <Route path="/login/staff" element={<GuestRoute><StaffLogin /></GuestRoute>} />
          <Route path="/login/patient" element={<GuestRoute><PatientLogin /></GuestRoute>} />

          <Route path="/dashboard" element={<ProtectedRoute><DashboardLanding /></ProtectedRoute>} />
          <Route path="/dashboard/account" element={<ProtectedRoute><AccountSecurity /></ProtectedRoute>} />

          <Route path="/dashboard/super-admin" element={<ProtectedRoute><RoleRoute allowedRoles={["SUPER_ADMIN"]}><SuperAdminDashboard /></RoleRoute></ProtectedRoute>} />
          <Route path="/dashboard/super-admin/blocked" element={<ProtectedRoute><RoleRoute allowedRoles={["SUPER_ADMIN"]}><SuperAdminBlockedUsersPage /></RoleRoute></ProtectedRoute>} />

          <Route path="/dashboard/admin" element={<ProtectedRoute><RoleRoute allowedRoles={["ADMIN", "SUPER_ADMIN"]}><DashboardLayout /></RoleRoute></ProtectedRoute>} />
          <Route path="/dashboard/settings" element={<ProtectedRoute><RoleRoute allowedRoles={["ADMIN", "SUPER_ADMIN"]}><Settings /></RoleRoute></ProtectedRoute>} />
          <Route path="/dashboard/staff-patients" element={<ProtectedRoute><RoleRoute allowedRoles={["ADMIN", "SUPER_ADMIN"]}><StaffPatients /></RoleRoute></ProtectedRoute>} />
          <Route path="/dashboard/staff-history/:staffId" element={<ProtectedRoute><RoleRoute allowedRoles={["ADMIN", "SUPER_ADMIN"]}><StaffHistoryPage /></RoleRoute></ProtectedRoute>} />
          <Route path="/dashboard/patient-history/:patientId" element={<ProtectedRoute><RoleRoute allowedRoles={["ADMIN", "SUPER_ADMIN"]}><PatientHistoryPage /></RoleRoute></ProtectedRoute>} />
          <Route path="/dashboard/user-access" element={<ProtectedRoute><RoleRoute allowedRoles={["ADMIN", "SUPER_ADMIN"]}><AdminUserAccessPage /></RoleRoute></ProtectedRoute>} />

          <Route path="/dashboard/doctor" element={<ProtectedRoute><RoleRoute allowedRoles={["DOCTOR", "ADMIN", "SUPER_ADMIN"]}><DoctorDashboard /></RoleRoute></ProtectedRoute>} />
          <Route path="/dashboard/doctor/medications" element={<ProtectedRoute><RoleRoute allowedRoles={["DOCTOR", "ADMIN", "SUPER_ADMIN"]}><DoctorMedicationsPage /></RoleRoute></ProtectedRoute>} />
          <Route path="/dashboard/doctor/clinical" element={<ProtectedRoute><RoleRoute allowedRoles={["DOCTOR", "ADMIN", "SUPER_ADMIN"]}><DoctorClinicalPage /></RoleRoute></ProtectedRoute>} />
          <Route path="/dashboard/doctor/symptoms" element={<ProtectedRoute><RoleRoute allowedRoles={["DOCTOR", "ADMIN", "SUPER_ADMIN"]}><DoctorSymptomsPage /></RoleRoute></ProtectedRoute>} />
          <Route path="/dashboard/doctor/patients" element={<ProtectedRoute><RoleRoute allowedRoles={["DOCTOR", "ADMIN", "SUPER_ADMIN"]}><DoctorPatientsPage /></RoleRoute></ProtectedRoute>} />
          <Route path="/dashboard/doctor/ai-imaging-lab" element={<ProtectedRoute><RoleRoute allowedRoles={["DOCTOR", "ADMIN", "SUPER_ADMIN"]}><DoctorAIImagingLabPage /></RoleRoute></ProtectedRoute>} />
          <Route path="/dashboard/doctor/imaging-reports" element={<ProtectedRoute><RoleRoute allowedRoles={["DOCTOR", "ADMIN", "SUPER_ADMIN"]}><DoctorImagingReportsPage /></RoleRoute></ProtectedRoute>} />
          <Route path="/dashboard/doctor/lab-reports" element={<ProtectedRoute><RoleRoute allowedRoles={["DOCTOR", "ADMIN", "SUPER_ADMIN"]}><DoctorLabReportsPage /></RoleRoute></ProtectedRoute>} />

          <Route path="/dashboard/nurse" element={<ProtectedRoute><RoleRoute allowedRoles={["NURSE", "ADMIN", "SUPER_ADMIN"]}><NurseDashboard /></RoleRoute></ProtectedRoute>} />
          <Route path="/dashboard/reception" element={<ProtectedRoute><RoleRoute allowedRoles={["RECEPTIONIST", "ADMIN", "SUPER_ADMIN"]}><ReceptionDashboard /></RoleRoute></ProtectedRoute>} />
          <Route path="/dashboard/reception/patients" element={<ProtectedRoute><RoleRoute allowedRoles={["RECEPTIONIST", "ADMIN", "SUPER_ADMIN"]}><ReceptionPatientsPage /></RoleRoute></ProtectedRoute>} />
          <Route path="/dashboard/reception/admissions" element={<ProtectedRoute><RoleRoute allowedRoles={["RECEPTIONIST", "ADMIN", "SUPER_ADMIN"]}><ReceptionAdmissionsPage /></RoleRoute></ProtectedRoute>} />
          <Route path="/dashboard/reception/radiology-billing" element={<ProtectedRoute><RoleRoute allowedRoles={["RECEPTIONIST", "ADMIN", "SUPER_ADMIN"]}><ReceptionRadiologyBillingHub /></RoleRoute></ProtectedRoute>} />
          <Route path="/dashboard/pharmacy" element={<ProtectedRoute><RoleRoute allowedRoles={["PHARMACY", "ADMIN", "SUPER_ADMIN"]}><PharmacyDashboard /></RoleRoute></ProtectedRoute>} />
          <Route path="/dashboard/lab" element={<ProtectedRoute><RoleRoute allowedRoles={["LAB", "ADMIN", "SUPER_ADMIN"]}><LabDashboard /></RoleRoute></ProtectedRoute>} />
          <Route path="/dashboard/lab/generate" element={<ProtectedRoute><RoleRoute allowedRoles={["LAB", "ADMIN", "SUPER_ADMIN"]}><LabReportGeneratorPage /></RoleRoute></ProtectedRoute>} />
          <Route path="/dashboard/lab/reports" element={<ProtectedRoute><RoleRoute allowedRoles={["LAB", "ADMIN", "SUPER_ADMIN"]}><LabReportsPage /></RoleRoute></ProtectedRoute>} />
          <Route path="/dashboard/radiology" element={<ProtectedRoute><RoleRoute allowedRoles={["DOCTOR", "RADIOLOGIST", "ADMIN", "SUPER_ADMIN"]}><RadiologyDashboard /></RoleRoute></ProtectedRoute>} />
          <Route path="/dashboard/radiology/reports" element={<ProtectedRoute><RoleRoute allowedRoles={["DOCTOR", "RADIOLOGIST", "ADMIN", "SUPER_ADMIN"]}><RadiologyReportsPage /></RoleRoute></ProtectedRoute>} />
          <Route path="/dashboard/finance" element={<ProtectedRoute><RoleRoute allowedRoles={["ACCOUNTANT", "SUPER_ADMIN"]}><FinanceDashboard /></RoleRoute></ProtectedRoute>} />
          <Route path="/dashboard/fleet" element={<ProtectedRoute><RoleRoute allowedRoles={["FLEET", "ACCOUNTANT", "SUPER_ADMIN"]}><FleetDashboard /></RoleRoute></ProtectedRoute>} />
          <Route path="/dashboard/operations" element={<ProtectedRoute><RoleRoute allowedRoles={["OPERATIONS", "ADMIN", "SUPER_ADMIN"]}><OperationsDashboard /></RoleRoute></ProtectedRoute>} />
          <Route path="/dashboard/patient" element={<ProtectedRoute><RoleRoute allowedRoles={["PATIENT", "ADMIN", "SUPER_ADMIN"]}><PatientDashboard /></RoleRoute></ProtectedRoute>} />
          <Route path="/dashboard/patient/reports" element={<ProtectedRoute><RoleRoute allowedRoles={["PATIENT", "ADMIN", "SUPER_ADMIN"]}><PatientReportsPage /></RoleRoute></ProtectedRoute>} />

          </Routes>
        </div>
      </Router>
    </HospitalSettingsProvider>
  );
}

export default App;


