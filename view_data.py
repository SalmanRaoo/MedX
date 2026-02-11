from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware 
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from pydantic import BaseModel
from typing import Optional, List
from datetime import date, datetime, timedelta
from jose import JWTError, jwt
from passlib.context import CryptContext

# IMPORT YOUR MODELS
import models 
from database import engine, get_db

# ==========================================
# 0. INITIALIZATION & CONFIG
# ==========================================
# Create Tables
models.Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="MedX Enterprise ERP", 
    description="Hospital Operating System: Clinical, Financial & AI Modules",
    version="3.0 (Final)"
)

# --- NEW: CORS MIDDLEWARE (Allow Frontend to Connect) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins (Streamlit, React, etc.)
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods (POST, GET, PUT, DELETE)
    allow_headers=["*"],
)

# ==========================================
# 1. SECURITY LAYER
# ==========================================
SECRET_KEY = "medx_secret_key_change_this_in_production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

def get_password_hash(password): return pwd_context.hash(password)
def verify_password(plain, hashed): return pwd_context.verify(plain, hashed)

def create_access_token(data: dict):
    to_encode = data.copy()
    to_encode.update({"exp": datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None: raise HTTPException(status_code=401)
    except JWTError: raise HTTPException(status_code=401)
    
    user = db.query(models.User).filter(models.User.email == email).first()
    if user is None: raise HTTPException(status_code=401, detail="User not found")
    return user

# ==========================================
# 2. DATA SCHEMAS (Pydantic)
# ==========================================
class UserCreate(BaseModel):
    email: str
    password: str
    user_type: str
class Token(BaseModel):
    access_token: str
    token_type: str

class StaffCreate(BaseModel):
    full_name: str
    role: str
    phone_number: str

class DoctorCreate(BaseModel):
    full_name: str
    specialization: str
    consultation_fee: float
    doctor_share: float = 0.70 

class PatientCreate(BaseModel):
    full_name: str
    dob: date
    gender: str
    blood_group: str
    phone_number: str
    address: str
    emergency_contact: str

class AppointmentCreate(BaseModel):
    patient_id: int
    doctor_id: int
    appointment_date: datetime
    reason_for_visit: str

class VitalsCreate(BaseModel):
    patient_id: int
    body_temperature: float
    blood_pressure_systolic: int
    blood_pressure_diastolic: int
    heart_rate: int

# Inventory & Finance
class MedicineCreate(BaseModel):
    medicine_name: str
    generic_name: str
    unit_price: float

class MedicineBatchCreate(BaseModel):
    medicine_id: int
    batch_number: str
    quantity: int
    expiry_date: date

class PharmacySaleCreate(BaseModel):
    patient_id: int
    medicine_id: int
    quantity: int

class ExpenseCreate(BaseModel):
    category: str
    description: str
    amount: float
    date_incurred: date

class SalaryPaymentCreate(BaseModel):
    staff_id: int
    amount: float
    month: str

# Admin Inputs
class CommissionUpdate(BaseModel):
    new_share_percentage: float 
class StockEntry(BaseModel):
    medicine_id: int
    quantity_to_add: int
    batch_number: str
    expiry_date: date
class PriceUpdate(BaseModel):
    new_price: float

# ==========================================
# 3. CORE ENDPOINTS
# ==========================================

@app.get("/")
def home():
    return {"status": "Online", "system": "MedX Enterprise ERP", "time": datetime.now()}

# --- AUTH ---
@app.post("/register/", response_model=Token)
def register(user: UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.email == user.email).first()
    if db_user: raise HTTPException(status_code=400, detail="Email exists")
    hashed = get_password_hash(user.password)
    new_user = models.User(email=user.email, password_hash=hashed, user_type=user.user_type)
    db.add(new_user)
    db.commit()
    return {"access_token": create_access_token(data={"sub": new_user.email}), "token_type": "bearer"}

@app.post("/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(status_code=401)
    return {"access_token": create_access_token(data={"sub": user.email}), "token_type": "bearer"}

# --- STAFF ---
@app.post("/doctors/")
def add_doctor(doctor: DoctorCreate, db: Session = Depends(get_db)):
    # 1. Create Staff Entry
    new_staff = models.Staff(full_name=doctor.full_name, role="Doctor")
    db.add(new_staff)
    db.commit()
    db.refresh(new_staff)
    # 2. Create Doctor Details
    new_doc = models.DoctorDetails(
        doctor_id=new_staff.staff_id,
        specialization=doctor.specialization,
        consultation_fee=doctor.consultation_fee,
        doctor_share_percentage=doctor.doctor_share
    )
    db.add(new_doc)
    db.commit()
    print(f"\n[🩺 SETUP] Dr. {doctor.full_name} | Fee: Rs.{doctor.consultation_fee} | Split: {doctor.doctor_share*100}%")
    return new_doc

@app.post("/staff/")
def add_staff(staff: StaffCreate, db: Session = Depends(get_db)):
    s = models.Staff(**staff.dict())
    db.add(s)
    db.commit()
    return s

# --- PATIENTS & SEARCH ---
@app.post("/patients/")
def add_patient(patient: PatientCreate, db: Session = Depends(get_db)):
    p = models.Patient(**patient.dict())
    db.add(p)
    db.commit()
    return p

@app.get("/patients/search/")
def search_patients(query: str, db: Session = Depends(get_db)):
    """
    🔍 SEARCH ENGINE: Find patient by Name or Phone
    """
    # Using 'ilike' for case-insensitive search
    results = db.query(models.Patient).filter(
        models.Patient.full_name.ilike(f"%{query}%") | 
        models.Patient.phone_number.contains(query)
    ).all()
    
    if not results: return {"message": "No match found", "data": []}
    return {"message": "Found", "data": results}

@app.post("/appointments/")
def add_appt(appt: AppointmentCreate, db: Session = Depends(get_db)):
    a = models.Appointment(**appt.dict())
    db.add(a)
    db.commit()
    return a

@app.post("/vitals/")
def add_vitals(vitals: VitalsCreate, db: Session = Depends(get_db)):
    # Simple AI Placeholder Rule
    risk = 0.8 if vitals.body_temperature > 100 else 0.1
    v = models.PatientVitals(**vitals.dict(), ai_risk_score=risk)
    db.add(v)
    db.commit()
    return v

# --- INVENTORY ---
@app.post("/medicines/")
def add_medicine(med: MedicineCreate, db: Session = Depends(get_db)):
    m = models.Medicine(**med.dict())
    db.add(m)
    db.commit()
    return m

@app.post("/medicine_batches/")
def add_batch(batch: MedicineBatchCreate, db: Session = Depends(get_db)):
    b = models.MedicineBatch(
        medicine_id=batch.medicine_id,
        batch_number=batch.batch_number,
        quantity_available=batch.quantity,
        expiry_date=batch.expiry_date,
        supplier_name="Initial Stock"
    )
    db.add(b)
    db.commit()
    return b

@app.post("/pharmacy_sales/")
def process_sale(sale: PharmacySaleCreate, db: Session = Depends(get_db)):
    # 1. Validate Medicine
    med = db.query(models.Medicine).filter(models.Medicine.medicine_id == sale.medicine_id).first()
    if not med: raise HTTPException(status_code=404, detail="Medicine not found")
    
    # 2. Check Stock (FIFO Logic)
    batch = db.query(models.MedicineBatch).filter(
        models.MedicineBatch.medicine_id == sale.medicine_id,
        models.MedicineBatch.quantity_available >= sale.quantity
    ).first()
    
    if not batch: raise HTTPException(status_code=400, detail="Out of Stock")
    
    # 3. Deduct & Record
    batch.quantity_available -= sale.quantity
    total = med.unit_price * sale.quantity
    
    new_sale = models.PharmacySale(
        patient_id=sale.patient_id,
        medicine_id=sale.medicine_id,
        quantity=sale.quantity,
        total_amount=total
    )
    db.add(new_sale)
    db.commit()
    print(f"\n[💊 SALE] Sold {sale.quantity}x {med.medicine_name} for Rs. {total}")
    return new_sale

# --- EXPENSES ---
@app.post("/finance/expenses/")
def add_expense(expense: ExpenseCreate, db: Session = Depends(get_db)):
    e = models.Expense(**expense.dict())
    db.add(e)
    db.commit()
    print(f"\n[💸 EXPENSE] {expense.category}: Rs. {expense.amount}")
    return e

@app.post("/finance/pay_salary/")
def pay_salary(payment: SalaryPaymentCreate, db: Session = Depends(get_db)):
    staff = db.query(models.Staff).filter(models.Staff.staff_id == payment.staff_id).first()
    if not staff: raise HTTPException(status_code=404, detail="Staff not found")
    
    exp = models.Expense(
        category="Salary", 
        description=f"Salary {staff.full_name} ({payment.month})", 
        amount=payment.amount, 
        date_incurred=date.today()
    )
    db.add(exp)
    db.commit()
    return {"message": "Salary Paid", "amount": payment.amount}

# ==========================================
# 4. ADVANCED BILLING ENGINE
# ==========================================
@app.get("/billing/calculate/{patient_id}")
def calculate_bill(
    patient_id: int, 
    tax_percent: float = 0.0, 
    discount_rs: float = 0.0, 
    db: Session = Depends(get_db)
):
    print(f"\n[🧮 BILLING] Processing for Patient ID {patient_id}")
    subtotal = 0.0
    items = []

    # 1. Doctor Fees
    appts = db.query(models.Appointment).filter(models.Appointment.patient_id == patient_id).all()
    for a in appts:
        doc = db.query(models.DoctorDetails).filter(models.DoctorDetails.doctor_id == a.doctor_id).first()
        if doc:
            fee = float(doc.consultation_fee)
            subtotal += fee
            items.append(f"Consultation (Dr. ID {doc.doctor_id}): Rs. {fee}")

    # 2. Pharmacy
    sales = db.query(models.PharmacySale).filter(models.PharmacySale.patient_id == patient_id).all()
    for s in sales:
        amt = float(s.total_amount)
        subtotal += amt
        items.append(f"Pharmacy Sale (ID {s.sale_id}): Rs. {amt}")

    # 3. Final Calculations
    tax_amt = (subtotal * tax_percent) / 100
    total = (subtotal + tax_amt) - discount_rs
    if total < 0: total = 0

    return {
        "patient_id": patient_id,
        "subtotal": subtotal,
        "tax": tax_amt,
        "discount": discount_rs,
        "GRAND_TOTAL_RS": total,
        "breakdown": items
    }

# ==========================================
# 5. FINANCIAL & OPERATIONAL ANALYTICS
# ==========================================

@app.get("/finance/erp_report/")
def erp_report(db: Session = Depends(get_db)):
    """
    📊 ERP REPORT: Calculates Net Profit after Doctor Splits
    """
    pharmacy_rev = db.query(func.sum(models.PharmacySale.total_amount)).scalar() or 0.0
    
    # Calculate Doctor Split
    doc_gross = 0.0
    hosp_net_from_docs = 0.0
    
    doctors = db.query(models.DoctorDetails).all()
    for doc in doctors:
        count = db.query(models.Appointment).filter(models.Appointment.doctor_id == doc.doctor_id).count()
        total_gen = count * doc.consultation_fee
        
        doc_share = total_gen * doc.doctor_share_percentage
        hosp_share = total_gen - doc_share
        
        doc_gross += total_gen
        hosp_net_from_docs += hosp_share

    expenses = db.query(func.sum(models.Expense.amount)).scalar() or 0.0
    
    # Final Profit
    net_revenue = pharmacy_rev + hosp_net_from_docs
    net_profit = net_revenue - expenses

    print(f"\n[📊 REPORT] Profit: Rs. {net_profit}")
    return {
        "gross_revenue": pharmacy_rev + doc_gross,
        "paid_to_doctors": doc_gross - hosp_net_from_docs,
        "hospital_net_revenue": net_revenue,
        "total_expenses": expenses,
        "NET_PROFIT": net_profit
    }

@app.get("/admin/analytics/bed_occupancy")
def bed_analytics(db: Session = Depends(get_db)):
    """
    🏥 CAPACITY REPORT: How full is the hospital?
    """
    total = db.query(models.Bed).count()
    occupied = db.query(models.Bed).filter(models.Bed.is_occupied == True).count()
    
    rate = 0.0
    if total > 0:
        rate = (occupied / total) * 100
        
    return {
        "total_beds": total,
        "occupied": occupied,
        "occupancy_rate_percent": round(rate, 1),
        "status": "CRITICAL" if rate > 90 else "Normal"
    }

# ==========================================
# 6. ADMIN TERMINAL (Configuration)
# ==========================================

@app.put("/admin/config/doctor_commission/{doctor_id}")
def config_commission(doctor_id: int, update: CommissionUpdate, db: Session = Depends(get_db)):
    doc = db.query(models.DoctorDetails).filter(models.DoctorDetails.doctor_id == doctor_id).first()
    if not doc: raise HTTPException(status_code=404, detail="Not Found")
    
    doc.doctor_share_percentage = update.new_share_percentage
    db.commit()
    print(f"[🔧 ADMIN] Dr. {doctor_id} Share Updated: {update.new_share_percentage*100}%")
    return {"message": "Updated"}

@app.put("/admin/config/medicine_price/{medicine_id}")
def config_price(medicine_id: int, price: PriceUpdate, db: Session = Depends(get_db)):
    med = db.query(models.Medicine).filter(models.Medicine.medicine_id == medicine_id).first()
    if not med: raise HTTPException(status_code=404, detail="Not Found")
    
    med.unit_price = price.new_price
    db.commit()
    return {"message": "Price Updated"}

@app.post("/admin/inventory/add_stock/")
def config_stock(entry: StockEntry, db: Session = Depends(get_db)):
    med = db.query(models.Medicine).filter(models.Medicine.medicine_id == entry.medicine_id).first()
    if not med: raise HTTPException(status_code=404, detail="Medicine Not Found")

    b = models.MedicineBatch(
        medicine_id=entry.medicine_id,
        batch_number=entry.batch_number,
        quantity_available=entry.quantity_to_add,
        expiry_date=entry.expiry_date,
        supplier_name="Manual Entry"
    )
    db.add(b)
    db.commit()
    print(f"[📦 ADMIN] Added Stock: {entry.quantity_to_add} units")
    return {"message": "Stock Added"}