from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Float, Date, DateTime, Text
from database import Base
from datetime import datetime

# ======================= 1. SECURITY & AUDIT =======================
class User(Base):
    __tablename__ = "users"
    user_id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    password_hash = Column(String)
    user_type = Column(String)

class AuditLog(Base):
    __tablename__ = "audit_logs"
    log_id = Column(Integer, primary_key=True, index=True)
    action = Column(String); details = Column(String); performed_by = Column(String)
    timestamp = Column(DateTime, default=datetime.utcnow)

# ======================= 2. STAFF & HR =======================
class Department(Base):
    __tablename__ = "departments"
    department_id = Column(Integer, primary_key=True, index=True)
    department_name = Column(String, unique=True); location = Column(String)

class Staff(Base):
    __tablename__ = "staff"
    staff_id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String); role = Column(String); phone_number = Column(String)
    department_id = Column(Integer, ForeignKey("departments.department_id"), nullable=True)

class DoctorDetails(Base):
    __tablename__ = "doctor_details"
    id = Column(Integer, primary_key=True, index=True)
    doctor_id = Column(Integer, ForeignKey("staff.staff_id"), unique=True)
    specialization = Column(String); consultation_fee = Column(Float); doctor_share_percentage = Column(Float, default=0.70)

class StaffSchedule(Base):
    __tablename__ = "staff_schedules"
    schedule_id = Column(Integer, primary_key=True, index=True)
    staff_id = Column(Integer, ForeignKey("staff.staff_id")); day_of_week = Column(String); shift_type = Column(String)

class LeaveRequest(Base):
    __tablename__ = "leave_requests"
    leave_id = Column(Integer, primary_key=True, index=True)
    staff_id = Column(Integer, ForeignKey("staff.staff_id"))
    start_date = Column(Date); end_date = Column(Date); reason = Column(String); status = Column(String, default="Pending")

# ======================= 3. PATIENT CARE =======================
class InsuranceProvider(Base):
    __tablename__ = "insurance_providers"
    provider_id = Column(Integer, primary_key=True, index=True)
    provider_name = Column(String, unique=True); coverage_limit = Column(Float)

class Patient(Base):
    __tablename__ = "patients"
    patient_id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String); dob = Column(Date); gender = Column(String); phone_number = Column(String)
    insurance_provider_id = Column(Integer, ForeignKey("insurance_providers.provider_id"), nullable=True)

class Appointment(Base):
    __tablename__ = "appointments"
    appointment_id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.patient_id"))
    doctor_id = Column(Integer, ForeignKey("staff.staff_id"))
    appointment_date = Column(DateTime); status = Column(String, default="Scheduled")
    type = Column(String, default="In-Person"); video_link = Column(String, nullable=True)

class Prescription(Base):
    __tablename__ = "prescriptions"
    prescription_id = Column(Integer, primary_key=True, index=True)
    appointment_id = Column(Integer, ForeignKey("appointments.appointment_id"))
    medicine_name = Column(String); dosage = Column(String); notes = Column(String)
    issued_at = Column(DateTime, default=datetime.utcnow)

class PatientVitals(Base):
    __tablename__ = "patient_vitals"
    vitals_id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.patient_id"))
    body_temperature = Column(Float); blood_pressure_systolic = Column(Integer); blood_pressure_diastolic = Column(Integer); ai_risk_score = Column(Float)
    recorded_at = Column(DateTime, default=datetime.utcnow)

class PatientFeedback(Base):
    __tablename__ = "patient_feedback"
    feedback_id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.patient_id")); rating = Column(Integer); comments = Column(String)

class Vaccination(Base):
    __tablename__ = "vaccinations"
    vaccine_id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.patient_id"))
    vaccine_name = Column(String); date_administered = Column(Date); next_due_date = Column(Date, nullable=True)

# ======================= 4. CLINICAL & LABS =======================
class LabTest(Base):
    __tablename__ = "lab_tests"
    test_id = Column(Integer, primary_key=True, index=True); test_name = Column(String); cost = Column(Float)

