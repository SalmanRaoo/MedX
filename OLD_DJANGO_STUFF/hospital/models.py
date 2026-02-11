from django.db import models
from django.contrib.auth.models import AbstractUser

# --- MODULE 1: USERS & AUTH ---
class User(AbstractUser):
    ROLE_CHOICES = (
        ('ADMIN', 'Admin'),
        ('DOCTOR', 'Doctor'),
        ('PATIENT', 'Patient'),
        ('STAFF', 'Staff'),
    )
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='PATIENT')
    phone_number = models.CharField(max_length=15, blank=True)

class Department(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.name

class DoctorProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='doctor_profile')
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True)
    specialization = models.CharField(max_length=100)
    license_number = models.CharField(max_length=50)
    is_available = models.BooleanField(default=True) # For Workforce Optimization AI

class PatientProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='patient_profile')
    date_of_birth = models.DateField()
    blood_group = models.CharField(max_length=5)
    medical_history_summary = models.TextField(blank=True) # AI can summarize this later

# --- MODULE 2: OPD & APPOINTMENTS ---
class Appointment(models.Model):
    STATUS_CHOICES = (
        ('PENDING', 'Pending'),
        ('CONFIRMED', 'Confirmed'),
        ('COMPLETED', 'Completed'),
        ('CANCELLED', 'Cancelled'),
    )
    patient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='appointments')
    doctor = models.ForeignKey(DoctorProfile, on_delete=models.CASCADE)
    date_time = models.DateTimeField()
    symptoms = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    
    # Field for AI Predicted Duration (Workforce Optimization)
    predicted_duration_minutes = models.IntegerField(null=True, blank=True)

# --- MODULE 3: EHR & AI DIAGNOSIS ---
class MedicalRecord(models.Model):
    appointment = models.OneToOneField(Appointment, on_delete=models.CASCADE)
    diagnosis = models.TextField()
    doctor_notes = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

class RadiologyScan(models.Model):
    patient = models.ForeignKey(User, on_delete=models.CASCADE)
    scan_type = models.CharField(max_length=50) # X-Ray, MRI, CT
    image = models.ImageField(upload_to='radiology_scans/') # Stores path, not blob
    uploaded_at = models.DateTimeField(auto_now_add=True)
    
    # --- AI INTEGRATION FIELDS ---
    ai_detected_disease = models.CharField(max_length=100, blank=True) # e.g., "Pneumonia"
    ai_confidence_score = models.FloatField(null=True, blank=True) # e.g., 98.5%
    is_verified_by_doctor = models.BooleanField(default=False)

class Prescription(models.Model):
    medical_record = models.ForeignKey(MedicalRecord, on_delete=models.CASCADE)
    medicine_name = models.CharField(max_length=100)
    dosage = models.CharField(max_length=100) # e.g., "10mg twice a day"
    duration_days = models.IntegerField()

# --- MODULE 4: IPD (ADMISSIONS) ---
class Bed(models.Model):
    ward_name = models.CharField(max_length=50) # ICU, General Ward
    bed_number = models.CharField(max_length=10)
    is_occupied = models.BooleanField(default=False)
    daily_charge = models.DecimalField(max_digits=10, decimal_places=2)

class Admission(models.Model):
    patient = models.ForeignKey(User, on_delete=models.CASCADE)
    bed = models.ForeignKey(Bed, on_delete=models.CASCADE)
    admission_date = models.DateTimeField(auto_now_add=True)
    discharge_date = models.DateTimeField(null=True, blank=True)
    
    # AI Risk Prediction (Readmission Risk)
    readmission_risk_score = models.FloatField(null=True, blank=True)

# --- MODULE 5: FINANCE ---
class Invoice(models.Model):
    patient = models.ForeignKey(User, on_delete=models.CASCADE)
    admission = models.ForeignKey(Admission, on_delete=models.SET_NULL, null=True, blank=True)
    appointment = models.ForeignKey(Appointment, on_delete=models.SET_NULL, null=True, blank=True)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    is_paid = models.BooleanField(default=False)
    issued_date = models.DateField(auto_now_add=True)

class Expense(models.Model):
    # For your Financial Analytics AI
    category = models.CharField(max_length=100) # Salary, Maintenance, Equipment
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    date = models.DateField()
    description = models.TextField()