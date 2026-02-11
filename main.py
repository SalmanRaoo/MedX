from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, File, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from datetime import date, datetime, timedelta
from jose import JWTError, jwt
from passlib.context import CryptContext
import shutil, os, json, requests
import models
from database import engine, get_db

# ======================= CONFIGURATION =======================
# 1. Initialize Database Tables
models.Base.metadata.create_all(bind=engine)

# 2. Setup Required Folders
UPLOAD_DIR = "uploaded_reports"
BACKUP_DIR = "database_backups"
for d in [UPLOAD_DIR, BACKUP_DIR]:
    if not os.path.exists(d): os.makedirs(d)

# 3. Connection to AI Microservice (Port 8001)
AI_URL = "http://localhost:8001"

app = FastAPI(title="MedX Ultimate ERP", description="Final Production Build (All Modules)", version="FINAL")

# 4. Enable CORS (Allows Frontend/Browser access)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.get("/favicon.ico", include_in_schema=False)
async def favicon(): return Response(content="", media_type="image/x-icon")

# ======================= SECURITY LAYER =======================
SECRET_KEY = "medx_secret_key_final"; ALGORITHM = "HS256"
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
# This creates the "Authorize" button in Swagger UI
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

def create_access_token(data: dict):
    to_encode = data.copy(); to_encode.update({"exp": datetime.utcnow() + timedelta(minutes=60)})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
    except: raise HTTPException(401, "Invalid Authentication Token")
    user = db.query(models.User).filter(models.User.email == email).first()
    if not user: raise HTTPException(401, "User not found")
    return user

# ======================= INPUT SCHEMAS =======================
class UserCreate(BaseModel): email: str; password: str; user_type: str
class StaffCreate(BaseModel): full_name: str; role: str; phone_number: str
class DoctorCreate(BaseModel): full_name: str; specialization: str; fee: float

# FIX: Changed 'phone' to 'phone_number' to match database
class PatientCreate(BaseModel): 
    full_name: str
    dob: date
    gender: str
    phone_number: str 
    insurance_provider_id: Optional[int] = None

class ApptCreate(BaseModel): patient_id: int; doctor_id: int; date: datetime; type: str="In-Person"
class AIRequest(BaseModel): symptoms: List[str]
class MedCreate(BaseModel): name: str; price: float
class StockCreate(BaseModel): medicine_id: int; quantity: int; batch: str
class SaleCreate(BaseModel): patient_id: int; medicine_id: int; quantity: int
class BedCreate(BaseModel): number: str; charge: float
class AdmitCreate(BaseModel): patient_id: int; bed_id: int
class LabValuesReq(BaseModel): values: List[float]
class TextReq(BaseModel): text: str

# ======================= ENDPOINTS =======================

@app.get("/")
def home(): return {"system": "MedX Final System", "status": "Operational"}