class LabRequest(Base):
    __tablename__ = "lab_requests"
    request_id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.patient_id")); test_id = Column(Integer, ForeignKey("lab_tests.test_id"))
    status = Column(String, default="Ordered"); result_notes = Column(Text, nullable=True); report_file_path = Column(String, nullable=True)

class OperationTheater(Base):
    __tablename__ = "operation_theaters"
    ot_id = Column(Integer, primary_key=True, index=True); room_number = Column(String); hourly_charge = Column(Float)

class Surgery(Base):
    __tablename__ = "surgeries"
    surgery_id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.patient_id")); ot_id = Column(Integer, ForeignKey("operation_theaters.ot_id"))
    surgery_name = Column(String); total_cost = Column(Float); status = Column(String, default="Scheduled")

class BloodInventory(Base):
    __tablename__ = "blood_inventory"
    blood_id = Column(Integer, primary_key=True, index=True); blood_group = Column(String, unique=True); bags_available = Column(Integer)

class MortuaryFreezer(Base):
    __tablename__ = "mortuary_freezers"
    freezer_id = Column(Integer, primary_key=True, index=True); freezer_number = Column(String); is_occupied = Column(Boolean, default=False); deceased_name = Column(String, nullable=True)

# ======================= 5. IPD & ASSETS =======================
class Bed(Base):
    __tablename__ = "beds"
    bed_id = Column(Integer, primary_key=True, index=True); bed_number = Column(String); is_occupied = Column(Boolean, default=False); daily_charge = Column(Float)

class Admission(Base):
    __tablename__ = "admissions"
    admission_id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.patient_id")); bed_id = Column(Integer, ForeignKey("beds.bed_id"))
    admission_date = Column(DateTime, default=datetime.utcnow); discharge_date = Column(DateTime, nullable=True)

class NursingRound(Base):
    __tablename__ = "nursing_rounds"
    round_id = Column(Integer, primary_key=True, index=True)
    admission_id = Column(Integer, ForeignKey("admissions.admission_id")); nurse_id = Column(Integer, ForeignKey("staff.staff_id")); observation_notes = Column(Text)

class Asset(Base):
    __tablename__ = "assets"
    asset_id = Column(Integer, primary_key=True, index=True); asset_name = Column(String); status = Column(String)

class Ambulance(Base):
    __tablename__ = "ambulances"
    vehicle_id = Column(Integer, primary_key=True, index=True); vehicle_number = Column(String, unique=True); status = Column(String, default="Available")

# ======================= 6. INVENTORY & FINANCE =======================
class Medicine(Base):
    __tablename__ = "medicines"
    medicine_id = Column(Integer, primary_key=True, index=True); medicine_name = Column(String); unit_price = Column(Float)

class MedicineBatch(Base):
    __tablename__ = "medicine_batches"
    batch_id = Column(Integer, primary_key=True, index=True)
    medicine_id = Column(Integer, ForeignKey("medicines.medicine_id")); quantity_available = Column(Integer); batch_number = Column(String)

class PharmacySale(Base):
    __tablename__ = "pharmacy_sales"
    sale_id = Column(Integer, primary_key=True, index=True); patient_id = Column(Integer, ForeignKey("patients.patient_id")); total_amount = Column(Float); sale_date = Column(DateTime, default=datetime.utcnow)

class Expense(Base):
    __tablename__ = "expenses"
    expense_id = Column(Integer, primary_key=True, index=True); category = Column(String); amount = Column(Float); date_incurred = Column(Date); description = Column(String)

# ======================= 7. LEGAL =======================
class BirthCertificate(Base):
    __tablename__ = "birth_certificates"
    cert_id = Column(Integer, primary_key=True, index=True); mother_patient_id = Column(Integer, ForeignKey("patients.patient_id")); baby_name = Column(String); birth_date = Column(DateTime); gender = Column(String)

class DeathCertificate(Base):
    __tablename__ = "death_certificates"
    cert_id = Column(Integer, primary_key=True, index=True); patient_id = Column(Integer, ForeignKey("patients.patient_id")); death_date = Column(DateTime); cause_of_death = Column(String)