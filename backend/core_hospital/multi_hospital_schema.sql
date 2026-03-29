PRAGMA foreign_keys = ON;

-- Multi-hospital (multi-tenant) schema with strict tenant isolation.
-- Isolation rule: every hospital-scoped table includes hospital_id, and
-- cross-table references use composite FKs (hospital_id, entity_id).

BEGIN TRANSACTION;

CREATE TABLE IF NOT EXISTS hospitals (
    hospital_id INTEGER PRIMARY KEY,
    hospital_code TEXT NOT NULL UNIQUE,
    hospital_name TEXT NOT NULL,
    address TEXT,
    phone_contact TEXT,
    email_contact TEXT,
    emergency_line TEXT,
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS roles (
    role_id INTEGER PRIMARY KEY,
    role_name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS hospital_user_memberships (
    membership_id INTEGER PRIMARY KEY,
    hospital_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    role_id INTEGER NOT NULL,
    staff_id INTEGER,
    is_primary INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (hospital_id, user_id),
    UNIQUE (hospital_id, membership_id),
    FOREIGN KEY (hospital_id) REFERENCES hospitals(hospital_id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (role_id) REFERENCES roles(role_id)
);

CREATE TABLE IF NOT EXISTS departments (
    department_id INTEGER PRIMARY KEY,
    hospital_id INTEGER NOT NULL,
    department_name TEXT NOT NULL,
    location TEXT,
    UNIQUE (hospital_id, department_id),
    UNIQUE (hospital_id, department_name),
    FOREIGN KEY (hospital_id) REFERENCES hospitals(hospital_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS staff (
    staff_id INTEGER PRIMARY KEY,
    hospital_id INTEGER NOT NULL,
    user_id INTEGER,
    full_name TEXT NOT NULL,
    role TEXT NOT NULL,
    phone_number TEXT,
    department_id INTEGER,
    license_number TEXT,
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (hospital_id, staff_id),
    UNIQUE (hospital_id, license_number),
    FOREIGN KEY (hospital_id) REFERENCES hospitals(hospital_id) ON DELETE CASCADE,
    FOREIGN KEY (hospital_id, department_id) REFERENCES departments(hospital_id, department_id),
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS doctor_details (
    doctor_detail_id INTEGER PRIMARY KEY,
    hospital_id INTEGER NOT NULL,
    doctor_staff_id INTEGER NOT NULL,
    specialization TEXT NOT NULL,
    consultation_fee REAL NOT NULL DEFAULT 0,
    doctor_share_percentage REAL NOT NULL DEFAULT 0.70,
    UNIQUE (hospital_id, doctor_detail_id),
    UNIQUE (hospital_id, doctor_staff_id),
    FOREIGN KEY (hospital_id) REFERENCES hospitals(hospital_id) ON DELETE CASCADE,
    FOREIGN KEY (hospital_id, doctor_staff_id) REFERENCES staff(hospital_id, staff_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS staff_schedules (
    schedule_id INTEGER PRIMARY KEY,
    hospital_id INTEGER NOT NULL,
    staff_id INTEGER NOT NULL,
    day_of_week TEXT NOT NULL,
    shift_type TEXT NOT NULL,
    start_time TEXT,
    end_time TEXT,
    UNIQUE (hospital_id, schedule_id),
    FOREIGN KEY (hospital_id) REFERENCES hospitals(hospital_id) ON DELETE CASCADE,
    FOREIGN KEY (hospital_id, staff_id) REFERENCES staff(hospital_id, staff_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS leave_requests (
    leave_id INTEGER PRIMARY KEY,
    hospital_id INTEGER NOT NULL,
    staff_id INTEGER NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    reason TEXT,
    status TEXT NOT NULL DEFAULT 'PENDING',
    UNIQUE (hospital_id, leave_id),
    FOREIGN KEY (hospital_id) REFERENCES hospitals(hospital_id) ON DELETE CASCADE,
    FOREIGN KEY (hospital_id, staff_id) REFERENCES staff(hospital_id, staff_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS insurance_providers (
    provider_id INTEGER PRIMARY KEY,
    hospital_id INTEGER NOT NULL,
    provider_name TEXT NOT NULL,
    coverage_limit REAL,
    UNIQUE (hospital_id, provider_id),
    UNIQUE (hospital_id, provider_name),
    FOREIGN KEY (hospital_id) REFERENCES hospitals(hospital_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS patients (
    patient_id INTEGER PRIMARY KEY,
    hospital_id INTEGER NOT NULL,
    patient_mrn TEXT NOT NULL,
    full_name TEXT NOT NULL,
    dob TEXT,
    gender TEXT,
    phone_number TEXT,
    insurance_provider_id INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (hospital_id, patient_id),
    UNIQUE (hospital_id, patient_mrn),
    FOREIGN KEY (hospital_id) REFERENCES hospitals(hospital_id) ON DELETE CASCADE,
    FOREIGN KEY (hospital_id, insurance_provider_id) REFERENCES insurance_providers(hospital_id, provider_id)
);

CREATE TABLE IF NOT EXISTS appointments (
    appointment_id INTEGER PRIMARY KEY,
    hospital_id INTEGER NOT NULL,
    patient_id INTEGER NOT NULL,
    doctor_id INTEGER NOT NULL,
    appointment_date TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'SCHEDULED',
    appointment_type TEXT NOT NULL DEFAULT 'IN_PERSON',
    video_link TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (hospital_id, appointment_id),
    FOREIGN KEY (hospital_id) REFERENCES hospitals(hospital_id) ON DELETE CASCADE,
    FOREIGN KEY (hospital_id, patient_id) REFERENCES patients(hospital_id, patient_id) ON DELETE CASCADE,
    FOREIGN KEY (hospital_id, doctor_id) REFERENCES staff(hospital_id, staff_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS prescriptions (
    prescription_id INTEGER PRIMARY KEY,
    hospital_id INTEGER NOT NULL,
    appointment_id INTEGER NOT NULL,
    prescribed_by_staff_id INTEGER NOT NULL,
    notes TEXT,
    issued_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (hospital_id, prescription_id),
    FOREIGN KEY (hospital_id) REFERENCES hospitals(hospital_id) ON DELETE CASCADE,
    FOREIGN KEY (hospital_id, appointment_id) REFERENCES appointments(hospital_id, appointment_id) ON DELETE CASCADE,
    FOREIGN KEY (hospital_id, prescribed_by_staff_id) REFERENCES staff(hospital_id, staff_id)
);

CREATE TABLE IF NOT EXISTS prescription_items (
    prescription_item_id INTEGER PRIMARY KEY,
    hospital_id INTEGER NOT NULL,
    prescription_id INTEGER NOT NULL,
    medicine_name TEXT NOT NULL,
    dosage TEXT NOT NULL,
    instructions TEXT,
    duration_days INTEGER,
    UNIQUE (hospital_id, prescription_item_id),
    FOREIGN KEY (hospital_id) REFERENCES hospitals(hospital_id) ON DELETE CASCADE,
    FOREIGN KEY (hospital_id, prescription_id) REFERENCES prescriptions(hospital_id, prescription_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS patient_vitals (
    vitals_id INTEGER PRIMARY KEY,
    hospital_id INTEGER NOT NULL,
    patient_id INTEGER NOT NULL,
    body_temperature REAL,
    blood_pressure_systolic INTEGER,
    blood_pressure_diastolic INTEGER,
    pulse_rate INTEGER,
    oxygen_saturation REAL,
    ai_risk_score REAL,
    recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    recorded_by_staff_id INTEGER,
    UNIQUE (hospital_id, vitals_id),
    FOREIGN KEY (hospital_id) REFERENCES hospitals(hospital_id) ON DELETE CASCADE,
    FOREIGN KEY (hospital_id, patient_id) REFERENCES patients(hospital_id, patient_id) ON DELETE CASCADE,
    FOREIGN KEY (hospital_id, recorded_by_staff_id) REFERENCES staff(hospital_id, staff_id)
);

CREATE TABLE IF NOT EXISTS patient_feedback (
    feedback_id INTEGER PRIMARY KEY,
    hospital_id INTEGER NOT NULL,
    patient_id INTEGER NOT NULL,
    rating INTEGER NOT NULL,
    comments TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (hospital_id, feedback_id),
    FOREIGN KEY (hospital_id) REFERENCES hospitals(hospital_id) ON DELETE CASCADE,
    FOREIGN KEY (hospital_id, patient_id) REFERENCES patients(hospital_id, patient_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS vaccinations (
    vaccine_id INTEGER PRIMARY KEY,
    hospital_id INTEGER NOT NULL,
    patient_id INTEGER NOT NULL,
    vaccine_name TEXT NOT NULL,
    date_administered TEXT NOT NULL,
    next_due_date TEXT,
    UNIQUE (hospital_id, vaccine_id),
    FOREIGN KEY (hospital_id) REFERENCES hospitals(hospital_id) ON DELETE CASCADE,
    FOREIGN KEY (hospital_id, patient_id) REFERENCES patients(hospital_id, patient_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS lab_tests (
    test_id INTEGER PRIMARY KEY,
    hospital_id INTEGER NOT NULL,
    test_name TEXT NOT NULL,
    cost REAL NOT NULL DEFAULT 0,
    UNIQUE (hospital_id, test_id),
    UNIQUE (hospital_id, test_name),
    FOREIGN KEY (hospital_id) REFERENCES hospitals(hospital_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS lab_requests (
    request_id INTEGER PRIMARY KEY,
    hospital_id INTEGER NOT NULL,
    patient_id INTEGER NOT NULL,
    test_id INTEGER NOT NULL,
    ordered_by_staff_id INTEGER,
    status TEXT NOT NULL DEFAULT 'ORDERED',
    result_notes TEXT,
    report_file_path TEXT,
    requested_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (hospital_id, request_id),
    FOREIGN KEY (hospital_id) REFERENCES hospitals(hospital_id) ON DELETE CASCADE,
    FOREIGN KEY (hospital_id, patient_id) REFERENCES patients(hospital_id, patient_id) ON DELETE CASCADE,
    FOREIGN KEY (hospital_id, test_id) REFERENCES lab_tests(hospital_id, test_id),
    FOREIGN KEY (hospital_id, ordered_by_staff_id) REFERENCES staff(hospital_id, staff_id)
);

CREATE TABLE IF NOT EXISTS operation_theaters (
    ot_id INTEGER PRIMARY KEY,
    hospital_id INTEGER NOT NULL,
    room_number TEXT NOT NULL,
    hourly_charge REAL NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1,
    UNIQUE (hospital_id, ot_id),
    UNIQUE (hospital_id, room_number),
    FOREIGN KEY (hospital_id) REFERENCES hospitals(hospital_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS surgeries (
    surgery_id INTEGER PRIMARY KEY,
    hospital_id INTEGER NOT NULL,
    patient_id INTEGER NOT NULL,
    ot_id INTEGER,
    lead_surgeon_id INTEGER,
    surgery_name TEXT NOT NULL,
    total_cost REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'SCHEDULED',
    surgery_date TEXT,
    UNIQUE (hospital_id, surgery_id),
    FOREIGN KEY (hospital_id) REFERENCES hospitals(hospital_id) ON DELETE CASCADE,
    FOREIGN KEY (hospital_id, patient_id) REFERENCES patients(hospital_id, patient_id) ON DELETE CASCADE,
    FOREIGN KEY (hospital_id, ot_id) REFERENCES operation_theaters(hospital_id, ot_id),
    FOREIGN KEY (hospital_id, lead_surgeon_id) REFERENCES staff(hospital_id, staff_id)
);

CREATE TABLE IF NOT EXISTS blood_inventory (
    blood_id INTEGER PRIMARY KEY,
    hospital_id INTEGER NOT NULL,
    blood_group TEXT NOT NULL,
    bags_available INTEGER NOT NULL DEFAULT 0,
    UNIQUE (hospital_id, blood_id),
    UNIQUE (hospital_id, blood_group),
    FOREIGN KEY (hospital_id) REFERENCES hospitals(hospital_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS mortuary_freezers (
    freezer_id INTEGER PRIMARY KEY,
    hospital_id INTEGER NOT NULL,
    freezer_number TEXT NOT NULL,
    is_occupied INTEGER NOT NULL DEFAULT 0,
    deceased_name TEXT,
    UNIQUE (hospital_id, freezer_id),
    UNIQUE (hospital_id, freezer_number),
    FOREIGN KEY (hospital_id) REFERENCES hospitals(hospital_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS ai_diagnoses (
    diagnosis_id INTEGER PRIMARY KEY,
    hospital_id INTEGER NOT NULL,
    patient_id INTEGER NOT NULL,
    doctor_id INTEGER,
    disease_category TEXT NOT NULL,
    prediction_result TEXT NOT NULL,
    confidence_score TEXT,
    scan_file_path TEXT,
    model_version TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (hospital_id, diagnosis_id),
    FOREIGN KEY (hospital_id) REFERENCES hospitals(hospital_id) ON DELETE CASCADE,
    FOREIGN KEY (hospital_id, patient_id) REFERENCES patients(hospital_id, patient_id) ON DELETE CASCADE,
    FOREIGN KEY (hospital_id, doctor_id) REFERENCES staff(hospital_id, staff_id)
);

CREATE TABLE IF NOT EXISTS beds (
    bed_id INTEGER PRIMARY KEY,
    hospital_id INTEGER NOT NULL,
    ward_name TEXT,
    bed_number TEXT NOT NULL,
    is_occupied INTEGER NOT NULL DEFAULT 0,
    daily_charge REAL NOT NULL DEFAULT 0,
    UNIQUE (hospital_id, bed_id),
    UNIQUE (hospital_id, bed_number),
    FOREIGN KEY (hospital_id) REFERENCES hospitals(hospital_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS admissions (
    admission_id INTEGER PRIMARY KEY,
    hospital_id INTEGER NOT NULL,
    patient_id INTEGER NOT NULL,
    bed_id INTEGER NOT NULL,
    admitted_by_staff_id INTEGER,
    admission_date TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    discharge_date TEXT,
    status TEXT NOT NULL DEFAULT 'ADMITTED',
    UNIQUE (hospital_id, admission_id),
    FOREIGN KEY (hospital_id) REFERENCES hospitals(hospital_id) ON DELETE CASCADE,
    FOREIGN KEY (hospital_id, patient_id) REFERENCES patients(hospital_id, patient_id) ON DELETE CASCADE,
    FOREIGN KEY (hospital_id, bed_id) REFERENCES beds(hospital_id, bed_id),
    FOREIGN KEY (hospital_id, admitted_by_staff_id) REFERENCES staff(hospital_id, staff_id)
);

CREATE TABLE IF NOT EXISTS nursing_rounds (
    round_id INTEGER PRIMARY KEY,
    hospital_id INTEGER NOT NULL,
    admission_id INTEGER NOT NULL,
    nurse_id INTEGER NOT NULL,
    observation_notes TEXT,
    recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (hospital_id, round_id),
    FOREIGN KEY (hospital_id) REFERENCES hospitals(hospital_id) ON DELETE CASCADE,
    FOREIGN KEY (hospital_id, admission_id) REFERENCES admissions(hospital_id, admission_id) ON DELETE CASCADE,
    FOREIGN KEY (hospital_id, nurse_id) REFERENCES staff(hospital_id, staff_id)
);

CREATE TABLE IF NOT EXISTS assets (
    asset_id INTEGER PRIMARY KEY,
    hospital_id INTEGER NOT NULL,
    asset_name TEXT NOT NULL,
    asset_type TEXT,
    serial_number TEXT,
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    UNIQUE (hospital_id, asset_id),
    UNIQUE (hospital_id, serial_number),
    FOREIGN KEY (hospital_id) REFERENCES hospitals(hospital_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS ambulances (
    vehicle_id INTEGER PRIMARY KEY,
    hospital_id INTEGER NOT NULL,
    vehicle_number TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'AVAILABLE',
    driver_name TEXT,
    UNIQUE (hospital_id, vehicle_id),
    UNIQUE (hospital_id, vehicle_number),
    FOREIGN KEY (hospital_id) REFERENCES hospitals(hospital_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS medicines (
    medicine_id INTEGER PRIMARY KEY,
    hospital_id INTEGER NOT NULL,
    medicine_name TEXT NOT NULL,
    unit_price REAL NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1,
    UNIQUE (hospital_id, medicine_id),
    UNIQUE (hospital_id, medicine_name),
    FOREIGN KEY (hospital_id) REFERENCES hospitals(hospital_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS medicine_batches (
    batch_id INTEGER PRIMARY KEY,
    hospital_id INTEGER NOT NULL,
    medicine_id INTEGER NOT NULL,
    batch_number TEXT NOT NULL,
    quantity_available INTEGER NOT NULL DEFAULT 0,
    expiry_date TEXT,
    UNIQUE (hospital_id, batch_id),
    UNIQUE (hospital_id, batch_number),
    FOREIGN KEY (hospital_id) REFERENCES hospitals(hospital_id) ON DELETE CASCADE,
    FOREIGN KEY (hospital_id, medicine_id) REFERENCES medicines(hospital_id, medicine_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS pharmacy_sales (
    sale_id INTEGER PRIMARY KEY,
    hospital_id INTEGER NOT NULL,
    patient_id INTEGER,
    sold_by_staff_id INTEGER,
    total_amount REAL NOT NULL DEFAULT 0,
    sale_date TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (hospital_id, sale_id),
    FOREIGN KEY (hospital_id) REFERENCES hospitals(hospital_id) ON DELETE CASCADE,
    FOREIGN KEY (hospital_id, patient_id) REFERENCES patients(hospital_id, patient_id),
    FOREIGN KEY (hospital_id, sold_by_staff_id) REFERENCES staff(hospital_id, staff_id)
);

CREATE TABLE IF NOT EXISTS pharmacy_sale_items (
    sale_item_id INTEGER PRIMARY KEY,
    hospital_id INTEGER NOT NULL,
    sale_id INTEGER NOT NULL,
    medicine_id INTEGER NOT NULL,
    batch_id INTEGER,
    quantity INTEGER NOT NULL,
    unit_price REAL NOT NULL,
    line_total REAL NOT NULL,
    UNIQUE (hospital_id, sale_item_id),
    FOREIGN KEY (hospital_id) REFERENCES hospitals(hospital_id) ON DELETE CASCADE,
    FOREIGN KEY (hospital_id, sale_id) REFERENCES pharmacy_sales(hospital_id, sale_id) ON DELETE CASCADE,
    FOREIGN KEY (hospital_id, medicine_id) REFERENCES medicines(hospital_id, medicine_id),
    FOREIGN KEY (hospital_id, batch_id) REFERENCES medicine_batches(hospital_id, batch_id)
);

CREATE TABLE IF NOT EXISTS expenses (
    expense_id INTEGER PRIMARY KEY,
    hospital_id INTEGER NOT NULL,
    category TEXT NOT NULL,
    amount REAL NOT NULL,
    date_incurred TEXT NOT NULL,
    description TEXT,
    recorded_by_staff_id INTEGER,
    UNIQUE (hospital_id, expense_id),
    FOREIGN KEY (hospital_id) REFERENCES hospitals(hospital_id) ON DELETE CASCADE,
    FOREIGN KEY (hospital_id, recorded_by_staff_id) REFERENCES staff(hospital_id, staff_id)
);

CREATE TABLE IF NOT EXISTS invoices (
    invoice_id INTEGER PRIMARY KEY,
    hospital_id INTEGER NOT NULL,
    patient_id INTEGER NOT NULL,
    invoice_number TEXT NOT NULL,
    invoice_date TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    gross_amount REAL NOT NULL DEFAULT 0,
    discount_amount REAL NOT NULL DEFAULT 0,
    net_amount REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'UNPAID',
    UNIQUE (hospital_id, invoice_id),
    UNIQUE (hospital_id, invoice_number),
    FOREIGN KEY (hospital_id) REFERENCES hospitals(hospital_id) ON DELETE CASCADE,
    FOREIGN KEY (hospital_id, patient_id) REFERENCES patients(hospital_id, patient_id)
);

CREATE TABLE IF NOT EXISTS invoice_items (
    invoice_item_id INTEGER PRIMARY KEY,
    hospital_id INTEGER NOT NULL,
    invoice_id INTEGER NOT NULL,
    item_type TEXT NOT NULL,
    reference_id INTEGER,
    description TEXT NOT NULL,
    quantity REAL NOT NULL DEFAULT 1,
    unit_price REAL NOT NULL DEFAULT 0,
    line_total REAL NOT NULL DEFAULT 0,
    UNIQUE (hospital_id, invoice_item_id),
    FOREIGN KEY (hospital_id) REFERENCES hospitals(hospital_id) ON DELETE CASCADE,
    FOREIGN KEY (hospital_id, invoice_id) REFERENCES invoices(hospital_id, invoice_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS payments (
    payment_id INTEGER PRIMARY KEY,
    hospital_id INTEGER NOT NULL,
    invoice_id INTEGER NOT NULL,
    amount_paid REAL NOT NULL,
    payment_method TEXT NOT NULL,
    payment_reference TEXT,
    paid_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    collected_by_staff_id INTEGER,
    UNIQUE (hospital_id, payment_id),
    FOREIGN KEY (hospital_id) REFERENCES hospitals(hospital_id) ON DELETE CASCADE,
    FOREIGN KEY (hospital_id, invoice_id) REFERENCES invoices(hospital_id, invoice_id) ON DELETE CASCADE,
    FOREIGN KEY (hospital_id, collected_by_staff_id) REFERENCES staff(hospital_id, staff_id)
);

CREATE TABLE IF NOT EXISTS birth_certificates (
    birth_cert_id INTEGER PRIMARY KEY,
    hospital_id INTEGER NOT NULL,
    mother_patient_id INTEGER NOT NULL,
    baby_name TEXT NOT NULL,
    birth_date TEXT NOT NULL,
    gender TEXT,
    issued_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (hospital_id, birth_cert_id),
    FOREIGN KEY (hospital_id) REFERENCES hospitals(hospital_id) ON DELETE CASCADE,
    FOREIGN KEY (hospital_id, mother_patient_id) REFERENCES patients(hospital_id, patient_id)
);

CREATE TABLE IF NOT EXISTS death_certificates (
    death_cert_id INTEGER PRIMARY KEY,
    hospital_id INTEGER NOT NULL,
    patient_id INTEGER NOT NULL,
    death_date TEXT NOT NULL,
    cause_of_death TEXT,
    issued_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (hospital_id, death_cert_id),
    FOREIGN KEY (hospital_id) REFERENCES hospitals(hospital_id) ON DELETE CASCADE,
    FOREIGN KEY (hospital_id, patient_id) REFERENCES patients(hospital_id, patient_id)
);

CREATE TABLE IF NOT EXISTS contact_messages (
    contact_message_id INTEGER PRIMARY KEY,
    hospital_id INTEGER,
    name TEXT NOT NULL,
    email TEXT,
    subject TEXT,
    message TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (hospital_id, contact_message_id),
    FOREIGN KEY (hospital_id) REFERENCES hospitals(hospital_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS hospital_settings (
    setting_id INTEGER PRIMARY KEY,
    hospital_id INTEGER NOT NULL,
    hospital_name TEXT NOT NULL,
    address TEXT,
    phone_contact TEXT,
    email_contact TEXT,
    emergency_line TEXT,
    opd_hours TEXT,
    timezone TEXT DEFAULT 'Asia/Karachi',
    UNIQUE (hospital_id, setting_id),
    UNIQUE (hospital_id),
    FOREIGN KEY (hospital_id) REFERENCES hospitals(hospital_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS audit_logs (
    log_id INTEGER PRIMARY KEY,
    hospital_id INTEGER,
    actor_user_id INTEGER,
    actor_staff_id INTEGER,
    action TEXT NOT NULL,
    entity_name TEXT,
    entity_id INTEGER,
    details TEXT,
    ip_address TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (hospital_id, log_id),
    FOREIGN KEY (hospital_id) REFERENCES hospitals(hospital_id) ON DELETE SET NULL,
    FOREIGN KEY (actor_user_id) REFERENCES users(user_id),
    FOREIGN KEY (hospital_id, actor_staff_id) REFERENCES staff(hospital_id, staff_id)
);

CREATE INDEX IF NOT EXISTS idx_membership_hospital_user ON hospital_user_memberships(hospital_id, user_id);
CREATE INDEX IF NOT EXISTS idx_staff_hospital ON staff(hospital_id);
CREATE INDEX IF NOT EXISTS idx_patients_hospital ON patients(hospital_id);
CREATE INDEX IF NOT EXISTS idx_appointments_hospital_date ON appointments(hospital_id, appointment_date);
CREATE INDEX IF NOT EXISTS idx_lab_requests_hospital_status ON lab_requests(hospital_id, status);
CREATE INDEX IF NOT EXISTS idx_admissions_hospital_status ON admissions(hospital_id, status);
CREATE INDEX IF NOT EXISTS idx_invoices_hospital_status ON invoices(hospital_id, status);
CREATE INDEX IF NOT EXISTS idx_audit_hospital_created ON audit_logs(hospital_id, created_at);

COMMIT;

-- ======================= EXTENSIONS: SAAS BILLING & AI REPORTS =======================
CREATE TABLE IF NOT EXISTS subscription_plans (
    plan_id INTEGER PRIMARY KEY,
    plan_code TEXT NOT NULL UNIQUE,
    plan_name TEXT NOT NULL,
    monthly_price REAL NOT NULL DEFAULT 0,
    yearly_price REAL NOT NULL DEFAULT 0,
    features_json TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS hospital_subscriptions (
    subscription_id INTEGER PRIMARY KEY,
    hospital_id INTEGER NOT NULL,
    plan_id INTEGER NOT NULL,
    billing_cycle TEXT NOT NULL,
    started_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    purchased_by_email TEXT,
    amount_paid REAL NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (hospital_id) REFERENCES hospitals(hospital_id) ON DELETE CASCADE,
    FOREIGN KEY (plan_id) REFERENCES subscription_plans(plan_id)
);

CREATE INDEX IF NOT EXISTS idx_subscriptions_hospital ON hospital_subscriptions(hospital_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_expiry ON hospital_subscriptions(expires_at);

CREATE TABLE IF NOT EXISTS ai_generated_reports (
    report_id INTEGER PRIMARY KEY,
    hospital_id INTEGER NOT NULL,
    patient_id INTEGER,
    doctor_id INTEGER,
    report_title TEXT NOT NULL,
    source_context TEXT,
    ai_summary TEXT NOT NULL,
    ai_recommendation TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    delivered_to_doctor INTEGER NOT NULL DEFAULT 0,
    delivered_to_patient INTEGER NOT NULL DEFAULT 0,
    printable_token TEXT,
    FOREIGN KEY (hospital_id) REFERENCES hospitals(hospital_id) ON DELETE CASCADE,
    FOREIGN KEY (hospital_id, patient_id) REFERENCES patients(hospital_id, patient_id),
    FOREIGN KEY (hospital_id, doctor_id) REFERENCES staff(hospital_id, staff_id)
);

CREATE INDEX IF NOT EXISTS idx_ai_reports_hospital_created ON ai_generated_reports(hospital_id, created_at);

-- ======================= EXTENSIONS: DOCTOR WORKSPACE FLOWS =======================
CREATE TABLE IF NOT EXISTS doctor_medications (
    medication_order_id INTEGER PRIMARY KEY,
    hospital_id INTEGER NOT NULL,
    patient_id INTEGER NOT NULL,
    doctor_id INTEGER,
    medication_name TEXT NOT NULL,
    dosage TEXT,
    frequency TEXT,
    duration_days INTEGER,
    instructions TEXT,
    pharmacy_status TEXT NOT NULL DEFAULT 'PENDING',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (hospital_id) REFERENCES hospitals(hospital_id) ON DELETE CASCADE,
    FOREIGN KEY (hospital_id, patient_id) REFERENCES patients(hospital_id, patient_id),
    FOREIGN KEY (hospital_id, doctor_id) REFERENCES staff(hospital_id, staff_id)
);

CREATE TABLE IF NOT EXISTS doctor_clinical_updates (
    update_id INTEGER PRIMARY KEY,
    hospital_id INTEGER NOT NULL,
    patient_id INTEGER NOT NULL,
    doctor_id INTEGER,
    update_type TEXT NOT NULL,
    title TEXT NOT NULL,
    details TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (hospital_id) REFERENCES hospitals(hospital_id) ON DELETE CASCADE,
    FOREIGN KEY (hospital_id, patient_id) REFERENCES patients(hospital_id, patient_id),
    FOREIGN KEY (hospital_id, doctor_id) REFERENCES staff(hospital_id, staff_id)
);

CREATE INDEX IF NOT EXISTS idx_doc_meds_hospital_created ON doctor_medications(hospital_id, created_at);
CREATE INDEX IF NOT EXISTS idx_doc_updates_hospital_created ON doctor_clinical_updates(hospital_id, created_at);

-- ======================= EXTENSIONS: PATIENT PORTAL LINKS =======================
CREATE TABLE IF NOT EXISTS patient_portal_accounts (
    portal_account_id INTEGER PRIMARY KEY,
    hospital_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    patient_id INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (hospital_id, user_id),
    UNIQUE (hospital_id, patient_id),
    FOREIGN KEY (hospital_id) REFERENCES hospitals(hospital_id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (hospital_id, patient_id) REFERENCES patients(hospital_id, patient_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_portal_accounts_hospital_user ON patient_portal_accounts(hospital_id, user_id);

-- ======================= EXTENSIONS: RECEPTION ADMISSION RECORDS =======================
CREATE TABLE IF NOT EXISTS reception_admission_records (
    reception_record_id INTEGER PRIMARY KEY,
    hospital_id INTEGER NOT NULL,
    admission_id INTEGER NOT NULL,
    admission_cost REAL NOT NULL DEFAULT 0,
    admission_notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (hospital_id, reception_record_id),
    UNIQUE (hospital_id, admission_id),
    FOREIGN KEY (hospital_id) REFERENCES hospitals(hospital_id) ON DELETE CASCADE,
    FOREIGN KEY (hospital_id, admission_id) REFERENCES admissions(hospital_id, admission_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_reception_adm_hospital ON reception_admission_records(hospital_id, created_at);

-- ======================= EXTENSIONS: SUPER ADMIN GOVERNANCE =======================
CREATE TABLE IF NOT EXISTS system_security_controls (
    control_id INTEGER PRIMARY KEY,
    control_key TEXT NOT NULL UNIQUE,
    control_value TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS role_module_permissions (
    permission_id INTEGER PRIMARY KEY,
    source_role TEXT NOT NULL,
    target_module TEXT NOT NULL,
    can_view INTEGER NOT NULL DEFAULT 1,
    can_edit INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (source_role, target_module)
);

CREATE TABLE IF NOT EXISTS ai_model_registry (
    model_id INTEGER PRIMARY KEY,
    model_key TEXT NOT NULL UNIQUE,
    model_name TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ai_model_metrics (
    metric_id INTEGER PRIMARY KEY,
    model_key TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    metric_value REAL NOT NULL,
    measured_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_perm_source_role ON role_module_permissions(source_role);
CREATE INDEX IF NOT EXISTS idx_ai_metrics_model_time ON ai_model_metrics(model_key, measured_at);

-- ======================= EXTENSIONS: USER ACCESS ACTION LOGS =======================
CREATE TABLE IF NOT EXISTS user_access_actions (
    action_id INTEGER PRIMARY KEY,
    hospital_id INTEGER,
    actor_user_id INTEGER,
    target_user_id INTEGER NOT NULL,
    action_type TEXT NOT NULL,
    reason TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (hospital_id) REFERENCES hospitals(hospital_id) ON DELETE SET NULL,
    FOREIGN KEY (actor_user_id) REFERENCES users(user_id),
    FOREIGN KEY (target_user_id) REFERENCES users(user_id)
);

CREATE INDEX IF NOT EXISTS idx_user_access_actions_hospital_time ON user_access_actions(hospital_id, created_at);

-- ======================= EXTENSIONS: RECEPTION VISIT LOGS =======================
CREATE TABLE IF NOT EXISTS reception_patient_visits (
    visit_id INTEGER PRIMARY KEY,
    hospital_id INTEGER NOT NULL,
    patient_id INTEGER NOT NULL,
    reception_staff_id INTEGER,
    visit_type TEXT NOT NULL DEFAULT 'OPD',
    chief_complaint TEXT,
    status TEXT NOT NULL DEFAULT 'REGISTERED',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (hospital_id, visit_id),
    FOREIGN KEY (hospital_id) REFERENCES hospitals(hospital_id) ON DELETE CASCADE,
    FOREIGN KEY (hospital_id, patient_id) REFERENCES patients(hospital_id, patient_id) ON DELETE CASCADE,
    FOREIGN KEY (hospital_id, reception_staff_id) REFERENCES staff(hospital_id, staff_id)
);

CREATE INDEX IF NOT EXISTS idx_reception_visits_hospital_patient_time ON reception_patient_visits(hospital_id, patient_id, created_at);