# --- 1. AUTHENTICATION (Public) ---
@app.post("/register/")
def register(u: UserCreate, db: Session = Depends(get_db)):
    # FIX: Check if user exists first to prevent Crash
    existing_user = db.query(models.User).filter(models.User.email == u.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered. Please Login.")

    h = pwd_context.hash(u.password)
    user = models.User(email=u.email, password_hash=h, user_type=u.user_type)
    db.add(user); db.commit()
    return {"token": create_access_token({"sub": u.email})}

@app.post("/login")
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    u = db.query(models.User).filter(models.User.email == form.username).first()
    if not u or not pwd_context.verify(form.password, u.password_hash): raise HTTPException(401, "Incorrect Email or Password")
    return {"access_token": create_access_token({"sub": u.email}), "token_type": "bearer"}

# --- 2. HR & STAFF (Protected) ---
@app.post("/hr/staff/")
def add_staff(s: StaffCreate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    st = models.Staff(**s.dict()); db.add(st); db.commit(); return st

@app.post("/hr/doctors/")
def add_doctor(d: DoctorCreate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    s = models.Staff(full_name=d.full_name, role="Doctor"); db.add(s); db.commit(); db.refresh(s)
    dt = models.DoctorDetails(doctor_id=s.staff_id, specialization=d.specialization, consultation_fee=d.fee); db.add(dt); db.commit(); return dt

# --- 3. PATIENTS & APPOINTMENTS (Protected) ---
@app.post("/patients/")
def add_pat(p: PatientCreate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    # This now uses phone_number correctly
    pat = models.Patient(**p.dict()); db.add(pat); db.commit(); return pat

@app.post("/appointments/")
def book_appt(a: ApptCreate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    apt = models.Appointment(patient_id=a.patient_id, doctor_id=a.doctor_id, appointment_date=a.date, type=a.type)
    db.add(apt); db.commit(); return apt

# --- 4. AI INTEGRATION (The 10 Models) ---
@app.post("/clinical/ai_predict_disease/")
def ai_disease(req: AIRequest, current_user: models.User = Depends(get_current_user)):
    try: return requests.post(f"{AI_URL}/predict/disease", json={"symptoms": req.symptoms}).json()
    except: return {"error": "AI Service Offline"}

@app.post("/clinical/analyze_xray/")
async def ai_xray(file: UploadFile = File(...), current_user: models.User = Depends(get_current_user)):
    try:
        files = {"file": (file.filename, file.file, file.content_type)}
        return requests.post(f"{AI_URL}/predict/pneumonia", files=files).json()
    except: return {"error": "AI Service Offline"}

@app.post("/clinical/ai_diabetes/")
def ai_diabetes(d: dict, current_user: models.User = Depends(get_current_user)):
    try: return requests.post(f"{AI_URL}/predict/diabetes", json=d).json()
    except: return {"error": "AI Service Offline"}

@app.post("/clinical/ai_heart/")
def ai_heart(h: dict, current_user: models.User = Depends(get_current_user)):
    try: return requests.post(f"{AI_URL}/predict/heart", json=h).json()
    except: return {"error": "AI Service Offline"}

@app.post("/clinical/ai_lab_analysis/{test_type}")
def ai_lab(test_type: str, vals: LabValuesReq, current_user: models.User = Depends(get_current_user)):
    # Handles kidney, liver, maternal
    try: return requests.post(f"{AI_URL}/predict/{test_type}", json=vals.dict()).json()
    except: return {"error": "AI Service Offline"}

@app.post("/clinical/ai_triage_bot/")
def ai_triage(text: TextReq, current_user: models.User = Depends(get_current_user)):
    try: return requests.post(f"{AI_URL}/predict/triage", json=text.dict()).json()
    except: return {"error": "AI Service Offline"}

@app.post("/clinical/ai_feedback_sentiment/")
def ai_sentiment(text: TextReq, current_user: models.User = Depends(get_current_user)):
    try: return requests.post(f"{AI_URL}/predict/sentiment", json=text.dict()).json()
    except: return {"error": "AI Service Offline"}

@app.post("/clinical/analyze_mri/")
async def ai_mri(file: UploadFile = File(...), current_user: models.User = Depends(get_current_user)):
    try:
        files = {"file": (file.filename, file.file, file.content_type)}
        return requests.post(f"{AI_URL}/predict/brain_tumor", files=files).json()
    except: return {"error": "AI Service Offline"}

# --- 5. BILLING & PHARMACY (Protected) ---
@app.post("/medicines/")
def add_med(m: MedCreate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    med = models.Medicine(medicine_name=m.name, unit_price=m.price); db.add(med); db.commit()
    db.add(models.MedicineBatch(medicine_id=med.medicine_id, quantity_available=0, batch_number="INIT")); db.commit()
    return med

@app.post("/inventory/stock/")
def add_stock(s: StockCreate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    b = models.MedicineBatch(medicine_id=s.medicine_id, quantity_available=s.quantity, batch_number=s.batch); db.add(b); db.commit(); return {"msg": "Stock Added"}

@app.post("/pharmacy_sales/")
def sell_med(s: SaleCreate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    b = db.query(models.MedicineBatch).filter(models.MedicineBatch.medicine_id==s.medicine_id).first()
    if not b or b.quantity_available < s.quantity: raise HTTPException(400, "Out of Stock")
    b.quantity_available -= s.quantity
    price = db.query(models.Medicine).get(s.medicine_id).unit_price
    sale = models.PharmacySale(patient_id=s.patient_id, total_amount=price*s.quantity); db.add(sale); db.commit()
    return sale

@app.get("/billing/calculate/{pid}")
def calculate_bill(pid: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    total = 0.0; items = []
    
    # 1. Doctor Fees
    for a in db.query(models.Appointment).filter(models.Appointment.patient_id == pid).all():
        doc = db.query(models.DoctorDetails).filter(models.DoctorDetails.doctor_id == a.doctor_id).first()
        fee = doc.consultation_fee if doc else 0
        total += fee; items.append(f"Consultation: {fee}")
        
    # 2. Pharmacy Costs
    for s in db.query(models.PharmacySale).filter(models.PharmacySale.patient_id == pid).all():
        total += s.total_amount; items.append(f"Meds: {s.total_amount}")
        
    return {"patient_id": pid, "total_bill": total, "breakdown": items}

# --- 6. ADMISSIONS & BEDS (Protected) ---
@app.post("/beds/")
def add_bed(b: BedCreate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    bed = models.Bed(bed_number=b.number, daily_charge=b.charge); db.add(bed); db.commit(); return bed

@app.post("/admissions/")
def admit(a: AdmitCreate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    bed = db.query(models.Bed).get(a.bed_id)
    if bed.is_occupied: raise HTTPException(400, "Bed Occupied")
    adm = models.Admission(**a.dict()); db.add(adm)
    bed.is_occupied = True; db.commit(); return adm

# --- 7. ADMIN BACKUPS (Protected) ---
@app.post("/admin/backup/create")
def create_backup(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    # 1. Security Check
    if current_user.user_type != "Admin": raise HTTPException(403, "Admin Access Only")
    
    # 2. Get Data
    patients = [p.__dict__ for p in db.query(models.Patient).all()]
    for p in patients: 
        p.pop('_sa_instance_state', None)
        p['dob'] = str(p['dob'])
    
    # 3. Save File
    filename = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(os.path.join(BACKUP_DIR, filename), "w") as f: json.dump(patients, f)
    
    # 4. SHOW ON TERMINAL (DEMO FEATURE)
    print("\n" + "="*60)
    print(f"🚀 DATABASE BACKUP SUCCESS: {filename}")
    print("="*60)
    print(json.dumps(patients, indent=4))
    print("="*60 + "\n")

    return {"message": "Backup Created", "file": filename}