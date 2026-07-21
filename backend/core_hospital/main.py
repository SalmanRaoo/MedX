import json
import uuid
import re
import os
import pickle
import base64
from pathlib import Path
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

from fastapi import Body, Depends, FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from sqlalchemy import insert, select, update, delete, text, func, case
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

import models
from database import get_db

app = FastAPI(title="MedX Multi-Hospital API", version="4.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SECRET_KEY = "medx_multi_hospital_secret"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 12
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


class BedSyncHub:
    def __init__(self) -> None:
        self.connections: Dict[int, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, hospital_id: int) -> None:
        await websocket.accept()
        self.connections.setdefault(hospital_id, []).append(websocket)

    def disconnect(self, websocket: WebSocket, hospital_id: int) -> None:
        current = self.connections.get(hospital_id, [])
        if websocket in current:
            current.remove(websocket)
        if not current and hospital_id in self.connections:
            self.connections.pop(hospital_id, None)

    async def broadcast(self, hospital_id: int, event: str, payload: Dict[str, Any]) -> None:
        sockets = list(self.connections.get(hospital_id, []))
        if not sockets:
            return
        message = {
            "event": event,
            "hospital_id": hospital_id,
            "payload": payload,
            "timestamp": datetime.utcnow().isoformat(),
        }
        stale: List[WebSocket] = []
        for socket in sockets:
            try:
                await socket.send_json(message)
            except Exception:
                stale.append(socket)
        for socket in stale:
            self.disconnect(socket, hospital_id)


bed_sync_hub = BedSyncHub()


class LoginRequest(BaseModel):
    email: str
    password: str
    selected_hospital_id: Optional[int] = None


class RegisterRequest(BaseModel):
    email: str
    password: str
    full_name: str
    hospital_name: str
    hospital_code: str


class HospitalSettingsUpsertRequest(BaseModel):
    hospital_name: str
    address: Optional[str] = None
    phone_contact: Optional[str] = None
    email_contact: Optional[str] = None
    emergency_line: Optional[str] = None
    opd_hours: Optional[str] = None
    timezone: Optional[str] = "Asia/Karachi"


class PurchasePlanRequest(BaseModel):
    hospital_name: str
    hospital_code: str
    admin_email: str
    plan_code: str
    billing_cycle: str = "monthly"


class SubscriptionPlanUpdateRequest(BaseModel):
    plan_name: Optional[str] = None
    monthly_price: Optional[float] = None
    yearly_price: Optional[float] = None
    features: Optional[List[str]] = None
    is_active: Optional[bool] = None


class AIReportRequest(BaseModel):
    report_title: str
    source_context: str
    patient_id: Optional[int] = None
    doctor_id: Optional[int] = None


def _serialize_value(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def _serialize_row(row: Any) -> Dict[str, Any]:
    return {k: _serialize_value(v) for k, v in row._mapping.items()}


def _normalize_email(value: Any) -> str:
    return str(value or "").strip().lower()


def _create_access_token(data: Dict[str, Any]) -> str:
    payload = data.copy()
    now = datetime.utcnow()
    payload['iat'] = int(now.timestamp())
    payload['exp'] = now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def _require_admin(current_user: Dict[str, Any]) -> None:
    role = (current_user.get("role_name") or "").upper()
    if role not in {"ADMIN", "SUPER_ADMIN"}:
        raise HTTPException(status_code=403, detail="Admin role required")


def _require_super_admin(current_user: Dict[str, Any]) -> None:
    role = (current_user.get("role_name") or "").upper()
    if role != "SUPER_ADMIN":
        raise HTTPException(status_code=403, detail="Super admin role required")


def _table_has_column(table, column_name: str) -> bool:
    return column_name in table.c


def _recent_order_expr(table, preferred_column: str, fallback_column: str):
    if _table_has_column(table, preferred_column):
        return table.c[preferred_column].desc()
    if _table_has_column(table, fallback_column):
        return table.c[fallback_column].desc()
    for col in table.primary_key.columns:
        return col.desc()
    return None


def _ensure_hospital_subscription_columns(db: Session) -> None:
    table = models.TABLES.get("hospital_subscriptions")
    if table is None:
        return

    desired_columns = {
        "suspended_at": "TEXT",
    }
    changed = False
    for col, col_type in desired_columns.items():
        if _table_has_column(table, col):
            continue
        db.execute(text(f"ALTER TABLE hospital_subscriptions ADD COLUMN {col} {col_type}"))
        changed = True

    if changed:
        db.commit()
        models.load_tables()

    db.execute(
        text(
            "CREATE INDEX IF NOT EXISTS idx_subscriptions_hospital_started ON hospital_subscriptions(hospital_id, started_at DESC)"
        )
    )
    db.commit()


def _ensure_patient_table_compatibility(db: Session) -> None:
    table = models.TABLES.get("patients")
    if table is None:
        return

    changed = False
    if not _table_has_column(table, "created_at"):
        db.execute(text("ALTER TABLE patients ADD COLUMN created_at TEXT"))
        changed = True

    if changed:
        db.commit()
        models.load_tables()
        table = models.TABLES.get("patients")

    if table is not None and _table_has_column(table, "created_at"):
        db.execute(
            text(
                "UPDATE patients SET created_at = COALESCE(NULLIF(created_at, ''), CURRENT_TIMESTAMP)"
            )
        )
        db.execute(text("CREATE INDEX IF NOT EXISTS idx_patients_hospital_created ON patients(hospital_id, created_at)"))
        db.commit()


def _seed_plans(db: Session) -> None:
    plans_table = models.TABLES["subscription_plans"]
    plans = db.execute(select(plans_table.c.plan_id).limit(1)).first()
    if plans:
        return

    seed_plans = [
        {
            "plan_code": "STARTER",
            "plan_name": "Starter",
            "monthly_price": 49,
            "yearly_price": 490,
            "features_json": json.dumps(["1 hospital", "Core ERP", "Basic AI reports"]),
            "is_active": 1,
        },
        {
            "plan_code": "PRO",
            "plan_name": "Professional",
            "monthly_price": 149,
            "yearly_price": 1490,
            "features_json": json.dumps(["Up to 3 hospitals", "Advanced analytics", "Priority support"]),
            "is_active": 1,
        },
        {
            "plan_code": "ENTERPRISE",
            "plan_name": "Enterprise",
            "monthly_price": 399,
            "yearly_price": 3990,
            "features_json": json.dumps(["Unlimited hospitals", "Custom AI workflows", "Dedicated success manager"]),
            "is_active": 1,
        },
    ]
    for plan in seed_plans:
        db.execute(insert(plans_table).values(**plan))


def _bootstrap_initial_data(db: Session) -> None:
    users_table = models.TABLES["users"]
    roles_table = models.TABLES["roles"]
    hospitals_table = models.TABLES["hospitals"]
    staff_table = models.TABLES["staff"]
    memberships_table = models.TABLES["hospital_user_memberships"]
    settings_table = models.TABLES["hospital_settings"]

    for role_name in ["SUPER_ADMIN", "ADMIN", "DOCTOR", "RADIOLOGIST", "NURSE", "RECEPTIONIST", "PHARMACY", "LAB", "FINANCE", "ACCOUNTANT", "FLEET", "OPERATIONS"]:
        existing_role = db.execute(select(roles_table).where(roles_table.c.role_name == role_name)).first()
        if not existing_role:
            db.execute(insert(roles_table).values(role_name=role_name))

    has_hospital = db.execute(select(hospitals_table.c.hospital_id).limit(1)).first()
    if not has_hospital:
        db.execute(
            insert(hospitals_table).values(
                hospital_code="MEDX-001",
                hospital_name="MedX General Hospital",
                address="Main Medical District",
                phone_contact="+92 000 0000000",
                email_contact="admin@medx.local",
                emergency_line="111-HELP",
                status="ACTIVE",
            )
        )

    hospital = db.execute(select(hospitals_table).where(hospitals_table.c.hospital_code == "MEDX-001")).first()

    existing_settings = db.execute(select(settings_table).where(settings_table.c.hospital_id == hospital.hospital_id)).first()
    if not existing_settings:
        db.execute(
            insert(settings_table).values(
                hospital_id=hospital.hospital_id,
                hospital_name=hospital.hospital_name,
                address=hospital.address,
                phone_contact=hospital.phone_contact,
                email_contact=hospital.email_contact,
                emergency_line=hospital.emergency_line,
                opd_hours="Mon-Sat: 9:00 AM - 5:00 PM",
                timezone="Asia/Karachi",
            )
        )

    _ensure_global_settings_row(db, int(hospital.hospital_id))

    seed_users = [
        {"email": "admin@medx.local", "password": "admin123", "role": "ADMIN", "full_name": "Hospital Admin"},
        {"email": "superadmin@medx.local", "password": "superadmin123", "role": "SUPER_ADMIN", "full_name": "MedX Super Admin"},
    ]

    for seed in seed_users:
        existing_user = db.execute(select(users_table).where(users_table.c.email == seed["email"])).first()
        if existing_user:
            continue

        db.execute(
            insert(users_table).values(
                email=seed["email"],
                password_hash=pwd_context.hash(seed["password"]),
                is_active=1,
            )
        )
        user = db.execute(select(users_table).where(users_table.c.email == seed["email"])).first()
        role = db.execute(select(roles_table).where(roles_table.c.role_name == seed["role"])).first()

        db.execute(
            insert(staff_table).values(
                hospital_id=hospital.hospital_id,
                user_id=user.user_id,
                full_name=seed["full_name"],
                role=seed["role"],
                status="ACTIVE",
            )
        )
        staff = db.execute(
            select(staff_table)
            .where(staff_table.c.hospital_id == hospital.hospital_id)
            .where(staff_table.c.user_id == user.user_id)
        ).first()

        db.execute(
            insert(memberships_table).values(
                hospital_id=hospital.hospital_id,
                user_id=user.user_id,
                role_id=role.role_id,
                staff_id=staff.staff_id,
                is_primary=1,
            )
        )

    _seed_plans(db)
    db.commit()


@app.on_event("startup")
def startup_seed() -> None:
    db_gen = get_db()
    db = next(db_gen)
    try:
        _bootstrap_initial_data(db)
        _ensure_hospital_subscription_columns(db)
        _ensure_patient_table_compatibility(db)
        _ensure_pharmacy_support_tables(db)
        _ensure_operational_units_table(db)
        _ensure_activity_audit_table(db)
        _ensure_fleet_auxiliary_tables(db)
    finally:
        db.close()


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> Dict[str, Any]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid authentication token")

    user_id = payload.get("user_id") or payload.get("sub")
    hospital_id = payload.get("hospital_id")
    role_name = payload.get("role_name")

    if user_id is None or hospital_id is None:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    users_table = models.TABLES["users"]
    user = db.execute(select(users_table).where(users_table.c.user_id == int(user_id))).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return {
        "user_id": int(user_id),
        "email": user.email,
        "hospital_id": int(hospital_id),
        "role_name": role_name,
    }


def _decode_ws_token(token: str) -> Dict[str, Any]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid authentication token")
    user_id = payload.get("user_id") or payload.get("sub")
    hospital_id = payload.get("hospital_id")
    role_name = payload.get("role_name")
    if user_id is None or hospital_id is None:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    return {
        "user_id": int(user_id),
        "hospital_id": int(hospital_id),
        "role_name": str(role_name or "").upper(),
    }


@app.websocket("/ws/bed-sync")
async def websocket_bed_sync(websocket: WebSocket, token: str = Query(default="")) -> None:
    if not token:
        await websocket.close(code=4401, reason="Missing token")
        return
    try:
        payload = _decode_ws_token(token)
    except HTTPException:
        await websocket.close(code=4401, reason="Invalid token")
        return

    hospital_id = int(payload["hospital_id"])
    await bed_sync_hub.connect(websocket, hospital_id)
    await websocket.send_json(
        {
            "event": "connected",
            "hospital_id": hospital_id,
            "payload": {"status": "ok"},
            "timestamp": datetime.utcnow().isoformat(),
        }
    )
    try:
        while True:
            message = await websocket.receive_text()
            if str(message).strip().lower() == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        bed_sync_hub.disconnect(websocket, hospital_id)
    except Exception:
        bed_sync_hub.disconnect(websocket, hospital_id)


def _get_user_memberships(db: Session, user_id: int) -> List[Dict[str, Any]]:
    memberships = models.TABLES["hospital_user_memberships"]
    hospitals = models.TABLES["hospitals"]
    roles = models.TABLES["roles"]

    rows = db.execute(
        select(
            memberships.c.hospital_id,
            hospitals.c.hospital_name,
            memberships.c.role_id,
            roles.c.role_name,
            memberships.c.staff_id,
            memberships.c.is_primary,
        )
        .select_from(
            memberships.join(hospitals, memberships.c.hospital_id == hospitals.c.hospital_id).join(
                roles, memberships.c.role_id == roles.c.role_id
            )
        )
        .where(memberships.c.user_id == user_id)
    ).fetchall()

    return [
        {
            "hospital_id": r.hospital_id,
            "hospital_name": r.hospital_name,
            "role_id": r.role_id,
            "role_name": r.role_name,
            "staff_id": r.staff_id,
            "is_primary": bool(r.is_primary),
        }
        for r in rows
    ]


def _generate_ai_summary(source_context: str) -> Dict[str, str]:
    text = (source_context or "").lower()
    risk = "low"
    rec = "Continue routine monitoring and follow current treatment plan."

    risk_words_high = ["severe", "critical", "tumor", "stroke", "respiratory failure", "emergency"]
    risk_words_medium = ["fever", "infection", "pain", "abnormal", "elevated", "hypertension"]

    if any(w in text for w in risk_words_high):
        risk = "high"
        rec = "Urgent physician review required. Prioritize diagnostics and immediate intervention plan."
    elif any(w in text for w in risk_words_medium):
        risk = "medium"
        rec = "Doctor follow-up recommended within 24 hours with targeted lab validation."

    summary = (
        f"AI analyzed the submitted report context and assessed an overall {risk.upper()} clinical risk level. "
        f"Key findings were extracted from narrative report text for triage support."
    )
    return {"summary": summary, "recommendation": rec}


DEFAULT_LAB_TEST_PRICING = {
    "CBC": 1200.0,
    "LFT": 1600.0,
    "RFT": 1500.0,
}


def _safe_json_dict(raw_value: Any, fallback: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if fallback is None:
        fallback = {}
    if isinstance(raw_value, dict):
        return raw_value
    if raw_value in [None, ""]:
        return dict(fallback)
    try:
        parsed = json.loads(raw_value)
        if isinstance(parsed, dict):
            return parsed
        return dict(fallback)
    except Exception:
        return dict(fallback)


def _safe_json_list(raw_value: Any, fallback: Optional[List[Any]] = None) -> List[Any]:
    if fallback is None:
        fallback = []
    if isinstance(raw_value, list):
        return list(raw_value)
    if raw_value in [None, ""]:
        return list(fallback)
    try:
        parsed = json.loads(raw_value)
        if isinstance(parsed, list):
            return list(parsed)
        return list(fallback)
    except Exception:
        return list(fallback)


def _ensure_global_settings_table(db: Session) -> None:
    if models.TABLES.get("global_settings") is not None:
        return
    db.execute(
        text(
            """
        CREATE TABLE IF NOT EXISTS global_settings (
            setting_id INTEGER PRIMARY KEY,
            hospital_id INTEGER NOT NULL UNIQUE,
            hospital_name TEXT,
            address TEXT,
            contact_number TEXT,
            logo_url TEXT,
            service_pricing_json TEXT NOT NULL DEFAULT '{}',
            staff_fees_json TEXT NOT NULL DEFAULT '{}',
            updated_by_user_id INTEGER,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
        )
    )
    db.commit()
    models.load_tables()


def _next_invoice_number(db: Session, hospital_id: int, prefix: str = "INV") -> str:
    invoices = models.TABLES["invoices"]
    clean_prefix = (prefix or "INV").upper().replace(" ", "_")
    for _ in range(20):
        token = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")[-10:]
        candidate = f"{clean_prefix}-{hospital_id}-{token}"
        exists = db.execute(
            select(invoices.c.invoice_id)
            .where(invoices.c.hospital_id == hospital_id)
            .where(invoices.c.invoice_number == candidate)
        ).first()
        if not exists:
            return candidate
    return f"{clean_prefix}-{hospital_id}-{uuid.uuid4().hex[:8].upper()}"


def _ensure_global_settings_row(db: Session, hospital_id: int) -> Any:
    _ensure_global_settings_table(db)
    table = models.TABLES["global_settings"]
    row = db.execute(select(table).where(table.c.hospital_id == int(hospital_id))).first()
    if row:
        return row

    hospitals = models.TABLES["hospitals"]
    hospital = db.execute(select(hospitals).where(hospitals.c.hospital_id == int(hospital_id))).first()
    if not hospital:
        raise HTTPException(status_code=404, detail="Hospital not found")

    settings = models.TABLES.get("hospital_settings")
    profile = None
    if settings is not None:
        profile = db.execute(select(settings).where(settings.c.hospital_id == int(hospital_id))).first()

    service_pricing = {
        "patient_registration_fee": 0.0,
        "lab_tests": dict(DEFAULT_LAB_TEST_PRICING),
        "radiology": {},
    }
    if models.TABLES.get("radiology_service_catalog") is not None:
        rad = models.TABLES["radiology_service_catalog"]
        rows = db.execute(
            select(rad.c.service_id, rad.c.service_fee)
            .where(rad.c.hospital_id == int(hospital_id))
            .where(rad.c.is_active == 1)
        ).fetchall()
        service_pricing["radiology"] = {str(r.service_id): float(r.service_fee or 0) for r in rows}

    staff_fees = {"doctor_consultation_fee_default": 0.0}
    if models.TABLES.get("doctor_details") is not None:
        doctor_details = models.TABLES["doctor_details"]
        fee = db.execute(
            select(func.avg(doctor_details.c.consultation_fee))
            .where(doctor_details.c.hospital_id == int(hospital_id))
        ).scalar()
        if fee is not None:
            staff_fees["doctor_consultation_fee_default"] = float(fee or 0)

    db.execute(
        insert(table).values(
            hospital_id=int(hospital_id),
            hospital_name=(profile.hospital_name if profile else hospital.hospital_name),
            address=(profile.address if profile else hospital.address),
            contact_number=(profile.phone_contact if profile else hospital.phone_contact),
            logo_url=None,
            service_pricing_json=json.dumps(service_pricing),
            staff_fees_json=json.dumps(staff_fees),
            updated_at=datetime.utcnow().isoformat(),
        )
    )
    db.commit()
    return db.execute(select(table).where(table.c.hospital_id == int(hospital_id))).first()


def _build_settings_payload(db: Session, hospital_id: int) -> Dict[str, Any]:
    row = _ensure_global_settings_row(db, int(hospital_id))
    service_pricing = _safe_json_dict(getattr(row, "service_pricing_json", "{}"), {})
    staff_fees = _safe_json_dict(getattr(row, "staff_fees_json", "{}"), {})

    service_pricing.setdefault("patient_registration_fee", 0.0)
    service_pricing.setdefault("lab_tests", dict(DEFAULT_LAB_TEST_PRICING))
    service_pricing.setdefault("radiology", {})
    staff_fees.setdefault("doctor_consultation_fee_default", 0.0)

    radiology_services: List[Dict[str, Any]] = []
    if models.TABLES.get("radiology_service_catalog") is not None:
        rad = models.TABLES["radiology_service_catalog"]
        rows = db.execute(
            select(rad)
            .where(rad.c.hospital_id == int(hospital_id))
            .where(rad.c.is_active == 1)
            .order_by(rad.c.modality.asc(), rad.c.scan_name.asc())
        ).fetchall()
        radiology_services = [_serialize_row(r) for r in rows]

    service_pricing["radiology_services"] = radiology_services

    return {
        "hospital_id": int(hospital_id),
        "hospital_metadata": {
            "hospital_name": row.hospital_name or "",
            "address": row.address or "",
            "contact_number": row.contact_number or "",
            "logo_url": row.logo_url or "",
        },
        "service_pricing": service_pricing,
        "staff_fees": staff_fees,
        "updated_at": row.updated_at,
    }


@app.get("/")
def home() -> Dict[str, Any]:
    return {
        "system": "MedX Multi-Hospital System",
        "status": "Operational",
        "table_count": len(models.TABLES),
    }


@app.post("/auth/register")
def register_first_hospital(req: RegisterRequest, db: Session = Depends(get_db)) -> Dict[str, Any]:
    users_table = models.TABLES["users"]
    hospitals_table = models.TABLES["hospitals"]
    roles_table = models.TABLES["roles"]
    memberships_table = models.TABLES["hospital_user_memberships"]
    staff_table = models.TABLES["staff"]

    email = _normalize_email(req.email)
    existing_user = db.execute(select(users_table).where(func.lower(users_table.c.email) == email)).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already exists")

    existing_hospital = db.execute(select(hospitals_table).where(hospitals_table.c.hospital_code == req.hospital_code)).first()
    if existing_hospital:
        raise HTTPException(status_code=400, detail="Hospital code already exists")

    admin_role = db.execute(select(roles_table).where(roles_table.c.role_name == "ADMIN")).first()

    try:
        db.execute(insert(hospitals_table).values(hospital_code=req.hospital_code, hospital_name=req.hospital_name, status="ACTIVE"))
        hospital = db.execute(select(hospitals_table).where(hospitals_table.c.hospital_code == req.hospital_code)).first()

        db.execute(insert(users_table).values(email=email, password_hash=pwd_context.hash(req.password), is_active=1))
        user = db.execute(select(users_table).where(func.lower(users_table.c.email) == email)).first()

        db.execute(insert(staff_table).values(hospital_id=hospital.hospital_id, user_id=user.user_id, full_name=req.full_name, role="ADMIN", status="ACTIVE"))
        staff = db.execute(select(staff_table).where(staff_table.c.hospital_id == hospital.hospital_id).where(staff_table.c.user_id == user.user_id)).first()

        db.execute(insert(memberships_table).values(hospital_id=hospital.hospital_id, user_id=user.user_id, role_id=admin_role.role_id, staff_id=staff.staff_id, is_primary=1))
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Integrity error: {exc.orig}")

    return {"status": "registered", "hospital_id": hospital.hospital_id, "user_id": user.user_id}


@app.post("/auth/login")
def login(req: LoginRequest, db: Session = Depends(get_db)) -> Dict[str, Any]:
    users_table = models.TABLES["users"]
    email = _normalize_email(req.email)
    if not email:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    user = db.execute(select(users_table).where(func.lower(users_table.c.email) == email)).first()

    if not user or not pwd_context.verify(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="User is inactive")

    memberships = _get_user_memberships(db, user.user_id)
    if not memberships:
        raise HTTPException(status_code=403, detail="No hospital access found")

    selected = None
    if req.selected_hospital_id is not None:
        selected = next((m for m in memberships if m["hospital_id"] == req.selected_hospital_id), None)
        if not selected:
            raise HTTPException(status_code=403, detail="Selected hospital is not assigned to this user")
    elif len(memberships) == 1:
        selected = memberships[0]

    if not selected:
        return {"require_hospital_selection": True, "hospitals": memberships}

    token = _create_access_token(
        {
            "user_id": int(user.user_id),
            "sub": str(user.user_id),
            "email": user.email,
            "hospital_id": selected["hospital_id"],
            "hospital_name": selected["hospital_name"],
            "role_name": selected["role_name"],
            "role": selected["role_name"],
        }
    )

    return {
        "require_hospital_selection": False,
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "user_id": user.user_id,
            "email": user.email,
            "hospital_id": selected["hospital_id"],
            "hospital_name": selected["hospital_name"],
            "role_name": selected["role_name"],
        },
        "hospitals": memberships,
    }


@app.get("/auth/me")
def auth_me(current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    return current_user


@app.get("/public/plans")
def public_plans(db: Session = Depends(get_db)) -> Dict[str, Any]:
    plans_table = models.TABLES["subscription_plans"]
    rows = db.execute(select(plans_table).where(plans_table.c.is_active == 1)).fetchall()
    items = []
    for r in rows:
        item = _serialize_row(r)
        item["features"] = _safe_json_list(item.get("features_json"), [])
        item["is_active"] = bool(item.get("is_active"))
        items.append(item)
    return {"count": len(items), "items": items}


@app.post("/public/plans/purchase")
def public_purchase_plan(payload: PurchasePlanRequest, db: Session = Depends(get_db)) -> Dict[str, Any]:
    plans_table = models.TABLES["subscription_plans"]
    hospitals_table = models.TABLES["hospitals"]
    subs_table = models.TABLES["hospital_subscriptions"]
    settings_table = models.TABLES["hospital_settings"]

    plan = db.execute(select(plans_table).where(plans_table.c.plan_code == payload.plan_code)).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    hospital = db.execute(select(hospitals_table).where(hospitals_table.c.hospital_code == payload.hospital_code)).first()
    if not hospital:
        db.execute(
            insert(hospitals_table).values(
                hospital_code=payload.hospital_code,
                hospital_name=payload.hospital_name,
                email_contact=payload.admin_email,
                status="ACTIVE",
            )
        )
        hospital = db.execute(select(hospitals_table).where(hospitals_table.c.hospital_code == payload.hospital_code)).first()

    existing_setting = db.execute(select(settings_table).where(settings_table.c.hospital_id == hospital.hospital_id)).first()
    if not existing_setting:
        db.execute(
            insert(settings_table).values(
                hospital_id=hospital.hospital_id,
                hospital_name=hospital.hospital_name,
                email_contact=payload.admin_email,
                opd_hours="Mon-Sat: 9:00 AM - 5:00 PM",
                timezone="Asia/Karachi",
            )
        )

    cycle = payload.billing_cycle.lower()
    if cycle not in {"monthly", "yearly"}:
        raise HTTPException(status_code=400, detail="billing_cycle must be monthly or yearly")

    started = datetime.utcnow()
    expires = started + timedelta(days=30 if cycle == "monthly" else 365)
    amount = float(plan.monthly_price if cycle == "monthly" else plan.yearly_price)

    db.execute(
        insert(subs_table).values(
            hospital_id=hospital.hospital_id,
            plan_id=plan.plan_id,
            billing_cycle=cycle,
            started_at=started.isoformat(),
            expires_at=expires.isoformat(),
            status="ACTIVE",
            purchased_by_email=payload.admin_email,
            amount_paid=amount,
        )
    )
    db.commit()

    return {
        "status": "purchased",
        "hospital_id": hospital.hospital_id,
        "hospital_name": hospital.hospital_name,
        "plan_code": payload.plan_code,
        "billing_cycle": cycle,
        "expires_at": expires.isoformat(),
        "amount_paid": amount,
    }


@app.get("/public/hospitals/contacts")
def public_hospital_contacts(db: Session = Depends(get_db)) -> Dict[str, Any]:
    settings_table = models.TABLES["hospital_settings"]
    rows = db.execute(select(settings_table)).fetchall()
    return {"count": len(rows), "items": [_serialize_row(r) for r in rows]}


@app.get("/public/hospitals")
def public_hospitals(db: Session = Depends(get_db)) -> Dict[str, Any]:
    hospitals = models.TABLES["hospitals"]
    rows = db.execute(
        select(hospitals)
        .where(hospitals.c.status == "ACTIVE")
        .order_by(hospitals.c.hospital_name.asc())
    ).fetchall()
    return {"count": len(rows), "items": [_serialize_row(r) for r in rows]}


@app.get("/public/hospitals/{hospital_id}/doctors")
def public_hospital_doctors(
    hospital_id: int,
    q: str = Query(default=""),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    hospitals = models.TABLES["hospitals"]
    staff = models.TABLES["staff"]
    doctor_details = models.TABLES["doctor_details"]
    departments = models.TABLES["departments"]

    hospital = db.execute(
        select(hospitals.c.hospital_id, hospitals.c.status)
        .where(hospitals.c.hospital_id == int(hospital_id))
    ).first()
    if not hospital or str(hospital.status or "").upper() != "ACTIVE":
        raise HTTPException(status_code=404, detail="Hospital not found")

    term = (q or "").strip()
    query = (
        select(
            staff.c.staff_id.label("doctor_id"),
            staff.c.full_name,
            staff.c.phone_number,
            staff.c.status,
            departments.c.department_name,
            doctor_details.c.specialization,
            doctor_details.c.consultation_fee,
        )
        .select_from(
            staff.outerjoin(
                doctor_details,
                (staff.c.hospital_id == doctor_details.c.hospital_id)
                & (staff.c.staff_id == doctor_details.c.doctor_staff_id),
            ).outerjoin(
                departments,
                (staff.c.hospital_id == departments.c.hospital_id)
                & (staff.c.department_id == departments.c.department_id),
            )
        )
        .where(staff.c.hospital_id == int(hospital_id))
        .where(func.upper(staff.c.role) == "DOCTOR")
        .where(staff.c.status == "ACTIVE")
        .order_by(staff.c.full_name.asc())
    )
    if term:
        like_term = f"%{term}%"
        query = query.where(
            (staff.c.full_name.like(like_term))
            | (doctor_details.c.specialization.like(like_term))
            | (departments.c.department_name.like(like_term))
        )

    rows = db.execute(query).fetchall()
    items = []
    for row in rows:
        item = _serialize_row(row)
        item["specialization"] = item.get("specialization") or "General Medicine"
        item["consultation_fee"] = float(item.get("consultation_fee") or 0)
        items.append(item)
    return {"count": len(items), "items": items}


def _next_public_booking_mrn(db: Session, hospital_id: int) -> str:
    patients = models.TABLES["patients"]
    for _ in range(20):
        suffix = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")[-10:]
        candidate = f"WEB-{hospital_id}-{suffix}"
        exists = db.execute(
            select(patients.c.patient_id)
            .where(patients.c.hospital_id == int(hospital_id))
            .where(patients.c.patient_mrn == candidate)
        ).first()
        if not exists:
            return candidate
    return f"WEB-{hospital_id}-{uuid.uuid4().hex[:8].upper()}"


@app.post("/public/appointments/book")
def public_book_appointment(
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    hospitals = models.TABLES["hospitals"]
    staff = models.TABLES["staff"]
    patients = models.TABLES["patients"]
    appointments = models.TABLES["appointments"]

    hospital_id = int(payload.get("hospital_id") or 0)
    doctor_id = int(payload.get("doctor_id") or 0)
    patient_name = str(payload.get("patient_name") or "").strip()
    patient_phone = str(payload.get("patient_phone") or "").strip()
    appointment_date = str(payload.get("appointment_date") or "").strip()
    appointment_time = str(payload.get("appointment_time") or "").strip()
    appointment_type = str(payload.get("appointment_type") or "IN_PERSON").strip().upper()
    patient_gender = str(payload.get("patient_gender") or "").strip() or None
    patient_dob = str(payload.get("patient_dob") or "").strip() or None

    if hospital_id <= 0:
        raise HTTPException(status_code=400, detail="hospital_id is required")
    if doctor_id <= 0:
        raise HTTPException(status_code=400, detail="doctor_id is required")
    if not patient_name:
        raise HTTPException(status_code=400, detail="patient_name is required")
    if not patient_phone:
        raise HTTPException(status_code=400, detail="patient_phone is required")
    if not appointment_date or not appointment_time:
        raise HTTPException(status_code=400, detail="appointment_date and appointment_time are required")

    if appointment_type not in {"IN_PERSON", "VIDEO"}:
        raise HTTPException(status_code=400, detail="appointment_type must be IN_PERSON or VIDEO")

    try:
        dt_obj = datetime.strptime(f"{appointment_date} {appointment_time}", "%Y-%m-%d %H:%M")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid date/time format. Use YYYY-MM-DD and HH:MM")
    if dt_obj < datetime.utcnow() - timedelta(minutes=5):
        raise HTTPException(status_code=400, detail="Appointment time must be in the future")

    hospital = db.execute(
        select(hospitals.c.hospital_id, hospitals.c.hospital_name, hospitals.c.status)
        .where(hospitals.c.hospital_id == hospital_id)
    ).first()
    if not hospital or str(hospital.status or "").upper() != "ACTIVE":
        raise HTTPException(status_code=404, detail="Hospital not found")

    doctor = db.execute(
        select(staff.c.staff_id, staff.c.full_name, staff.c.role, staff.c.status)
        .where(staff.c.hospital_id == hospital_id)
        .where(staff.c.staff_id == doctor_id)
    ).first()
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found")
    if str(doctor.status or "").upper() != "ACTIVE" or str(doctor.role or "").upper() != "DOCTOR":
        raise HTTPException(status_code=400, detail="Selected doctor is unavailable")

    appointment_datetime = dt_obj.strftime("%Y-%m-%d %H:%M:%S")
    occupied = db.execute(
        select(appointments.c.appointment_id)
        .where(appointments.c.hospital_id == hospital_id)
        .where(appointments.c.doctor_id == doctor_id)
        .where(appointments.c.appointment_date == appointment_datetime)
        .where(appointments.c.status.in_(["SCHEDULED", "CONFIRMED", "BOOKED"]))
    ).first()
    if occupied:
        raise HTTPException(status_code=409, detail="Selected slot is already booked for this doctor")

    patient_recent_order = _recent_order_expr(patients, "created_at", "patient_id")
    existing_patient_query = (
        select(patients)
        .where(patients.c.hospital_id == hospital_id)
        .where(patients.c.full_name == patient_name)
        .where(patients.c.phone_number == patient_phone)
    )
    if patient_recent_order is not None:
        existing_patient_query = existing_patient_query.order_by(patient_recent_order)
    existing_patient = db.execute(existing_patient_query).first()

    if existing_patient:
        patient_id = int(existing_patient.patient_id)
        patient_mrn = str(existing_patient.patient_mrn)
    else:
        patient_mrn = _next_public_booking_mrn(db, hospital_id)
        patient_result = db.execute(
            insert(patients).values(
                hospital_id=hospital_id,
                patient_mrn=patient_mrn,
                full_name=patient_name,
                dob=patient_dob,
                gender=patient_gender,
                phone_number=patient_phone,
                insurance_provider_id=None,
            )
        )
        patient_id = patient_result.inserted_primary_key[0] if patient_result.inserted_primary_key else None
        if not patient_id:
            raise HTTPException(status_code=500, detail="Unable to create patient record")

    result = db.execute(
        insert(appointments).values(
            hospital_id=hospital_id,
            patient_id=int(patient_id),
            doctor_id=doctor_id,
            appointment_date=appointment_datetime,
            status="SCHEDULED",
            appointment_type=appointment_type,
            video_link=None,
        )
    )
    appointment_id = result.inserted_primary_key[0] if result.inserted_primary_key else None
    _log_activity_audit(
        db,
        hospital_id=hospital_id,
        actor_user_id=None,
        actor_staff_id=None,
        actor_role="PUBLIC",
        module="APPOINTMENT",
        action="PUBLIC_BOOKING",
        entity_type="APPOINTMENT",
        entity_id=int(appointment_id or 0) or None,
        details={
            "doctor_id": doctor_id,
            "doctor_name": doctor.full_name,
            "patient_id": int(patient_id),
            "patient_name": patient_name,
            "patient_mrn": patient_mrn,
            "appointment_date": appointment_datetime,
            "appointment_type": appointment_type,
        },
    )
    db.commit()

    return {
        "status": "booked",
        "appointment": {
            "appointment_id": appointment_id,
            "appointment_date": appointment_datetime,
            "appointment_type": appointment_type,
            "status": "SCHEDULED",
            "hospital_id": hospital_id,
            "hospital_name": hospital.hospital_name,
            "doctor_id": doctor_id,
            "doctor_name": doctor.full_name,
            "patient_id": int(patient_id),
            "patient_name": patient_name,
            "patient_mrn": patient_mrn,
            "patient_phone": patient_phone,
        },
    }


@app.get("/settings")
def get_global_settings(
    hospital_id: Optional[int] = Query(default=None, ge=1),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    target_hospital_id = current_user["hospital_id"]
    if hospital_id is not None:
        if (current_user.get("role_name") or "").upper() != "SUPER_ADMIN":
            raise HTTPException(status_code=403, detail="Only super admin can read settings of another hospital")
        target_hospital_id = int(hospital_id)
    return _build_settings_payload(db, int(target_hospital_id))


@app.put("/settings")
def update_global_settings(
    payload: Dict[str, Any] = Body(...),
    hospital_id: Optional[int] = Query(default=None, ge=1),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_admin(current_user)
    _ensure_global_settings_table(db)

    target_hospital_id = current_user["hospital_id"]
    if hospital_id is not None:
        if (current_user.get("role_name") or "").upper() != "SUPER_ADMIN":
            raise HTTPException(status_code=403, detail="Only super admin can update settings of another hospital")
        target_hospital_id = int(hospital_id)
    elif payload.get("hospital_id") is not None:
        if (current_user.get("role_name") or "").upper() != "SUPER_ADMIN":
            raise HTTPException(status_code=403, detail="Only super admin can update settings of another hospital")
        target_hospital_id = int(payload.get("hospital_id"))

    table = models.TABLES["global_settings"]
    existing = _ensure_global_settings_row(db, int(target_hospital_id))
    service_pricing = _safe_json_dict(existing.service_pricing_json, {})
    staff_fees = _safe_json_dict(existing.staff_fees_json, {})

    service_pricing.setdefault("patient_registration_fee", 0.0)
    service_pricing.setdefault("lab_tests", dict(DEFAULT_LAB_TEST_PRICING))
    service_pricing.setdefault("radiology", {})
    staff_fees.setdefault("doctor_consultation_fee_default", 0.0)

    metadata_payload = payload.get("hospital_metadata") or {}
    hospital_name = str(metadata_payload.get("hospital_name") or existing.hospital_name or "").strip()
    address = str(metadata_payload.get("address") or existing.address or "").strip() or None
    contact_number = str(metadata_payload.get("contact_number") or existing.contact_number or "").strip() or None
    logo_url = str(metadata_payload.get("logo_url") or existing.logo_url or "").strip() or None

    service_payload = payload.get("service_pricing") or {}
    if "patient_registration_fee" in service_payload:
        try:
            service_pricing["patient_registration_fee"] = float(service_payload.get("patient_registration_fee") or 0)
        except Exception:
            raise HTTPException(status_code=400, detail="patient_registration_fee must be numeric")

    if isinstance(service_payload.get("lab_tests"), dict):
        next_lab_tests = {}
        for k, v in service_payload["lab_tests"].items():
            key = str(k).strip()
            if not key:
                continue
            try:
                next_lab_tests[key] = float(v or 0)
            except Exception:
                raise HTTPException(status_code=400, detail=f"lab_tests value for '{key}' must be numeric")
        service_pricing["lab_tests"] = next_lab_tests

    radiology_updates = service_payload.get("radiology_services")
    if radiology_updates is not None and not isinstance(radiology_updates, list):
        raise HTTPException(status_code=400, detail="radiology_services must be a list")

    if radiology_updates and models.TABLES.get("radiology_service_catalog") is not None:
        services = models.TABLES["radiology_service_catalog"]
        for item in radiology_updates:
            service_id = item.get("service_id")
            if service_id is None:
                continue
            try:
                service_id = int(service_id)
                fee = float(item.get("service_fee") or 0)
            except Exception:
                raise HTTPException(status_code=400, detail="radiology_services entries require numeric service_id and service_fee")
            db.execute(
                update(services)
                .where(services.c.hospital_id == int(target_hospital_id))
                .where(services.c.service_id == service_id)
                .values(service_fee=fee)
            )

    if models.TABLES.get("radiology_service_catalog") is not None:
        services = models.TABLES["radiology_service_catalog"]
        rows = db.execute(
            select(services.c.service_id, services.c.service_fee)
            .where(services.c.hospital_id == int(target_hospital_id))
            .where(services.c.is_active == 1)
        ).fetchall()
        service_pricing["radiology"] = {str(r.service_id): float(r.service_fee or 0) for r in rows}

    staff_payload = payload.get("staff_fees") or {}
    if "doctor_consultation_fee_default" in staff_payload:
        try:
            consultation_fee = float(staff_payload.get("doctor_consultation_fee_default") or 0)
        except Exception:
            raise HTTPException(status_code=400, detail="doctor_consultation_fee_default must be numeric")
        staff_fees["doctor_consultation_fee_default"] = consultation_fee

        if models.TABLES.get("doctor_details") is not None:
            doctor_details = models.TABLES["doctor_details"]
            db.execute(
                update(doctor_details)
                .where(doctor_details.c.hospital_id == int(target_hospital_id))
                .values(consultation_fee=consultation_fee)
            )

    db.execute(
        update(table)
        .where(table.c.hospital_id == int(target_hospital_id))
        .values(
            hospital_name=hospital_name,
            address=address,
            contact_number=contact_number,
            logo_url=logo_url,
            service_pricing_json=json.dumps(service_pricing),
            staff_fees_json=json.dumps(staff_fees),
            updated_by_user_id=current_user["user_id"],
            updated_at=datetime.utcnow().isoformat(),
        )
    )

    if models.TABLES.get("hospital_settings") is not None:
        hs = models.TABLES["hospital_settings"]
        hs_row = db.execute(select(hs).where(hs.c.hospital_id == int(target_hospital_id))).first()
        hs_values = {
            "hospital_name": hospital_name or (hs_row.hospital_name if hs_row else "Hospital"),
            "address": address,
            "phone_contact": contact_number,
        }
        if hs_row:
            db.execute(update(hs).where(hs.c.hospital_id == int(target_hospital_id)).values(**hs_values))
        else:
            db.execute(insert(hs).values(hospital_id=int(target_hospital_id), **hs_values))

    hospitals = models.TABLES["hospitals"]
    db.execute(
        update(hospitals)
        .where(hospitals.c.hospital_id == int(target_hospital_id))
        .values(
            hospital_name=hospital_name or hospitals.c.hospital_name,
            address=address,
            phone_contact=contact_number,
        )
    )

    db.commit()
    return {"status": "updated", "settings": _build_settings_payload(db, int(target_hospital_id))}


@app.post("/admin/hospital-settings/upsert")
def upsert_hospital_settings(
    payload: HospitalSettingsUpsertRequest,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_admin(current_user)
    settings_table = models.TABLES["hospital_settings"]
    hospital_id = current_user["hospital_id"]

    existing = db.execute(select(settings_table).where(settings_table.c.hospital_id == hospital_id)).first()
    values = {
        "hospital_name": payload.hospital_name,
        "address": payload.address,
        "phone_contact": payload.phone_contact,
        "email_contact": payload.email_contact,
        "emergency_line": payload.emergency_line,
        "opd_hours": payload.opd_hours,
        "timezone": payload.timezone,
    }

    if existing:
        db.execute(update(settings_table).where(settings_table.c.hospital_id == hospital_id).values(**values))
        status = "updated"
    else:
        db.execute(insert(settings_table).values(hospital_id=hospital_id, **values))
        status = "created"

    db.commit()
    if models.TABLES.get("global_settings") is not None:
        _ensure_global_settings_row(db, hospital_id)
        gs = models.TABLES["global_settings"]
        db.execute(
            update(gs)
            .where(gs.c.hospital_id == hospital_id)
            .values(
                hospital_name=payload.hospital_name,
                address=payload.address,
                contact_number=payload.phone_contact,
                updated_by_user_id=current_user["user_id"],
                updated_at=datetime.utcnow().isoformat(),
            )
        )
        db.commit()

    row = db.execute(select(settings_table).where(settings_table.c.hospital_id == hospital_id)).first()
    return {"status": status, "hospital_id": hospital_id, "item": _serialize_row(row)}


@app.post("/ai/reports/generate")
def generate_ai_report(
    payload: AIReportRequest,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    if (current_user.get("role_name") or "").upper() not in {"ADMIN", "SUPER_ADMIN", "DOCTOR", "NURSE"}:
        raise HTTPException(status_code=403, detail="Role not allowed for AI report generation")

    reports_table = models.TABLES["ai_generated_reports"]
    hospital_id = current_user["hospital_id"]
    analysis = _generate_ai_summary(payload.source_context)
    printable_token = uuid.uuid4().hex

    result = db.execute(
        insert(reports_table).values(
            hospital_id=hospital_id,
            patient_id=payload.patient_id,
            doctor_id=payload.doctor_id,
            report_title=payload.report_title,
            source_context=payload.source_context,
            ai_summary=analysis["summary"],
            ai_recommendation=analysis["recommendation"],
            delivered_to_doctor=1 if payload.doctor_id else 0,
            delivered_to_patient=1 if payload.patient_id else 0,
            printable_token=printable_token,
        )
    )
    db.commit()

    inserted_id = result.inserted_primary_key[0] if result.inserted_primary_key else None
    report = db.execute(
        select(reports_table)
        .where(reports_table.c.hospital_id == hospital_id)
        .where(reports_table.c.report_id == inserted_id)
    ).first()

    return {
        "status": "generated",
        "delivery": {
            "doctor": bool(payload.doctor_id),
            "patient": bool(payload.patient_id),
        },
        "report": _serialize_row(report),
    }


@app.get("/ai/reports")
def list_ai_reports(
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    reports_table = models.TABLES["ai_generated_reports"]
    rows = db.execute(
        select(reports_table)
        .where(reports_table.c.hospital_id == current_user["hospital_id"])
        .limit(limit)
        .offset(offset)
    ).fetchall()
    return {
        "count": len(rows),
        "items": [_serialize_row(r) for r in rows],
    }


@app.get("/super-admin/subscriptions")
def super_admin_subscriptions(
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_super_admin(current_user)
    _ensure_hospital_subscription_columns(db)

    subs = models.TABLES["hospital_subscriptions"]
    plans = models.TABLES["subscription_plans"]
    hospitals = models.TABLES["hospitals"]

    subscription_rows = db.execute(
        select(
            subs.c.subscription_id,
            subs.c.hospital_id,
            subs.c.status,
            subs.c.billing_cycle,
            subs.c.started_at,
            subs.c.expires_at,
            subs.c.suspended_at,
            subs.c.amount_paid,
            subs.c.purchased_by_email,
            plans.c.plan_code,
            plans.c.plan_name,
        )
        .select_from(subs.join(plans, subs.c.plan_id == plans.c.plan_id))
        .order_by(subs.c.hospital_id.asc(), subs.c.started_at.desc(), subs.c.subscription_id.desc())
    ).fetchall()

    latest_sub_by_hospital: Dict[int, Dict[str, Any]] = {}
    for row in subscription_rows:
        serialized = _serialize_row(row)
        hid = int(serialized.get("hospital_id") or 0)
        if hid > 0 and hid not in latest_sub_by_hospital:
            latest_sub_by_hospital[hid] = serialized

    hospital_rows = db.execute(
        select(
            hospitals.c.hospital_id,
            hospitals.c.hospital_code,
            hospitals.c.hospital_name,
            hospitals.c.status.label("hospital_status"),
            hospitals.c.created_at.label("hospital_created_at"),
        ).order_by(hospitals.c.hospital_name.asc())
    ).fetchall()

    items: List[Dict[str, Any]] = []
    for h in hospital_rows:
        hospital_item = _serialize_row(h)
        latest = latest_sub_by_hospital.get(int(hospital_item["hospital_id"]))
        if latest:
            hospital_item.update(
                {
                    "subscription_id": latest.get("subscription_id"),
                    "status": latest.get("status"),
                    "billing_cycle": latest.get("billing_cycle"),
                    "started_at": latest.get("started_at"),
                    "expires_at": latest.get("expires_at"),
                    "suspended_at": latest.get("suspended_at"),
                    "amount_paid": latest.get("amount_paid"),
                    "purchased_by_email": latest.get("purchased_by_email"),
                    "plan_code": latest.get("plan_code"),
                    "plan_name": latest.get("plan_name"),
                }
            )
        else:
            hospital_item.update(
                {
                    "subscription_id": None,
                    "status": "NO_SUBSCRIPTION",
                    "billing_cycle": None,
                    "started_at": None,
                    "expires_at": None,
                    "suspended_at": None,
                    "amount_paid": 0,
                    "purchased_by_email": None,
                    "plan_code": None,
                    "plan_name": None,
                }
            )
        items.append(hospital_item)

    return {"count": len(items), "items": items}


@app.get("/super-admin/pricing/plans")
def super_admin_pricing_plans(
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_super_admin(current_user)

    plans = models.TABLES["subscription_plans"]
    rows = db.execute(select(plans).order_by(plans.c.plan_id.asc())).fetchall()
    items: List[Dict[str, Any]] = []
    for row in rows:
        item = _serialize_row(row)
        item["features"] = _safe_json_list(item.get("features_json"), [])
        item["is_active"] = bool(item.get("is_active"))
        items.append(item)
    return {"count": len(items), "items": items}


@app.post("/super-admin/pricing/plans/{plan_id}")
def super_admin_pricing_update_plan(
    plan_id: int,
    payload: SubscriptionPlanUpdateRequest,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_super_admin(current_user)

    plans = models.TABLES["subscription_plans"]
    existing = db.execute(select(plans).where(plans.c.plan_id == int(plan_id))).first()
    if not existing:
        raise HTTPException(status_code=404, detail="Plan not found")

    updates: Dict[str, Any] = {}

    if payload.plan_name is not None:
        plan_name = payload.plan_name.strip()
        if not plan_name:
            raise HTTPException(status_code=400, detail="plan_name cannot be empty")
        updates["plan_name"] = plan_name

    if payload.monthly_price is not None:
        monthly = float(payload.monthly_price)
        if monthly < 0:
            raise HTTPException(status_code=400, detail="monthly_price cannot be negative")
        updates["monthly_price"] = monthly

    if payload.yearly_price is not None:
        yearly = float(payload.yearly_price)
        if yearly < 0:
            raise HTTPException(status_code=400, detail="yearly_price cannot be negative")
        updates["yearly_price"] = yearly

    if payload.features is not None:
        cleaned_features = [str(feature).strip() for feature in payload.features if str(feature).strip()]
        updates["features_json"] = json.dumps(cleaned_features)

    if payload.is_active is not None:
        updates["is_active"] = 1 if payload.is_active else 0

    if not updates:
        raise HTTPException(status_code=400, detail="No fields provided for update")

    db.execute(update(plans).where(plans.c.plan_id == int(plan_id)).values(**updates))
    db.commit()

    refreshed = db.execute(select(plans).where(plans.c.plan_id == int(plan_id))).first()
    item = _serialize_row(refreshed)
    item["features"] = _safe_json_list(item.get("features_json"), [])
    item["is_active"] = bool(item.get("is_active"))
    return {"status": "updated", "item": item}


@app.get("/super-admin/overview")
def super_admin_overview(
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_super_admin(current_user)

    hospitals = models.TABLES["hospitals"]
    subs = models.TABLES["hospital_subscriptions"]

    hospitals_count = db.execute(select(hospitals.c.hospital_id)).fetchall()
    active_subs = db.execute(select(subs).where(subs.c.status == "ACTIVE")).fetchall()

    threshold = (datetime.utcnow() + timedelta(days=30)).isoformat()
    expiring_soon = db.execute(
        select(subs).where(subs.c.status == "ACTIVE").where(subs.c.expires_at <= threshold)
    ).fetchall()

    return {
        "hospitals": len(hospitals_count),
        "active_subscriptions": len(active_subs),
        "expiring_in_30_days": len(expiring_soon),
    }


def _make_get_handler(table_name: str):
    table = models.TABLES[table_name]

    def get_rows(
        limit: int = Query(default=100, ge=1, le=1000),
        offset: int = Query(default=0, ge=0),
        db: Session = Depends(get_db),
        current_user: Dict[str, Any] = Depends(get_current_user),
    ) -> Dict[str, Any]:
        hospital_id = current_user["hospital_id"]

        if table_name == "staff" and models.TABLES.get("users") is not None and _table_has_column(table, "user_id"):
            users = models.TABLES["users"]
            query = (
                select(table, users.c.email.label("email"))
                .select_from(
                    table.outerjoin(users, table.c.user_id == users.c.user_id)
                )
                .where(table.c.hospital_id == hospital_id)
            )
            rows = db.execute(query.limit(limit).offset(offset)).fetchall()
        elif table_name == "patients":
            portal = models.TABLES.get("patient_portal_accounts")
            users = models.TABLES.get("users")
            if portal is not None and users is not None:
                query = (
                    select(table, users.c.email.label("portal_email"))
                    .select_from(
                        table.outerjoin(
                            portal,
                            (table.c.hospital_id == portal.c.hospital_id)
                            & (table.c.patient_id == portal.c.patient_id),
                        ).outerjoin(users, portal.c.user_id == users.c.user_id)
                    )
                    .where(table.c.hospital_id == hospital_id)
                )
                rows = db.execute(query.limit(limit).offset(offset)).fetchall()
            else:
                query = select(table).where(table.c.hospital_id == hospital_id)
                rows = db.execute(query.limit(limit).offset(offset)).fetchall()
        else:
            query = select(table)
            if _table_has_column(table, "hospital_id"):
                query = query.where(table.c.hospital_id == hospital_id)
            rows = db.execute(query.limit(limit).offset(offset)).fetchall()

        return {
            "table": table_name,
            "hospital_id": hospital_id,
            "count": len(rows),
            "items": [_serialize_row(r) for r in rows],
        }

    return get_rows


def _make_public_get_handler(table_name: str):
    table = models.TABLES[table_name]

    def get_rows(
        limit: int = Query(default=100, ge=1, le=1000),
        offset: int = Query(default=0, ge=0),
        db: Session = Depends(get_db),
    ) -> Dict[str, Any]:
        rows = db.execute(select(table).limit(limit).offset(offset)).fetchall()
        return {"table": table_name, "count": len(rows), "items": [_serialize_row(r) for r in rows]}

    return get_rows


def _make_post_handler(table_name: str):
    table = models.TABLES[table_name]
    valid_columns = {c.name for c in table.columns}

    def create_row(
        payload: Dict[str, Any] = Body(...),
        db: Session = Depends(get_db),
        current_user: Dict[str, Any] = Depends(get_current_user),
    ) -> Dict[str, Any]:
        _require_admin(current_user)

        unknown_columns = sorted(set(payload.keys()) - valid_columns)
        if unknown_columns:
            raise HTTPException(status_code=400, detail=f"Unknown columns for {table_name}: {', '.join(unknown_columns)}")

        if _table_has_column(table, "hospital_id"):
            client_hospital_id = payload.get("hospital_id")
            if client_hospital_id is not None and int(client_hospital_id) != current_user["hospital_id"]:
                raise HTTPException(status_code=403, detail="Cross-hospital write is not allowed")
            payload["hospital_id"] = current_user["hospital_id"]

        try:
            result = db.execute(insert(table).values(**payload))
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(status_code=400, detail=f"Integrity error: {exc.orig}")
        except SQLAlchemyError as exc:
            db.rollback()
            raise HTTPException(status_code=500, detail=f"Database error: {str(exc)}")

        return {
            "table": table_name,
            "status": "created",
            "hospital_id": current_user["hospital_id"],
            "inserted_primary_key": [_serialize_value(v) for v in (result.inserted_primary_key or [])],
            "payload": payload,
        }

    return create_row


def _make_public_post_handler(table_name: str):
    table = models.TABLES[table_name]
    valid_columns = {c.name for c in table.columns}

    def create_row(payload: Dict[str, Any] = Body(...), db: Session = Depends(get_db)) -> Dict[str, Any]:
        unknown_columns = sorted(set(payload.keys()) - valid_columns)
        if unknown_columns:
            raise HTTPException(status_code=400, detail=f"Unknown columns for {table_name}: {', '.join(unknown_columns)}")

        result = db.execute(insert(table).values(**payload))
        db.commit()
        return {
            "table": table_name,
            "status": "created",
            "inserted_primary_key": [_serialize_value(v) for v in (result.inserted_primary_key or [])],
            "payload": payload,
        }

    return create_row


PUBLIC_GET_TABLES = {"hospital_settings"}
PUBLIC_POST_TABLES = {"contact_messages"}

for table_name in sorted(models.TABLES.keys()):
    get_handler = _make_public_get_handler(table_name) if table_name in PUBLIC_GET_TABLES else _make_get_handler(table_name)
    post_handler = _make_public_post_handler(table_name) if table_name in PUBLIC_POST_TABLES else _make_post_handler(table_name)

    app.get(f"/{table_name}/", name=f"get_{table_name}", tags=["tables"])(get_handler)
    app.post(f"/{table_name}/", name=f"post_{table_name}", tags=["tables"])(post_handler)

# ======================= ADDITIONAL ACCOUNT & ADMIN ENDPOINTS =======================
@app.post("/auth/change-password")
def auth_change_password(
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    current_password = (payload.get("current_password") or "").strip()
    new_password = (payload.get("new_password") or "").strip()

    if not current_password or not new_password:
        raise HTTPException(status_code=400, detail="current_password and new_password are required")
    if len(new_password) < 8:
        raise HTTPException(status_code=400, detail="New password must be at least 8 characters")

    users_table = models.TABLES["users"]
    user_row = db.execute(select(users_table).where(users_table.c.user_id == current_user["user_id"])).first()
    if not user_row:
        raise HTTPException(status_code=404, detail="User not found")

    if not pwd_context.verify(current_password, user_row.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    db.execute(
        update(users_table)
        .where(users_table.c.user_id == current_user["user_id"])
        .values(password_hash=pwd_context.hash(new_password))
    )
    db.commit()
    return {"status": "password_updated"}


@app.post("/admin/users/create")
def admin_create_user(
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_admin(current_user)

    required_fields = ["full_name", "email", "password", "role_name"]
    missing = [f for f in required_fields if not payload.get(f)]
    if missing:
        raise HTTPException(status_code=400, detail=f"Missing fields: {', '.join(missing)}")

    full_name = payload["full_name"].strip()
    email = payload["email"].strip().lower()
    password = payload["password"].strip()
    role_name = payload["role_name"].strip().upper().replace(" ", "_")
    phone_number = (payload.get("phone_number") or "").strip() or None
    department_name = (payload.get("department_name") or "").strip() or None
    department_location = (payload.get("department_location") or "").strip() or None
    license_number = (payload.get("license_number") or "").strip() or None

    alias = {
        "RECEPTION": "RECEPTIONIST",
        "LABORATORY": "LAB",
        "LAB_TECH": "LAB",
        "LAB_TECHNICIAN": "LAB",
        "FINANCE": "ACCOUNTANT",
        "ACCOUNTS": "ACCOUNTANT",
        "FLEET_MANAGER": "FLEET",
        "AMBULANCE": "FLEET",
    }
    role_name = alias.get(role_name, role_name)

    users_table = models.TABLES["users"]
    roles_table = models.TABLES["roles"]
    staff_table = models.TABLES["staff"]
    memberships_table = models.TABLES["hospital_user_memberships"]
    departments_table = models.TABLES["departments"]

    role = db.execute(select(roles_table).where(roles_table.c.role_name == role_name)).first()
    if not role:
        db.execute(insert(roles_table).values(role_name=role_name))
        db.commit()
        role = db.execute(select(roles_table).where(roles_table.c.role_name == role_name)).first()

    hospital_id = current_user["hospital_id"]
    department_id = None

    if department_name:
        department = db.execute(
            select(departments_table)
            .where(departments_table.c.hospital_id == hospital_id)
            .where(departments_table.c.department_name == department_name)
        ).first()

        if not department:
            db.execute(
                insert(departments_table).values(
                    hospital_id=hospital_id,
                    department_name=department_name,
                    location=department_location,
                )
            )
            db.commit()
            department = db.execute(
                select(departments_table)
                .where(departments_table.c.hospital_id == hospital_id)
                .where(departments_table.c.department_name == department_name)
            ).first()
        department_id = department.department_id

    existing_user = db.execute(select(users_table).where(func.lower(users_table.c.email) == email)).first()

    try:
        if existing_user:
            user_id = existing_user.user_id

            existing_membership = db.execute(
                select(memberships_table)
                .where(memberships_table.c.hospital_id == hospital_id)
                .where(memberships_table.c.user_id == user_id)
            ).first()
            if existing_membership:
                raise HTTPException(status_code=400, detail="Email already exists")
            db.execute(
                update(users_table)
                .where(users_table.c.user_id == user_id)
                .values(password_hash=pwd_context.hash(password), is_active=1)
            )
        else:
            user_result = db.execute(
                insert(users_table).values(
                    email=email,
                    password_hash=pwd_context.hash(password),
                    is_active=1,
                )
            )
            user_id = user_result.inserted_primary_key[0] if user_result.inserted_primary_key else None

        staff_result = db.execute(
            insert(staff_table).values(
                hospital_id=hospital_id,
                user_id=user_id,
                full_name=full_name,
                role=role_name,
                phone_number=phone_number,
                department_id=department_id,
                license_number=license_number,
                status="ACTIVE",
            )
        )
        staff_id = staff_result.inserted_primary_key[0] if staff_result.inserted_primary_key else None

        db.execute(
            insert(memberships_table).values(
                hospital_id=hospital_id,
                user_id=user_id,
                role_id=role.role_id,
                staff_id=staff_id,
                is_primary=0,
            )
        )

        db.commit()

        persisted_user = db.execute(select(users_table).where(users_table.c.user_id == user_id)).first()
        persisted_membership = db.execute(
            select(memberships_table.c.membership_id)
            .where(memberships_table.c.hospital_id == hospital_id)
            .where(memberships_table.c.user_id == user_id)
        ).first()
        if not persisted_user or not persisted_membership:
            raise HTTPException(status_code=500, detail="User creation did not persist correctly")
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Integrity error: {exc.orig}")

    return {
        "status": "created",
        "user_id": user_id,
        "staff_id": staff_id,
        "role_name": role_name,
        "department_id": department_id,
    }
# ======================= DOCTOR WORKSPACE ENDPOINTS =======================
def _require_roles(current_user: Dict[str, Any], allowed_roles: set[str]) -> None:
    role = (current_user.get("role_name") or "").upper()
    if role not in allowed_roles:
        allowed = ", ".join(sorted(allowed_roles))
        raise HTTPException(status_code=403, detail=f"Role not allowed. Allowed: {allowed}")


def _get_current_staff_id(db: Session, current_user: Dict[str, Any]) -> Optional[int]:
    memberships_table = models.TABLES["hospital_user_memberships"]
    staff_table = models.TABLES["staff"]
    hospital_id = current_user["hospital_id"]
    user_id = current_user["user_id"]

    membership = db.execute(
        select(memberships_table.c.staff_id)
        .where(memberships_table.c.hospital_id == hospital_id)
        .where(memberships_table.c.user_id == user_id)
    ).first()
    if membership and membership.staff_id:
        return int(membership.staff_id)

    staff = db.execute(
        select(staff_table.c.staff_id)
        .where(staff_table.c.hospital_id == hospital_id)
        .where(staff_table.c.user_id == user_id)
    ).first()
    return int(staff.staff_id) if staff and staff.staff_id else None

def _record_reception_visit(
    db: Session,
    hospital_id: int,
    patient_id: int,
    current_user: Dict[str, Any],
    payload: Dict[str, Any],
) -> None:
    visits_table = models.TABLES.get("reception_patient_visits")
    if visits_table is None:
        return

    visit_type = (payload.get("visit_type") or "OPD").strip().upper()
    if not visit_type:
        visit_type = "OPD"

    status = (payload.get("visit_status") or "REGISTERED").strip().upper()
    if not status:
        status = "REGISTERED"

    db.execute(
        insert(visits_table).values(
            hospital_id=hospital_id,
            patient_id=int(patient_id),
            reception_staff_id=_get_current_staff_id(db, current_user),
            visit_type=visit_type,
            chief_complaint=(payload.get("chief_complaint") or None),
            status=status,
        )
    )



LAB_TEST_CATALOG: Dict[str, Dict[str, Any]] = {
    "diabetes": {
        "label": "Diabetes",
        "ai_path": "/predict/diabetes",
        "fields": [
            {"key": "pregnancies", "label": "Pregnancies"},
            {"key": "glucose", "label": "Glucose"},
            {"key": "bp", "label": "Blood Pressure"},
            {"key": "skin", "label": "Skin Thickness"},
            {"key": "insulin", "label": "Insulin"},
            {"key": "bmi", "label": "BMI"},
            {"key": "dpf", "label": "Diabetes Pedigree Function"},
            {"key": "age", "label": "Age"},
        ],
    },
    "heart": {
        "label": "Heart Disease",
        "ai_path": "/predict/heart",
        "fields": [
            {"key": "age", "label": "Age"},
            {"key": "sex", "label": "Sex (0/1)"},
            {"key": "cp", "label": "Chest Pain Type"},
            {"key": "trestbps", "label": "Resting BP"},
            {"key": "chol", "label": "Cholesterol"},
            {"key": "fbs", "label": "Fasting Blood Sugar >120 (0/1)"},
            {"key": "restecg", "label": "Rest ECG"},
            {"key": "thalach", "label": "Max Heart Rate"},
            {"key": "exang", "label": "Exercise Angina (0/1)"},
            {"key": "oldpeak", "label": "Oldpeak"},
            {"key": "slope", "label": "Slope"},
            {"key": "ca", "label": "Major Vessels (CA)"},
            {"key": "thal", "label": "Thal"},
        ],
    },
    "liver": {
        "label": "Liver Disease",
        "ai_path": "/predict/liver",
        "fields": [
            {"key": "age", "label": "Age"},
            {"key": "gender", "label": "Gender (0/1)"},
            {"key": "total_bilirubin", "label": "Total Bilirubin"},
            {"key": "direct_bilirubin", "label": "Direct Bilirubin"},
            {"key": "alkaline_phosphotase", "label": "Alkaline Phosphotase"},
            {"key": "alamine_aminotransferase", "label": "Alamine Aminotransferase"},
            {"key": "aspartate_aminotransferase", "label": "Aspartate Aminotransferase"},
            {"key": "total_proteins", "label": "Total Proteins"},
            {"key": "albumin", "label": "Albumin"},
            {"key": "albumin_and_globulin_ratio", "label": "Albumin/Globulin Ratio"},
        ],
    },
    "kidney": {
        "label": "Kidney Disease",
        "ai_path": "/predict/kidney",
        "fields": [
            {"key": "age", "label": "Age"}, {"key": "bp", "label": "Blood Pressure"}, {"key": "sg", "label": "Specific Gravity"},
            {"key": "al", "label": "Albumin"}, {"key": "su", "label": "Sugar"}, {"key": "rbc", "label": "RBC (0/1)"},
            {"key": "pc", "label": "Pus Cell (0/1)"}, {"key": "pcc", "label": "Pus Cell Clumps (0/1)"}, {"key": "ba", "label": "Bacteria (0/1)"},
            {"key": "bgr", "label": "Blood Glucose Random"}, {"key": "bu", "label": "Blood Urea"}, {"key": "sc", "label": "Serum Creatinine"},
            {"key": "sod", "label": "Sodium"}, {"key": "pot", "label": "Potassium"}, {"key": "hemo", "label": "Hemoglobin"},
            {"key": "pcv", "label": "Packed Cell Volume"}, {"key": "wc", "label": "White Blood Cell Count"}, {"key": "rc", "label": "Red Blood Cell Count"},
            {"key": "htn", "label": "Hypertension (0/1)"}, {"key": "dm", "label": "Diabetes Mellitus (0/1)"}, {"key": "cad", "label": "Coronary Artery Disease (0/1)"},
            {"key": "appet", "label": "Appetite (0/1)"}, {"key": "pe", "label": "Pedal Edema (0/1)"}, {"key": "ane", "label": "Anemia (0/1)"},
        ],
    },
    "breast_cancer": {
        "label": "Breast Cancer",
        "ai_path": "/predict/breast_cancer",
        "fields": [
            {"key": "radius", "label": "Radius"},
            {"key": "texture", "label": "Texture"},
            {"key": "perimeter", "label": "Perimeter"},
            {"key": "area", "label": "Area"},
            {"key": "smoothness", "label": "Smoothness"},
        ],
    },
    "parkinsons": {
        "label": "Parkinson's",
        "ai_path": "/predict/parkinsons",
        "fields": [
            {"key": "mdvp_fo", "label": "MDVP:Fo(Hz)"}, {"key": "mdvp_fhi", "label": "MDVP:Fhi(Hz)"}, {"key": "mdvp_flo", "label": "MDVP:Flo(Hz)"},
            {"key": "mdvp_jitter_percent", "label": "MDVP:Jitter(%)"}, {"key": "mdvp_jitter_abs", "label": "MDVP:Jitter(Abs)"}, {"key": "mdvp_rap", "label": "MDVP:RAP"},
            {"key": "mdvp_ppq", "label": "MDVP:PPQ"}, {"key": "jitter_ddp", "label": "Jitter:DDP"}, {"key": "mdvp_shimmer", "label": "MDVP:Shimmer"},
            {"key": "mdvp_shimmer_db", "label": "MDVP:Shimmer(dB)"}, {"key": "shimmer_apq3", "label": "Shimmer:APQ3"}, {"key": "shimmer_apq5", "label": "Shimmer:APQ5"},
            {"key": "mdvp_apq", "label": "MDVP:APQ"}, {"key": "shimmer_dda", "label": "Shimmer:DDA"}, {"key": "nhr", "label": "NHR"},
            {"key": "hnr", "label": "HNR"}, {"key": "rpde", "label": "RPDE"}, {"key": "dfa", "label": "DFA"},
            {"key": "spread1", "label": "Spread1"}, {"key": "spread2", "label": "Spread2"}, {"key": "d2", "label": "D2"}, {"key": "ppe", "label": "PPE"},
        ],
    },
}

LAB_STANDARD_PANELS: Dict[str, Any] = {
    "CBC": [
        {"key": "cbc_hemoglobin", "label": "Hemoglobin", "unit": "g/dL", "range": "12-17"},
        {"key": "cbc_wbc", "label": "WBC", "unit": "x10^9/L", "range": "4-11"},
        {"key": "cbc_rbc", "label": "RBC", "unit": "x10^12/L", "range": "4.2-6.1"},
        {"key": "cbc_platelets", "label": "Platelets", "unit": "x10^9/L", "range": "150-450"},
    ],
    "BLOOD_SUGAR": [
        {"key": "sugar_fasting", "label": "Fasting Glucose", "unit": "mg/dL", "range": "70-99"},
        {"key": "sugar_random", "label": "Random Glucose", "unit": "mg/dL", "range": "70-140"},
        {"key": "hba1c", "label": "HbA1c", "unit": "%", "range": "4.0-5.6"},
    ],
    "CHOLESTEROL": [
        {"key": "chol_total", "label": "Total Cholesterol", "unit": "mg/dL", "range": "<200"},
        {"key": "chol_hdl", "label": "HDL", "unit": "mg/dL", "range": ">40"},
        {"key": "chol_ldl", "label": "LDL", "unit": "mg/dL", "range": "<100"},
        {"key": "chol_trig", "label": "Triglycerides", "unit": "mg/dL", "range": "<150"},
    ],
    "LIVER_FUNCTION": [
        {"key": "total_bilirubin", "label": "Total Bilirubin", "unit": "mg/dL", "range": "0.3-1.2"},
        {"key": "direct_bilirubin", "label": "Direct Bilirubin", "unit": "mg/dL", "range": "0.0-0.3"},
        {"key": "alkaline_phosphotase", "label": "Alkaline Phosphotase", "unit": "U/L", "range": "44-147"},
        {"key": "alamine_aminotransferase", "label": "ALT", "unit": "U/L", "range": "7-56"},
        {"key": "aspartate_aminotransferase", "label": "AST", "unit": "U/L", "range": "10-40"},
        {"key": "total_proteins", "label": "Total Proteins", "unit": "g/dL", "range": "6.0-8.3"},
        {"key": "albumin", "label": "Albumin", "unit": "g/dL", "range": "3.4-5.4"},
        {"key": "albumin_and_globulin_ratio", "label": "A/G Ratio", "unit": "ratio", "range": "1.0-2.5"},
    ],
}

LAB_CLINICAL_FORM_TESTS: Dict[str, Dict[str, Any]] = {
    "CBC": {
        "label": "CBC (Haematology)",
        "department": "Haematology",
        "markers": [
            {"key": "wbc", "marker_name": "WBC", "units": "x10^9/L", "reference_range": {"min": 4.0, "max": 11.0}},
            {"key": "rbc", "marker_name": "RBC", "units": "x10^12/L", "reference_range": {"min": 4.2, "max": 6.1}},
            {"key": "haemoglobin", "marker_name": "Haemoglobin", "units": "g/dL", "reference_range": {"min": 12.0, "max": 17.0}},
            {"key": "hct", "marker_name": "HCT", "units": "%", "reference_range": {"min": 36.0, "max": 52.0}},
            {"key": "mcv", "marker_name": "MCV", "units": "fL", "reference_range": {"min": 80.0, "max": 100.0}},
            {"key": "mch", "marker_name": "MCH", "units": "pg", "reference_range": {"min": 27.0, "max": 33.0}},
            {"key": "platelets", "marker_name": "Platelets", "units": "x10^9/L", "reference_range": {"min": 150.0, "max": 450.0}},
        ],
    },
    "LFT": {
        "label": "LFT (Biochemistry)",
        "department": "Biochemistry",
        "markers": [
            {"key": "bilirubin", "marker_name": "Bilirubin", "units": "mg/dL", "reference_range": {"min": 0.3, "max": 1.2}},
            {"key": "alt", "marker_name": "ALT", "units": "U/L", "reference_range": {"min": 7.0, "max": 56.0}},
            {"key": "ast", "marker_name": "AST", "units": "U/L", "reference_range": {"min": 10.0, "max": 40.0}},
            {"key": "alkaline_phosphatase", "marker_name": "Alkaline Phosphatase", "units": "U/L", "reference_range": {"min": 44.0, "max": 147.0}},
            {"key": "albumin", "marker_name": "Albumin", "units": "g/dL", "reference_range": {"min": 3.4, "max": 5.4}},
        ],
    },
    "RFT": {
        "label": "RFT (Biochemistry)",
        "department": "Biochemistry",
        "markers": [
            {"key": "creatinine", "marker_name": "Creatinine", "units": "mg/dL", "reference_range": {"min": 0.7, "max": 1.3}},
            {"key": "urea", "marker_name": "Urea", "units": "mg/dL", "reference_range": {"min": 7.0, "max": 20.0}},
            {"key": "sodium", "marker_name": "Sodium", "units": "mmol/L", "reference_range": {"min": 135.0, "max": 145.0}},
            {"key": "potassium", "marker_name": "Potassium", "units": "mmol/L", "reference_range": {"min": 3.5, "max": 5.1}},
        ],
    },
    "DIABETES": {
        "label": "Diabetes (AI-Integrated)",
        "department": "Biochemistry",
        "ai_test_key": "diabetes",
        "markers": [
            {
                "key": "glucose",
                "marker_name": "Glucose",
                "units": "mg/dL",
                "reference_range": {"min": 70.0, "max": 99.0},
                "description": "Plasma glucose concentration (2-hour oral glucose tolerance test).",
            },
            {
                "key": "bp",
                "marker_name": "Blood Pressure",
                "units": "mm Hg",
                "reference_range": {"min": 60.0, "max": 90.0},
                "description": "Diastolic blood pressure.",
            },
            {
                "key": "insulin",
                "marker_name": "Insulin",
                "units": "mu U/ml",
                "reference_range": {"min": 2.0, "max": 25.0},
                "description": "2-hour serum insulin.",
            },
            {
                "key": "bmi",
                "marker_name": "BMI",
                "units": "kg/m2",
                "reference_range": {"min": 18.5, "max": 24.9},
                "description": "Body Mass Index (weight in kg / (height in m)^2).",
            },
            {
                "key": "pregnancies",
                "marker_name": "Pregnancies",
                "units": "count",
                "reference_range": {"min": 0.0, "max": 20.0},
                "description": "Number of times the patient has been pregnant.",
            },
            {
                "key": "skin",
                "marker_name": "Skin Thickness",
                "units": "mm",
                "reference_range": {"min": 10.0, "max": 50.0},
                "description": "Triceps skin fold thickness.",
            },
            {
                "key": "dpf",
                "marker_name": "Diabetes Pedigree Function",
                "units": "score",
                "reference_range": {"min": 0.0, "max": 2.5},
                "description": "Genetic likelihood score based on family history.",
            },
            {
                "key": "age",
                "marker_name": "Age",
                "units": "years",
                "reference_range": {"min": 1.0, "max": 120.0},
                "description": "Patient age in years used by diabetes model.",
            },
            {
                "key": "hba1c",
                "marker_name": "HbA1c",
                "units": "%",
                "reference_range": {"min": 4.0, "max": 5.6},
                "description": "Additional clinical marker retained in MedX diabetes panel.",
            },
        ],
    },
}

LAB_SPECIMEN_TYPES: List[str] = ["Serum", "Whole Blood", "Urine", "Plasma", "CSF", "Swab", "Stool", "Other"]

LAB_SMART_STANDARD_MARKERS: Dict[str, List[Dict[str, Any]]] = {
    "CBC": [
        {"key": "cbc_wbc", "marker_name": "WBC", "units": "x10^9/L", "reference_range": {"min": 4.0, "max": 11.0}},
        {"key": "cbc_rbc", "marker_name": "RBC", "units": "x10^12/L", "reference_range": {"min": 4.2, "max": 6.1}},
        {"key": "cbc_haemoglobin", "marker_name": "Haemoglobin", "units": "g/dL", "reference_range": {"min": 12.0, "max": 17.0}},
        {"key": "cbc_hct", "marker_name": "HCT", "units": "%", "reference_range": {"min": 36.0, "max": 52.0}},
        {"key": "cbc_platelets", "marker_name": "Platelets", "units": "x10^9/L", "reference_range": {"min": 150.0, "max": 450.0}},
    ],
    "LFT": [
        {"key": "bilirubin", "marker_name": "Bilirubin", "units": "mg/dL", "reference_range": {"min": 0.3, "max": 1.2}},
        {"key": "alt", "marker_name": "ALT", "units": "U/L", "reference_range": {"min": 7.0, "max": 56.0}},
        {"key": "ast", "marker_name": "AST", "units": "U/L", "reference_range": {"min": 10.0, "max": 40.0}},
        {"key": "alkaline_phosphatase", "marker_name": "Alkaline Phosphatase", "units": "U/L", "reference_range": {"min": 44.0, "max": 147.0}},
        {"key": "albumin", "marker_name": "Albumin", "units": "g/dL", "reference_range": {"min": 3.4, "max": 5.4}},
    ],
    "RFT": [
        {"key": "creatinine", "marker_name": "Creatinine", "units": "mg/dL", "reference_range": {"min": 0.7, "max": 1.3}},
        {"key": "urea", "marker_name": "Urea", "units": "mg/dL", "reference_range": {"min": 7.0, "max": 20.0}},
        {"key": "sodium", "marker_name": "Sodium", "units": "mmol/L", "reference_range": {"min": 135.0, "max": 145.0}},
        {"key": "potassium", "marker_name": "Potassium", "units": "mmol/L", "reference_range": {"min": 3.5, "max": 5.1}},
    ],
    "LIPID": [
        {"key": "chol_total", "marker_name": "Total Cholesterol", "units": "mg/dL", "reference_range": {"min": 0.0, "max": 200.0}},
        {"key": "chol_hdl", "marker_name": "HDL", "units": "mg/dL", "reference_range": {"min": 40.0, "max": 100.0}},
        {"key": "chol_ldl", "marker_name": "LDL", "units": "mg/dL", "reference_range": {"min": 0.0, "max": 100.0}},
        {"key": "chol_trig", "marker_name": "Triglycerides", "units": "mg/dL", "reference_range": {"min": 0.0, "max": 150.0}},
    ]
}

LAB_SMART_MODEL_SPECS: Dict[str, Dict[str, Any]] = {
    "DIABETES": {"label": "Diabetes", "department": "Biochemistry", "ai_key": "diabetes", "ai_path": "/predict/diabetes", "input_mode": "numeric", "model_name": "diabetes_model"},
    "HEART": {"label": "Heart Disease", "department": "Cardiology", "ai_key": "heart", "ai_path": "/predict/heart", "input_mode": "numeric", "model_name": "heart_model"},
    "LIVER": {"label": "Liver Disease", "department": "Biochemistry", "ai_key": "liver", "ai_path": "/predict/liver", "input_mode": "numeric", "model_name": "liver_model"},
    "BREAST_CANCER": {"label": "Breast Cancer", "department": "Oncology", "ai_key": "breast_cancer", "ai_path": "/predict/breast_cancer", "input_mode": "numeric", "model_name": "breast_cancer_model"},
    "PARKINSONS": {"label": "Parkinson's", "department": "Neurology", "ai_key": "parkinsons", "ai_path": "/predict/parkinsons", "input_mode": "numeric", "model_name": "parkinsons_model"},
    "MATERNAL": {"label": "Maternal Health", "department": "Obstetrics", "ai_key": "maternal", "ai_path": "/predict/maternal", "input_mode": "numeric", "model_name": "maternal_model"},
    "KIDNEY": {"label": "Kidney Disease", "department": "Nephrology", "ai_key": "kidney", "ai_path": "/predict/kidney", "input_mode": "numeric", "model_name": "kidney_model"},
    "GENERAL_DISEASE": {"label": "General Disease (Symptoms)", "department": "General Medicine", "ai_key": "disease", "ai_path": "/predict/disease", "input_mode": "symptoms", "model_name": "disease_predictor"},
}

LAB_SMART_FALLBACK_FEATURES: Dict[str, List[str]] = {
    "diabetes_model": ["pregnancies", "glucose", "bp", "skin", "insulin", "bmi", "dpf", "age"],
    "heart_model": ["age", "anaemia", "creatinine_phosphokinase", "diabetes", "ejection_fraction", "high_blood_pressure", "platelets", "serum_creatinine", "serum_sodium", "sex", "smoking", "time"],
    "liver_model": ["age", "gender", "total_bilirubin", "direct_bilirubin", "alkaline_phosphotase", "alamine_aminotransferase", "aspartate_aminotransferase", "total_proteins", "albumin", "albumin_and_globulin_ratio"],
    "breast_cancer_model": ["radius", "texture", "perimeter", "area", "smoothness"],
    "parkinsons_model": ["mdvp_fo", "mdvp_fhi", "mdvp_flo", "mdvp_jitter_percent", "mdvp_jitter_abs", "mdvp_rap", "mdvp_ppq", "jitter_ddp", "mdvp_shimmer", "mdvp_shimmer_db", "shimmer_apq3", "shimmer_apq5", "mdvp_apq", "shimmer_dda", "nhr", "hnr", "rpde", "dfa", "spread1", "spread2", "d2", "ppe"],
    "maternal_model": ["age", "systolicbp", "diastolicbp", "bs", "bodytemp", "heartrate"],
    "kidney_model": ["age", "bp", "sg", "al", "su", "rbc", "pc", "pcc", "ba", "bgr", "bu", "sc", "sod", "pot", "hemo", "pcv", "wc", "rc", "htn", "dm", "cad", "appet", "pe", "ane"],
    "disease_predictor": ["fever", "cough", "fatigue", "body_pain", "runny_nose", "chills", "headache", "weight_loss", "high_fever", "sweating", "nausea", "joint_pain", "vomiting", "rash", "abdominal_pain", "diarrhea", "yellowish_skin", "chest_pain", "breathlessness", "itching", "skin_rash", "bumps", "acidity", "indigestion", "burning_chest", "swelling"],
}

LAB_SMART_FEATURE_HINTS: Dict[str, Dict[str, Any]] = {
    "glucose": {"label": "Glucose", "units": "mg/dL", "description": "Plasma glucose concentration (2-hour OGTT).", "reference_range": {"min": 70.0, "max": 99.0}},
    "bp": {"label": "Blood Pressure", "units": "mm Hg", "description": "Diastolic blood pressure.", "reference_range": {"min": 60.0, "max": 90.0}},
    "insulin": {"label": "Insulin", "units": "mu U/ml", "description": "2-hour serum insulin.", "reference_range": {"min": 2.0, "max": 25.0}},
    "bmi": {"label": "BMI", "units": "kg/m2", "reference_range": {"min": 18.5, "max": 24.9}},
    "pregnancies": {"label": "Pregnancies", "units": "count"},
    "skin": {"label": "Skin Thickness", "units": "mm"},
    "dpf": {"label": "Diabetes Pedigree Function", "units": "score"},
    "bloodpressure": {"label": "Blood Pressure", "units": "mm Hg", "description": "Diastolic blood pressure."},
    "skinthickness": {"label": "Skin Thickness", "units": "mm"},
    "diabetespedigreefunction": {"label": "Diabetes Pedigree Function", "units": "score"},
    "trestbps": {"label": "Resting BP", "units": "mm Hg"},
    "chol": {"label": "Cholesterol", "units": "mg/dL"},
    "thalach": {"label": "Max Heart Rate", "units": "bpm"},
    "anaemia": {"label": "Anaemia (0/1)", "units": "binary"},
    "creatinine_phosphokinase": {"label": "Creatinine Phosphokinase", "units": "mcg/L"},
    "ejection_fraction": {"label": "Ejection Fraction", "units": "%"},
    "high_blood_pressure": {"label": "High Blood Pressure (0/1)", "units": "binary"},
    "serum_creatinine": {"label": "Serum Creatinine", "units": "mg/dL"},
    "serum_sodium": {"label": "Serum Sodium", "units": "mEq/L"},
    "smoking": {"label": "Smoking (0/1)", "units": "binary"},
    "time": {"label": "Follow-up Time", "units": "days"},
    "total_bilirubin": {"label": "Total Bilirubin", "units": "mg/dL"},
    "direct_bilirubin": {"label": "Direct Bilirubin", "units": "mg/dL"},
    "alkaline_phosphotase": {"label": "Alkaline Phosphatase", "units": "U/L"},
    "alamine_aminotransferase": {"label": "ALT", "units": "U/L"},
    "aspartate_aminotransferase": {"label": "AST", "units": "U/L"},
    "total_proteins": {"label": "Total Proteins", "units": "g/dL"},
    "albumin": {"label": "Albumin", "units": "g/dL"},
    "albumin_and_globulin_ratio": {"label": "Albumin/Globulin Ratio", "units": "ratio"},
    "systolicbp": {"label": "Systolic BP", "units": "mm Hg"},
    "diastolicbp": {"label": "Diastolic BP", "units": "mm Hg"},
    "bs": {"label": "Blood Sugar", "units": "mmol/L"},
    "bodytemp": {"label": "Body Temperature", "units": "F"},
    "heartrate": {"label": "Heart Rate", "units": "bpm"},
    "bgr": {"label": "Blood Glucose Random", "units": "mg/dL"},
    "bu": {"label": "Blood Urea", "units": "mg/dL"},
    "sc": {"label": "Serum Creatinine", "units": "mg/dL"},
    "sod": {"label": "Sodium", "units": "mmol/L"},
    "pot": {"label": "Potassium", "units": "mmol/L"},
}

LAB_MODELS_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "ai_engine", "hospital_ai_assets", "models"))
LAB_MODEL_COLS_FILES: Dict[str, str] = {
    "diabetes_model": "diabetes_model_cols.pkl",
    "heart_model": "heart_model_cols.pkl",
    "liver_model": "liver_model_cols.pkl",
    "maternal_model": "maternal_model_cols.pkl",
    "kidney_model": "kidney_model_cols.pkl",
    "disease_predictor": "disease_predictor_cols.pkl",
}
LAB_MODEL_FILES: Dict[str, str] = {
    "diabetes_model": "diabetes_model.pkl",
    "heart_model": "heart_model.pkl",
    "liver_model": "liver_model.pkl",
    "breast_cancer_model": "breast_cancer_model.pkl",
    "parkinsons_model": "parkinsons_model.pkl",
    "maternal_model": "maternal_model.pkl",
    "kidney_model": "kidney_model.pkl",
    "disease_predictor": "disease_predictor.pkl",
}
LAB_MODEL_FEATURES_CACHE: Dict[str, List[str]] = {}

LAB_AI_INPUT_ALIASES: Dict[str, Dict[str, str]] = {
    "diabetes": {
        "bloodpressure": "bp",
        "skinthickness": "skin",
        "diabetespedigreefunction": "dpf",
    }
}

LAB_MASTER_TESTS: List[Dict[str, Any]] = [
    {"code": "DIABETES_MODEL", "name": "Diabetes Risk AI Report", "department": "AI Diagnostics", "aliases": ["Diabetes"]},
    {"code": "HEART_MODEL", "name": "Heart Disease AI Report", "department": "AI Diagnostics", "aliases": ["Heart"]},
    {"code": "LIVER_MODEL", "name": "Liver Disease AI Report", "department": "AI Diagnostics", "aliases": ["Liver"]},
    {"code": "KIDNEY_MODEL", "name": "Kidney Disease AI Report", "department": "AI Diagnostics", "aliases": ["Kidney"]},
    {"code": "BREAST_CANCER_MODEL", "name": "Breast Cancer AI Report", "department": "AI Diagnostics", "aliases": ["Breast Cancer"]},
    {"code": "PARKINSONS_MODEL", "name": "Parkinsons AI Report", "department": "AI Diagnostics", "aliases": ["Parkinsons"]},
    {"code": "A1AT", "name": "Alpha-1-Antitrypsin", "department": "Biochemistry", "aliases": ["A1AT"]},
    {"code": "ABG", "name": "Acid base status", "department": "Biochemistry", "aliases": ["Gases", "ABG"]},
    {"code": "APTT", "name": "Activated partial thromboplastin time", "department": "Haematology", "aliases": ["APTT"]},
    {"code": "AFP", "name": "Alpha-feto-protein", "department": "Biochemistry", "aliases": ["AFP"]},
    {"code": "ALB", "name": "Albumin", "department": "Biochemistry", "aliases": []},
    {"code": "ACR", "name": "Albumin Creatinine Ratio (ACR)", "department": "Biochemistry", "aliases": ["ACR"]},
    {"code": "ALDOSTERONE", "name": "Aldosterone", "department": "Biochemistry", "aliases": []},
    {"code": "ALP", "name": "Alkaline Phosphatase", "department": "Biochemistry", "aliases": ["ALP"]},
    {"code": "ALT", "name": "Alanine Aminotransferase", "department": "Biochemistry", "aliases": ["ALT"]},
    {"code": "AST", "name": "Aspartate Aminotransferase", "department": "Biochemistry", "aliases": ["AST"]},
    {"code": "ANA", "name": "Antinuclear antibody (ANA)", "department": "Immunology", "aliases": ["ANA"]},
    {"code": "ANCA", "name": "Anti-neutrophil cytoplasmic antibody (ANCA)", "department": "Immunology", "aliases": ["ANCA"]},
    {"code": "AMH", "name": "Anti-Mullerian Hormone", "department": "Biochemistry", "aliases": ["AMH"]},
    {"code": "ASO", "name": "Streptococcal serology - Antistreptolysin O", "department": "Virology", "aliases": ["ASO"]},
    {"code": "BLOOD_CULTURE", "name": "Blood Cultures", "department": "Bacteriology", "aliases": []},
    {"code": "BILIRUBIN_TOTAL", "name": "Bilirubin (total)", "department": "Biochemistry", "aliases": []},
    {"code": "BILIRUBIN_DIRECT", "name": "Bilirubin (conjugated/direct)", "department": "Biochemistry", "aliases": []},
    {"code": "BNP", "name": "BNP (N-terminal pro BNP)", "department": "Biochemistry", "aliases": ["NT-proBNP"]},
    {"code": "C3", "name": "Complement C3", "department": "Immunology", "aliases": []},
    {"code": "C4", "name": "Complement C4", "department": "Immunology", "aliases": []},
    {"code": "CA125", "name": "CA125", "department": "Biochemistry", "aliases": []},
    {"code": "CALCIUM_TOTAL", "name": "Calcium, plasma, total", "department": "Biochemistry", "aliases": ["Calcium"]},
    {"code": "CALCIUM_IONIZED", "name": "Calcium ionized", "department": "Biochemistry", "aliases": []},
    {"code": "CARBAMAZEPINE", "name": "Carbamazepine", "department": "Biochemistry", "aliases": []},
    {"code": "CBC", "name": "Full blood count and automated differential", "department": "Haematology", "aliases": ["FBC", "CBC"]},
    {"code": "CEA", "name": "CEA", "department": "Biochemistry", "aliases": []},
    {"code": "CHLORIDE", "name": "Chloride", "department": "Biochemistry", "aliases": []},
    {"code": "CHOLESTEROL", "name": "Cholesterol", "department": "Biochemistry", "aliases": []},
    {"code": "CK", "name": "Creatine Kinase", "department": "Biochemistry", "aliases": ["CK"]},
    {"code": "CMV_IGG", "name": "CMV (cytomegalovirus) IgG", "department": "Virology", "aliases": []},
    {"code": "CMV_IGM", "name": "CMV (cytomegalovirus) IgM", "department": "Virology", "aliases": []},
    {"code": "CMV_VL", "name": "CMV (cytomegalovirus) viral load", "department": "Molecular Microbiology", "aliases": []},
    {"code": "COVID_PCR", "name": "Coronavirus COVID-19 Testing for SARS-CoV-2", "department": "Molecular Microbiology", "aliases": ["COVID PCR"]},
    {"code": "CORTISOL", "name": "Cortisol", "department": "Biochemistry", "aliases": []},
    {"code": "CRP", "name": "C-reactive protein (CRP)", "department": "Biochemistry", "aliases": ["CRP"]},
    {"code": "CREATININE", "name": "Creatinine (blood and urine)", "department": "Biochemistry", "aliases": []},
    {"code": "CSF_GLUCOSE", "name": "CSF - Glucose", "department": "Biochemistry", "aliases": []},
    {"code": "CSF_PROTEIN", "name": "CSF - Protein", "department": "Biochemistry", "aliases": []},
    {"code": "D_DIMER", "name": "FDP D-Dimers", "department": "Haematology", "aliases": ["D-Dimer"]},
    {"code": "DIGOXIN", "name": "Digoxin", "department": "Biochemistry", "aliases": []},
    {"code": "EGFR", "name": "eGFR (estimated GFR)", "department": "Biochemistry", "aliases": ["eGFR"]},
    {"code": "ESR", "name": "Erythrocyte Sedimentation Rate (ESR)", "department": "Haematology", "aliases": ["ESR"]},
    {"code": "FERRITIN", "name": "Ferritin", "department": "Biochemistry", "aliases": []},
    {"code": "FIBRINOGEN", "name": "Fibrinogen", "department": "Haematology", "aliases": []},
    {"code": "FOLATE", "name": "Folate (serum and red cell)", "department": "Biochemistry", "aliases": []},
    {"code": "FSH", "name": "Follicle stimulating hormone", "department": "Biochemistry", "aliases": ["FSH"]},
    {"code": "FREE_T3", "name": "Free Tri-iodothyronine", "department": "Biochemistry", "aliases": ["Free T3"]},
    {"code": "FREE_T4", "name": "Free thyroxine", "department": "Biochemistry", "aliases": ["Free T4"]},
    {"code": "GGT", "name": "Gamma-glutamyl transferase", "department": "Biochemistry", "aliases": ["GGT"]},
    {"code": "GLUCOSE", "name": "Glucose", "department": "Biochemistry", "aliases": []},
    {"code": "HBA1C", "name": "Glycated Haemoglobin", "department": "Biochemistry", "aliases": ["HbA1c"]},
    {"code": "HCG", "name": "HCG blood (pregnancy and tumour marker)", "department": "Biochemistry", "aliases": ["Pregnancy test (blood)"]},
    {"code": "HEPATITIS_B_HBSAG", "name": "Hepatitis B (HBV) surface antigen (HBsAg)", "department": "Virology", "aliases": ["HBsAg"]},
    {"code": "HEPATITIS_C_AB", "name": "Hepatitis C antibody (HCV) screen and confirmation", "department": "Virology", "aliases": ["Anti-HCV"]},
    {"code": "HIV_SCREEN", "name": "HIV screen (4th generation: HIV1/2 and p24 antigen)", "department": "Virology", "aliases": []},
    {"code": "INSULIN", "name": "Insulin", "department": "Biochemistry", "aliases": []},
    {"code": "IRON", "name": "Iron", "department": "Biochemistry", "aliases": []},
    {"code": "LACTATE", "name": "Lactate", "department": "Biochemistry", "aliases": []},
    {"code": "LDH", "name": "Lactate Dehydrogenase (LDH)", "department": "Biochemistry", "aliases": ["LDH"]},
    {"code": "LFT", "name": "Liver Function Tests", "department": "Biochemistry", "aliases": ["LFT"]},
    {"code": "LIPID_PROFILE", "name": "Lipid profile incl. total cholesterol, LDL, HDL, triglyceride", "department": "Biochemistry", "aliases": []},
    {"code": "LUTEINISING_HORMONE", "name": "Luteinising Hormone", "department": "Biochemistry", "aliases": ["LH"]},
    {"code": "MAGNESIUM", "name": "Magnesium (Blood and Urine)", "department": "Biochemistry", "aliases": []},
    {"code": "NOROVIRUS_PCR", "name": "Norovirus PCR", "department": "Molecular Microbiology", "aliases": []},
    {"code": "OSMOLALITY", "name": "Osmolality (Blood and Urine)", "department": "Biochemistry", "aliases": []},
    {"code": "PCR", "name": "Protein creatinine ratio (urine)", "department": "Biochemistry", "aliases": []},
    {"code": "PHOSPHATE", "name": "Phosphate (blood and urine)", "department": "Biochemistry", "aliases": []},
    {"code": "PLATELET_COUNT", "name": "Platelets Aggregation Studies", "department": "Haematology", "aliases": []},
    {"code": "POTASSIUM", "name": "Potassium", "department": "Biochemistry", "aliases": []},
    {"code": "PROCALCITONIN", "name": "Procalcitonin", "department": "Biochemistry", "aliases": []},
    {"code": "PROTHROMBIN_TIME", "name": "Prothrombin time", "department": "Haematology", "aliases": ["PT"]},
    {"code": "PTH", "name": "Parathyroid hormone", "department": "Biochemistry", "aliases": ["PTH"]},
    {"code": "RESPIRATORY_PCR", "name": "Respiratory virus PCR", "department": "Molecular Microbiology", "aliases": ["Respiratory screen"]},
    {"code": "RUBELLA_IGG", "name": "Rubella IgG", "department": "Virology", "aliases": []},
    {"code": "RUBELLA_IGM", "name": "Rubella IgM", "department": "Virology", "aliases": []},
    {"code": "SODIUM", "name": "Sodium (blood and urine)", "department": "Biochemistry", "aliases": []},
    {"code": "THYROID_PEROXIDASE_AB", "name": "Thyroid peroxidase (TPO) antibodies", "department": "Biochemistry", "aliases": ["TPO"]},
    {"code": "TOTAL_PROTEIN", "name": "Total Protein", "department": "Biochemistry", "aliases": []},
    {"code": "TROPONIN_T", "name": "Troponin T", "department": "Biochemistry", "aliases": []},
    {"code": "TSH", "name": "Thyroid Stimulating Hormone", "department": "Biochemistry", "aliases": ["TSH"]},
    {"code": "UREA", "name": "Urea (blood and urine)", "department": "Biochemistry", "aliases": []},
    {"code": "URINE_CULTURE", "name": "Urine Culture", "department": "Bacteriology", "aliases": ["Urines"]},
    {"code": "URATE", "name": "Urate (blood and urine)", "department": "Biochemistry", "aliases": []},
    {"code": "VITAMIN_B12", "name": "Vitamin B12", "department": "Biochemistry", "aliases": []},
    {"code": "VITAMIN_D", "name": "Vitamin D", "department": "Biochemistry", "aliases": []},
    {"code": "WOUND_CULTURE", "name": "Wounds - Skin, Superficial, Non-surgical", "department": "Bacteriology", "aliases": []},
    {"code": "XANTHOCHROMIA", "name": "Xanthochromia Screen (CSF)", "department": "Biochemistry", "aliases": []},
    {"code": "ZINC", "name": "Zinc", "department": "Biochemistry", "aliases": []},
]

LAB_MASTER_TESTS_FILE = os.path.join(os.path.dirname(__file__), "lab_master_tests_custom.json")

LAB_TEST_FORM_OVERRIDES: Dict[str, List[Dict[str, Any]]] = {
    "CBC": [
        {"key": "hemoglobin", "label": "Hemoglobin", "type": "number", "required": True, "unit": "g/dL", "min": 0, "max": 25},
        {"key": "wbc", "label": "WBC", "type": "number", "required": True, "unit": "x10^9/L", "min": 0, "max": 300},
        {"key": "rbc", "label": "RBC", "type": "number", "required": True, "unit": "x10^12/L", "min": 0, "max": 15},
        {"key": "platelets", "label": "Platelets", "type": "number", "required": True, "unit": "x10^9/L", "min": 0, "max": 1500},
        {"key": "hematocrit", "label": "Hematocrit", "type": "number", "required": False, "unit": "%", "min": 0, "max": 100},
    ],
    "LIPID_PROFILE": [
        {"key": "chol_total", "label": "Total Cholesterol", "type": "number", "required": True, "unit": "mg/dL", "min": 0, "max": 600},
        {"key": "chol_ldl", "label": "LDL", "type": "number", "required": True, "unit": "mg/dL", "min": 0, "max": 500},
        {"key": "chol_hdl", "label": "HDL", "type": "number", "required": True, "unit": "mg/dL", "min": 0, "max": 200},
        {"key": "triglycerides", "label": "Triglycerides", "type": "number", "required": True, "unit": "mg/dL", "min": 0, "max": 1500},
    ],
    "LFT": [
        {"key": "alt", "label": "ALT", "type": "number", "required": True, "unit": "U/L", "min": 0, "max": 5000},
        {"key": "ast", "label": "AST", "type": "number", "required": True, "unit": "U/L", "min": 0, "max": 5000},
        {"key": "alp", "label": "ALP", "type": "number", "required": True, "unit": "U/L", "min": 0, "max": 3000},
        {"key": "total_bilirubin", "label": "Total Bilirubin", "type": "number", "required": True, "unit": "mg/dL", "min": 0, "max": 60},
        {"key": "albumin", "label": "Albumin", "type": "number", "required": False, "unit": "g/dL", "min": 0, "max": 10},
    ],
    "THYROID_PANEL": [
        {"key": "tsh", "label": "TSH", "type": "number", "required": True, "unit": "mIU/L", "min": 0, "max": 200},
        {"key": "free_t4", "label": "Free T4", "type": "number", "required": False, "unit": "ng/dL", "min": 0, "max": 10},
        {"key": "free_t3", "label": "Free T3", "type": "number", "required": False, "unit": "pg/mL", "min": 0, "max": 30},
    ],
    "HBA1C": [
        {"key": "hba1c", "label": "HbA1c", "type": "number", "required": True, "unit": "%", "min": 2, "max": 20},
    ],
    "GLUCOSE": [
        {"key": "glucose", "label": "Glucose", "type": "number", "required": True, "unit": "mg/dL", "min": 0, "max": 1000},
    ],
}

LAB_AI_TEST_CODE_MAP: Dict[str, str] = {
    "DIABETES_MODEL": "diabetes",
    "HEART_MODEL": "heart",
    "LIVER_MODEL": "liver",
    "KIDNEY_MODEL": "kidney",
    "BREAST_CANCER_MODEL": "breast_cancer",
    "PARKINSONS_MODEL": "parkinsons",
}


def _slugify_lab_test_name(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", (name or "").strip().lower())
    return re.sub(r"_+", "_", s).strip("_") or "lab_test"


def _normalize_lab_test_code(name: str) -> str:
    slug = _slugify_lab_test_name(name).upper()
    if len(slug) > 40:
        slug = slug[:40]
    return slug or f"T_{uuid.uuid4().hex[:8].upper()}"


def _load_custom_lab_tests() -> List[Dict[str, Any]]:
    if not os.path.exists(LAB_MASTER_TESTS_FILE):
        return []
    try:
        with open(LAB_MASTER_TESTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return [d for d in data if isinstance(d, dict)]
    except Exception:
        return []
    return []


def _save_custom_lab_tests(items: List[Dict[str, Any]]) -> None:
    with open(LAB_MASTER_TESTS_FILE, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


def _all_master_tests() -> List[Dict[str, Any]]:
    base = list(LAB_MASTER_TESTS)
    custom = _load_custom_lab_tests()
    by_code: Dict[str, Dict[str, Any]] = {}
    for t in base + custom:
        code = (t.get("code") or "").upper().strip()
        if not code:
            continue
        by_code[code] = {
            "code": code,
            "name": t.get("name") or code,
            "department": t.get("department") or "Laboratory",
            "aliases": t.get("aliases") or [],
        }
    return list(by_code.values())


def _is_molecular_or_qualitative(name: str, department: str) -> bool:
    text = f"{name} {department}".lower()
    keywords = ["pcr", "culture", "screen", "antibody", "antibodies", "igg", "igm", "fna", "cytology", "panel", "ag", "toxin"]
    return any(k in text for k in keywords)


def _default_lab_form_schema(test_code: str, test_name: str, department: str) -> List[Dict[str, Any]]:
    common = [
        {"key": "specimen_type", "label": "Specimen Type", "type": "select", "required": True, "options": ["Blood", "Urine", "Stool", "CSF", "Swab", "Other"]},
        {"key": "collection_datetime", "label": "Collection DateTime", "type": "datetime", "required": True},
        {"key": "clinical_notes", "label": "Clinical Notes", "type": "textarea", "required": False, "max_length": 500},
    ]
    if test_code in LAB_TEST_FORM_OVERRIDES:
        return common + LAB_TEST_FORM_OVERRIDES[test_code]

    if _is_molecular_or_qualitative(test_name, department):
        return common + [
            {"key": "result_status", "label": "Result", "type": "select", "required": True, "options": ["Positive", "Negative", "Reactive", "Non-reactive", "Inconclusive"]},
            {"key": "organism_or_marker", "label": "Organism / Marker", "type": "text", "required": False, "max_length": 120},
            {"key": "method", "label": "Method", "type": "text", "required": False, "max_length": 120},
        ]

    return common + [
        {"key": "result_value", "label": "Measured Value", "type": "number", "required": True, "min": 0, "max": 1000000},
        {"key": "unit", "label": "Unit", "type": "text", "required": True, "max_length": 20},
        {"key": "reference_range", "label": "Reference Range", "type": "text", "required": False, "max_length": 80},
    ]


def _to_float(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    try:
        return float(value)
    except Exception:
        return 0.0


def _build_ai_payload(test_key: str, inputs: Dict[str, Any]) -> Dict[str, Any]:
    test = test_key.lower().strip()
    if test in {"diabetes", "heart", "breast_cancer"}:
        return {k: _to_float(v) for k, v in inputs.items()}

    if test == "liver":
        vals = [
            _to_float(inputs.get("age")),
            _to_float(inputs.get("gender")),
            _to_float(inputs.get("total_bilirubin")),
            _to_float(inputs.get("direct_bilirubin")),
            _to_float(inputs.get("alkaline_phosphotase")),
            _to_float(inputs.get("alamine_aminotransferase")),
            _to_float(inputs.get("aspartate_aminotransferase")),
            _to_float(inputs.get("total_proteins")),
            _to_float(inputs.get("albumin")),
            _to_float(inputs.get("albumin_and_globulin_ratio")),
        ]
        return {"values": vals}

    if test == "kidney":
        order = ["age","bp","sg","al","su","rbc","pc","pcc","ba","bgr","bu","sc","sod","pot","hemo","pcv","wc","rc","htn","dm","cad","appet","pe","ane"]
        return {"values": [_to_float(inputs.get(k)) for k in order]}

    if test == "parkinsons":
        order = [
            "mdvp_fo","mdvp_fhi","mdvp_flo","mdvp_jitter_percent","mdvp_jitter_abs","mdvp_rap","mdvp_ppq","jitter_ddp",
            "mdvp_shimmer","mdvp_shimmer_db","shimmer_apq3","shimmer_apq5","mdvp_apq","shimmer_dda","nhr","hnr",
            "rpde","dfa","spread1","spread2","d2","ppe",
        ]
        return {"values": [_to_float(inputs.get(k)) for k in order]}

    if test == "maternal":
        order = ["age", "systolicbp", "diastolicbp", "bs", "bodytemp", "heartrate"]
        return {"values": [_to_float(inputs.get(k)) for k in order]}

    if test == "disease":
        symptoms = inputs.get("symptoms") or []
        if isinstance(symptoms, str):
            symptoms = [s.strip() for s in symptoms.split(",") if s.strip()]
        return {"symptoms": [str(s).strip().lower().replace(" ", "_") for s in symptoms if str(s).strip()]}

    raise HTTPException(status_code=400, detail="Unsupported test key")


def _call_ai_service(ai_path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    import urllib.request

    ai_url = f"http://127.0.0.1:8001{ai_path}"
    req = urllib.request.Request(
        ai_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        raw = resp.read().decode("utf-8", errors="ignore")
    return json.loads(raw)


def _run_background_ai_models(tests: Dict[str, Any]) -> Dict[str, Any]:
    outputs: Dict[str, Any] = {}

    candidates: Dict[str, Dict[str, Any]] = {
        "diabetes": {
            "pregnancies": tests.get("pregnancies"),
            "glucose": tests.get("glucose") or tests.get("sugar_random") or tests.get("sugar_fasting"),
            "bp": tests.get("bp") or tests.get("trestbps"),
            "skin": tests.get("skin"),
            "insulin": tests.get("insulin"),
            "bmi": tests.get("bmi"),
            "dpf": tests.get("dpf"),
            "age": tests.get("age"),
        },
        "heart": {
            "age": tests.get("age"),
            "sex": tests.get("sex"),
            "cp": tests.get("cp"),
            "trestbps": tests.get("trestbps") or tests.get("bp"),
            "chol": tests.get("chol") or tests.get("chol_total"),
            "fbs": tests.get("fbs"),
            "restecg": tests.get("restecg"),
            "thalach": tests.get("thalach"),
            "exang": tests.get("exang"),
            "oldpeak": tests.get("oldpeak"),
            "slope": tests.get("slope"),
            "ca": tests.get("ca"),
            "thal": tests.get("thal"),
        },
        "liver": {
            "age": tests.get("age"),
            "gender": tests.get("gender"),
            "total_bilirubin": tests.get("total_bilirubin"),
            "direct_bilirubin": tests.get("direct_bilirubin"),
            "alkaline_phosphotase": tests.get("alkaline_phosphotase"),
            "alamine_aminotransferase": tests.get("alamine_aminotransferase"),
            "aspartate_aminotransferase": tests.get("aspartate_aminotransferase"),
            "total_proteins": tests.get("total_proteins"),
            "albumin": tests.get("albumin"),
            "albumin_and_globulin_ratio": tests.get("albumin_and_globulin_ratio"),
        },
        "kidney": {
            "age": tests.get("age"),
            "bp": tests.get("bp"),
            "sg": tests.get("sg"),
            "al": tests.get("al"),
            "su": tests.get("su"),
            "rbc": tests.get("rbc"),
            "pc": tests.get("pc"),
            "pcc": tests.get("pcc"),
            "ba": tests.get("ba"),
            "bgr": tests.get("bgr"),
            "bu": tests.get("bu"),
            "sc": tests.get("sc"),
            "sod": tests.get("sod"),
            "pot": tests.get("pot"),
            "hemo": tests.get("hemo"),
            "pcv": tests.get("pcv"),
            "wc": tests.get("wc"),
            "rc": tests.get("rc"),
            "htn": tests.get("htn"),
            "dm": tests.get("dm"),
            "cad": tests.get("cad"),
            "appet": tests.get("appet"),
            "pe": tests.get("pe"),
            "ane": tests.get("ane"),
        },
        "breast_cancer": {
            "radius": tests.get("radius"),
            "texture": tests.get("texture"),
            "perimeter": tests.get("perimeter"),
            "area": tests.get("area"),
            "smoothness": tests.get("smoothness"),
        },
        "parkinsons": {
            "mdvp_fo": tests.get("mdvp_fo"),
            "mdvp_fhi": tests.get("mdvp_fhi"),
            "mdvp_flo": tests.get("mdvp_flo"),
            "mdvp_jitter_percent": tests.get("mdvp_jitter_percent"),
            "mdvp_jitter_abs": tests.get("mdvp_jitter_abs"),
            "mdvp_rap": tests.get("mdvp_rap"),
            "mdvp_ppq": tests.get("mdvp_ppq"),
            "jitter_ddp": tests.get("jitter_ddp"),
            "mdvp_shimmer": tests.get("mdvp_shimmer"),
            "mdvp_shimmer_db": tests.get("mdvp_shimmer_db"),
            "shimmer_apq3": tests.get("shimmer_apq3"),
            "shimmer_apq5": tests.get("shimmer_apq5"),
            "mdvp_apq": tests.get("mdvp_apq"),
            "shimmer_dda": tests.get("shimmer_dda"),
            "nhr": tests.get("nhr"),
            "hnr": tests.get("hnr"),
            "rpde": tests.get("rpde"),
            "dfa": tests.get("dfa"),
            "spread1": tests.get("spread1"),
            "spread2": tests.get("spread2"),
            "d2": tests.get("d2"),
            "ppe": tests.get("ppe"),
        },
    }

    for test_key, raw_inputs in candidates.items():
        filled = {k: v for k, v in raw_inputs.items() if v not in [None, ""]}
        if test_key == "parkinsons":
            min_required = 22
        elif test_key == "kidney":
            min_required = 18
        elif test_key in {"heart", "liver"}:
            min_required = 5
        elif test_key in {"breast_cancer"}:
            min_required = 5
        else:
            min_required = 4
        if len(filled) < min_required:
            continue

        spec = LAB_TEST_CATALOG.get(test_key)
        if not spec:
            continue

        try:
            ai_payload = _build_ai_payload(test_key, raw_inputs)
            ai_response = _call_ai_service(spec["ai_path"], ai_payload)
            outputs[test_key] = {
                "label": spec["label"],
                "result": ai_response.get("result") or ai_response.get("prediction") or "Unknown",
                "confidence": ai_response.get("confidence") or "N/A",
                "raw": ai_response,
            }
        except Exception as exc:
            outputs[test_key] = {
                "label": spec["label"],
                "error": str(exc),
            }

    return outputs


def _ensure_lab_records_table(db: Session) -> None:
    db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS lab_records (
                record_id INTEGER PRIMARY KEY,
                hospital_id INTEGER NOT NULL,
                patient_id INTEGER NOT NULL,
                collected_by_staff_id INTEGER,
                test_type TEXT NOT NULL,
                department TEXT NOT NULL,
                specimen_type TEXT NOT NULL,
                collection_timestamp TEXT NOT NULL,
                clinical_notes TEXT,
                patient_full_name_snapshot TEXT,
                patient_mrn_snapshot TEXT,
                patient_gender_snapshot TEXT,
                patient_age_snapshot INTEGER,
                markers_json TEXT NOT NULL,
                ai_outputs_json TEXT,
                status TEXT NOT NULL DEFAULT 'COMPLETED',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    )
    db.execute(text("CREATE INDEX IF NOT EXISTS idx_lab_records_hospital_status_time ON lab_records(hospital_id, status, created_at)"))
    db.commit()
    models.load_tables()


def _safe_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except Exception:
        return None


def _calc_age_from_dob(dob_value: Any) -> Optional[int]:
    if not dob_value:
        return None
    try:
        d = datetime.fromisoformat(str(dob_value)[:10]).date()
    except Exception:
        return None
    today = date.today()
    age = today.year - d.year - ((today.month, today.day) < (d.month, d.day))
    return age if age >= 0 else None


def _is_marker_critical(result_value: Any, reference_range: Dict[str, Any]) -> bool:
    num = _safe_float(result_value)
    if num is None:
        return False
    rr_min = _safe_float(reference_range.get("min"))
    rr_max = _safe_float(reference_range.get("max"))
    if rr_min is not None and num < rr_min:
        return True
    if rr_max is not None and num > rr_max:
        return True
    return False


def _normalize_feature_key(value: str) -> str:
    key = re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower())
    key = re.sub(r"_+", "_", key)
    return key.strip("_")


def _feature_label_from_key(key: str) -> str:
    return " ".join([part.capitalize() for part in _normalize_feature_key(key).split("_") if part])


def _load_feature_list_from_pickle(path: str) -> List[str]:
    if not os.path.exists(path):
        return []
    obj = None
    try:
        with open(path, "rb") as f:
            obj = pickle.load(f)
    except Exception:
        try:
            import joblib  # type: ignore

            obj = joblib.load(path)
        except Exception:
            obj = None
    if obj is None:
        return []
    if hasattr(obj, "tolist"):
        obj = obj.tolist()
    if isinstance(obj, (list, tuple)):
        return [_normalize_feature_key(v) for v in obj if str(v).strip()]
    return [_normalize_feature_key(obj)]


def _load_model_feature_names(model_name: str) -> List[str]:
    model_file = LAB_MODEL_FILES.get(model_name)
    if not model_file:
        return []
    path = os.path.join(LAB_MODELS_DIR, model_file)
    if not os.path.exists(path):
        return []

    model_obj = None
    try:
        with open(path, "rb") as f:
            model_obj = pickle.load(f)
    except Exception:
        try:
            import joblib  # type: ignore

            model_obj = joblib.load(path)
        except Exception:
            model_obj = None
    if model_obj is None or not hasattr(model_obj, "feature_names_in_"):
        return []

    raw = getattr(model_obj, "feature_names_in_")
    if hasattr(raw, "tolist"):
        raw = raw.tolist()
    if not isinstance(raw, (list, tuple)):
        raw = [raw]
    return [_normalize_feature_key(v) for v in raw if str(v).strip()]


def _looks_valid_feature_list(items: List[str]) -> bool:
    if not items:
        return False
    alpha_like = 0
    for item in items:
        if re.search(r"[a-z]", str(item)):
            alpha_like += 1
    return alpha_like >= max(1, int(len(items) * 0.7))


def _resolve_model_features(model_name: str) -> List[str]:
    if model_name in LAB_MODEL_FEATURES_CACHE:
        return LAB_MODEL_FEATURES_CACHE[model_name]

    features: List[str] = []
    model_features = _load_model_feature_names(model_name)
    if _looks_valid_feature_list(model_features):
        features = model_features

    cols_file = LAB_MODEL_COLS_FILES.get(model_name)
    if cols_file:
        cols_features = _load_feature_list_from_pickle(os.path.join(LAB_MODELS_DIR, cols_file))
        if not features and cols_features:
            features = cols_features

    if not features:
        features = [_normalize_feature_key(v) for v in LAB_SMART_FALLBACK_FEATURES.get(model_name, [])]

    LAB_MODEL_FEATURES_CACHE[model_name] = features
    return features


def _smart_model_form_fields(model_code: str) -> List[Dict[str, Any]]:
    spec = LAB_SMART_MODEL_SPECS[model_code]
    model_name = spec["model_name"]
    features = _resolve_model_features(model_name)
    fields: List[Dict[str, Any]] = []
    for key in features:
        hint = LAB_SMART_FEATURE_HINTS.get(key, {})
        fields.append(
            {
                "key": key,
                "label": hint.get("label") or _feature_label_from_key(key),
                "units": hint.get("units") or "",
                "description": hint.get("description") or "",
                "reference_range": hint.get("reference_range") or {},
            }
        )
    return fields


def _build_smart_ai_payload(model_code: str, clinical_inputs: Dict[str, Any], selected_symptoms: List[str]) -> Dict[str, Any]:
    spec = LAB_SMART_MODEL_SPECS[model_code]
    ai_key = spec["ai_key"]
    features = _resolve_model_features(spec["model_name"])

    if spec["input_mode"] == "symptoms":
        clean_symptoms = [_normalize_feature_key(s) for s in selected_symptoms if str(s).strip()]
        return {"symptoms": clean_symptoms}

    normalized_inputs = {_normalize_feature_key(k): v for k, v in (clinical_inputs or {}).items()}
    if ai_key in {"liver", "kidney", "parkinsons", "maternal"}:
        values = []
        for feature in features:
            raw = normalized_inputs.get(feature)
            num = _safe_float(raw)
            values.append(0.0 if num is None else float(num))
        return {"values": values}

    aliases = LAB_AI_INPUT_ALIASES.get(ai_key, {})
    out: Dict[str, float] = {}
    for feature in features:
        ai_feature = aliases.get(feature, feature)
        num = _safe_float(normalized_inputs.get(feature))
        out[ai_feature] = 0.0 if num is None else float(num)
    return out


def _validate_smart_inputs(model_code: str, clinical_inputs: Dict[str, Any], selected_symptoms: List[str]) -> Dict[str, Any]:
    spec = LAB_SMART_MODEL_SPECS[model_code]
    features = _resolve_model_features(spec["model_name"])
    normalized_inputs = {_normalize_feature_key(k): v for k, v in (clinical_inputs or {}).items()}

    if spec["input_mode"] == "symptoms":
        selected = [_normalize_feature_key(s) for s in selected_symptoms if str(s).strip()]
        if len(selected) == 0:
            raise HTTPException(status_code=400, detail="At least one symptom is required for GENERAL_DISEASE")
        if features:
            unknown = sorted([s for s in selected if s not in set(features)])
            if unknown:
                raise HTTPException(status_code=400, detail=f"Unknown symptoms for disease model: {', '.join(unknown[:20])}")
        return {"selected_symptoms": selected}

    missing = [f for f in features if normalized_inputs.get(f) in [None, ""]]
    if missing:
        raise HTTPException(status_code=400, detail=f"Missing required clinical inputs: {', '.join(missing)}")

    for f in features:
        if _safe_float(normalized_inputs.get(f)) is None:
            raise HTTPException(status_code=400, detail=f"Input '{f}' must be numeric")

    return {"clinical_inputs": {f: float(_safe_float(normalized_inputs.get(f))) for f in features}}


def _ensure_lab_test(db: Session, hospital_id: int, test_label: str):
    table = models.TABLES["lab_tests"]
    row = db.execute(
        select(table)
        .where(table.c.hospital_id == hospital_id)
        .where(table.c.test_name == test_label)
    ).first()
    if row:
        return row

    db.execute(insert(table).values(hospital_id=hospital_id, test_name=test_label, cost=0))
    db.commit()
    return db.execute(
        select(table)
        .where(table.c.hospital_id == hospital_id)
        .where(table.c.test_name == test_label)
    ).first()


def _infer_patient_doctor_id(db: Session, hospital_id: int, patient_id: int) -> Optional[int]:
    appointments = models.TABLES.get("appointments")
    if appointments is None:
        return None

    row = db.execute(
        select(appointments.c.doctor_id)
        .where(appointments.c.hospital_id == hospital_id)
        .where(appointments.c.patient_id == patient_id)
        .order_by(appointments.c.created_at.desc())
        .limit(1)
    ).first()
    return int(row.doctor_id) if row and row.doctor_id is not None else None


def _ensure_radiology_table(db: Session) -> None:
    if models.TABLES.get("radiology_requests") is not None:
        return
    db.execute(
        text(
            """
        CREATE TABLE IF NOT EXISTS radiology_requests (
            radiology_request_id INTEGER PRIMARY KEY,
            hospital_id INTEGER NOT NULL,
            patient_id INTEGER NOT NULL,
            ordered_by_staff_id INTEGER,
            test_name TEXT NOT NULL,
            body_part TEXT,
            priority TEXT NOT NULL DEFAULT 'ROUTINE',
            status TEXT NOT NULL DEFAULT 'ORDERED',
            notes TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
        )
    )
    db.commit()
    models.load_tables()


RADIOLOGY_MODALITY_BODY_PARTS: Dict[str, Dict[str, Any]] = {
    "X_RAY": {
        "label": "X-Ray",
        "body_parts": [
            "CHEST",
            "ABDOMEN",
            "PELVIS",
            "SPINE",
            "CERVICAL_SPINE",
            "THORACIC_SPINE",
            "LUMBAR_SPINE",
            "SHOULDER",
            "CLAVICLE",
            "SCAPULA",
            "HUMERUS",
            "ELBOW",
            "FOREARM",
            "WRIST",
            "HAND",
            "FINGERS",
            "ARM",
            "ARMS",
            "HIP",
            "FEMUR",
            "KNEE",
            "TIBIA_FIBULA",
            "ANKLE",
            "FOOT",
            "TOES",
            "SKULL",
            "FACIAL_BONES",
            "SINUSES",
            "MANDIBLE",
            "RIBS",
            "LIMBS",
            "WHOLE_BODY",
        ],
    },
    "ULTRASOUND": {
        "label": "Ultrasound",
        "body_parts": ["ABDOMEN", "KIDNEY", "PELVIS"],
    },
    "MRI": {
        "label": "MRI",
        "body_parts": ["BRAIN", "PELVIS", "SPINE"],
    },
    "CT_SCAN": {
        "label": "CT Scan",
        "body_parts": ["BRAIN", "CHEST", "ABDOMEN", "PELVIS", "SPINE", "SINUSES"],
    },
}

RADIOLOGY_AI_TRIGGERS: Dict[str, Dict[str, str]] = {
    "X_RAY::CHEST": {
        "action": "Run Pneumonia AI",
        "ai_model_key": "pneumonia_model.h5",
        "ai_path": "/predict/pneumonia",
    },
    "MRI::BRAIN": {
        "action": "Run Tumor Detection AI",
        "ai_model_key": "brain_tumor_model.h5",
        "ai_path": "/predict/brain_tumor",
    },
}

UPLOADED_REPORTS_DIR = Path(__file__).resolve().parent / "uploaded_reports"


def _slug_text(value: Any, fallback: str) -> str:
    text_value = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(value or "").strip()).strip("_").lower()
    return text_value or fallback


def _save_scan_data_url_file(
    scan_image_data_url: Optional[str],
    hospital_id: int,
    patient_id: int,
    modality: str,
    body_part: str,
) -> Optional[str]:
    raw = str(scan_image_data_url or "").strip()
    if not raw:
        return None
    if not raw.startswith("data:image/") or ";base64," not in raw:
        return None

    header, encoded = raw.split(";base64,", 1)
    mime = header.replace("data:", "").strip().lower()
    ext_map = {
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
        "image/bmp": ".bmp",
        "image/tiff": ".tiff",
        "image/svg+xml": ".svg",
    }
    ext = ext_map.get(mime, ".png")

    try:
        file_bytes = base64.b64decode(encoded, validate=True)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid uploaded image payload")

    UPLOADED_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
    file_name = (
        f"h{int(hospital_id)}_p{int(patient_id)}_"
        f"{_slug_text(modality, 'modality')}_{_slug_text(body_part, 'body_part')}_{stamp}{ext}"
    )
    target = UPLOADED_REPORTS_DIR / file_name
    target.write_bytes(file_bytes)
    return str(target)


def _ensure_imaging_records_table(db: Session) -> None:
    if models.TABLES.get("imaging_records") is None:
        db.execute(
            text(
                """
            CREATE TABLE IF NOT EXISTS imaging_records (
                imaging_record_id INTEGER PRIMARY KEY,
                hospital_id INTEGER NOT NULL,
                patient_id INTEGER NOT NULL,
                patient_mrn_snapshot TEXT NOT NULL,
                patient_name_snapshot TEXT,
                modality TEXT NOT NULL,
                body_part TEXT NOT NULL,
                study_title TEXT,
                source_page TEXT NOT NULL DEFAULT 'RADIOLOGY_DASHBOARD',
                request_id INTEGER,
                technician_notes TEXT,
                doctor_notes TEXT,
                ai_model_key TEXT,
                ai_result TEXT,
                ai_confidence TEXT,
                ai_findings_json TEXT,
                scan_image_data_url TEXT,
                scan_file_path TEXT,
                status TEXT NOT NULL DEFAULT 'DRAFT',
                doctor_signature_name TEXT,
                doctor_signature_at TEXT,
                recorded_by_staff_id INTEGER,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
            )
        )
        db.commit()
        models.load_tables()

    table = models.TABLES.get("imaging_records")
    if table is None:
        return

    desired_columns = {
        "patient_mrn_snapshot": "TEXT",
        "patient_name_snapshot": "TEXT",
        "source_page": "TEXT",
        "request_id": "INTEGER",
        "technician_notes": "TEXT",
        "doctor_notes": "TEXT",
        "ai_model_key": "TEXT",
        "ai_result": "TEXT",
        "ai_confidence": "TEXT",
        "ai_findings_json": "TEXT",
        "scan_image_data_url": "TEXT",
        "scan_file_path": "TEXT",
        "status": "TEXT",
        "doctor_signature_name": "TEXT",
        "doctor_signature_at": "TEXT",
        "recorded_by_staff_id": "INTEGER",
        "created_at": "TEXT",
        "updated_at": "TEXT",
    }
    changed = False
    for col, col_sql in desired_columns.items():
        if _table_has_column(table, col):
            continue
        db.execute(text(f"ALTER TABLE imaging_records ADD COLUMN {col} {col_sql}"))
        changed = True

    if changed:
        db.commit()
        models.load_tables()
        table = models.TABLES.get("imaging_records")
        if table is None:
            return

    if _table_has_column(table, "source_page"):
        db.execute(
            text(
                "UPDATE imaging_records SET source_page = COALESCE(NULLIF(source_page, ''), 'RADIOLOGY_DASHBOARD')"
            )
        )
    if _table_has_column(table, "status"):
        db.execute(
            text(
                "UPDATE imaging_records SET status = COALESCE(NULLIF(status, ''), 'DRAFT')"
            )
        )
    if _table_has_column(table, "created_at"):
        db.execute(
            text(
                "UPDATE imaging_records SET created_at = COALESCE(NULLIF(created_at, ''), CURRENT_TIMESTAMP)"
            )
        )
    if _table_has_column(table, "updated_at"):
        db.execute(
            text(
                "UPDATE imaging_records SET updated_at = COALESCE(NULLIF(updated_at, ''), CURRENT_TIMESTAMP)"
            )
        )

    db.execute(
        text(
            "CREATE INDEX IF NOT EXISTS idx_imaging_records_hospital_status_time ON imaging_records(hospital_id, status, created_at)"
        )
    )
    db.commit()
    models.load_tables()


REPORT_TYPE_LAB_RECORD = "LAB_RECORD"
REPORT_TYPE_IMAGING_RECORD = "IMAGING_RECORD"


def _ensure_shared_reports_table(db: Session) -> None:
    if models.TABLES.get("shared_reports") is not None:
        return
    db.execute(
        text(
            """
        CREATE TABLE IF NOT EXISTS shared_reports (
            shared_report_id INTEGER PRIMARY KEY,
            hospital_id INTEGER NOT NULL,
            patient_id INTEGER NOT NULL,
            report_type TEXT NOT NULL,
            source_record_id INTEGER NOT NULL,
            shared_to_patient INTEGER NOT NULL DEFAULT 1,
            shared_to_doctor INTEGER NOT NULL DEFAULT 1,
            share_notes TEXT,
            shared_by_staff_id INTEGER,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (hospital_id, report_type, source_record_id)
        )
        """
        )
    )
    db.execute(
        text(
            "CREATE INDEX IF NOT EXISTS idx_shared_reports_hospital_patient_time ON shared_reports(hospital_id, patient_id, created_at)"
        )
    )
    db.execute(
        text(
            "CREATE INDEX IF NOT EXISTS idx_shared_reports_hospital_type ON shared_reports(hospital_id, report_type, source_record_id)"
        )
    )
    db.commit()
    models.load_tables()


def _resolve_portal_patient_id(db: Session, hospital_id: int, user_id: int) -> int:
    portal = models.TABLES["patient_portal_accounts"]
    link = db.execute(
        select(portal.c.patient_id)
        .where(portal.c.hospital_id == hospital_id)
        .where(portal.c.user_id == user_id)
    ).first()
    if not link:
        raise HTTPException(status_code=404, detail="No patient profile linked to this account")
    return int(link.patient_id)


def _extract_patient_id_for_report_source(
    db: Session, hospital_id: int, report_type: str, source_record_id: int
) -> int:
    if report_type == REPORT_TYPE_LAB_RECORD:
        _ensure_lab_records_table(db)
        table = models.TABLES["lab_records"]
        row = db.execute(
            select(table.c.patient_id)
            .where(table.c.hospital_id == hospital_id)
            .where(table.c.record_id == source_record_id)
        ).first()
        if not row:
            raise HTTPException(status_code=404, detail="Lab record not found")
        return int(row.patient_id)

    if report_type == REPORT_TYPE_IMAGING_RECORD:
        _ensure_imaging_records_table(db)
        table = models.TABLES["imaging_records"]
        row = db.execute(
            select(table.c.patient_id)
            .where(table.c.hospital_id == hospital_id)
            .where(table.c.imaging_record_id == source_record_id)
        ).first()
        if not row:
            raise HTTPException(status_code=404, detail="Imaging record not found")
        return int(row.patient_id)

    raise HTTPException(status_code=400, detail="report_type must be LAB_RECORD or IMAGING_RECORD")


def _build_shared_report_payload(db: Session, shared_row: Any) -> Dict[str, Any]:
    base = _serialize_row(shared_row)
    report_type = str(base.get("report_type") or "").upper()
    source_record_id = int(base.get("source_record_id") or 0)
    hospital_id = int(base.get("hospital_id") or 0)

    if report_type == REPORT_TYPE_LAB_RECORD:
        _ensure_lab_records_table(db)
        lab_records = models.TABLES["lab_records"]
        source = db.execute(
            select(lab_records)
            .where(lab_records.c.hospital_id == hospital_id)
            .where(lab_records.c.record_id == source_record_id)
        ).first()
        if source:
            report = _serialize_row(source)
            try:
                report["markers_json"] = json.loads(report.get("markers_json") or "[]")
            except Exception:
                report["markers_json"] = []
            try:
                report["ai_outputs_json"] = json.loads(report.get("ai_outputs_json") or "{}")
            except Exception:
                report["ai_outputs_json"] = {}
            base["title"] = f"Lab Report: {report.get('test_type') or 'LAB'}"
            base["summary"] = f"Specimen: {report.get('specimen_type') or '-'} | Status: {report.get('status') or '-'}"
            base["patient_name"] = report.get("patient_full_name_snapshot")
            base["patient_mrn"] = report.get("patient_mrn_snapshot")
            base["report"] = report
            return base

    if report_type == REPORT_TYPE_IMAGING_RECORD:
        _ensure_imaging_records_table(db)
        imaging_records = models.TABLES["imaging_records"]
        source = db.execute(
            select(imaging_records)
            .where(imaging_records.c.hospital_id == hospital_id)
            .where(imaging_records.c.imaging_record_id == source_record_id)
        ).first()
        if source:
            report = _serialize_row(source)
            try:
                report["ai_findings_json"] = json.loads(report.get("ai_findings_json") or "{}")
            except Exception:
                report["ai_findings_json"] = {}
            base["title"] = f"Imaging Report: {report.get('modality') or '-'} {report.get('body_part') or ''}".strip()
            base["summary"] = f"AI: {report.get('ai_result') or 'N/A'} ({report.get('ai_confidence') or 'N/A'})"
            base["patient_name"] = report.get("patient_name_snapshot")
            base["patient_mrn"] = report.get("patient_mrn_snapshot")
            base["report"] = report
            return base

    base["title"] = f"{report_type or 'REPORT'} #{source_record_id}"
    base["summary"] = "Source report not found."
    base["report"] = None
    return base


def _require_accounts_roles(current_user: Dict[str, Any]) -> None:
    _require_roles(current_user, {"SUPER_ADMIN", "ACCOUNTANT"})


def _require_fleet_roles(current_user: Dict[str, Any]) -> None:
    _require_roles(current_user, {"SUPER_ADMIN", "ACCOUNTANT", "FLEET"})


def _ensure_activity_audit_table(db: Session) -> None:
    if models.TABLES.get("activity_audit") is not None:
        return
    db.execute(
        text(
            """
        CREATE TABLE IF NOT EXISTS activity_audit (
            activity_id INTEGER PRIMARY KEY,
            hospital_id INTEGER NOT NULL,
            actor_user_id INTEGER,
            actor_staff_id INTEGER,
            actor_role TEXT,
            module TEXT NOT NULL,
            action TEXT NOT NULL,
            entity_type TEXT,
            entity_id INTEGER,
            details_json TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
        )
    )
    db.execute(
        text(
            "CREATE INDEX IF NOT EXISTS idx_activity_audit_hospital_module_time ON activity_audit(hospital_id, module, created_at)"
        )
    )
    db.commit()
    models.load_tables()


def _log_activity_audit(
    db: Session,
    hospital_id: int,
    actor_user_id: Optional[int],
    actor_staff_id: Optional[int],
    actor_role: Optional[str],
    module: str,
    action: str,
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    _ensure_activity_audit_table(db)
    audit = models.TABLES["activity_audit"]
    db.execute(
        insert(audit).values(
            hospital_id=hospital_id,
            actor_user_id=actor_user_id,
            actor_staff_id=actor_staff_id,
            actor_role=(actor_role or "").upper() or None,
            module=str(module or "").upper(),
            action=str(action or "").upper(),
            entity_type=entity_type,
            entity_id=entity_id,
            details_json=json.dumps(details or {}),
            created_at=datetime.utcnow().isoformat(),
        )
    )


def _ensure_operational_units_table(db: Session) -> None:
    changed = False
    touched = False
    if models.TABLES.get("operational_units") is None:
        db.execute(
            text(
                """
            CREATE TABLE IF NOT EXISTS operational_units (
                unit_id INTEGER PRIMARY KEY,
                hospital_id INTEGER NOT NULL,
                unit_name TEXT NOT NULL,
                unit_type TEXT NOT NULL,
                total_beds INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'ACTIVE',
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (hospital_id, unit_id),
                UNIQUE (hospital_id, unit_name, unit_type)
            )
            """
            )
        )
        db.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_operational_units_hospital_type_name ON operational_units(hospital_id, unit_type, unit_name)"
            )
        )
        changed = True
        touched = True

    if models.TABLES.get("operational_units") is not None or changed:
        op_cols = {str(r[1]) for r in db.execute(text("PRAGMA table_info(operational_units)")).fetchall()}
        op_desired = {
            "unit_type": "TEXT NOT NULL DEFAULT 'WARD'",
            "total_beds": "INTEGER NOT NULL DEFAULT 0",
            "status": "TEXT NOT NULL DEFAULT 'ACTIVE'",
            "is_active": "INTEGER NOT NULL DEFAULT 1",
            "created_at": "TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP",
            "updated_at": "TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP",
        }
        for col, col_sql in op_desired.items():
            if col in op_cols:
                continue
            db.execute(text(f"ALTER TABLE operational_units ADD COLUMN {col} {col_sql}"))
            changed = True
            touched = True
        op_cols = {str(r[1]) for r in db.execute(text("PRAGMA table_info(operational_units)")).fetchall()}
        if {"hospital_id", "unit_type", "unit_name"}.issubset(op_cols):
            db.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS idx_operational_units_hospital_type_name ON operational_units(hospital_id, unit_type, unit_name)"
                )
            )
            touched = True

    if models.TABLES.get("beds") is not None:
        existing = {
            str(r[1])
            for r in db.execute(text("PRAGMA table_info(beds)")).fetchall()
        }
        desired = {
            "unit_type": "TEXT NOT NULL DEFAULT 'WARD'",
            "status": "TEXT NOT NULL DEFAULT 'FREE'",
            "current_patient_id": "INTEGER",
            "updated_at": "TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP",
        }
        for col, col_sql in desired.items():
            if col in existing:
                continue
            db.execute(text(f"ALTER TABLE beds ADD COLUMN {col} {col_sql}"))
            changed = True
            touched = True
        existing = {
            str(r[1])
            for r in db.execute(text("PRAGMA table_info(beds)")).fetchall()
        }
        if {"hospital_id", "unit_type", "ward_name", "status"}.issubset(existing):
            db.execute(
                text("CREATE INDEX IF NOT EXISTS idx_beds_hospital_unit_status ON beds(hospital_id, unit_type, ward_name, status)")
            )
            touched = True

    if models.TABLES.get("operation_theaters") is not None:
        ot_cols = {
            str(r[1]) for r in db.execute(text("PRAGMA table_info(operation_theaters)")).fetchall()
        }
        if "status" not in ot_cols:
            db.execute(text("ALTER TABLE operation_theaters ADD COLUMN status TEXT NOT NULL DEFAULT 'AVAILABLE'"))
            changed = True
            touched = True

    if touched:
        db.commit()
    if changed:
        models.load_tables()


def _ensure_fleet_management_table(db: Session) -> None:
    if models.TABLES.get("fleet_management") is not None:
        return
    db.execute(
        text(
            """
        CREATE TABLE IF NOT EXISTS fleet_management (
            fleet_id INTEGER PRIMARY KEY,
            hospital_id INTEGER NOT NULL,
            plate_number TEXT NOT NULL,
            vehicle_type TEXT NOT NULL,
            model_name TEXT,
            assigned_driver TEXT,
            status TEXT NOT NULL DEFAULT 'FREE',
            destination TEXT,
            eta_return TEXT,
            notes TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (hospital_id, fleet_id),
            UNIQUE (hospital_id, plate_number)
        )
        """
        )
    )
    db.execute(
        text(
            "CREATE INDEX IF NOT EXISTS idx_fleet_management_hospital_status_time ON fleet_management(hospital_id, status, created_at)"
        )
    )
    db.commit()
    models.load_tables()


def _ensure_fleet_auxiliary_tables(db: Session) -> None:
    _ensure_fleet_management_table(db)
    changed = False

    fleet_cols = {
        str(r[1]) for r in db.execute(text("PRAGMA table_info(fleet_management)")).fetchall()
    }
    if "mission_patient_name" not in fleet_cols:
        db.execute(text("ALTER TABLE fleet_management ADD COLUMN mission_patient_name TEXT"))
        changed = True

    if models.TABLES.get("fleet_trip_logs") is None:
        db.execute(
            text(
                """
            CREATE TABLE IF NOT EXISTS fleet_trip_logs (
                trip_id INTEGER PRIMARY KEY,
                hospital_id INTEGER NOT NULL,
                fleet_id INTEGER NOT NULL,
                destination TEXT,
                patient_name TEXT,
                assigned_driver TEXT,
                trip_status TEXT NOT NULL DEFAULT 'COMPLETED',
                started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                ended_at TEXT,
                notes TEXT,
                created_by_staff_id INTEGER,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
            )
        )
        db.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_fleet_trips_hospital_fleet_time ON fleet_trip_logs(hospital_id, fleet_id, started_at)"
            )
        )
        changed = True

    if models.TABLES.get("fleet_fuel_logs") is None:
        db.execute(
            text(
                """
            CREATE TABLE IF NOT EXISTS fleet_fuel_logs (
                fuel_log_id INTEGER PRIMARY KEY,
                hospital_id INTEGER NOT NULL,
                fleet_id INTEGER NOT NULL,
                liters REAL NOT NULL DEFAULT 0,
                cost_amount REAL NOT NULL DEFAULT 0,
                fuel_date TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                notes TEXT,
                expense_id INTEGER,
                created_by_staff_id INTEGER,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
            )
        )
        db.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_fleet_fuel_hospital_fleet_date ON fleet_fuel_logs(hospital_id, fleet_id, fuel_date)"
            )
        )
        changed = True

    if changed:
        db.commit()
        models.load_tables()


def _normalize_fleet_status(value: Any) -> str:
    status = str(value or "").strip().upper().replace("-", "_").replace(" ", "_")
    alias = {
        "AVAILABLE": "FREE",
        "ON_MISSION": "ON_MISSION",
        "BUSY": "ON_MISSION",
        "MAINTENANCE": "IN_MAINTENANCE",
    }
    status = alias.get(status, status)
    if status not in {"FREE", "ON_MISSION", "IN_MAINTENANCE"}:
        raise HTTPException(status_code=400, detail="status must be FREE, ON_MISSION, or IN_MAINTENANCE")
    return status


def _normalize_radiology_modality(value: Any) -> str:
    norm = str(value or "").strip().upper().replace("-", "_").replace(" ", "_")
    if norm in {"XRAY", "XRAY_", "X_RAY_"}:
        norm = "X_RAY"
    if norm == "X-RAY":
        norm = "X_RAY"
    if norm in {"CT", "CTSCAN", "CT_SCAN_", "CAT_SCAN"}:
        norm = "CT_SCAN"
    return norm


def _normalize_body_part(value: Any) -> str:
    return str(value or "").strip().upper().replace("-", "_").replace(" ", "_")


def _normalize_unit_type(value: Any) -> str:
    unit_type = str(value or "").strip().upper().replace("-", "_").replace(" ", "_")
    aliases = {
        "WARD": "WARD",
        "WARDS": "WARD",
        "ICU": "ICU",
        "OT": "OT",
        "OPERATION_THEATER": "OT",
        "OPERATION_THEATRE": "OT",
        "THEATER": "OT",
        "THEATRE": "OT",
    }
    unit_type = aliases.get(unit_type, unit_type)
    if unit_type not in {"WARD", "ICU", "OT"}:
        raise HTTPException(status_code=400, detail="unit_type must be WARD, ICU, or OT")
    return unit_type


def _normalize_bed_status(value: Any) -> str:
    status = str(value or "").strip().upper().replace("-", "_").replace(" ", "_")
    aliases = {
        "FREE": "FREE",
        "AVAILABLE": "FREE",
        "VACANT": "FREE",
        "OCCUPIED": "OCCUPIED",
        "BUSY": "OCCUPIED",
        "CLEANING": "CLEANING",
        "MAINTENANCE": "CLEANING",
        "PENDING": "CLEANING",
    }
    status = aliases.get(status, status)
    if status not in {"FREE", "OCCUPIED", "CLEANING"}:
        raise HTTPException(status_code=400, detail="bed status must be FREE, OCCUPIED, or CLEANING")
    return status


def _normalize_ot_status(value: Any) -> str:
    status = str(value or "").strip().upper().replace("-", "_").replace(" ", "_")
    aliases = {
        "AVAILABLE": "AVAILABLE",
        "FREE": "AVAILABLE",
        "SCHEDULED": "SCHEDULED",
        "BOOKED": "SCHEDULED",
    }
    status = aliases.get(status, status)
    if status not in {"AVAILABLE", "SCHEDULED"}:
        raise HTTPException(status_code=400, detail="OT status must be AVAILABLE or SCHEDULED")
    return status


@app.get("/lab/test-catalog")
def lab_test_catalog(
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_roles(current_user, {"LAB", "RADIOLOGIST", "ADMIN", "SUPER_ADMIN"})
    return {"ai_models": LAB_TEST_CATALOG, "standard_panels": LAB_STANDARD_PANELS}


@app.get("/lab/smart-form-config")
def lab_smart_form_config(
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_roles(current_user, {"LAB", "RADIOLOGIST", "ADMIN", "SUPER_ADMIN"})

    models_payload: List[Dict[str, Any]] = []
    mapping_payload: Dict[str, List[str]] = {}
    unified_feature_map: Dict[str, Dict[str, Any]] = {}
    symptom_options: List[str] = []
    for code, spec in LAB_SMART_MODEL_SPECS.items():
        feature_fields = _smart_model_form_fields(code)
        mapping_payload[code] = [f["key"] for f in feature_fields]
        model_item = {
            "code": code,
            "label": spec["label"],
            "department": spec["department"],
            "input_mode": spec["input_mode"],
            "ai_path": spec["ai_path"],
            "model_name": spec["model_name"],
            "features": feature_fields,
        }
        if spec["input_mode"] == "symptoms":
            model_symptoms = [f["key"] for f in feature_fields]
            model_item["symptom_options"] = model_symptoms
            symptom_options.extend(model_symptoms)
        else:
            for f in feature_fields:
                if f["key"] not in unified_feature_map:
                    unified_feature_map[f["key"]] = dict(f)
        models_payload.append(model_item)

    return {
        "models": models_payload,
        "model_feature_mapping": mapping_payload,
        "unified_features": list(unified_feature_map.values()),
        "symptom_options": sorted(list(set(symptom_options))),
        "specimen_types": LAB_SPECIMEN_TYPES,
        "standard_marker_sets": LAB_SMART_STANDARD_MARKERS,
    }


@app.post("/lab/smart-records")
def lab_create_smart_record(
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_roles(current_user, {"LAB", "RADIOLOGIST", "ADMIN", "SUPER_ADMIN"})
    _ensure_lab_records_table(db)

    hospital_id = current_user["hospital_id"]
    patient_id = int(payload.get("patient_id") or 0)
    selected_models_payload = payload.get("selected_models") or []
    selected_models: List[str] = []
    if isinstance(selected_models_payload, list):
        selected_models = [str(m).strip().upper() for m in selected_models_payload if str(m).strip()]
    if not selected_models:
        single = (payload.get("test_type") or payload.get("model_code") or "").strip().upper()
        if single:
            selected_models = [single]

    specimen_type = (payload.get("specimen_type") or "").strip()
    collection_timestamp = (payload.get("collection_timestamp") or "").strip()
    clinical_notes = (payload.get("clinical_notes") or "").strip() or None
    clinical_inputs = payload.get("clinical_inputs") or {}
    selected_symptoms = payload.get("selected_symptoms") or []
    standard_markers_payload = payload.get("standard_markers") or []

    if patient_id <= 0:
        raise HTTPException(status_code=400, detail="patient_id is required")
    if not selected_models:
        raise HTTPException(status_code=400, detail="selected_models is required")
    invalid = [m for m in selected_models if m not in LAB_SMART_MODEL_SPECS]
    if invalid:
        raise HTTPException(status_code=400, detail=f"Unsupported model_code(s): {', '.join(invalid)}")
    if not specimen_type:
        raise HTTPException(status_code=400, detail="specimen_type is required")
    if not collection_timestamp:
        raise HTTPException(status_code=400, detail="collection_timestamp is required")

    patients = models.TABLES["patients"]
    patient = db.execute(
        select(patients)
        .where(patients.c.hospital_id == hospital_id)
        .where(patients.c.patient_id == patient_id)
    ).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found for this hospital")

    ai_outputs: Dict[str, Any] = {}
    clinical_rows: List[Dict[str, Any]] = []
    diagnosis_rows: List[Dict[str, Any]] = []
    departments: List[str] = []

    for model_code in selected_models:
        spec = LAB_SMART_MODEL_SPECS[model_code]
        departments.append(spec["department"])
        validated = _validate_smart_inputs(model_code, clinical_inputs, selected_symptoms)
        ai_payload = _build_smart_ai_payload(
            model_code=model_code,
            clinical_inputs=validated.get("clinical_inputs", {}),
            selected_symptoms=validated.get("selected_symptoms", []),
        )

        try:
            ai_response = _call_ai_service(spec["ai_path"], ai_payload)
            ai_result = ai_response.get("result") or ai_response.get("prediction") or "N/A"
            ai_confidence = ai_response.get("confidence") or "N/A"
            ai_outputs[spec["ai_key"]] = {
                "label": spec["label"],
                "result": ai_result,
                "confidence": ai_confidence,
                "raw": ai_response,
                "model_code": model_code,
            }
            diagnosis_rows.append(
                {
                    "disease_category": f"LAB_{model_code}",
                    "prediction_result": str(ai_result),
                    "confidence_score": str(ai_confidence),
                    "model_version": f"{spec['model_name']}-bridge-v1",
                }
            )
        except Exception as exc:
            ai_outputs[spec["ai_key"]] = {
                "label": spec["label"],
                "error": str(exc),
                "model_code": model_code,
            }

        feature_fields = _smart_model_form_fields(model_code)
        clinical_values = validated.get("clinical_inputs", {})
        if spec["input_mode"] == "symptoms":
            for symptom in validated.get("selected_symptoms", []):
                clinical_rows.append(
                    {
                        "group": "clinical_inputs",
                        "model_code": model_code,
                        "key": symptom,
                        "marker_name": _feature_label_from_key(symptom),
                        "result_value": 1,
                        "units": "present",
                        "reference_range": {},
                        "critical_flag": False,
                        "description": "Selected symptom for disease predictor model",
                    }
                )
        else:
            for f in feature_fields:
                key = f["key"]
                value = clinical_values.get(key)
                ref = f.get("reference_range") or {}
                clinical_rows.append(
                    {
                        "group": "clinical_inputs",
                        "model_code": model_code,
                        "key": key,
                        "marker_name": f.get("label") or _feature_label_from_key(key),
                        "result_value": value,
                        "units": f.get("units") or "",
                        "reference_range": ref,
                        "critical_flag": _is_marker_critical(value, ref),
                        "description": f.get("description") or "",
                    }
                )

    standard_rows: List[Dict[str, Any]] = []
    for marker in standard_markers_payload:
        key = _normalize_feature_key(marker.get("key") or marker.get("marker_name") or "")
        if not key:
            continue
        rr = marker.get("reference_range") or {}
        value = marker.get("result_value")
        standard_rows.append(
            {
                "group": "standard_markers",
                "key": key,
                "marker_name": marker.get("marker_name") or _feature_label_from_key(key),
                "result_value": _safe_float(value) if _safe_float(value) is not None else value,
                "units": marker.get("units") or "",
                "reference_range": rr,
                "critical_flag": bool(marker.get("critical_flag")) or _is_marker_critical(value, rr),
            }
        )

    records = models.TABLES["lab_records"]
    age_override = _safe_float(payload.get("patient_age"))
    age_snapshot = int(age_override) if age_override is not None else _calc_age_from_dob(patient.dob)
    unique_departments = sorted(list(set([d for d in departments if d])))
    dept_label = ", ".join(unique_departments) if unique_departments else "Laboratory"
    record_type = selected_models[0] if len(selected_models) == 1 else "MULTI_MODEL"

    insert_result = db.execute(
        insert(records).values(
            hospital_id=hospital_id,
            patient_id=patient_id,
            collected_by_staff_id=_get_current_staff_id(db, current_user),
            test_type=record_type,
            department=dept_label,
            specimen_type=specimen_type,
            collection_timestamp=collection_timestamp,
            clinical_notes=clinical_notes,
            patient_full_name_snapshot=patient.full_name,
            patient_mrn_snapshot=patient.patient_mrn,
            patient_gender_snapshot=patient.gender,
            patient_age_snapshot=age_snapshot,
            markers_json=json.dumps({"clinical_inputs": clinical_rows, "standard_markers": standard_rows}),
            ai_outputs_json=json.dumps(ai_outputs),
            status="COMPLETED",
            updated_at=datetime.utcnow().isoformat(),
        )
    )
    record_id = insert_result.inserted_primary_key[0] if insert_result.inserted_primary_key else None

    if models.TABLES.get("ai_diagnoses") is not None:
        for d in diagnosis_rows:
            db.execute(
                insert(models.TABLES["ai_diagnoses"]).values(
                    hospital_id=hospital_id,
                    patient_id=patient_id,
                    doctor_id=_infer_patient_doctor_id(db, hospital_id, patient_id),
                    disease_category=d["disease_category"],
                    prediction_result=d["prediction_result"],
                    confidence_score=d["confidence_score"],
                    model_version=d["model_version"],
                )
            )
    db.commit()

    row = db.execute(
        select(records)
        .where(records.c.hospital_id == hospital_id)
        .where(records.c.record_id == record_id)
    ).first()
    item = _serialize_row(row) if row else {}
    try:
        item["markers_json"] = json.loads(item.get("markers_json") or "{}")
    except Exception:
        item["markers_json"] = {}
    try:
        item["ai_outputs_json"] = json.loads(item.get("ai_outputs_json") or "{}")
    except Exception:
        item["ai_outputs_json"] = {}

    return {"status": "saved", "record": item}


@app.get("/lab/clinical-form-config")
def lab_clinical_form_config(
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_roles(current_user, {"LAB", "ADMIN", "SUPER_ADMIN"})
    return {
        "test_types": LAB_CLINICAL_FORM_TESTS,
        "specimen_types": LAB_SPECIMEN_TYPES,
    }


@app.post("/lab/records")
def lab_create_record(
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_roles(current_user, {"LAB", "ADMIN", "SUPER_ADMIN"})
    _ensure_lab_records_table(db)

    hospital_id = current_user["hospital_id"]
    patient_id = int(payload.get("patient_id") or 0)
    test_type = (payload.get("test_type") or "").strip().upper()
    specimen_type = (payload.get("specimen_type") or "").strip()
    collection_timestamp = (payload.get("collection_timestamp") or "").strip()
    clinical_notes = (payload.get("clinical_notes") or "").strip() or None
    markers_payload = payload.get("markers") or []

    if patient_id <= 0:
        raise HTTPException(status_code=400, detail="patient_id is required")
    if test_type not in LAB_CLINICAL_FORM_TESTS:
        raise HTTPException(status_code=400, detail="test_type must be CBC, LFT, RFT, or DIABETES")
    if not specimen_type:
        raise HTTPException(status_code=400, detail="specimen_type is required")
    if not collection_timestamp:
        raise HTTPException(status_code=400, detail="collection_timestamp is required")
    if not isinstance(markers_payload, list) or len(markers_payload) == 0:
        raise HTTPException(status_code=400, detail="markers list is required")

    patients = models.TABLES["patients"]
    patient = db.execute(
        select(patients)
        .where(patients.c.hospital_id == hospital_id)
        .where(patients.c.patient_id == patient_id)
    ).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found for this hospital")

    marker_specs = {m["key"]: m for m in LAB_CLINICAL_FORM_TESTS[test_type]["markers"]}
    markers: List[Dict[str, Any]] = []
    tests_for_ai: Dict[str, Any] = {}
    for marker in markers_payload:
        key = str(marker.get("key") or "").strip()
        if key not in marker_specs:
            continue
        spec = marker_specs[key]
        result_value = marker.get("result_value")
        rr = marker.get("reference_range") or spec.get("reference_range") or {}
        critical = bool(marker.get("critical_flag"))
        if not marker.get("critical_flag"):
            critical = _is_marker_critical(result_value, rr)

        marker_obj = {
            "key": key,
            "marker_name": spec.get("marker_name"),
            "result_value": _safe_float(result_value) if _safe_float(result_value) is not None else result_value,
            "units": marker.get("units") or spec.get("units") or "",
            "reference_range": rr,
            "critical_flag": critical,
        }
        markers.append(marker_obj)
        tests_for_ai[key] = marker_obj["result_value"]

    if len(markers) == 0:
        raise HTTPException(status_code=400, detail="No valid markers submitted for selected test_type")

    ai_outputs: Dict[str, Any] = {}
    ai_test_key = LAB_CLINICAL_FORM_TESTS[test_type].get("ai_test_key")
    if ai_test_key:
        try:
            ai_payload = _build_ai_payload(ai_test_key, tests_for_ai)
            ai_outputs[ai_test_key] = _call_ai_service(LAB_TEST_CATALOG[ai_test_key]["ai_path"], ai_payload)
        except Exception as exc:
            ai_outputs[ai_test_key] = {"error": str(exc)}

    records = models.TABLES["lab_records"]
    department = LAB_CLINICAL_FORM_TESTS[test_type]["department"]
    age_override = _safe_float(payload.get("patient_age"))
    age_snapshot = int(age_override) if age_override is not None else _calc_age_from_dob(patient.dob)
    result = db.execute(
        insert(records).values(
            hospital_id=hospital_id,
            patient_id=patient_id,
            collected_by_staff_id=_get_current_staff_id(db, current_user),
            test_type=test_type,
            department=department,
            specimen_type=specimen_type,
            collection_timestamp=collection_timestamp,
            clinical_notes=clinical_notes,
            patient_full_name_snapshot=patient.full_name,
            patient_mrn_snapshot=patient.patient_mrn,
            patient_gender_snapshot=patient.gender,
            patient_age_snapshot=age_snapshot,
            markers_json=json.dumps(markers),
            ai_outputs_json=json.dumps(ai_outputs),
            status="COMPLETED",
            updated_at=datetime.utcnow().isoformat(),
        )
    )

    record_id = result.inserted_primary_key[0] if result.inserted_primary_key else None

    if ai_test_key and models.TABLES.get("ai_diagnoses") is not None:
        ai_row = ai_outputs.get(ai_test_key) or {}
        if isinstance(ai_row, dict) and not ai_row.get("error"):
            db.execute(
                insert(models.TABLES["ai_diagnoses"]).values(
                    hospital_id=hospital_id,
                    patient_id=patient_id,
                    doctor_id=_infer_patient_doctor_id(db, hospital_id, patient_id),
                    disease_category=f"LAB_{test_type}",
                    prediction_result=str(ai_row.get("result") or ai_row.get("prediction") or "N/A"),
                    confidence_score=str(ai_row.get("confidence") or "N/A"),
                    model_version="UCI-LAB-v1",
                )
            )

    db.commit()

    row = db.execute(
        select(records)
        .where(records.c.hospital_id == hospital_id)
        .where(records.c.record_id == record_id)
    ).first()

    item = _serialize_row(row) if row else {}
    try:
        item["markers_json"] = json.loads(item.get("markers_json") or "[]")
    except Exception:
        item["markers_json"] = []
    try:
        item["ai_outputs_json"] = json.loads(item.get("ai_outputs_json") or "{}")
    except Exception:
        item["ai_outputs_json"] = {}

    return {"status": "saved", "record": item}


@app.get("/lab/records")
def lab_list_records(
    status: Optional[str] = Query(default="COMPLETED"),
    record_id: Optional[int] = Query(default=None, ge=1),
    patient_mrn: Optional[str] = Query(default=None),
    test_type: Optional[str] = Query(default=None),
    limit: int = Query(default=300, ge=1, le=1000),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_roles(current_user, {"LAB", "RADIOLOGIST", "ADMIN", "SUPER_ADMIN"})
    _ensure_lab_records_table(db)

    hospital_id = current_user["hospital_id"]
    records = models.TABLES["lab_records"]
    patients = models.TABLES["patients"]

    query = (
        select(
            records,
            patients.c.full_name.label("patient_name"),
            patients.c.patient_mrn.label("patient_mrn"),
        )
        .select_from(
            records.join(
                patients,
                (records.c.hospital_id == patients.c.hospital_id)
                & (records.c.patient_id == patients.c.patient_id),
            )
        )
        .where(records.c.hospital_id == hospital_id)
        .order_by(records.c.created_at.desc())
    )

    if status:
        query = query.where(records.c.status == status.upper().strip())
    if record_id is not None:
        query = query.where(records.c.record_id == int(record_id))
    if patient_mrn:
        query = query.where(patients.c.patient_mrn == str(patient_mrn).strip())
    if test_type:
        query = query.where(records.c.test_type == str(test_type).strip().upper())

    rows = db.execute(query.limit(limit)).fetchall()
    items = []
    for r in rows:
        item = _serialize_row(r)
        try:
            item["markers_json"] = json.loads(item.get("markers_json") or "[]")
        except Exception:
            item["markers_json"] = []
        try:
            item["ai_outputs_json"] = json.loads(item.get("ai_outputs_json") or "{}")
        except Exception:
            item["ai_outputs_json"] = {}
        items.append(item)
    return {"count": len(items), "items": items}


@app.get("/lab/records/{record_id}/report")
def lab_record_report(
    record_id: int,
    patient_mrn: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_roles(current_user, {"LAB", "RADIOLOGIST", "ADMIN", "SUPER_ADMIN"})
    _ensure_lab_records_table(db)

    hospital_id = current_user["hospital_id"]
    records = models.TABLES["lab_records"]
    settings = models.TABLES.get("hospital_settings")
    patients = models.TABLES["patients"]

    row = db.execute(
        select(
            records,
            patients.c.full_name.label("patient_name"),
            patients.c.patient_mrn.label("patient_mrn"),
            patients.c.dob.label("patient_dob"),
            patients.c.gender.label("patient_gender"),
        )
        .select_from(
            records.join(
                patients,
                (records.c.hospital_id == patients.c.hospital_id)
                & (records.c.patient_id == patients.c.patient_id),
            )
        )
        .where(records.c.hospital_id == hospital_id)
        .where(records.c.record_id == record_id)
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Lab record not found")
    if patient_mrn and str(row.patient_mrn or "").strip() != str(patient_mrn).strip():
        raise HTTPException(status_code=404, detail="Lab record not found for provided patient_mrn")

    hospital_profile = None
    if settings is not None:
        hospital_profile = db.execute(select(settings).where(settings.c.hospital_id == hospital_id)).first()

    item = _serialize_row(row)
    try:
        item["markers_json"] = json.loads(item.get("markers_json") or "[]")
    except Exception:
        item["markers_json"] = []
    try:
        item["ai_outputs_json"] = json.loads(item.get("ai_outputs_json") or "{}")
    except Exception:
        item["ai_outputs_json"] = {}

    return {
        "record": item,
        "hospital": _serialize_row(hospital_profile) if hospital_profile else None,
    }


@app.get("/doctor/lab-reports")
def doctor_lab_reports(
    status: Optional[str] = Query(default="COMPLETED"),
    patient_id: Optional[int] = Query(default=None, ge=1),
    record_id: Optional[int] = Query(default=None, ge=1),
    patient_mrn: Optional[str] = Query(default=None),
    test_type: Optional[str] = Query(default=None),
    limit: int = Query(default=1000, ge=1, le=2000),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_roles(current_user, {"DOCTOR", "ADMIN", "SUPER_ADMIN"})
    _ensure_lab_records_table(db)

    hospital_id = current_user["hospital_id"]
    records = models.TABLES["lab_records"]
    patients = models.TABLES["patients"]

    query = (
        select(
            records,
            patients.c.full_name.label("patient_name"),
            patients.c.patient_mrn.label("patient_mrn"),
        )
        .select_from(
            records.join(
                patients,
                (records.c.hospital_id == patients.c.hospital_id)
                & (records.c.patient_id == patients.c.patient_id),
            )
        )
        .where(records.c.hospital_id == hospital_id)
        .order_by(records.c.created_at.desc())
    )

    if status:
        query = query.where(records.c.status == status.upper().strip())
    if patient_id is not None:
        query = query.where(records.c.patient_id == int(patient_id))
    if record_id is not None:
        query = query.where(records.c.record_id == int(record_id))
    if patient_mrn:
        query = query.where(patients.c.patient_mrn == str(patient_mrn).strip())
    if test_type:
        query = query.where(records.c.test_type == str(test_type).strip().upper())

    rows = db.execute(query.limit(limit)).fetchall()
    items = []
    for r in rows:
        item = _serialize_row(r)
        try:
            item["markers_json"] = json.loads(item.get("markers_json") or "[]")
        except Exception:
            item["markers_json"] = []
        try:
            item["ai_outputs_json"] = json.loads(item.get("ai_outputs_json") or "{}")
        except Exception:
            item["ai_outputs_json"] = {}
        items.append(item)
    return {"count": len(items), "items": items}


@app.get("/lab/master-tests")
def lab_master_tests(
    q: str = Query(default=""),
    department: Optional[str] = Query(default=None),
    limit: int = Query(default=500, ge=1, le=5000),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_roles(current_user, {"LAB", "DOCTOR", "ADMIN", "SUPER_ADMIN"})

    query = (q or "").strip().lower()
    dept = (department or "").strip().lower()
    items: List[Dict[str, Any]] = []
    for t in _all_master_tests():
        if dept and (t.get("department") or "").lower() != dept:
            continue
        blob = f"{t.get('code','')} {t.get('name','')} {' '.join(t.get('aliases') or [])}".lower()
        if query and query not in blob:
            continue
        row = dict(t)
        row["slug"] = _slugify_lab_test_name(t.get("name") or t.get("code") or "")
        items.append(row)
        if len(items) >= limit:
            break
    return {"count": len(items), "items": items}


@app.get("/lab/master-tests/{test_code}/form-schema")
def lab_master_test_form_schema(
    test_code: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_roles(current_user, {"LAB", "ADMIN", "SUPER_ADMIN"})

    key = (test_code or "").strip().upper()
    item = next((t for t in _all_master_tests() if (t.get("code") or "").upper() == key), None)
    if not item:
        raise HTTPException(status_code=404, detail="Test code not found")

    fields = _default_lab_form_schema(
        test_code=item.get("code") or key,
        test_name=item.get("name") or key,
        department=item.get("department") or "",
    )
    return {
        "test": {
            "code": item.get("code"),
            "name": item.get("name"),
            "department": item.get("department"),
            "aliases": item.get("aliases") or [],
            "slug": _slugify_lab_test_name(item.get("name") or item.get("code") or ""),
        },
        "fields": fields,
    }


@app.post("/lab/master-tests/import")
def lab_import_master_tests(
    payload: Dict[str, Any] = Body(...),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_roles(current_user, {"ADMIN", "SUPER_ADMIN", "LAB"})

    raw_text = str(payload.get("raw_text") or "").strip()
    if not raw_text:
        raise HTTPException(status_code=400, detail="raw_text is required")

    existing = { (t.get("code") or "").upper(): t for t in _all_master_tests() }
    custom = _load_custom_lab_tests()
    custom_by_code = { (t.get("code") or "").upper(): t for t in custom }

    imported = 0
    skipped = 0
    lines = raw_text.splitlines()
    for line in lines:
        text = line.strip()
        if not text:
            continue
        if text.lower() in {"back to top", "i"}:
            continue
        if re.fullmatch(r"[a-zA-Z]", text):
            continue

        parts = [p.strip() for p in re.split(r"\t+", text) if p.strip()]
        if len(parts) < 2:
            skipped += 1
            continue

        test_name = parts[0]
        department = parts[1] if len(parts) > 1 else "Laboratory"
        notes = parts[2] if len(parts) > 2 else ""
        aliases = [a.strip() for a in re.split(r"[;,]", notes) if a.strip()]

        code = _normalize_lab_test_code(test_name)
        if code in existing:
            skipped += 1
            continue

        row = {
            "code": code,
            "name": test_name,
            "department": department,
            "aliases": aliases,
        }
        custom_by_code[code] = row
        existing[code] = row
        imported += 1

    _save_custom_lab_tests(list(custom_by_code.values()))
    return {
        "status": "imported",
        "imported": imported,
        "skipped": skipped,
        "total_catalog_size": len(_all_master_tests()),
    }


@app.get("/lab/patient-search")
def lab_patient_search(
    q: str = Query(default=""),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_roles(current_user, {"LAB", "DOCTOR", "RADIOLOGIST", "ADMIN", "SUPER_ADMIN"})

    patients = models.TABLES["patients"]
    hospital_id = current_user["hospital_id"]

    query = select(patients).where(patients.c.hospital_id == hospital_id)
    if q.strip():
        term = f"%{q.strip()}%"
        query = query.where((patients.c.patient_mrn.like(term)) | (patients.c.full_name.like(term)))

    patient_recent_order = _recent_order_expr(patients, "created_at", "patient_id")
    if patient_recent_order is not None:
        query = query.order_by(patient_recent_order)
    rows = db.execute(query.limit(limit)).fetchall()
    return {"count": len(rows), "items": [_serialize_row(r) for r in rows]}


@app.post("/lab/entries")
def lab_create_entry(
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_roles(current_user, {"LAB", "ADMIN", "SUPER_ADMIN"})

    hospital_id = current_user["hospital_id"]
    patient_id = int(payload.get("patient_id") or 0)
    tests = payload.get("tests") or {}
    panel_name = (payload.get("panel_name") or "GENERAL").strip().upper()
    collection_date = payload.get("collection_date")
    technician_signature = (payload.get("technician_signature") or "").strip() or None

    if patient_id <= 0:
        raise HTTPException(status_code=400, detail="patient_id is required")

    patients = models.TABLES["patients"]
    entries = models.TABLES["lab_result_entries"]

    patient = db.execute(
        select(patients)
        .where(patients.c.hospital_id == hospital_id)
        .where(patients.c.patient_id == patient_id)
    ).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found for this hospital")

    ai_outputs = _run_background_ai_models(tests)

    result = db.execute(
        insert(entries).values(
            hospital_id=hospital_id,
            patient_id=patient_id,
            collected_by_staff_id=_get_current_staff_id(db, current_user),
            collection_date=collection_date,
            panel_name=panel_name,
            tests_json=json.dumps(tests),
            ai_outputs_json=json.dumps(ai_outputs),
            status="DRAFT",
            technician_signature=technician_signature,
        )
    )
    db.commit()

    entry_id = result.inserted_primary_key[0] if result.inserted_primary_key else None
    row = db.execute(
        select(entries)
        .where(entries.c.hospital_id == hospital_id)
        .where(entries.c.entry_id == entry_id)
    ).first()

    return {
        "status": "saved",
        "entry": _serialize_row(row) if row else None,
        "ai_outputs": ai_outputs,
    }


@app.get("/lab/entries")
def lab_list_entries(
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_roles(current_user, {"LAB", "ADMIN", "SUPER_ADMIN"})

    hospital_id = current_user["hospital_id"]
    entries = models.TABLES["lab_result_entries"]
    patients = models.TABLES["patients"]

    query = (
        select(
            entries,
            patients.c.full_name.label("patient_name"),
            patients.c.patient_mrn.label("patient_mrn"),
        )
        .select_from(
            entries.join(
                patients,
                (entries.c.hospital_id == patients.c.hospital_id)
                & (entries.c.patient_id == patients.c.patient_id),
            )
        )
        .where(entries.c.hospital_id == hospital_id)
        .order_by(entries.c.created_at.desc())
    )

    if status:
        query = query.where(entries.c.status == status.upper().strip())

    rows = db.execute(query.limit(limit)).fetchall()
    items = []
    for r in rows:
        row = _serialize_row(r)
        try:
            row["tests_json"] = json.loads(row.get("tests_json") or "{}")
        except Exception:
            row["tests_json"] = {}
        try:
            row["ai_outputs_json"] = json.loads(row.get("ai_outputs_json") or "{}")
        except Exception:
            row["ai_outputs_json"] = {}
        items.append(row)

    return {"count": len(items), "items": items}


@app.post("/lab/entries/{entry_id}/finalize")
def lab_finalize_entry(
    entry_id: int,
    payload: Dict[str, Any] = Body(default={}),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_roles(current_user, {"LAB", "ADMIN", "SUPER_ADMIN"})

    hospital_id = current_user["hospital_id"]
    entries = models.TABLES["lab_result_entries"]
    diagnoses = models.TABLES["ai_diagnoses"]
    lab_requests = models.TABLES.get("lab_requests")

    row = db.execute(
        select(entries)
        .where(entries.c.hospital_id == hospital_id)
        .where(entries.c.entry_id == entry_id)
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Lab entry not found")

    if (row.status or "").upper() == "COMPLETED":
        return {"status": "already_finalized", "entry_id": entry_id}

    try:
        tests = json.loads(row.tests_json or "{}")
    except Exception:
        tests = {}

    try:
        ai_outputs = json.loads(row.ai_outputs_json or "{}")
    except Exception:
        ai_outputs = {}

    doctor_id = payload.get("doctor_id")
    if doctor_id in [None, "", 0]:
        doctor_id = _infer_patient_doctor_id(db, hospital_id, int(row.patient_id))
    else:
        doctor_id = int(doctor_id)

    created_diagnoses = 0
    for key, data in ai_outputs.items():
        if not isinstance(data, dict) or data.get("error"):
            continue
        db.execute(
            insert(diagnoses).values(
                hospital_id=hospital_id,
                patient_id=int(row.patient_id),
                doctor_id=doctor_id,
                disease_category=key.upper(),
                prediction_result=str(data.get("result") or "Unknown"),
                confidence_score=str(data.get("confidence") or "N/A"),
                scan_file_path=None,
                model_version="UCI-LAB-v1",
            )
        )
        created_diagnoses += 1

    if lab_requests is not None:
        test_row = _ensure_lab_test(db, hospital_id, f"{row.panel_name} PANEL")
        summary = f"{row.panel_name} report finalized with {created_diagnoses} AI insights"
        db.execute(
            insert(lab_requests).values(
                hospital_id=hospital_id,
                patient_id=int(row.patient_id),
                test_id=test_row.test_id,
                ordered_by_staff_id=row.collected_by_staff_id,
                status="COMPLETED",
                result_notes=summary,
                report_file_path=None,
            )
        )

    now_iso = datetime.utcnow().isoformat()
    db.execute(
        update(entries)
        .where(entries.c.hospital_id == hospital_id)
        .where(entries.c.entry_id == entry_id)
        .values(status="COMPLETED", finalized_at=now_iso)
    )

    db.commit()

    return {
        "status": "finalized",
        "entry_id": entry_id,
        "sync": {
            "doctor_portal": True,
            "patient_portal": True,
            "created_ai_diagnoses": created_diagnoses,
        },
    }


@app.get("/lab/entries/{entry_id}/report")
def lab_entry_report(
    entry_id: int,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_roles(current_user, {"LAB", "ADMIN", "SUPER_ADMIN"})

    hospital_id = current_user["hospital_id"]
    entries = models.TABLES["lab_result_entries"]
    patients = models.TABLES["patients"]
    settings = models.TABLES.get("hospital_settings")

    row = db.execute(
        select(entries, patients.c.full_name.label("patient_name"), patients.c.patient_mrn.label("patient_mrn"), patients.c.dob.label("patient_dob"))
        .select_from(
            entries.join(
                patients,
                (entries.c.hospital_id == patients.c.hospital_id)
                & (entries.c.patient_id == patients.c.patient_id),
            )
        )
        .where(entries.c.hospital_id == hospital_id)
        .where(entries.c.entry_id == entry_id)
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Lab entry not found")

    hospital_profile = None
    if settings is not None:
        hospital_profile = db.execute(select(settings).where(settings.c.hospital_id == hospital_id)).first()

    item = _serialize_row(row)
    try:
        item["tests_json"] = json.loads(item.get("tests_json") or "{}")
    except Exception:
        item["tests_json"] = {}
    try:
        item["ai_outputs_json"] = json.loads(item.get("ai_outputs_json") or "{}")
    except Exception:
        item["ai_outputs_json"] = {}

    return {
        "entry": item,
        "hospital": _serialize_row(hospital_profile) if hospital_profile else None,
    }


@app.get("/doctor/recent-results")
def doctor_recent_results(
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_roles(current_user, {"DOCTOR", "ADMIN", "SUPER_ADMIN", "LAB"})
    hospital_id = current_user["hospital_id"]

    diagnoses = models.TABLES["ai_diagnoses"]
    patients = models.TABLES["patients"]

    rows = db.execute(
        select(
            diagnoses,
            patients.c.full_name.label("patient_name"),
            patients.c.patient_mrn.label("patient_mrn"),
        )
        .select_from(
            diagnoses.join(
                patients,
                (diagnoses.c.hospital_id == patients.c.hospital_id)
                & (diagnoses.c.patient_id == patients.c.patient_id),
            )
        )
        .where(diagnoses.c.hospital_id == hospital_id)
        .order_by(diagnoses.c.created_at.desc())
        .limit(limit)
    ).fetchall()

    return {"count": len(rows), "items": [_serialize_row(r) for r in rows]}


@app.get("/doctor/appointments")
def doctor_appointments_feed(
    status: Optional[str] = Query(default="SCHEDULED"),
    doctor_id: Optional[int] = Query(default=None, ge=1),
    date: Optional[str] = Query(default=None, description="YYYY-MM-DD optional"),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_roles(current_user, {"DOCTOR", "ADMIN", "SUPER_ADMIN"})

    hospital_id = current_user["hospital_id"]
    role = (current_user.get("role_name") or "").upper()
    appointments = models.TABLES["appointments"]
    patients = models.TABLES["patients"]
    staff = models.TABLES["staff"]

    query = (
        select(
            appointments,
            patients.c.full_name.label("patient_name"),
            patients.c.patient_mrn.label("patient_mrn"),
            staff.c.full_name.label("doctor_name"),
        )
        .select_from(
            appointments.join(
                patients,
                (appointments.c.hospital_id == patients.c.hospital_id)
                & (appointments.c.patient_id == patients.c.patient_id),
            ).join(
                staff,
                (appointments.c.hospital_id == staff.c.hospital_id)
                & (appointments.c.doctor_id == staff.c.staff_id),
            )
        )
        .where(appointments.c.hospital_id == hospital_id)
    )

    status_norm = (status or "").strip().upper()
    if status_norm and status_norm != "ALL":
        query = query.where(appointments.c.status == status_norm)

    if date:
        date_norm = str(date).strip()
        try:
            datetime.strptime(date_norm, "%Y-%m-%d")
        except Exception:
            raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD")
        query = query.where(appointments.c.appointment_date.like(f"{date_norm}%"))

    if role == "DOCTOR":
        doctor_staff_id = _get_current_staff_id(db, current_user)
        if not doctor_staff_id:
            raise HTTPException(status_code=403, detail="No doctor staff profile linked to this account")
        query = query.where(appointments.c.doctor_id == int(doctor_staff_id))
    elif doctor_id is not None:
        query = query.where(appointments.c.doctor_id == int(doctor_id))

    rows = db.execute(
        query.order_by(appointments.c.appointment_date.asc()).limit(limit).offset(offset)
    ).fetchall()
    return {"count": len(rows), "items": [_serialize_row(r) for r in rows]}


@app.get("/reception/appointments")
def reception_appointments_feed(
    status: Optional[str] = Query(default="SCHEDULED"),
    doctor_id: Optional[int] = Query(default=None, ge=1),
    date: Optional[str] = Query(default=None, description="YYYY-MM-DD optional"),
    limit: int = Query(default=150, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_roles(current_user, {"RECEPTIONIST", "ADMIN", "SUPER_ADMIN"})

    hospital_id = current_user["hospital_id"]
    appointments = models.TABLES["appointments"]
    patients = models.TABLES["patients"]
    staff = models.TABLES["staff"]

    query = (
        select(
            appointments,
            patients.c.full_name.label("patient_name"),
            patients.c.patient_mrn.label("patient_mrn"),
            staff.c.full_name.label("doctor_name"),
        )
        .select_from(
            appointments.join(
                patients,
                (appointments.c.hospital_id == patients.c.hospital_id)
                & (appointments.c.patient_id == patients.c.patient_id),
            ).join(
                staff,
                (appointments.c.hospital_id == staff.c.hospital_id)
                & (appointments.c.doctor_id == staff.c.staff_id),
            )
        )
        .where(appointments.c.hospital_id == hospital_id)
    )

    status_norm = (status or "").strip().upper()
    if status_norm and status_norm != "ALL":
        query = query.where(appointments.c.status == status_norm)
    if doctor_id is not None:
        query = query.where(appointments.c.doctor_id == int(doctor_id))
    if date:
        date_norm = str(date).strip()
        try:
            datetime.strptime(date_norm, "%Y-%m-%d")
        except Exception:
            raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD")
        query = query.where(appointments.c.appointment_date.like(f"{date_norm}%"))

    rows = db.execute(
        query.order_by(appointments.c.appointment_date.asc()).limit(limit).offset(offset)
    ).fetchall()
    return {"count": len(rows), "items": [_serialize_row(r) for r in rows]}


@app.post("/doctor/requests")
def doctor_create_request(
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_roles(current_user, {"DOCTOR", "ADMIN", "SUPER_ADMIN"})

    hospital_id = current_user["hospital_id"]
    patient_id = int(payload.get("patient_id") or 0)
    request_type = (payload.get("request_type") or "LAB").strip().upper()
    priority = (payload.get("priority") or "ROUTINE").strip().upper()
    notes = (payload.get("notes") or "").strip() or None

    if patient_id <= 0:
        raise HTTPException(status_code=400, detail="patient_id is required")
    if request_type not in {"LAB", "RADIOLOGY"}:
        raise HTTPException(status_code=400, detail="request_type must be LAB or RADIOLOGY")
    if priority not in {"ROUTINE", "URGENT", "STAT"}:
        priority = "ROUTINE"

    patients = models.TABLES["patients"]
    patient = db.execute(
        select(patients.c.patient_id)
        .where(patients.c.hospital_id == hospital_id)
        .where(patients.c.patient_id == patient_id)
    ).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found for this hospital")

    doctor_staff_id = _get_current_staff_id(db, current_user)

    if request_type == "LAB":
        test_code = (payload.get("test_code") or "").strip().upper()
        if not test_code:
            raise HTTPException(status_code=400, detail="test_code is required for LAB request")

        test_info = next((t for t in _all_master_tests() if (t.get("code") or "").upper() == test_code), None)
        if not test_info:
            raise HTTPException(status_code=404, detail="Lab test code not found")

        lab_tests = models.TABLES["lab_tests"]
        lab_requests = models.TABLES["lab_requests"]

        test_row = db.execute(
            select(lab_tests)
            .where(lab_tests.c.hospital_id == hospital_id)
            .where(lab_tests.c.test_name == test_info["name"])
        ).first()
        if not test_row:
            db.execute(
                insert(lab_tests).values(
                    hospital_id=hospital_id,
                    test_name=test_info["name"],
                    cost=payload.get("estimated_cost") or 0,
                )
            )
            db.commit()
            test_row = db.execute(
                select(lab_tests)
                .where(lab_tests.c.hospital_id == hospital_id)
                .where(lab_tests.c.test_name == test_info["name"])
            ).first()

        result = db.execute(
            insert(lab_requests).values(
                hospital_id=hospital_id,
                patient_id=patient_id,
                test_id=test_row.test_id,
                ordered_by_staff_id=doctor_staff_id,
                status="ORDERED",
                result_notes=notes,
            )
        )
        db.commit()
        request_id = result.inserted_primary_key[0] if result.inserted_primary_key else None

        row = db.execute(
            select(
                lab_requests,
                lab_tests.c.test_name.label("test_name"),
                patients.c.full_name.label("patient_name"),
                patients.c.patient_mrn.label("patient_mrn"),
            )
            .select_from(
                lab_requests.join(
                    lab_tests,
                    (lab_requests.c.hospital_id == lab_tests.c.hospital_id)
                    & (lab_requests.c.test_id == lab_tests.c.test_id),
                ).join(
                    patients,
                    (lab_requests.c.hospital_id == patients.c.hospital_id)
                    & (lab_requests.c.patient_id == patients.c.patient_id),
                )
            )
            .where(lab_requests.c.hospital_id == hospital_id)
            .where(lab_requests.c.request_id == request_id)
        ).first()

        return {"status": "created", "request_type": "LAB", "item": _serialize_row(row) if row else None}

    _ensure_radiology_table(db)
    radiology = models.TABLES["radiology_requests"]
    test_name = (payload.get("test_name") or "").strip()
    if not test_name:
        raise HTTPException(status_code=400, detail="test_name is required for RADIOLOGY request")

    result = db.execute(
        insert(radiology).values(
            hospital_id=hospital_id,
            patient_id=patient_id,
            ordered_by_staff_id=doctor_staff_id,
            test_name=test_name,
            body_part=(payload.get("body_part") or None),
            priority=priority,
            status="ORDERED",
            notes=notes,
        )
    )
    db.commit()
    rad_id = result.inserted_primary_key[0] if result.inserted_primary_key else None
    row = db.execute(
        select(radiology)
        .where(radiology.c.hospital_id == hospital_id)
        .where(radiology.c.radiology_request_id == rad_id)
    ).first()
    return {"status": "created", "request_type": "RADIOLOGY", "item": _serialize_row(row) if row else None}


@app.get("/doctor/patients/{patient_id}/requests")
def doctor_patient_requests(
    patient_id: int,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_roles(current_user, {"DOCTOR", "LAB", "RADIOLOGIST", "ADMIN", "SUPER_ADMIN"})
    hospital_id = current_user["hospital_id"]

    patients = models.TABLES["patients"]
    p = db.execute(
        select(patients.c.patient_id, patients.c.full_name, patients.c.patient_mrn)
        .where(patients.c.hospital_id == hospital_id)
        .where(patients.c.patient_id == patient_id)
    ).first()
    if not p:
        raise HTTPException(status_code=404, detail="Patient not found")

    lab_items: List[Dict[str, Any]] = []
    if models.TABLES.get("lab_requests") is not None and models.TABLES.get("lab_tests") is not None:
        lab_requests = models.TABLES["lab_requests"]
        lab_tests = models.TABLES["lab_tests"]
        lrows = db.execute(
            select(
                lab_requests,
                lab_tests.c.test_name.label("test_name"),
            )
            .select_from(
                lab_requests.join(
                    lab_tests,
                    (lab_requests.c.hospital_id == lab_tests.c.hospital_id)
                    & (lab_requests.c.test_id == lab_tests.c.test_id),
                )
            )
            .where(lab_requests.c.hospital_id == hospital_id)
            .where(lab_requests.c.patient_id == patient_id)
            .order_by(lab_requests.c.request_id.desc())
        ).fetchall()
        lab_items = [_serialize_row(r) for r in lrows]

    radiology_items: List[Dict[str, Any]] = []
    if models.TABLES.get("radiology_requests") is not None:
        rad = models.TABLES["radiology_requests"]
        rrows = db.execute(
            select(rad)
            .where(rad.c.hospital_id == hospital_id)
            .where(rad.c.patient_id == patient_id)
            .order_by(rad.c.radiology_request_id.desc())
        ).fetchall()
        radiology_items = [_serialize_row(r) for r in rrows]

    return {
        "patient": _serialize_row(p),
        "lab_requests": lab_items,
        "radiology_requests": radiology_items,
    }


@app.get("/radiology/config")
def radiology_config(
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_roles(current_user, {"LAB", "DOCTOR", "RADIOLOGIST", "ADMIN", "SUPER_ADMIN"})

    modalities = []
    for code, spec in RADIOLOGY_MODALITY_BODY_PARTS.items():
        modalities.append(
            {
                "code": code,
                "label": spec.get("label") or code,
                "body_parts": [
                    {"code": bp, "label": bp.replace("_", " ").title()}
                    for bp in (spec.get("body_parts") or [])
                ],
            }
        )

    return {
        "modalities": modalities,
        "ai_triggers": RADIOLOGY_AI_TRIGGERS,
    }


@app.post("/radiology/imaging-records")
def create_imaging_record(
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_roles(current_user, {"LAB", "DOCTOR", "RADIOLOGIST", "ADMIN", "SUPER_ADMIN"})
    _ensure_imaging_records_table(db)

    hospital_id = current_user["hospital_id"]
    patient_id = int(payload.get("patient_id") or 0)
    patient_mrn = str(payload.get("patient_mrn") or "").strip()
    modality = _normalize_radiology_modality(payload.get("modality"))
    body_part = _normalize_body_part(payload.get("body_part"))
    study_title = (payload.get("study_title") or "").strip() or None
    source_page = (payload.get("source_page") or "RADIOLOGY_DASHBOARD").strip().upper()
    technician_notes = (payload.get("technician_notes") or "").strip() or None
    doctor_notes = (payload.get("doctor_notes") or "").strip() or None
    ai_model_key = (payload.get("ai_model_key") or "").strip() or None
    ai_result = (payload.get("ai_result") or "").strip() or None
    ai_confidence = (payload.get("ai_confidence") or "").strip() or None
    scan_image_data_url = (payload.get("scan_image_data_url") or "").strip() or None
    scan_file_path = _save_scan_data_url_file(
        scan_image_data_url=scan_image_data_url,
        hospital_id=hospital_id,
        patient_id=patient_id,
        modality=modality,
        body_part=body_part,
    )
    ai_findings = payload.get("ai_findings")
    if ai_findings is None:
        ai_findings = {}
    request_id = payload.get("request_id")
    status = (payload.get("status") or "DRAFT").strip().upper()
    if status not in {"DRAFT", "COMPLETED", "FINALIZED"}:
        status = "DRAFT"
    add_to_patient_record = bool(payload.get("add_to_patient_record"))

    if patient_id <= 0:
        raise HTTPException(status_code=400, detail="patient_id is required")
    if not patient_mrn:
        raise HTTPException(status_code=400, detail="patient_mrn is required")
    if modality not in RADIOLOGY_MODALITY_BODY_PARTS:
        allowed = ", ".join(sorted(RADIOLOGY_MODALITY_BODY_PARTS.keys()))
        raise HTTPException(status_code=400, detail=f"Unsupported modality. Allowed: {allowed}")
    allowed_body_parts = set(RADIOLOGY_MODALITY_BODY_PARTS[modality].get("body_parts") or [])
    if body_part not in allowed_body_parts:
        allowed_bp = ", ".join(sorted(allowed_body_parts))
        raise HTTPException(status_code=400, detail=f"Unsupported body_part for {modality}. Allowed: {allowed_bp}")

    patients = models.TABLES["patients"]
    patient = db.execute(
        select(patients.c.patient_id, patients.c.patient_mrn, patients.c.full_name)
        .where(patients.c.hospital_id == hospital_id)
        .where(patients.c.patient_id == patient_id)
    ).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found for this hospital")
    if str(patient.patient_mrn or "").strip() != patient_mrn:
        raise HTTPException(status_code=400, detail="patient_mrn does not match patient_id")

    request_id_int = None
    if request_id not in [None, ""]:
        try:
            request_id_int = int(request_id)
        except Exception:
            request_id_int = None

    records = models.TABLES["imaging_records"]
    now_iso = datetime.utcnow().isoformat()
    result = db.execute(
        insert(records).values(
            hospital_id=hospital_id,
            patient_id=patient_id,
            patient_mrn_snapshot=patient_mrn,
            patient_name_snapshot=patient.full_name,
            modality=modality,
            body_part=body_part,
            study_title=study_title,
            source_page=source_page,
            request_id=request_id_int,
            technician_notes=technician_notes,
            doctor_notes=doctor_notes,
            ai_model_key=ai_model_key,
            ai_result=ai_result,
            ai_confidence=ai_confidence,
            ai_findings_json=json.dumps(ai_findings),
            scan_image_data_url=scan_image_data_url,
            scan_file_path=scan_file_path,
            status=status,
            recorded_by_staff_id=_get_current_staff_id(db, current_user),
            updated_at=now_iso,
        )
    )
    imaging_record_id = result.inserted_primary_key[0] if result.inserted_primary_key else None

    if add_to_patient_record and ai_result and models.TABLES.get("ai_diagnoses") is not None:
        db.execute(
            insert(models.TABLES["ai_diagnoses"]).values(
                hospital_id=hospital_id,
                patient_id=patient_id,
                doctor_id=_infer_patient_doctor_id(db, hospital_id, patient_id),
                disease_category=f"IMAGING_{modality}_{body_part}",
                prediction_result=str(ai_result),
                confidence_score=str(ai_confidence or "N/A"),
                scan_file_path=f"imaging_record:{imaging_record_id}",
                model_version=(ai_model_key or "imaging-ai-v1"),
            )
        )

    db.commit()

    row = db.execute(
        select(records)
        .where(records.c.hospital_id == hospital_id)
        .where(records.c.imaging_record_id == imaging_record_id)
    ).first()
    item = _serialize_row(row) if row else {}
    try:
        item["ai_findings_json"] = json.loads(item.get("ai_findings_json") or "{}")
    except Exception:
        item["ai_findings_json"] = {}

    return {"status": "saved", "record": item}


@app.get("/radiology/imaging-records")
def list_imaging_records(
    imaging_record_id: Optional[int] = Query(default=None, ge=1),
    patient_id: Optional[int] = Query(default=None, ge=1),
    patient_mrn: Optional[str] = Query(default=None),
    modality: Optional[str] = Query(default=None),
    body_part: Optional[str] = Query(default=None),
    request_id: Optional[int] = Query(default=None, ge=1),
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_roles(current_user, {"LAB", "DOCTOR", "RADIOLOGIST", "ADMIN", "SUPER_ADMIN"})
    _ensure_imaging_records_table(db)

    hospital_id = current_user["hospital_id"]
    records = models.TABLES["imaging_records"]
    query = select(records).where(records.c.hospital_id == hospital_id)

    if imaging_record_id is not None:
        query = query.where(records.c.imaging_record_id == int(imaging_record_id))
    if patient_id is not None:
        query = query.where(records.c.patient_id == int(patient_id))
    if patient_mrn and _table_has_column(records, "patient_mrn_snapshot"):
        query = query.where(
            func.lower(records.c.patient_mrn_snapshot) == str(patient_mrn).strip().lower()
        )
    if request_id is not None:
        query = query.where(records.c.request_id == int(request_id))
    if modality:
        query = query.where(records.c.modality == _normalize_radiology_modality(modality))
    if body_part:
        query = query.where(records.c.body_part == _normalize_body_part(body_part))
    if status:
        query = query.where(records.c.status == str(status).strip().upper())

    rows = db.execute(query.order_by(records.c.imaging_record_id.desc()).limit(limit)).fetchall()
    items: List[Dict[str, Any]] = []
    for r in rows:
        item = _serialize_row(r)
        try:
            item["ai_findings_json"] = json.loads(item.get("ai_findings_json") or "{}")
        except Exception:
            item["ai_findings_json"] = {}
        items.append(item)

    return {"count": len(items), "items": items}


@app.get("/radiology/imaging-records/{imaging_record_id}")
def get_imaging_record(
    imaging_record_id: int,
    patient_mrn: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_roles(current_user, {"LAB", "DOCTOR", "RADIOLOGIST", "ADMIN", "SUPER_ADMIN"})
    _ensure_imaging_records_table(db)

    hospital_id = current_user["hospital_id"]
    records = models.TABLES["imaging_records"]
    row = db.execute(
        select(records)
        .where(records.c.hospital_id == hospital_id)
        .where(records.c.imaging_record_id == imaging_record_id)
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Imaging record not found")
    if patient_mrn and _table_has_column(records, "patient_mrn_snapshot"):
        snapshot_mrn = str(getattr(row, "patient_mrn_snapshot", "") or "").strip().lower()
        requested_mrn = str(patient_mrn).strip().lower()
        if snapshot_mrn and snapshot_mrn != requested_mrn:
            # Allow record lookup by ID even if patient MRN has been corrected later.
            pass

    item = _serialize_row(row)
    try:
        item["ai_findings_json"] = json.loads(item.get("ai_findings_json") or "{}")
    except Exception:
        item["ai_findings_json"] = {}

    settings = models.TABLES.get("hospital_settings")
    hospital_profile = None
    if settings is not None:
        hospital_profile = db.execute(select(settings).where(settings.c.hospital_id == hospital_id)).first()

    return {
        "record": item,
        "hospital": _serialize_row(hospital_profile) if hospital_profile else None,
    }


@app.post("/radiology/imaging-records/{imaging_record_id}/finalize")
def finalize_imaging_record(
    imaging_record_id: int,
    payload: Dict[str, Any] = Body(default={}),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_roles(current_user, {"DOCTOR", "RADIOLOGIST", "ADMIN", "SUPER_ADMIN"})
    _ensure_imaging_records_table(db)

    hospital_id = current_user["hospital_id"]
    records = models.TABLES["imaging_records"]
    row = db.execute(
        select(records)
        .where(records.c.hospital_id == hospital_id)
        .where(records.c.imaging_record_id == imaging_record_id)
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Imaging record not found")

    signature_name = (payload.get("radiologist_signature_name") or payload.get("doctor_signature_name") or "").strip()
    if not signature_name:
        signature_name = str(current_user.get("email") or "").strip()
    if not signature_name:
        raise HTTPException(status_code=400, detail="radiologist_signature_name is required")

    final_impression = (payload.get("manual_impression") or payload.get("final_impression") or "").strip()
    next_status = (payload.get("status") or "FINALIZED").strip().upper()
    if next_status not in {"FINALIZED", "COMPLETED"}:
        next_status = "FINALIZED"

    existing_notes = (row.doctor_notes or "").strip()
    merged_notes = existing_notes
    if final_impression:
        merged_notes = f"{existing_notes}\n\nFinal Impression: {final_impression}".strip() if existing_notes else final_impression

    now_iso = datetime.utcnow().isoformat()
    db.execute(
        update(records)
        .where(records.c.hospital_id == hospital_id)
        .where(records.c.imaging_record_id == imaging_record_id)
        .values(
            doctor_notes=merged_notes or None,
            doctor_signature_name=signature_name,
            doctor_signature_at=now_iso,
            status=next_status,
            updated_at=now_iso,
        )
    )
    db.commit()

    updated_row = db.execute(
        select(records)
        .where(records.c.hospital_id == hospital_id)
        .where(records.c.imaging_record_id == imaging_record_id)
    ).first()
    item = _serialize_row(updated_row) if updated_row else {}
    try:
        item["ai_findings_json"] = json.loads(item.get("ai_findings_json") or "{}")
    except Exception:
        item["ai_findings_json"] = {}

    return {"status": "finalized", "record": item}


@app.post("/reports/share")
def share_report_to_portals(
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_roles(current_user, {"DOCTOR", "LAB", "RADIOLOGIST", "ADMIN", "SUPER_ADMIN"})
    _ensure_shared_reports_table(db)

    hospital_id = current_user["hospital_id"]
    report_type = str(payload.get("report_type") or "").strip().upper()
    source_record_id = int(payload.get("source_record_id") or 0)
    share_to_patient = 1 if bool(payload.get("share_to_patient", True)) else 0
    share_to_doctor = 1 if bool(payload.get("share_to_doctor", True)) else 0
    share_notes = (payload.get("share_notes") or "").strip() or None

    if source_record_id <= 0:
        raise HTTPException(status_code=400, detail="source_record_id is required")
    if report_type not in {REPORT_TYPE_LAB_RECORD, REPORT_TYPE_IMAGING_RECORD}:
        raise HTTPException(status_code=400, detail="report_type must be LAB_RECORD or IMAGING_RECORD")
    if not share_to_patient and not share_to_doctor:
        raise HTTPException(status_code=400, detail="At least one target must be selected")

    patient_id = _extract_patient_id_for_report_source(db, hospital_id, report_type, source_record_id)
    shared = models.TABLES["shared_reports"]
    existing = db.execute(
        select(shared)
        .where(shared.c.hospital_id == hospital_id)
        .where(shared.c.report_type == report_type)
        .where(shared.c.source_record_id == source_record_id)
    ).first()

    now_iso = datetime.utcnow().isoformat()
    staff_id = _get_current_staff_id(db, current_user)
    if existing:
        next_share_to_patient = 1 if int(existing.shared_to_patient or 0) or share_to_patient else 0
        next_share_to_doctor = 1 if int(existing.shared_to_doctor or 0) or share_to_doctor else 0
        db.execute(
            update(shared)
            .where(shared.c.shared_report_id == existing.shared_report_id)
            .values(
                shared_to_patient=next_share_to_patient,
                shared_to_doctor=next_share_to_doctor,
                share_notes=share_notes or existing.share_notes,
                shared_by_staff_id=staff_id,
                updated_at=now_iso,
            )
        )
        shared_report_id = int(existing.shared_report_id)
    else:
        result = db.execute(
            insert(shared).values(
                hospital_id=hospital_id,
                patient_id=patient_id,
                report_type=report_type,
                source_record_id=source_record_id,
                shared_to_patient=share_to_patient,
                shared_to_doctor=share_to_doctor,
                share_notes=share_notes,
                shared_by_staff_id=staff_id,
                updated_at=now_iso,
            )
        )
        shared_report_id = result.inserted_primary_key[0] if result.inserted_primary_key else None

    db.commit()

    row = db.execute(
        select(shared)
        .where(shared.c.hospital_id == hospital_id)
        .where(shared.c.shared_report_id == shared_report_id)
    ).first()
    if not row:
        raise HTTPException(status_code=500, detail="Failed to save shared report")

    return {"status": "shared", "item": _build_shared_report_payload(db, row)}


@app.get("/reports/shared")
def list_shared_reports(
    patient_id: Optional[int] = Query(default=None, ge=1),
    audience: str = Query(default="ALL"),
    report_type: Optional[str] = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_roles(current_user, {"PATIENT", "DOCTOR", "NURSE", "LAB", "RADIOLOGIST", "ADMIN", "SUPER_ADMIN"})
    _ensure_shared_reports_table(db)

    hospital_id = current_user["hospital_id"]
    role = (current_user.get("role_name") or "").upper()
    target_patient_id = patient_id
    audience_norm = (audience or "ALL").strip().upper()
    if audience_norm not in {"ALL", "PATIENT", "DOCTOR"}:
        audience_norm = "ALL"

    if role == "PATIENT":
        target_patient_id = _resolve_portal_patient_id(db, hospital_id, int(current_user["user_id"]))
        audience_norm = "PATIENT"

    shared = models.TABLES["shared_reports"]
    query = select(shared).where(shared.c.hospital_id == hospital_id)
    if target_patient_id is not None:
        query = query.where(shared.c.patient_id == int(target_patient_id))
    if audience_norm == "PATIENT":
        query = query.where(shared.c.shared_to_patient == 1)
    elif audience_norm == "DOCTOR":
        query = query.where(shared.c.shared_to_doctor == 1)
    if report_type:
        query = query.where(shared.c.report_type == str(report_type).strip().upper())

    rows = db.execute(query.order_by(shared.c.created_at.desc()).limit(limit)).fetchall()
    items = [_build_shared_report_payload(db, r) for r in rows]
    return {"count": len(items), "items": items}


@app.get("/patient/my-reports")
def patient_my_reports(
    patient_id: Optional[int] = Query(default=None, ge=1),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_roles(current_user, {"PATIENT", "ADMIN", "SUPER_ADMIN", "DOCTOR", "NURSE", "LAB"})

    hospital_id = current_user["hospital_id"]
    diagnoses = models.TABLES["ai_diagnoses"]
    patients = models.TABLES["patients"]

    if (current_user.get("role_name") or "").upper() == "PATIENT":
        portal = models.TABLES["patient_portal_accounts"]
        link = db.execute(
            select(portal.c.patient_id)
            .where(portal.c.hospital_id == hospital_id)
            .where(portal.c.user_id == current_user["user_id"])
        ).first()
        if not link:
            raise HTTPException(status_code=404, detail="No patient profile linked to this account")
        target_patient_id = int(link.patient_id)
        where_filters = [diagnoses.c.hospital_id == hospital_id, diagnoses.c.patient_id == target_patient_id]
    else:
        where_filters = [diagnoses.c.hospital_id == hospital_id]
        if patient_id is not None:
            where_filters.append(diagnoses.c.patient_id == int(patient_id))

    query = (
        select(
            diagnoses,
            patients.c.full_name.label("patient_name"),
            patients.c.patient_mrn.label("patient_mrn"),
        )
        .select_from(
            diagnoses.join(
                patients,
                (diagnoses.c.hospital_id == patients.c.hospital_id)
                & (diagnoses.c.patient_id == patients.c.patient_id),
            )
        )
    )

    for cond in where_filters:
        query = query.where(cond)

    rows = db.execute(query.order_by(diagnoses.c.created_at.desc()).limit(limit)).fetchall()
    return {"count": len(rows), "items": [_serialize_row(r) for r in rows]}
@app.post("/doctor/medications")
def doctor_create_medication(
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_roles(current_user, {"DOCTOR", "ADMIN", "SUPER_ADMIN"})

    hospital_id = current_user["hospital_id"]
    patient_id = payload.get("patient_id")
    medication_name = (payload.get("medication_name") or "").strip()

    if not patient_id or not medication_name:
        raise HTTPException(status_code=400, detail="patient_id and medication_name are required")

    patients_table = models.TABLES["patients"]
    meds_table = models.TABLES["doctor_medications"]

    patient = db.execute(
        select(patients_table.c.patient_id)
        .where(patients_table.c.hospital_id == hospital_id)
        .where(patients_table.c.patient_id == int(patient_id))
    ).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found for this hospital")

    doctor_id = _get_current_staff_id(db, current_user)
    result = db.execute(
        insert(meds_table).values(
            hospital_id=hospital_id,
            patient_id=int(patient_id),
            doctor_id=doctor_id,
            medication_name=medication_name,
            dosage=(payload.get("dosage") or None),
            frequency=(payload.get("frequency") or None),
            duration_days=payload.get("duration_days"),
            instructions=(payload.get("instructions") or None),
            pharmacy_status="PENDING",
        )
    )
    db.commit()

    medication_order_id = result.inserted_primary_key[0] if result.inserted_primary_key else None
    row = db.execute(
        select(meds_table)
        .where(meds_table.c.hospital_id == hospital_id)
        .where(meds_table.c.medication_order_id == medication_order_id)
    ).first()
    return {"status": "created", "item": _serialize_row(row)}


@app.post("/doctor/clinical-updates")
def doctor_create_clinical_update(
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_roles(current_user, {"DOCTOR", "ADMIN", "SUPER_ADMIN"})

    hospital_id = current_user["hospital_id"]
    patient_id = payload.get("patient_id")
    update_type = (payload.get("update_type") or "").strip().upper()
    title = (payload.get("title") or "").strip()

    if not patient_id or not update_type or not title:
        raise HTTPException(status_code=400, detail="patient_id, update_type, and title are required")
    if update_type not in {"DIAGNOSIS", "PROCEDURE"}:
        raise HTTPException(status_code=400, detail="update_type must be DIAGNOSIS or PROCEDURE")

    patients_table = models.TABLES["patients"]
    updates_table = models.TABLES["doctor_clinical_updates"]

    patient = db.execute(
        select(patients_table.c.patient_id)
        .where(patients_table.c.hospital_id == hospital_id)
        .where(patients_table.c.patient_id == int(patient_id))
    ).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found for this hospital")

    doctor_id = _get_current_staff_id(db, current_user)
    result = db.execute(
        insert(updates_table).values(
            hospital_id=hospital_id,
            patient_id=int(patient_id),
            doctor_id=doctor_id,
            update_type=update_type,
            title=title,
            details=(payload.get("details") or None),
        )
    )
    db.commit()

    update_id = result.inserted_primary_key[0] if result.inserted_primary_key else None
    row = db.execute(
        select(updates_table)
        .where(updates_table.c.hospital_id == hospital_id)
        .where(updates_table.c.update_id == update_id)
    ).first()
    return {"status": "created", "item": _serialize_row(row)}


def _ensure_medicine_inventory_table(db: Session) -> None:
    if models.TABLES.get("medicine_inventory") is None:
        db.execute(
            text(
                """
            CREATE TABLE IF NOT EXISTS medicine_inventory (
                inventory_id INTEGER PRIMARY KEY,
                hospital_id INTEGER NOT NULL,
                medicine_name TEXT NOT NULL,
                generic_name TEXT,
                batch_number TEXT NOT NULL,
                expiry_date TEXT,
                manufacturer TEXT,
                unit_price REAL NOT NULL DEFAULT 0,
                quantity_available INTEGER NOT NULL DEFAULT 0,
                minimum_threshold INTEGER NOT NULL DEFAULT 50,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_by_staff_id INTEGER,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (hospital_id, inventory_id),
                UNIQUE (hospital_id, batch_number)
            )
            """
            )
        )
        db.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_medicine_inventory_hospital_name ON medicine_inventory(hospital_id, medicine_name, is_active)"
            )
        )
        db.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_medicine_inventory_hospital_threshold ON medicine_inventory(hospital_id, quantity_available, minimum_threshold)"
            )
        )
        db.commit()
        models.load_tables()


def _ensure_doctor_medication_dispense_columns(db: Session) -> None:
    if models.TABLES.get("doctor_medications") is None:
        return
    rows = db.execute(text("PRAGMA table_info(doctor_medications)")).fetchall()
    existing_cols = {str(r[1]) for r in rows}
    desired_cols = {
        "dispensed_quantity": "INTEGER",
        "dispensed_at": "TEXT",
        "dispensed_by_staff_id": "INTEGER",
        "dispense_notes": "TEXT",
        "dispense_invoice_id": "INTEGER",
    }
    added = False
    for col, sql_type in desired_cols.items():
        if col in existing_cols:
            continue
        db.execute(text(f"ALTER TABLE doctor_medications ADD COLUMN {col} {sql_type}"))
        added = True
    if added:
        db.commit()
        models.load_tables()


def _ensure_prescription_item_dispense_columns(db: Session) -> None:
    if models.TABLES.get("prescription_items") is None:
        return
    rows = db.execute(text("PRAGMA table_info(prescription_items)")).fetchall()
    existing_cols = {str(r[1]) for r in rows}
    desired_cols = {
        "dispense_status": "TEXT NOT NULL DEFAULT 'PENDING'",
        "dispensed_quantity": "INTEGER",
        "dispensed_at": "TEXT",
        "dispensed_by_staff_id": "INTEGER",
        "dispense_notes": "TEXT",
    }
    added = False
    for col, sql_type in desired_cols.items():
        if col in existing_cols:
            continue
        db.execute(text(f"ALTER TABLE prescription_items ADD COLUMN {col} {sql_type}"))
        added = True
    if added:
        db.commit()
        models.load_tables()


def _ensure_pharmacy_support_tables(db: Session) -> None:
    _ensure_medicine_inventory_table(db)
    _ensure_doctor_medication_dispense_columns(db)
    _ensure_prescription_item_dispense_columns(db)


def _pharmacy_can_edit_prices(current_user: Dict[str, Any]) -> bool:
    role = str(current_user.get("role_name") or "").upper()
    return role in {"PHARMACY", "ADMIN", "SUPER_ADMIN"}


def _inventory_stock_map(db: Session, hospital_id: int, medicine_names: List[str]) -> Dict[str, Dict[str, Any]]:
    if not medicine_names:
        return {}
    _ensure_pharmacy_support_tables(db)
    inventory = models.TABLES["medicine_inventory"]
    keys = sorted({str(n).strip().lower() for n in medicine_names if str(n or "").strip()})
    if not keys:
        return {}
    today_iso = date.today().isoformat()
    rows = db.execute(
        select(
            func.lower(inventory.c.medicine_name).label("medicine_key"),
            func.sum(inventory.c.quantity_available).label("quantity_total"),
            func.min(inventory.c.unit_price).label("min_unit_price"),
        )
        .where(inventory.c.hospital_id == int(hospital_id))
        .where(func.lower(inventory.c.medicine_name).in_(keys))
        .where(inventory.c.is_active == 1)
        .where(inventory.c.quantity_available > 0)
        .where(
            (inventory.c.expiry_date.is_(None))
            | (inventory.c.expiry_date == "")
            | (inventory.c.expiry_date >= today_iso)
        )
        .group_by(func.lower(inventory.c.medicine_name))
    ).fetchall()
    return {
        str(r.medicine_key): {
            "available_quantity": int(r.quantity_total or 0),
            "unit_price": float(r.min_unit_price or 0),
        }
        for r in rows
    }


def _sync_inventory_row_to_legacy_tables(
    db: Session,
    hospital_id: int,
    medicine_name: str,
    batch_number: str,
    unit_price: float,
    quantity_available: int,
    expiry_date: Optional[str],
) -> Dict[str, Optional[int]]:
    if models.TABLES.get("medicines") is None or models.TABLES.get("medicine_batches") is None:
        return {"medicine_id": None, "batch_id": None}

    medicines = models.TABLES["medicines"]
    batches = models.TABLES["medicine_batches"]

    med = db.execute(
        select(medicines)
        .where(medicines.c.hospital_id == int(hospital_id))
        .where(func.lower(medicines.c.medicine_name) == str(medicine_name).strip().lower())
    ).first()
    if not med:
        med_result = db.execute(
            insert(medicines).values(
                hospital_id=int(hospital_id),
                medicine_name=str(medicine_name).strip(),
                unit_price=float(unit_price or 0),
                is_active=1,
            )
        )
        medicine_id = med_result.inserted_primary_key[0] if med_result.inserted_primary_key else None
    else:
        medicine_id = med.medicine_id
        db.execute(
            update(medicines)
            .where(medicines.c.hospital_id == int(hospital_id))
            .where(medicines.c.medicine_id == int(medicine_id))
            .values(
                medicine_name=str(medicine_name).strip(),
                unit_price=float(unit_price or 0),
                is_active=1,
            )
        )

    if medicine_id is None:
        return {"medicine_id": None, "batch_id": None}

    batch = db.execute(
        select(batches)
        .where(batches.c.hospital_id == int(hospital_id))
        .where(batches.c.batch_number == str(batch_number).strip())
    ).first()

    if batch:
        batch_id = batch.batch_id
        db.execute(
            update(batches)
            .where(batches.c.hospital_id == int(hospital_id))
            .where(batches.c.batch_id == int(batch_id))
            .values(
                medicine_id=int(medicine_id),
                quantity_available=int(quantity_available or 0),
                expiry_date=(str(expiry_date).strip() if expiry_date else None),
            )
        )
    else:
        batch_result = db.execute(
            insert(batches).values(
                hospital_id=int(hospital_id),
                medicine_id=int(medicine_id),
                batch_number=str(batch_number).strip(),
                quantity_available=int(quantity_available or 0),
                expiry_date=(str(expiry_date).strip() if expiry_date else None),
            )
        )
        batch_id = batch_result.inserted_primary_key[0] if batch_result.inserted_primary_key else None

    return {"medicine_id": int(medicine_id), "batch_id": int(batch_id) if batch_id else None}


@app.get("/pharmacy/patient-search")
def pharmacy_patient_search(
    q: str = Query(default=""),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_roles(current_user, {"PHARMACY", "ADMIN", "SUPER_ADMIN"})

    patients = models.TABLES["patients"]
    hospital_id = current_user["hospital_id"]
    query = select(patients).where(patients.c.hospital_id == hospital_id)
    if q.strip():
        term = f"%{q.strip()}%"
        query = query.where(
            (patients.c.patient_mrn.like(term))
            | (patients.c.full_name.like(term))
            | (patients.c.phone_number.like(term))
        )
    patient_recent_order = _recent_order_expr(patients, "created_at", "patient_id")
    if patient_recent_order is not None:
        query = query.order_by(patient_recent_order)
    rows = db.execute(query.limit(limit)).fetchall()
    return {"count": len(rows), "items": [_serialize_row(r) for r in rows]}


@app.get("/pharmacy/prescriptions")
def pharmacy_prescriptions_by_mrn(
    patient_mrn: str = Query(...),
    include_dispensed: int = Query(default=0, ge=0, le=1),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_roles(current_user, {"PHARMACY", "ADMIN", "SUPER_ADMIN"})
    _ensure_pharmacy_support_tables(db)

    hospital_id = current_user["hospital_id"]
    patients = models.TABLES["patients"]
    patient = db.execute(
        select(patients)
        .where(patients.c.hospital_id == hospital_id)
        .where(func.lower(patients.c.patient_mrn) == str(patient_mrn).strip().lower())
    ).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found for this MRN")

    patient_id = int(patient.patient_id)
    items: List[Dict[str, Any]] = []

    meds_table = models.TABLES["doctor_medications"]
    meds_query = (
        select(meds_table)
        .where(meds_table.c.hospital_id == hospital_id)
        .where(meds_table.c.patient_id == patient_id)
        .order_by(meds_table.c.created_at.desc())
    )
    if not include_dispensed:
        meds_query = meds_query.where(meds_table.c.pharmacy_status != "DISPENSED")
    med_rows = db.execute(meds_query).fetchall()
    for row in med_rows:
        status = (row.pharmacy_status or "PENDING").upper()
        items.append(
            {
                "source": "DOCTOR_MEDICATION",
                "source_id": int(row.medication_order_id),
                "patient_id": patient_id,
                "medication_name": row.medication_name,
                "dosage": row.dosage,
                "frequency": row.frequency,
                "duration_days": row.duration_days,
                "instructions": row.instructions,
                "status": status,
                "created_at": row.created_at,
                "recommended_quantity": int(row.dispensed_quantity or 1) if status == "DISPENSED" else 1,
            }
        )

    has_prescriptions = (
        models.TABLES.get("prescriptions") is not None
        and models.TABLES.get("prescription_items") is not None
        and models.TABLES.get("appointments") is not None
    )
    if has_prescriptions:
        pres = models.TABLES["prescriptions"]
        items_table = models.TABLES["prescription_items"]
        appointments = models.TABLES["appointments"]

        pres_query = (
            select(
                items_table,
                pres.c.issued_at.label("prescription_issued_at"),
                pres.c.prescription_id.label("prescription_id"),
            )
            .select_from(
                items_table.join(
                    pres,
                    (items_table.c.hospital_id == pres.c.hospital_id)
                    & (items_table.c.prescription_id == pres.c.prescription_id),
                ).join(
                    appointments,
                    (pres.c.hospital_id == appointments.c.hospital_id)
                    & (pres.c.appointment_id == appointments.c.appointment_id),
                )
            )
            .where(items_table.c.hospital_id == hospital_id)
            .where(appointments.c.patient_id == patient_id)
            .order_by(pres.c.issued_at.desc())
        )
        if _table_has_column(items_table, "dispense_status") and not include_dispensed:
            pres_query = pres_query.where(func.upper(items_table.c.dispense_status) != "DISPENSED")

        pres_rows = db.execute(pres_query).fetchall()
        for row in pres_rows:
            status = "PENDING"
            if _table_has_column(items_table, "dispense_status"):
                status = str(row.dispense_status or "PENDING").upper()
            items.append(
                {
                    "source": "PRESCRIPTION_ITEM",
                    "source_id": int(row.prescription_item_id),
                    "prescription_id": int(row.prescription_id),
                    "patient_id": patient_id,
                    "medication_name": row.medicine_name,
                    "dosage": row.dosage,
                    "frequency": None,
                    "duration_days": row.duration_days,
                    "instructions": row.instructions,
                    "status": status,
                    "created_at": row.prescription_issued_at,
                    "recommended_quantity": int(row.dispensed_quantity or 1)
                    if status == "DISPENSED" and _table_has_column(items_table, "dispensed_quantity")
                    else 1,
                }
            )

    stock_map = _inventory_stock_map(db, hospital_id, [i["medication_name"] for i in items])
    for item in items:
        key = str(item.get("medication_name") or "").strip().lower()
        stock = stock_map.get(key, {"available_quantity": 0, "unit_price": 0})
        requested_qty = int(item.get("recommended_quantity") or 1)
        item["available_quantity"] = int(stock["available_quantity"])
        item["unit_price"] = float(stock["unit_price"])
        item["in_stock"] = bool(item["available_quantity"] >= requested_qty and requested_qty > 0)
        item["estimated_total"] = float(requested_qty * item["unit_price"])

    return {
        "patient": _serialize_row(patient),
        "count": len(items),
        "items": items,
    }


@app.get("/pharmacy/inventory")
def pharmacy_inventory_list(
    q: str = Query(default=""),
    include_inactive: int = Query(default=0, ge=0, le=1),
    limit: int = Query(default=400, ge=1, le=2000),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_roles(current_user, {"PHARMACY", "ADMIN", "SUPER_ADMIN"})
    _ensure_pharmacy_support_tables(db)

    inventory = models.TABLES["medicine_inventory"]
    hospital_id = current_user["hospital_id"]
    today_iso = date.today().isoformat()

    query = select(inventory).where(inventory.c.hospital_id == hospital_id)
    if not include_inactive:
        query = query.where(inventory.c.is_active == 1)
    if q.strip():
        term = f"%{q.strip()}%"
        query = query.where(
            (inventory.c.medicine_name.like(term))
            | (inventory.c.generic_name.like(term))
            | (inventory.c.batch_number.like(term))
            | (inventory.c.manufacturer.like(term))
        )

    rows = db.execute(query.order_by(inventory.c.medicine_name.asc(), inventory.c.expiry_date.asc()).limit(limit)).fetchall()
    items = []
    for row in rows:
        payload = _serialize_row(row)
        qty = int(payload.get("quantity_available") or 0)
        threshold = int(payload.get("minimum_threshold") or 0)
        exp = str(payload.get("expiry_date") or "").strip()
        payload["is_low_stock"] = bool(qty <= threshold)
        payload["is_expired"] = bool(exp and exp < today_iso)
        items.append(payload)
    return {"count": len(items), "items": items}


@app.get("/pharmacy/inventory/alerts")
def pharmacy_inventory_alerts(
    threshold: int = Query(default=50, ge=0, le=100000),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_roles(current_user, {"PHARMACY", "ADMIN", "SUPER_ADMIN"})
    _ensure_pharmacy_support_tables(db)

    inventory = models.TABLES["medicine_inventory"]
    hospital_id = current_user["hospital_id"]
    today_iso = date.today().isoformat()

    rows = db.execute(
        select(inventory)
        .where(inventory.c.hospital_id == hospital_id)
        .where(inventory.c.is_active == 1)
        .where(inventory.c.quantity_available <= threshold)
        .where((inventory.c.expiry_date.is_(None)) | (inventory.c.expiry_date == "") | (inventory.c.expiry_date >= today_iso))
        .order_by(inventory.c.quantity_available.asc(), inventory.c.medicine_name.asc())
    ).fetchall()
    return {"count": len(rows), "items": [_serialize_row(r) for r in rows]}


@app.post("/pharmacy/inventory")
def pharmacy_inventory_create(
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_roles(current_user, {"PHARMACY", "ADMIN", "SUPER_ADMIN"})
    _ensure_pharmacy_support_tables(db)

    inventory = models.TABLES["medicine_inventory"]
    hospital_id = current_user["hospital_id"]

    medicine_name = str(payload.get("medicine_name") or "").strip()
    batch_number = str(payload.get("batch_number") or "").strip()
    if not medicine_name or not batch_number:
        raise HTTPException(status_code=400, detail="medicine_name and batch_number are required")

    try:
        quantity_available = int(payload.get("quantity_available") or 0)
        minimum_threshold = int(payload.get("minimum_threshold") or 50)
        unit_price = float(payload.get("unit_price") or 0)
    except Exception:
        raise HTTPException(status_code=400, detail="quantity_available, minimum_threshold and unit_price must be numeric")

    if quantity_available < 0 or minimum_threshold < 0 or unit_price < 0:
        raise HTTPException(status_code=400, detail="Numeric values cannot be negative")

    expiry_date = (payload.get("expiry_date") or None)
    if expiry_date:
        expiry_date = str(expiry_date).strip()
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", expiry_date):
            raise HTTPException(status_code=400, detail="expiry_date must be YYYY-MM-DD")

    existing_batch = db.execute(
        select(inventory.c.inventory_id)
        .where(inventory.c.hospital_id == hospital_id)
        .where(inventory.c.batch_number == batch_number)
    ).first()
    if existing_batch:
        raise HTTPException(status_code=400, detail="Batch number already exists in inventory")

    staff_id = _get_current_staff_id(db, current_user)
    result = db.execute(
        insert(inventory).values(
            hospital_id=hospital_id,
            medicine_name=medicine_name,
            generic_name=(payload.get("generic_name") or None),
            batch_number=batch_number,
            expiry_date=expiry_date,
            manufacturer=(payload.get("manufacturer") or None),
            unit_price=unit_price,
            quantity_available=quantity_available,
            minimum_threshold=minimum_threshold,
            is_active=1,
            created_by_staff_id=staff_id,
        )
    )
    inventory_id = result.inserted_primary_key[0] if result.inserted_primary_key else None
    _sync_inventory_row_to_legacy_tables(
        db,
        hospital_id=hospital_id,
        medicine_name=medicine_name,
        batch_number=batch_number,
        unit_price=unit_price,
        quantity_available=quantity_available,
        expiry_date=expiry_date,
    )
    db.commit()

    row = db.execute(
        select(inventory)
        .where(inventory.c.hospital_id == hospital_id)
        .where(inventory.c.inventory_id == inventory_id)
    ).first()
    return {"status": "created", "item": _serialize_row(row)}


@app.put("/pharmacy/inventory/{inventory_id}")
def pharmacy_inventory_update(
    inventory_id: int,
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_roles(current_user, {"PHARMACY", "ADMIN", "SUPER_ADMIN"})
    _ensure_pharmacy_support_tables(db)

    inventory = models.TABLES["medicine_inventory"]
    hospital_id = current_user["hospital_id"]

    row = db.execute(
        select(inventory)
        .where(inventory.c.hospital_id == hospital_id)
        .where(inventory.c.inventory_id == int(inventory_id))
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Inventory item not found")

    updates: Dict[str, Any] = {}

    if "medicine_name" in payload:
        name = str(payload.get("medicine_name") or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="medicine_name cannot be empty")
        updates["medicine_name"] = name

    if "generic_name" in payload:
        updates["generic_name"] = (payload.get("generic_name") or None)

    if "manufacturer" in payload:
        updates["manufacturer"] = (payload.get("manufacturer") or None)

    if "batch_number" in payload:
        batch_number = str(payload.get("batch_number") or "").strip()
        if not batch_number:
            raise HTTPException(status_code=400, detail="batch_number cannot be empty")
        dup = db.execute(
            select(inventory.c.inventory_id)
            .where(inventory.c.hospital_id == hospital_id)
            .where(inventory.c.batch_number == batch_number)
            .where(inventory.c.inventory_id != int(inventory_id))
        ).first()
        if dup:
            raise HTTPException(status_code=400, detail="batch_number already exists")
        updates["batch_number"] = batch_number

    if "expiry_date" in payload:
        expiry_date = payload.get("expiry_date")
        if expiry_date in [None, ""]:
            updates["expiry_date"] = None
        else:
            expiry_text = str(expiry_date).strip()
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", expiry_text):
                raise HTTPException(status_code=400, detail="expiry_date must be YYYY-MM-DD")
            updates["expiry_date"] = expiry_text

    if "quantity_available" in payload:
        try:
            qty = int(payload.get("quantity_available"))
        except Exception:
            raise HTTPException(status_code=400, detail="quantity_available must be numeric")
        if qty < 0:
            raise HTTPException(status_code=400, detail="quantity_available cannot be negative")
        updates["quantity_available"] = qty

    if "minimum_threshold" in payload:
        try:
            threshold = int(payload.get("minimum_threshold"))
        except Exception:
            raise HTTPException(status_code=400, detail="minimum_threshold must be numeric")
        if threshold < 0:
            raise HTTPException(status_code=400, detail="minimum_threshold cannot be negative")
        updates["minimum_threshold"] = threshold

    if "unit_price" in payload:
        if not _pharmacy_can_edit_prices(current_user):
            raise HTTPException(status_code=403, detail="Only Pharmacist/Admin can edit medicine prices")
        try:
            price = float(payload.get("unit_price"))
        except Exception:
            raise HTTPException(status_code=400, detail="unit_price must be numeric")
        if price < 0:
            raise HTTPException(status_code=400, detail="unit_price cannot be negative")
        updates["unit_price"] = price

    if "is_active" in payload:
        updates["is_active"] = 1 if int(payload.get("is_active") or 0) == 1 else 0

    if not updates:
        raise HTTPException(status_code=400, detail="No valid fields provided for update")

    updates["updated_at"] = datetime.utcnow().isoformat()
    db.execute(
        update(inventory)
        .where(inventory.c.hospital_id == hospital_id)
        .where(inventory.c.inventory_id == int(inventory_id))
        .values(**updates)
    )

    refreshed = db.execute(
        select(inventory)
        .where(inventory.c.hospital_id == hospital_id)
        .where(inventory.c.inventory_id == int(inventory_id))
    ).first()

    _sync_inventory_row_to_legacy_tables(
        db,
        hospital_id=hospital_id,
        medicine_name=str(refreshed.medicine_name),
        batch_number=str(refreshed.batch_number),
        unit_price=float(refreshed.unit_price or 0),
        quantity_available=int(refreshed.quantity_available or 0),
        expiry_date=(str(refreshed.expiry_date).strip() if refreshed.expiry_date else None),
    )
    db.commit()
    return {"status": "updated", "item": _serialize_row(refreshed)}


@app.delete("/pharmacy/inventory/expired")
def pharmacy_inventory_delete_expired(
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_roles(current_user, {"PHARMACY", "ADMIN", "SUPER_ADMIN"})
    _ensure_pharmacy_support_tables(db)
    inventory = models.TABLES["medicine_inventory"]
    hospital_id = current_user["hospital_id"]
    today_iso = date.today().isoformat()

    rows = db.execute(
        select(inventory.c.inventory_id)
        .where(inventory.c.hospital_id == hospital_id)
        .where(inventory.c.expiry_date.is_not(None))
        .where(inventory.c.expiry_date != "")
        .where(inventory.c.expiry_date < today_iso)
    ).fetchall()
    ids = [int(r.inventory_id) for r in rows]
    if ids:
        db.execute(
            delete(inventory)
            .where(inventory.c.hospital_id == hospital_id)
            .where(inventory.c.inventory_id.in_(ids))
        )
        db.commit()
    return {"status": "deleted", "deleted_count": len(ids)}


@app.delete("/pharmacy/inventory/{inventory_id}")
def pharmacy_inventory_delete(
    inventory_id: int,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_roles(current_user, {"PHARMACY", "ADMIN", "SUPER_ADMIN"})
    _ensure_pharmacy_support_tables(db)
    inventory = models.TABLES["medicine_inventory"]
    hospital_id = current_user["hospital_id"]
    exists = db.execute(
        select(inventory.c.inventory_id)
        .where(inventory.c.hospital_id == hospital_id)
        .where(inventory.c.inventory_id == int(inventory_id))
    ).first()
    if not exists:
        raise HTTPException(status_code=404, detail="Inventory item not found")
    db.execute(
        delete(inventory)
        .where(inventory.c.hospital_id == hospital_id)
        .where(inventory.c.inventory_id == int(inventory_id))
    )
    db.commit()
    return {"status": "deleted", "inventory_id": int(inventory_id)}


@app.post("/pharmacy/dispense")
def pharmacy_mark_dispensed(
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_roles(current_user, {"PHARMACY", "ADMIN", "SUPER_ADMIN"})
    _ensure_pharmacy_support_tables(db)

    hospital_id = current_user["hospital_id"]
    staff_id = _get_current_staff_id(db, current_user)
    patients = models.TABLES["patients"]
    inventory = models.TABLES["medicine_inventory"]
    meds_table = models.TABLES["doctor_medications"]

    source = str(payload.get("source") or "").strip().upper()
    source_id = payload.get("source_id")
    if not source and payload.get("medication_order_id"):
        source = "DOCTOR_MEDICATION"
        source_id = payload.get("medication_order_id")

    if source not in {"DOCTOR_MEDICATION", "PRESCRIPTION_ITEM"}:
        raise HTTPException(status_code=400, detail="source must be DOCTOR_MEDICATION or PRESCRIPTION_ITEM")
    if not source_id:
        raise HTTPException(status_code=400, detail="source_id is required")

    try:
        source_id = int(source_id)
    except Exception:
        raise HTTPException(status_code=400, detail="source_id must be integer")

    quantity = payload.get("quantity")
    if quantity in [None, ""]:
        quantity = 1
    try:
        quantity = int(quantity)
    except Exception:
        raise HTTPException(status_code=400, detail="quantity must be integer")
    if quantity <= 0:
        raise HTTPException(status_code=400, detail="quantity must be greater than 0")

    medication_name = ""
    dosage = None
    instructions = None
    patient_id = None

    if source == "DOCTOR_MEDICATION":
        med = db.execute(
            select(meds_table)
            .where(meds_table.c.hospital_id == hospital_id)
            .where(meds_table.c.medication_order_id == source_id)
        ).first()
        if not med:
            raise HTTPException(status_code=404, detail="Medication order not found")
        status = str(med.pharmacy_status or "").upper()
        if status == "DISPENSED":
            raise HTTPException(status_code=400, detail="Medication order already dispensed")
        medication_name = str(med.medication_name or "").strip()
        dosage = med.dosage
        instructions = med.instructions
        patient_id = int(med.patient_id)
    else:
        if (
            models.TABLES.get("prescription_items") is None
            or models.TABLES.get("prescriptions") is None
            or models.TABLES.get("appointments") is None
        ):
            raise HTTPException(status_code=400, detail="Prescription tables are not available")

        items_table = models.TABLES["prescription_items"]
        prescriptions = models.TABLES["prescriptions"]
        appointments = models.TABLES["appointments"]
        item = db.execute(
            select(
                items_table,
                appointments.c.patient_id.label("appointment_patient_id"),
            )
            .select_from(
                items_table.join(
                    prescriptions,
                    (items_table.c.hospital_id == prescriptions.c.hospital_id)
                    & (items_table.c.prescription_id == prescriptions.c.prescription_id),
                ).join(
                    appointments,
                    (prescriptions.c.hospital_id == appointments.c.hospital_id)
                    & (prescriptions.c.appointment_id == appointments.c.appointment_id),
                )
            )
            .where(items_table.c.hospital_id == hospital_id)
            .where(items_table.c.prescription_item_id == source_id)
        ).first()
        if not item:
            raise HTTPException(status_code=404, detail="Prescription item not found")
        if _table_has_column(items_table, "dispense_status") and str(item.dispense_status or "").upper() == "DISPENSED":
            raise HTTPException(status_code=400, detail="Prescription item already dispensed")
        medication_name = str(item.medicine_name or "").strip()
        dosage = item.dosage
        instructions = item.instructions
        patient_id = int(item.appointment_patient_id)

    patient = db.execute(
        select(patients)
        .where(patients.c.hospital_id == hospital_id)
        .where(patients.c.patient_id == patient_id)
    ).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    today_iso = date.today().isoformat()
    inv_rows = db.execute(
        select(inventory)
        .where(inventory.c.hospital_id == hospital_id)
        .where(func.lower(inventory.c.medicine_name) == medication_name.lower())
        .where(inventory.c.is_active == 1)
        .where(inventory.c.quantity_available > 0)
        .where((inventory.c.expiry_date.is_(None)) | (inventory.c.expiry_date == "") | (inventory.c.expiry_date >= today_iso))
        .order_by(case((inventory.c.expiry_date.is_(None), "9999-12-31"), else_=inventory.c.expiry_date).asc())
    ).fetchall()

    available = sum(int(r.quantity_available or 0) for r in inv_rows)
    if available < quantity:
        raise HTTPException(status_code=400, detail=f"Out of stock: required {quantity}, available {available}")

    remaining = int(quantity)
    consumed_rows: List[Dict[str, Any]] = []
    total_amount = 0.0
    for row in inv_rows:
        if remaining <= 0:
            break
        row_qty = int(row.quantity_available or 0)
        take_qty = min(remaining, row_qty)
        new_qty = row_qty - take_qty
        unit_price = float(row.unit_price or 0)
        line_total = float(take_qty * unit_price)
        total_amount += line_total
        db.execute(
            update(inventory)
            .where(inventory.c.hospital_id == hospital_id)
            .where(inventory.c.inventory_id == int(row.inventory_id))
            .values(
                quantity_available=new_qty,
                is_active=1 if new_qty > 0 else 0,
                updated_at=datetime.utcnow().isoformat(),
            )
        )
        legacy_ids = _sync_inventory_row_to_legacy_tables(
            db,
            hospital_id=hospital_id,
            medicine_name=str(row.medicine_name),
            batch_number=str(row.batch_number),
            unit_price=unit_price,
            quantity_available=new_qty,
            expiry_date=(str(row.expiry_date).strip() if row.expiry_date else None),
        )
        consumed_rows.append(
            {
                "inventory_id": int(row.inventory_id),
                "batch_number": row.batch_number,
                "quantity": int(take_qty),
                "unit_price": unit_price,
                "line_total": line_total,
                "medicine_id": legacy_ids.get("medicine_id"),
                "batch_id": legacy_ids.get("batch_id"),
            }
        )
        remaining -= take_qty

    sales = models.TABLES["pharmacy_sales"]
    sale_result = db.execute(
        insert(sales).values(
            hospital_id=hospital_id,
            patient_id=patient_id,
            sold_by_staff_id=staff_id,
            total_amount=float(total_amount),
        )
    )
    sale_id = sale_result.inserted_primary_key[0] if sale_result.inserted_primary_key else None

    invoice_id = None
    invoice_number = None
    if models.TABLES.get("invoices") is not None and models.TABLES.get("invoice_items") is not None and sale_id is not None:
        invoices = models.TABLES["invoices"]
        invoice_items = models.TABLES["invoice_items"]
        invoice_number = _next_invoice_number(db, hospital_id, prefix="INV-PHAR")
        inv_result = db.execute(
            insert(invoices).values(
                hospital_id=hospital_id,
                patient_id=patient_id,
                invoice_number=invoice_number,
                gross_amount=float(total_amount),
                discount_amount=0,
                net_amount=float(total_amount),
                status="UNPAID",
            )
        )
        invoice_id = inv_result.inserted_primary_key[0] if inv_result.inserted_primary_key else None
        db.execute(
            insert(invoice_items).values(
                hospital_id=hospital_id,
                invoice_id=invoice_id,
                item_type="PHARMACY_MEDICINE",
                reference_id=sale_id,
                description=f"{medication_name} x {quantity}",
                quantity=quantity,
                unit_price=float(total_amount / quantity) if quantity else 0,
                line_total=float(total_amount),
            )
        )

    if models.TABLES.get("pharmacy_sale_items") is not None and sale_id is not None:
        sale_items = models.TABLES["pharmacy_sale_items"]
        for row in consumed_rows:
            medicine_id = row.get("medicine_id")
            if not medicine_id:
                continue
            db.execute(
                insert(sale_items).values(
                    hospital_id=hospital_id,
                    sale_id=sale_id,
                    medicine_id=int(medicine_id),
                    batch_id=row.get("batch_id"),
                    quantity=int(row["quantity"]),
                    unit_price=float(row["unit_price"]),
                    line_total=float(row["line_total"]),
                )
            )

    if source == "DOCTOR_MEDICATION":
        update_values: Dict[str, Any] = {
            "pharmacy_status": "DISPENSED",
        }
        if _table_has_column(meds_table, "dispensed_quantity"):
            update_values["dispensed_quantity"] = int(quantity)
        if _table_has_column(meds_table, "dispensed_at"):
            update_values["dispensed_at"] = datetime.utcnow().isoformat()
        if _table_has_column(meds_table, "dispensed_by_staff_id"):
            update_values["dispensed_by_staff_id"] = staff_id
        if _table_has_column(meds_table, "dispense_notes"):
            update_values["dispense_notes"] = (payload.get("dispense_notes") or None)
        if _table_has_column(meds_table, "dispense_invoice_id") and invoice_id is not None:
            update_values["dispense_invoice_id"] = int(invoice_id)
        db.execute(
            update(meds_table)
            .where(meds_table.c.hospital_id == hospital_id)
            .where(meds_table.c.medication_order_id == source_id)
            .values(**update_values)
        )
    else:
        items_table = models.TABLES["prescription_items"]
        update_values = {}
        if _table_has_column(items_table, "dispense_status"):
            update_values["dispense_status"] = "DISPENSED"
        if _table_has_column(items_table, "dispensed_quantity"):
            update_values["dispensed_quantity"] = int(quantity)
        if _table_has_column(items_table, "dispensed_at"):
            update_values["dispensed_at"] = datetime.utcnow().isoformat()
        if _table_has_column(items_table, "dispensed_by_staff_id"):
            update_values["dispensed_by_staff_id"] = staff_id
        if _table_has_column(items_table, "dispense_notes"):
            update_values["dispense_notes"] = (payload.get("dispense_notes") or None)
        if update_values:
            db.execute(
                update(items_table)
                .where(items_table.c.hospital_id == hospital_id)
                .where(items_table.c.prescription_item_id == source_id)
                .values(**update_values)
            )

    db.commit()

    return {
        "status": "dispensed",
        "sale_id": sale_id,
        "invoice_id": invoice_id,
        "invoice_number": invoice_number,
        "patient_id": patient_id,
        "patient_mrn": patient.patient_mrn,
        "patient_name": patient.full_name,
        "source": source,
        "source_id": source_id,
        "medication_name": medication_name,
        "dosage": dosage,
        "instructions": instructions,
        "quantity": quantity,
        "total_amount": float(total_amount),
        "consumed_batches": consumed_rows,
    }


@app.get("/pharmacy/sales")
def pharmacy_sales_feed(
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_roles(current_user, {"PHARMACY", "ADMIN", "SUPER_ADMIN", "ACCOUNTANT"})
    hospital_id = current_user["hospital_id"]
    sales = models.TABLES["pharmacy_sales"]
    patients = models.TABLES["patients"]
    rows = db.execute(
        select(
            sales,
            patients.c.full_name.label("patient_name"),
            patients.c.patient_mrn.label("patient_mrn"),
        )
        .select_from(
            sales.join(
                patients,
                (sales.c.hospital_id == patients.c.hospital_id)
                & (sales.c.patient_id == patients.c.patient_id),
                isouter=True,
            )
        )
        .where(sales.c.hospital_id == hospital_id)
        .order_by(sales.c.sale_date.desc())
        .limit(limit)
    ).fetchall()
    return {"count": len(rows), "items": [_serialize_row(r) for r in rows]}


@app.get("/pharmacy/medication-queue")
def pharmacy_medication_queue(
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_roles(current_user, {"PHARMACY", "ADMIN", "SUPER_ADMIN"})
    _ensure_pharmacy_support_tables(db)

    hospital_id = current_user["hospital_id"]
    meds_table = models.TABLES["doctor_medications"]
    patients_table = models.TABLES["patients"]

    query = (
        select(
            meds_table,
            patients_table.c.full_name.label("patient_name"),
            patients_table.c.patient_mrn.label("patient_mrn"),
        )
        .select_from(
            meds_table.join(
                patients_table,
                (meds_table.c.hospital_id == patients_table.c.hospital_id)
                & (meds_table.c.patient_id == patients_table.c.patient_id),
            )
        )
        .where(meds_table.c.hospital_id == hospital_id)
        .order_by(meds_table.c.created_at.desc())
    )

    if status:
        query = query.where(meds_table.c.pharmacy_status == status.upper().strip())

    rows = db.execute(query.limit(limit).offset(offset)).fetchall()
    items = [_serialize_row(r) for r in rows]
    stock_map = _inventory_stock_map(db, hospital_id, [i.get("medication_name") for i in items])
    for item in items:
        stock = stock_map.get(str(item.get("medication_name") or "").strip().lower(), {"available_quantity": 0, "unit_price": 0})
        item["available_quantity"] = int(stock.get("available_quantity") or 0)
        item["unit_price"] = float(stock.get("unit_price") or 0)
        item["in_stock"] = bool(item["available_quantity"] > 0)
    return {"count": len(items), "items": items}


@app.get("/patient/care-feed")
def patient_care_feed(
    patient_id: int = Query(..., ge=1),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_roles(current_user, {"PATIENT", "DOCTOR", "NURSE", "ADMIN", "SUPER_ADMIN"})

    hospital_id = current_user["hospital_id"]
    patients_table = models.TABLES["patients"]
    meds_table = models.TABLES["doctor_medications"]
    updates_table = models.TABLES["doctor_clinical_updates"]

    patient = db.execute(
        select(patients_table)
        .where(patients_table.c.hospital_id == hospital_id)
        .where(patients_table.c.patient_id == patient_id)
    ).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found for this hospital")

    medications = db.execute(
        select(meds_table)
        .where(meds_table.c.hospital_id == hospital_id)
        .where(meds_table.c.patient_id == patient_id)
        .order_by(meds_table.c.created_at.desc())
    ).fetchall()

    clinical_updates = db.execute(
        select(updates_table)
        .where(updates_table.c.hospital_id == hospital_id)
        .where(updates_table.c.patient_id == patient_id)
        .order_by(updates_table.c.created_at.desc())
    ).fetchall()

    return {
        "patient": _serialize_row(patient),
        "medications": [_serialize_row(r) for r in medications],
        "clinical_updates": [_serialize_row(r) for r in clinical_updates],
    }

def _ensure_patient_vitals_extended_columns(db: Session) -> None:
    if models.TABLES.get("patient_vitals") is None:
        return
    rows = db.execute(text("PRAGMA table_info(patient_vitals)")).fetchall()
    existing_cols = {str(r[1]) for r in rows}
    desired_cols = {
        "respiratory_rate": "REAL",
        "weight_kg": "REAL",
        "bmi": "REAL",
        "chief_complaint": "TEXT",
        "observation_notes": "TEXT",
    }
    added = False
    for col, sql_type in desired_cols.items():
        if col in existing_cols:
            continue
        db.execute(text(f"ALTER TABLE patient_vitals ADD COLUMN {col} {sql_type}"))
        added = True
    if added:
        db.commit()
        models.load_tables()


def _ensure_radiology_service_catalog_table(db: Session) -> None:
    changed = False
    touched = False
    if models.TABLES.get("radiology_service_catalog") is None:
        db.execute(
            text(
                """
            CREATE TABLE IF NOT EXISTS radiology_service_catalog (
                service_id INTEGER PRIMARY KEY,
                hospital_id INTEGER NOT NULL,
                modality TEXT NOT NULL,
                scan_name TEXT NOT NULL,
                body_part TEXT NOT NULL,
                service_fee REAL NOT NULL DEFAULT 0,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (hospital_id, service_id),
                UNIQUE (hospital_id, modality, scan_name, body_part)
            )
            """
            )
        )
        changed = True
        touched = True
    else:
        table = models.TABLES["radiology_service_catalog"]
        desired = {
            "modality": "TEXT NOT NULL DEFAULT 'X_RAY'",
            "scan_name": "TEXT NOT NULL DEFAULT 'Scan'",
            "body_part": "TEXT NOT NULL DEFAULT 'GENERAL'",
            "service_fee": "REAL NOT NULL DEFAULT 0",
            "is_active": "INTEGER NOT NULL DEFAULT 1",
            "created_at": "TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP",
        }
        for col, col_sql in desired.items():
            if _table_has_column(table, col):
                continue
            db.execute(text(f"ALTER TABLE radiology_service_catalog ADD COLUMN {col} {col_sql}"))
            changed = True
            touched = True

    if changed:
        db.commit()
        models.load_tables()

    table = models.TABLES.get("radiology_service_catalog")
    if table is not None:
        cols = {"hospital_id", "modality", "is_active"}
        if all(_table_has_column(table, col) for col in cols):
            db.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS idx_rad_service_catalog_hospital_modality ON radiology_service_catalog(hospital_id, modality, is_active)"
                )
            )
            touched = True
    if touched:
        db.commit()


def _ensure_reception_radiology_billing_table(db: Session) -> None:
    changed = False
    if models.TABLES.get("reception_radiology_billings") is None:
        db.execute(
            text(
                """
            CREATE TABLE IF NOT EXISTS reception_radiology_billings (
                billing_id INTEGER PRIMARY KEY,
                hospital_id INTEGER NOT NULL,
                patient_id INTEGER NOT NULL,
                patient_mrn_snapshot TEXT NOT NULL,
                service_id INTEGER NOT NULL,
                radiology_request_id INTEGER NOT NULL,
                invoice_id INTEGER NOT NULL,
                procedure_tag TEXT,
                amount_due REAL NOT NULL DEFAULT 0,
                payment_status TEXT NOT NULL DEFAULT 'UNPAID',
                created_by_staff_id INTEGER,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (hospital_id, billing_id)
            )
            """
            )
        )
        db.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_reception_rad_billings_hospital_time ON reception_radiology_billings(hospital_id, created_at)"
            )
        )
        changed = True
    else:
        table = models.TABLES["reception_radiology_billings"]
        if not _table_has_column(table, "procedure_tag"):
            db.execute(text("ALTER TABLE reception_radiology_billings ADD COLUMN procedure_tag TEXT"))
            changed = True
        db.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_reception_rad_billings_hospital_time ON reception_radiology_billings(hospital_id, created_at)"
            )
        )

    if changed:
        db.commit()
        models.load_tables()


def _seed_default_radiology_services(db: Session, hospital_id: int) -> None:
    _ensure_radiology_service_catalog_table(db)
    table = models.TABLES["radiology_service_catalog"]
    exists = db.execute(
        select(table.c.service_id).where(table.c.hospital_id == hospital_id).limit(1)
    ).first()
    if exists:
        return

    defaults = [
        {"modality": "X_RAY", "scan_name": "X-Ray - Chest", "body_part": "CHEST", "service_fee": 1200},
        {"modality": "X_RAY", "scan_name": "X-Ray - Spine", "body_part": "SPINE", "service_fee": 1500},
        {"modality": "X_RAY", "scan_name": "X-Ray - Limb", "body_part": "LIMBS", "service_fee": 1100},
        {"modality": "ULTRASOUND", "scan_name": "Ultrasound - Abdomen", "body_part": "ABDOMEN", "service_fee": 2200},
        {"modality": "ULTRASOUND", "scan_name": "Ultrasound - Pelvis", "body_part": "PELVIS", "service_fee": 2300},
        {"modality": "ULTRASOUND", "scan_name": "Ultrasound - Kidney", "body_part": "KIDNEY", "service_fee": 2100},
        {"modality": "MRI", "scan_name": "MRI - Brain", "body_part": "BRAIN", "service_fee": 8500},
        {"modality": "MRI", "scan_name": "MRI - Spine", "body_part": "SPINE", "service_fee": 9000},
        {"modality": "MRI", "scan_name": "MRI - Pelvis", "body_part": "PELVIS", "service_fee": 8800},
        {"modality": "CT_SCAN", "scan_name": "CT Scan - Brain", "body_part": "BRAIN", "service_fee": 7000},
        {"modality": "CT_SCAN", "scan_name": "CT Scan - Chest", "body_part": "CHEST", "service_fee": 7600},
        {"modality": "CT_SCAN", "scan_name": "CT Scan - Abdomen", "body_part": "ABDOMEN", "service_fee": 7800},
        {"modality": "CT_SCAN", "scan_name": "CT Scan - Spine", "body_part": "SPINE", "service_fee": 7400},
    ]
    for item in defaults:
        db.execute(
            insert(table).values(
                hospital_id=hospital_id,
                modality=item["modality"],
                scan_name=item["scan_name"],
                body_part=item["body_part"],
                service_fee=item["service_fee"],
                is_active=1,
            )
        )
    db.commit()


def _next_radiology_invoice_number(db: Session, hospital_id: int) -> str:
    return _next_invoice_number(db, hospital_id, prefix="INV-RAD")


@app.get("/nurse/patient-search")
def nurse_patient_search(
    q: str = Query(default=""),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_roles(current_user, {"NURSE", "DOCTOR", "OPERATIONS", "ADMIN", "SUPER_ADMIN"})
    hospital_id = current_user["hospital_id"]
    patients = models.TABLES["patients"]

    query = select(patients).where(patients.c.hospital_id == hospital_id)
    if q.strip():
        term = f"%{q.strip()}%"
        query = query.where((patients.c.patient_mrn.like(term)) | (patients.c.full_name.like(term)))

    patient_recent_order = _recent_order_expr(patients, "created_at", "patient_id")
    if patient_recent_order is not None:
        query = query.order_by(patient_recent_order)
    rows = db.execute(query.limit(limit)).fetchall()
    return {"count": len(rows), "items": [_serialize_row(r) for r in rows]}


@app.post("/nurse/vitals")
def nurse_record_vitals(
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_roles(current_user, {"NURSE", "ADMIN", "SUPER_ADMIN"})
    _ensure_patient_vitals_extended_columns(db)

    hospital_id = current_user["hospital_id"]
    patients = models.TABLES["patients"]
    vitals = models.TABLES["patient_vitals"]

    patient_id = int(payload.get("patient_id") or 0)
    patient_mrn = str(payload.get("patient_mrn") or "").strip()
    if patient_id <= 0 or not patient_mrn:
        raise HTTPException(status_code=400, detail="patient_id and patient_mrn are required")

    patient = db.execute(
        select(patients)
        .where(patients.c.hospital_id == hospital_id)
        .where(patients.c.patient_id == patient_id)
    ).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    if str(patient.patient_mrn or "").strip() != patient_mrn:
        raise HTTPException(status_code=400, detail="patient_mrn does not match patient_id")

    def _n(value: Any) -> Optional[float]:
        if value in [None, ""]:
            return None
        try:
            return float(value)
        except Exception:
            raise HTTPException(status_code=400, detail="Vitals values must be numeric")

    result = db.execute(
        insert(vitals).values(
            hospital_id=hospital_id,
            patient_id=patient_id,
            body_temperature=_n(payload.get("body_temperature")),
            blood_pressure_systolic=int(_n(payload.get("blood_pressure_systolic")) or 0) if payload.get("blood_pressure_systolic") not in [None, ""] else None,
            blood_pressure_diastolic=int(_n(payload.get("blood_pressure_diastolic")) or 0) if payload.get("blood_pressure_diastolic") not in [None, ""] else None,
            pulse_rate=int(_n(payload.get("heart_rate")) or 0) if payload.get("heart_rate") not in [None, ""] else None,
            oxygen_saturation=_n(payload.get("oxygen_saturation")),
            respiratory_rate=_n(payload.get("respiratory_rate")),
            weight_kg=_n(payload.get("weight_kg")),
            bmi=_n(payload.get("bmi")),
            chief_complaint=(payload.get("chief_complaint") or "").strip() or None,
            observation_notes=(payload.get("observation_notes") or "").strip() or None,
            recorded_by_staff_id=_get_current_staff_id(db, current_user),
        )
    )
    db.commit()

    vitals_id = result.inserted_primary_key[0] if result.inserted_primary_key else None
    row = db.execute(
        select(vitals)
        .where(vitals.c.hospital_id == hospital_id)
        .where(vitals.c.vitals_id == vitals_id)
    ).first()
    return {"status": "saved", "item": _serialize_row(row) if row else None}


@app.get("/nurse/vitals")
def nurse_list_vitals(
    patient_id: Optional[int] = Query(default=None, ge=1),
    patient_mrn: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_roles(current_user, {"NURSE", "DOCTOR", "ADMIN", "SUPER_ADMIN"})
    _ensure_patient_vitals_extended_columns(db)

    hospital_id = current_user["hospital_id"]
    vitals = models.TABLES["patient_vitals"]
    patients = models.TABLES["patients"]

    query = (
        select(
            vitals,
            patients.c.full_name.label("patient_name"),
            patients.c.patient_mrn.label("patient_mrn"),
        )
        .select_from(
            vitals.join(
                patients,
                (vitals.c.hospital_id == patients.c.hospital_id)
                & (vitals.c.patient_id == patients.c.patient_id),
            )
        )
        .where(vitals.c.hospital_id == hospital_id)
    )
    if patient_id is not None:
        query = query.where(vitals.c.patient_id == int(patient_id))
    if patient_mrn:
        query = query.where(patients.c.patient_mrn == str(patient_mrn).strip())

    rows = db.execute(query.order_by(vitals.c.vitals_id.desc()).limit(limit)).fetchall()
    return {"count": len(rows), "items": [_serialize_row(r) for r in rows]}


@app.get("/reception/radiology-services")
def reception_radiology_services(
    modality: Optional[str] = Query(default=None),
    q: str = Query(default=""),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_roles(current_user, {"RECEPTIONIST", "ADMIN", "SUPER_ADMIN"})
    hospital_id = current_user["hospital_id"]
    _seed_default_radiology_services(db, hospital_id)

    table = models.TABLES["radiology_service_catalog"]
    query = select(table).where(table.c.hospital_id == hospital_id).where(table.c.is_active == 1)
    if modality:
        query = query.where(table.c.modality == _normalize_radiology_modality(modality))
    if q.strip():
        term = f"%{q.strip()}%"
        query = query.where((table.c.scan_name.like(term)) | (table.c.body_part.like(term)))

    rows = db.execute(query.order_by(table.c.modality.asc(), table.c.scan_name.asc())).fetchall()
    return {"count": len(rows), "items": [_serialize_row(r) for r in rows]}


@app.post("/reception/radiology-billing/register")
def reception_register_radiology_billing(
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_roles(current_user, {"RECEPTIONIST", "ADMIN", "SUPER_ADMIN"})
    _ensure_radiology_table(db)
    _ensure_reception_radiology_billing_table(db)
    _seed_default_radiology_services(db, current_user["hospital_id"])

    hospital_id = current_user["hospital_id"]
    patients = models.TABLES["patients"]
    services = models.TABLES["radiology_service_catalog"]
    radiology = models.TABLES["radiology_requests"]
    invoices = models.TABLES["invoices"]
    invoice_items = models.TABLES["invoice_items"]
    payments = models.TABLES["payments"]
    billings = models.TABLES["reception_radiology_billings"]

    patient_id = int(payload.get("patient_id") or 0)
    patient_mrn = str(payload.get("patient_mrn") or "").strip()
    service_id = int(payload.get("service_id") or 0)
    procedure_tag = str(payload.get("procedure_tag") or "").strip() or "Radiology Scan"
    service_fee_override = payload.get("service_fee")
    payment_status = str(payload.get("payment_status") or "UNPAID").strip().upper()
    payment_method = str(payload.get("payment_method") or "CASH").strip().upper()
    notes = (payload.get("notes") or "").strip() or None

    if patient_id <= 0 or not patient_mrn:
        raise HTTPException(status_code=400, detail="patient_id and patient_mrn are required")
    if service_id <= 0:
        raise HTTPException(status_code=400, detail="service_id is required")
    if payment_status not in {"PAID", "UNPAID"}:
        raise HTTPException(status_code=400, detail="payment_status must be PAID or UNPAID")

    patient = db.execute(
        select(patients)
        .where(patients.c.hospital_id == hospital_id)
        .where(patients.c.patient_id == patient_id)
    ).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    if str(patient.patient_mrn or "").strip() != patient_mrn:
        raise HTTPException(status_code=400, detail="patient_mrn does not match patient_id")

    service = db.execute(
        select(services)
        .where(services.c.hospital_id == hospital_id)
        .where(services.c.service_id == service_id)
        .where(services.c.is_active == 1)
    ).first()
    if not service:
        raise HTTPException(status_code=404, detail="Radiology service not found")

    staff_id = _get_current_staff_id(db, current_user)
    rad_result = db.execute(
        insert(radiology).values(
            hospital_id=hospital_id,
            patient_id=patient_id,
            ordered_by_staff_id=staff_id,
            test_name=service.scan_name,
            body_part=service.body_part,
            priority="ROUTINE",
            status="ORDERED",
            notes=notes,
        )
    )
    rad_request_id = rad_result.inserted_primary_key[0] if rad_result.inserted_primary_key else None

    amount_due = float(service.service_fee or 0)
    if service_fee_override not in [None, ""]:
        try:
            amount_due = float(service_fee_override or 0)
        except Exception:
            raise HTTPException(status_code=400, detail="service_fee must be numeric")
    if amount_due < 0:
        raise HTTPException(status_code=400, detail="service_fee cannot be negative")
    invoice_number = _next_radiology_invoice_number(db, hospital_id)
    invoice_result = db.execute(
        insert(invoices).values(
            hospital_id=hospital_id,
            patient_id=patient_id,
            invoice_number=invoice_number,
            gross_amount=amount_due,
            discount_amount=0,
            net_amount=amount_due,
            status=payment_status,
        )
    )
    invoice_id = invoice_result.inserted_primary_key[0] if invoice_result.inserted_primary_key else None

    db.execute(
        insert(invoice_items).values(
            hospital_id=hospital_id,
            invoice_id=invoice_id,
            item_type="RADIOLOGY",
            reference_id=rad_request_id,
            description=f"{service.scan_name} | Procedure Tag: {procedure_tag}",
            quantity=1,
            unit_price=amount_due,
            line_total=amount_due,
        )
    )

    if payment_status == "PAID" and amount_due > 0:
        db.execute(
            insert(payments).values(
                hospital_id=hospital_id,
                invoice_id=invoice_id,
                amount_paid=amount_due,
                payment_method=payment_method,
                payment_reference=f"RAD-{rad_request_id}",
                collected_by_staff_id=staff_id,
            )
        )

    billing_insert_values = {
        "hospital_id": hospital_id,
        "patient_id": patient_id,
        "patient_mrn_snapshot": patient_mrn,
        "service_id": service_id,
        "radiology_request_id": rad_request_id,
        "invoice_id": invoice_id,
        "amount_due": amount_due,
        "payment_status": payment_status,
        "created_by_staff_id": staff_id,
        "updated_at": datetime.utcnow().isoformat(),
    }
    if _table_has_column(billings, "procedure_tag"):
        billing_insert_values["procedure_tag"] = procedure_tag

    billing_result = db.execute(insert(billings).values(**billing_insert_values))
    billing_id = billing_result.inserted_primary_key[0] if billing_result.inserted_primary_key else None
    db.commit()
    settings_snapshot = _build_settings_payload(db, hospital_id)
    hospital_meta = settings_snapshot.get("hospital_metadata") or {}

    receipt = {
        "receipt_no": f"RAD-REC-{hospital_id}-{billing_id}",
        "created_at": datetime.utcnow().isoformat(),
        "hospital_name": hospital_meta.get("hospital_name"),
        "hospital_address": hospital_meta.get("address"),
        "hospital_logo_url": hospital_meta.get("logo_url"),
        "patient_name": patient.full_name,
        "patient_mrn": patient.patient_mrn,
        "scan_type": service.scan_name,
        "procedure_tag": procedure_tag,
        "modality": service.modality,
        "body_part": service.body_part,
        "total_amount_due": amount_due,
        "payment_status": payment_status,
        "invoice_number": invoice_number,
    }

    return {
        "status": "registered",
        "billing_id": billing_id,
        "radiology_request_id": rad_request_id,
        "invoice_id": invoice_id,
        "invoice_number": invoice_number,
        "service": _serialize_row(service),
        "receipt": receipt,
    }


@app.get("/reception/radiology-billing/orders")
def reception_list_radiology_billings(
    patient_mrn: Optional[str] = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_roles(current_user, {"RECEPTIONIST", "ADMIN", "SUPER_ADMIN"})
    _ensure_reception_radiology_billing_table(db)
    _ensure_radiology_service_catalog_table(db)

    hospital_id = current_user["hospital_id"]
    billings = models.TABLES["reception_radiology_billings"]
    services = models.TABLES["radiology_service_catalog"]
    patients = models.TABLES["patients"]
    invoices = models.TABLES["invoices"]

    query = (
        select(
            billings,
            services.c.scan_name,
            services.c.modality,
            services.c.body_part,
            patients.c.full_name.label("patient_name"),
            patients.c.patient_mrn.label("patient_mrn"),
            invoices.c.invoice_number,
            invoices.c.status.label("invoice_status"),
            invoices.c.net_amount,
        )
        .select_from(
            billings.join(
                services,
                (billings.c.hospital_id == services.c.hospital_id)
                & (billings.c.service_id == services.c.service_id),
            ).join(
                patients,
                (billings.c.hospital_id == patients.c.hospital_id)
                & (billings.c.patient_id == patients.c.patient_id),
            ).join(
                invoices,
                (billings.c.hospital_id == invoices.c.hospital_id)
                & (billings.c.invoice_id == invoices.c.invoice_id),
            )
        )
        .where(billings.c.hospital_id == hospital_id)
    )
    if patient_mrn:
        query = query.where(patients.c.patient_mrn == str(patient_mrn).strip())

    rows = db.execute(query.order_by(billings.c.billing_id.desc()).limit(limit)).fetchall()
    return {"count": len(rows), "items": [_serialize_row(r) for r in rows]}


@app.post("/reception/radiology-billing/{billing_id}/payment-status")
def reception_update_radiology_payment_status(
    billing_id: int,
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_roles(current_user, {"RECEPTIONIST", "ADMIN", "SUPER_ADMIN"})
    _ensure_reception_radiology_billing_table(db)

    hospital_id = current_user["hospital_id"]
    billings = models.TABLES["reception_radiology_billings"]
    invoices = models.TABLES["invoices"]
    payments = models.TABLES["payments"]
    payment_status = str(payload.get("payment_status") or "").strip().upper()
    payment_method = str(payload.get("payment_method") or "CASH").strip().upper()

    if payment_status not in {"PAID", "UNPAID"}:
        raise HTTPException(status_code=400, detail="payment_status must be PAID or UNPAID")

    row = db.execute(
        select(billings)
        .where(billings.c.hospital_id == hospital_id)
        .where(billings.c.billing_id == billing_id)
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Billing order not found")

    invoice_id = int(row.invoice_id)
    amount_due = float(row.amount_due or 0)
    staff_id = _get_current_staff_id(db, current_user)

    if payment_status == "PAID":
        paid_total = float(
            db.execute(
                select(func.coalesce(func.sum(payments.c.amount_paid), 0))
                .where(payments.c.hospital_id == hospital_id)
                .where(payments.c.invoice_id == invoice_id)
            ).scalar()
            or 0
        )
        diff = round(amount_due - paid_total, 2)
        if diff > 0:
            db.execute(
                insert(payments).values(
                    hospital_id=hospital_id,
                    invoice_id=invoice_id,
                    amount_paid=diff,
                    payment_method=payment_method,
                    payment_reference=f"RAD-BILL-{billing_id}",
                    collected_by_staff_id=staff_id,
                )
            )
        db.execute(
            update(invoices)
            .where(invoices.c.hospital_id == hospital_id)
            .where(invoices.c.invoice_id == invoice_id)
            .values(status="PAID")
        )
    else:
        db.execute(
            delete(payments)
            .where(payments.c.hospital_id == hospital_id)
            .where(payments.c.invoice_id == invoice_id)
        )
        db.execute(
            update(invoices)
            .where(invoices.c.hospital_id == hospital_id)
            .where(invoices.c.invoice_id == invoice_id)
            .values(status="UNPAID")
        )

    db.execute(
        update(billings)
        .where(billings.c.hospital_id == hospital_id)
        .where(billings.c.billing_id == billing_id)
        .values(payment_status=payment_status, updated_at=datetime.utcnow().isoformat())
    )
    db.commit()

    updated = db.execute(
        select(billings)
        .where(billings.c.hospital_id == hospital_id)
        .where(billings.c.billing_id == billing_id)
    ).first()
    return {"status": "updated", "item": _serialize_row(updated) if updated else None}


@app.post("/reception/patients")
def reception_create_patient(
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_roles(current_user, {"RECEPTIONIST", "ADMIN", "SUPER_ADMIN"})

    patients_table = models.TABLES["patients"]
    hospital_id = current_user["hospital_id"]

    full_name = (payload.get("full_name") or "").strip()
    if not full_name:
        raise HTTPException(status_code=400, detail="full_name is required")

    mrn = (payload.get("patient_mrn") or "").strip()
    if not mrn:
        mrn = f"MRN-{hospital_id}-{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')[-10:]}"

    values = {
        "hospital_id": hospital_id,
        "patient_mrn": mrn,
        "full_name": full_name,
        "dob": (payload.get("dob") or None),
        "gender": (payload.get("gender") or None),
        "phone_number": (payload.get("phone_number") or None),
        "insurance_provider_id": payload.get("insurance_provider_id"),
    }

    try:
        result = db.execute(insert(patients_table).values(**values))
        patient_id = result.inserted_primary_key[0] if result.inserted_primary_key else None
        if patient_id is not None:
            _record_reception_visit(db, hospital_id, int(patient_id), current_user, payload)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Integrity error: {exc.orig}")
    row = db.execute(
        select(patients_table)
        .where(patients_table.c.hospital_id == hospital_id)
        .where(patients_table.c.patient_id == patient_id)
    ).first()

    return {"status": "created", "item": _serialize_row(row)}

@app.post("/reception/patients/register-portal")
def reception_register_patient_portal(
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_roles(current_user, {"RECEPTIONIST", "ADMIN", "SUPER_ADMIN"})

    full_name = (payload.get("full_name") or "").strip()
    email = _normalize_email(payload.get("email"))
    if not full_name or not email:
        raise HTTPException(status_code=400, detail="full_name and email are required")

    hospital_id = current_user["hospital_id"]
    mrn = (payload.get("patient_mrn") or "").strip()
    if not mrn:
        mrn = f"MRN-{hospital_id}-{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')[-10:]}"

    temp_password = (payload.get("portal_password") or "").strip()
    if not temp_password:
        temp_password = f"MedX{uuid.uuid4().hex[:8]}!"

    patients_table = models.TABLES["patients"]
    users_table = models.TABLES["users"]
    roles_table = models.TABLES["roles"]
    memberships_table = models.TABLES["hospital_user_memberships"]
    portal_table = models.TABLES["patient_portal_accounts"]
    invoices_table = models.TABLES["invoices"]
    invoice_items_table = models.TABLES["invoice_items"]

    settings_snapshot = _build_settings_payload(db, hospital_id)
    service_pricing = settings_snapshot.get("service_pricing") or {}
    registration_fee = float(service_pricing.get("patient_registration_fee") or 0)
    if payload.get("service_fee") not in [None, ""]:
        try:
            registration_fee = float(payload.get("service_fee") or 0)
        except Exception:
            raise HTTPException(status_code=400, detail="service_fee must be numeric")
    if registration_fee < 0:
        raise HTTPException(status_code=400, detail="service_fee cannot be negative")
    procedure_tag = str(payload.get("procedure_tag") or "").strip() or "Patient Registration"
    billing_status = "UNPAID" if registration_fee > 0 else "PAID"
    invoice_number = None
    invoice_id = None

    existing_user = db.execute(select(users_table).where(users_table.c.email == email)).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already exists")

    patient_role = db.execute(select(roles_table).where(roles_table.c.role_name == "PATIENT")).first()
    if not patient_role:
        db.execute(insert(roles_table).values(role_name="PATIENT"))
        db.commit()
        patient_role = db.execute(select(roles_table).where(roles_table.c.role_name == "PATIENT")).first()

    try:
        patient_result = db.execute(
            insert(patients_table).values(
                hospital_id=hospital_id,
                patient_mrn=mrn,
                full_name=full_name,
                dob=(payload.get("dob") or None),
                gender=(payload.get("gender") or None),
                phone_number=(payload.get("phone_number") or None),
                insurance_provider_id=payload.get("insurance_provider_id"),
            )
        )
        patient_id = patient_result.inserted_primary_key[0] if patient_result.inserted_primary_key else None
        if patient_id is not None:
            _record_reception_visit(db, hospital_id, int(patient_id), current_user, payload)

        user_result = db.execute(
            insert(users_table).values(
                email=email,
                password_hash=pwd_context.hash(temp_password),
                is_active=1,
            )
        )
        user_id = user_result.inserted_primary_key[0] if user_result.inserted_primary_key else None

        db.execute(
            insert(memberships_table).values(
                hospital_id=hospital_id,
                user_id=user_id,
                role_id=patient_role.role_id,
                staff_id=None,
                is_primary=1,
            )
        )

        db.execute(
            insert(portal_table).values(
                hospital_id=hospital_id,
                user_id=user_id,
                patient_id=patient_id,
            )
        )

        invoice_number = _next_invoice_number(db, hospital_id, prefix="INV-REG")
        invoice_result = db.execute(
            insert(invoices_table).values(
                hospital_id=hospital_id,
                patient_id=patient_id,
                invoice_number=invoice_number,
                gross_amount=registration_fee,
                discount_amount=0,
                net_amount=registration_fee,
                status=billing_status,
            )
        )
        invoice_id = invoice_result.inserted_primary_key[0] if invoice_result.inserted_primary_key else None
        db.execute(
            insert(invoice_items_table).values(
                hospital_id=hospital_id,
                invoice_id=invoice_id,
                item_type="PATIENT_REGISTRATION",
                reference_id=patient_id,
                description=f"Patient Registration | Procedure Tag: {procedure_tag}",
                quantity=1,
                unit_price=registration_fee,
                line_total=registration_fee,
            )
        )

        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Integrity error: {exc.orig}")

    patient = db.execute(
        select(patients_table)
        .where(patients_table.c.hospital_id == hospital_id)
        .where(patients_table.c.patient_id == patient_id)
    ).first()

    created_at = datetime.utcnow().isoformat()
    hospital_meta = settings_snapshot.get("hospital_metadata") or {}
    receipt = {
        "receipt_no": f"REC-{hospital_id}-{patient_id}-{datetime.utcnow().strftime('%H%M%S')}",
        "created_at": created_at,
        "hospital_id": hospital_id,
        "hospital_name": hospital_meta.get("hospital_name"),
        "hospital_address": hospital_meta.get("address"),
        "hospital_logo_url": hospital_meta.get("logo_url"),
        "patient_id": patient_id,
        "patient_name": full_name,
        "patient_mrn": mrn,
        "portal_email": email,
        "visit_type": (payload.get("visit_type") or "OPD"),
        "chief_complaint": (payload.get("chief_complaint") or None),
        "procedure_tag": procedure_tag,
        "service_type": "PATIENT_REGISTRATION",
        "service_fee": registration_fee,
        "invoice_id": invoice_id,
        "invoice_number": invoice_number,
        "billing_status": billing_status,
    }

    return {
        "status": "registered",
        "patient": _serialize_row(patient),
        "portal_credentials": {
            "email": email,
            "temporary_password": temp_password,
        },
        "receipt": receipt,
    }


@app.get("/patient/my-feed")
def patient_my_feed(
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_roles(current_user, {"PATIENT"})

    hospital_id = current_user["hospital_id"]
    user_id = current_user["user_id"]

    portal_table = models.TABLES["patient_portal_accounts"]
    patients_table = models.TABLES["patients"]
    meds_table = models.TABLES["doctor_medications"]
    updates_table = models.TABLES["doctor_clinical_updates"]

    link = db.execute(
        select(portal_table.c.patient_id)
        .where(portal_table.c.hospital_id == hospital_id)
        .where(portal_table.c.user_id == user_id)
    ).first()
    if not link:
        raise HTTPException(status_code=404, detail="No patient profile linked to this account")

    patient_id = int(link.patient_id)
    patient = db.execute(
        select(patients_table)
        .where(patients_table.c.hospital_id == hospital_id)
        .where(patients_table.c.patient_id == patient_id)
    ).first()

    medications = db.execute(
        select(meds_table)
        .where(meds_table.c.hospital_id == hospital_id)
        .where(meds_table.c.patient_id == patient_id)
        .order_by(meds_table.c.created_at.desc())
    ).fetchall()

    clinical_updates = db.execute(
        select(updates_table)
        .where(updates_table.c.hospital_id == hospital_id)
        .where(updates_table.c.patient_id == patient_id)
        .order_by(updates_table.c.created_at.desc())
    ).fetchall()

    return {
        "patient": _serialize_row(patient),
        "medications": [_serialize_row(r) for r in medications],
        "clinical_updates": [_serialize_row(r) for r in clinical_updates],
    }

@app.post("/reception/patients/register-portal-auto")
def reception_register_patient_portal_auto(
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_roles(current_user, {"RECEPTIONIST", "ADMIN", "SUPER_ADMIN"})

    full_name = (payload.get("full_name") or "").strip()
    if not full_name:
        raise HTTPException(status_code=400, detail="full_name is required")

    hospital_id = current_user["hospital_id"]
    mrn = (payload.get("patient_mrn") or "").strip()
    if not mrn:
        mrn = f"MRN-{hospital_id}-{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')[-10:]}"

    temp_password = (payload.get("portal_password") or "").strip()
    if not temp_password:
        temp_password = f"MedX{uuid.uuid4().hex[:8]}!"

    patients_table = models.TABLES["patients"]
    users_table = models.TABLES["users"]
    roles_table = models.TABLES["roles"]
    memberships_table = models.TABLES["hospital_user_memberships"]
    portal_table = models.TABLES["patient_portal_accounts"]
    invoices_table = models.TABLES["invoices"]
    invoice_items_table = models.TABLES["invoice_items"]

    settings_snapshot = _build_settings_payload(db, hospital_id)
    service_pricing = settings_snapshot.get("service_pricing") or {}
    registration_fee = float(service_pricing.get("patient_registration_fee") or 0)
    if payload.get("service_fee") not in [None, ""]:
        try:
            registration_fee = float(payload.get("service_fee") or 0)
        except Exception:
            raise HTTPException(status_code=400, detail="service_fee must be numeric")
    if registration_fee < 0:
        raise HTTPException(status_code=400, detail="service_fee cannot be negative")
    procedure_tag = str(payload.get("procedure_tag") or "").strip() or "Patient Registration"
    billing_status = "UNPAID" if registration_fee > 0 else "PAID"
    invoice_number = None
    invoice_id = None

    base_slug = "".join(ch.lower() for ch in full_name if ch.isalnum())[:12] or "patient"
    email = f"{base_slug}.{mrn.lower().replace(' ', '').replace('/', '-')[:10]}@patient.medx.local"

    counter = 1
    while db.execute(select(users_table.c.user_id).where(users_table.c.email == email)).first():
        email = f"{base_slug}.{counter}@patient.medx.local"
        counter += 1

    patient_role = db.execute(select(roles_table).where(roles_table.c.role_name == "PATIENT")).first()
    if not patient_role:
        db.execute(insert(roles_table).values(role_name="PATIENT"))
        db.commit()
        patient_role = db.execute(select(roles_table).where(roles_table.c.role_name == "PATIENT")).first()

    try:
        patient_result = db.execute(
            insert(patients_table).values(
                hospital_id=hospital_id,
                patient_mrn=mrn,
                full_name=full_name,
                dob=(payload.get("dob") or None),
                gender=(payload.get("gender") or None),
                phone_number=(payload.get("phone_number") or None),
                insurance_provider_id=payload.get("insurance_provider_id"),
            )
        )
        patient_id = patient_result.inserted_primary_key[0] if patient_result.inserted_primary_key else None
        if patient_id is not None:
            _record_reception_visit(db, hospital_id, int(patient_id), current_user, payload)

        user_result = db.execute(
            insert(users_table).values(
                email=email,
                password_hash=pwd_context.hash(temp_password),
                is_active=1,
            )
        )
        user_id = user_result.inserted_primary_key[0] if user_result.inserted_primary_key else None

        db.execute(
            insert(memberships_table).values(
                hospital_id=hospital_id,
                user_id=user_id,
                role_id=patient_role.role_id,
                staff_id=None,
                is_primary=1,
            )
        )

        db.execute(
            insert(portal_table).values(
                hospital_id=hospital_id,
                user_id=user_id,
                patient_id=patient_id,
            )
        )

        invoice_number = _next_invoice_number(db, hospital_id, prefix="INV-REG")
        invoice_result = db.execute(
            insert(invoices_table).values(
                hospital_id=hospital_id,
                patient_id=patient_id,
                invoice_number=invoice_number,
                gross_amount=registration_fee,
                discount_amount=0,
                net_amount=registration_fee,
                status=billing_status,
            )
        )
        invoice_id = invoice_result.inserted_primary_key[0] if invoice_result.inserted_primary_key else None
        db.execute(
            insert(invoice_items_table).values(
                hospital_id=hospital_id,
                invoice_id=invoice_id,
                item_type="PATIENT_REGISTRATION",
                reference_id=patient_id,
                description=f"Patient Registration | Procedure Tag: {procedure_tag}",
                quantity=1,
                unit_price=registration_fee,
                line_total=registration_fee,
            )
        )

        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Integrity error: {exc.orig}")

    patient = db.execute(
        select(patients_table)
        .where(patients_table.c.hospital_id == hospital_id)
        .where(patients_table.c.patient_id == patient_id)
    ).first()

    hospital_meta = settings_snapshot.get("hospital_metadata") or {}

    receipt = {
        "receipt_no": f"REC-{hospital_id}-{patient_id}-{datetime.utcnow().strftime('%H%M%S')}",
        "created_at": datetime.utcnow().isoformat(),
        "hospital_id": hospital_id,
        "hospital_name": hospital_meta.get("hospital_name"),
        "hospital_address": hospital_meta.get("address"),
        "hospital_logo_url": hospital_meta.get("logo_url"),
        "patient_id": patient_id,
        "patient_name": full_name,
        "patient_mrn": mrn,
        "portal_email": email,
        "visit_type": (payload.get("visit_type") or "OPD"),
        "chief_complaint": (payload.get("chief_complaint") or None),
        "procedure_tag": procedure_tag,
        "service_type": "PATIENT_REGISTRATION",
        "service_fee": registration_fee,
        "invoice_id": invoice_id,
        "invoice_number": invoice_number,
        "billing_status": billing_status,
    }

    return {
        "status": "registered",
        "patient": _serialize_row(patient),
        "portal_credentials": {
            "email": email,
            "temporary_password": temp_password,
        },
        "receipt": receipt,
    }


@app.post("/reception/admissions/register")
async def reception_register_admission(
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_roles(current_user, {"RECEPTIONIST", "ADMIN", "SUPER_ADMIN"})
    _ensure_operational_units_table(db)

    hospital_id = current_user["hospital_id"]
    patient_id = payload.get("patient_id")
    if not patient_id:
        raise HTTPException(status_code=400, detail="patient_id is required")

    admission_cost = payload.get("admission_cost")
    if admission_cost is None:
        admission_cost = 0

    ward_name = (payload.get("ward_name") or "General").strip()
    bed_number = (payload.get("bed_number") or "").strip()
    if not bed_number:
        bed_number = f"AUTO-{datetime.utcnow().strftime('%H%M%S')}"

    patients_table = models.TABLES["patients"]
    beds_table = models.TABLES["beds"]
    admissions_table = models.TABLES["admissions"]
    reception_records_table = models.TABLES["reception_admission_records"]

    patient = db.execute(
        select(patients_table)
        .where(patients_table.c.hospital_id == hospital_id)
        .where(patients_table.c.patient_id == int(patient_id))
    ).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found for this hospital")

    bed = db.execute(
        select(beds_table)
        .where(beds_table.c.hospital_id == hospital_id)
        .where(beds_table.c.bed_number == bed_number)
    ).first()

    if not bed:
        insert_values = {
            "hospital_id": hospital_id,
            "ward_name": ward_name,
            "bed_number": bed_number,
            "is_occupied": 1,
            "daily_charge": 0,
        }
        if _table_has_column(beds_table, "unit_type"):
            insert_values["unit_type"] = "WARD"
        if _table_has_column(beds_table, "status"):
            insert_values["status"] = "OCCUPIED"
        if _table_has_column(beds_table, "current_patient_id"):
            insert_values["current_patient_id"] = int(patient_id)
        if _table_has_column(beds_table, "updated_at"):
            insert_values["updated_at"] = datetime.utcnow().isoformat()
        bed_result = db.execute(
            insert(beds_table).values(**insert_values)
        )
        bed_id = bed_result.inserted_primary_key[0] if bed_result.inserted_primary_key else None
    else:
        bed_id = bed.bed_id
        update_values = {"is_occupied": 1, "ward_name": ward_name}
        if _table_has_column(beds_table, "unit_type"):
            update_values["unit_type"] = "WARD"
        if _table_has_column(beds_table, "status"):
            update_values["status"] = "OCCUPIED"
        if _table_has_column(beds_table, "current_patient_id"):
            update_values["current_patient_id"] = int(patient_id)
        if _table_has_column(beds_table, "updated_at"):
            update_values["updated_at"] = datetime.utcnow().isoformat()
        db.execute(
            update(beds_table)
            .where(beds_table.c.hospital_id == hospital_id)
            .where(beds_table.c.bed_id == bed_id)
            .values(**update_values)
        )

    admitted_by_staff_id = _get_current_staff_id(db, current_user)

    admission_result = db.execute(
        insert(admissions_table).values(
            hospital_id=hospital_id,
            patient_id=int(patient_id),
            bed_id=bed_id,
            admitted_by_staff_id=admitted_by_staff_id,
            status="ADMITTED",
        )
    )
    admission_id = admission_result.inserted_primary_key[0] if admission_result.inserted_primary_key else None

    db.execute(
        insert(reception_records_table).values(
            hospital_id=hospital_id,
            admission_id=admission_id,
            admission_cost=float(admission_cost),
            admission_notes=(payload.get("admission_notes") or None),
        )
    )
    _log_activity_audit(
        db,
        hospital_id=hospital_id,
        actor_user_id=current_user.get("user_id"),
        actor_staff_id=admitted_by_staff_id,
        actor_role=current_user.get("role_name"),
        module="BED",
        action="RECEPTION_ADMISSION",
        entity_type="BED",
        entity_id=int(bed_id or 0) or None,
        details={
            "patient_id": int(patient_id),
            "ward_name": ward_name,
            "bed_number": bed_number,
            "admission_id": admission_id,
        },
    )
    db.commit()
    await bed_sync_hub.broadcast(
        hospital_id,
        "bed_status_changed",
        {
            "bed_id": int(bed_id or 0),
            "ward_name": ward_name,
            "bed_number": bed_number,
            "status": "OCCUPIED",
            "patient_id": int(patient_id),
            "source": "reception_admission",
        },
    )

    receipt = {
        "receipt_no": f"ADM-{hospital_id}-{admission_id}-{datetime.utcnow().strftime('%H%M%S')}",
        "created_at": datetime.utcnow().isoformat(),
        "patient_name": patient.full_name,
        "patient_mrn": patient.patient_mrn,
        "ward_name": ward_name,
        "bed_number": bed_number,
        "admission_cost": float(admission_cost),
    }

    return {
        "status": "admitted",
        "admission_id": admission_id,
        "receipt": receipt,
    }


@app.get("/reception/admissions")
def reception_list_admissions(
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_roles(current_user, {"RECEPTIONIST", "ADMIN", "SUPER_ADMIN"})

    hospital_id = current_user["hospital_id"]
    admissions_table = models.TABLES["admissions"]
    patients_table = models.TABLES["patients"]
    beds_table = models.TABLES["beds"]
    reception_records_table = models.TABLES["reception_admission_records"]

    rows = db.execute(
        select(
            admissions_table.c.admission_id,
            admissions_table.c.admission_date,
            admissions_table.c.status,
            patients_table.c.patient_id,
            patients_table.c.full_name.label("patient_name"),
            patients_table.c.patient_mrn,
            beds_table.c.ward_name,
            beds_table.c.bed_number,
            reception_records_table.c.admission_cost,
            reception_records_table.c.admission_notes,
        )
        .select_from(
            admissions_table
            .join(
                patients_table,
                (admissions_table.c.hospital_id == patients_table.c.hospital_id)
                & (admissions_table.c.patient_id == patients_table.c.patient_id),
            )
            .join(
                beds_table,
                (admissions_table.c.hospital_id == beds_table.c.hospital_id)
                & (admissions_table.c.bed_id == beds_table.c.bed_id),
            )
            .join(
                reception_records_table,
                (admissions_table.c.hospital_id == reception_records_table.c.hospital_id)
                & (admissions_table.c.admission_id == reception_records_table.c.admission_id),
            )
        )
        .where(admissions_table.c.hospital_id == hospital_id)
        .order_by(admissions_table.c.admission_date.desc())
        .limit(limit)
        .offset(offset)
    ).fetchall()

    return {"count": len(rows), "items": [_serialize_row(r) for r in rows]}


# ======================= ACCOUNTS & FLEET HUB =======================


@app.get("/finance/revenue-feed")
def finance_revenue_feed(
    month: Optional[str] = Query(default=None, description="YYYY-MM optional filter"),
    limit: int = Query(default=300, ge=1, le=2000),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_accounts_roles(current_user)

    hospital_id = current_user["hospital_id"]
    invoices = models.TABLES["invoices"]
    invoice_items = models.TABLES["invoice_items"]
    patients = models.TABLES["patients"]
    payments = models.TABLES["payments"]

    month_start = None
    month_end = None
    if month:
        try:
            base = datetime.strptime(f"{month}-01", "%Y-%m-%d")
            month_start = base.strftime("%Y-%m-%d")
            if base.month == 12:
                month_end = f"{base.year + 1}-01-01"
            else:
                month_end = f"{base.year}-{base.month + 1:02d}-01"
        except Exception:
            raise HTTPException(status_code=400, detail="month must be YYYY-MM")

    payments_sq = (
        select(
            payments.c.invoice_id.label("invoice_id"),
            func.coalesce(func.sum(payments.c.amount_paid), 0).label("paid_total"),
            func.max(payments.c.paid_at).label("last_paid_at"),
        )
        .where(payments.c.hospital_id == hospital_id)
        .group_by(payments.c.invoice_id)
        .subquery()
    )

    query = (
        select(
            invoices.c.invoice_id,
            invoices.c.invoice_number,
            invoices.c.invoice_date,
            invoices.c.status.label("invoice_status"),
            patients.c.patient_id,
            patients.c.patient_mrn,
            patients.c.full_name.label("patient_name"),
            invoice_items.c.item_type.label("service_type"),
            invoice_items.c.description.label("service_description"),
            invoice_items.c.line_total.label("service_fee"),
            func.coalesce(payments_sq.c.paid_total, 0).label("paid_amount"),
            payments_sq.c.last_paid_at,
            case(
                (func.coalesce(payments_sq.c.paid_total, 0) >= invoice_items.c.line_total, "PAID"),
                else_="PENDING",
            ).label("feed_status"),
        )
        .select_from(
            invoice_items.join(
                invoices,
                (invoice_items.c.hospital_id == invoices.c.hospital_id)
                & (invoice_items.c.invoice_id == invoices.c.invoice_id),
            )
            .join(
                patients,
                (invoices.c.hospital_id == patients.c.hospital_id)
                & (invoices.c.patient_id == patients.c.patient_id),
            )
            .outerjoin(payments_sq, invoices.c.invoice_id == payments_sq.c.invoice_id)
        )
        .where(invoices.c.hospital_id == hospital_id)
        .order_by(invoices.c.invoice_date.desc(), invoices.c.invoice_id.desc(), invoice_items.c.invoice_item_id.desc())
        .limit(limit)
    )
    if month_start and month_end:
        query = query.where(invoices.c.invoice_date >= month_start).where(invoices.c.invoice_date < month_end)

    rows = db.execute(query).fetchall()
    items = [_serialize_row(r) for r in rows]
    pending_count = sum(1 for r in items if str(r.get("feed_status") or "").upper() == "PENDING")
    paid_count = sum(1 for r in items if str(r.get("feed_status") or "").upper() == "PAID")
    return {
        "month": month,
        "count": len(items),
        "pending_count": pending_count,
        "paid_count": paid_count,
        "items": items,
    }


@app.get("/finance/command-center")
def finance_command_center(
    month: Optional[str] = Query(default=None, description="YYYY-MM optional filter"),
    ledger_limit: int = Query(default=300, ge=1, le=2000),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_accounts_roles(current_user)

    hospital_id = current_user["hospital_id"]
    invoices = models.TABLES["invoices"]
    invoice_items = models.TABLES["invoice_items"]
    patients = models.TABLES["patients"]
    payments = models.TABLES["payments"]
    expenses = models.TABLES["expenses"]

    month_start = None
    month_end = None
    if month:
        try:
            base = datetime.strptime(f"{month}-01", "%Y-%m-%d")
            month_start = base.strftime("%Y-%m-%d")
            if base.month == 12:
                month_end = f"{base.year + 1}-01-01"
            else:
                month_end = f"{base.year}-{base.month + 1:02d}-01"
        except Exception:
            raise HTTPException(status_code=400, detail="month must be YYYY-MM")

    payment_query = (
        select(
            payments.c.invoice_id.label("invoice_id"),
            func.sum(payments.c.amount_paid).label("paid_total"),
            func.max(payments.c.paid_at).label("last_paid_at"),
        )
        .where(payments.c.hospital_id == hospital_id)
    )
    if month_start and month_end:
        payment_query = payment_query.where(payments.c.paid_at >= month_start).where(payments.c.paid_at < month_end)
    payments_sq = payment_query.group_by(payments.c.invoice_id).subquery()

    ledger_query = (
        select(
            invoices.c.invoice_id,
            invoices.c.invoice_number,
            invoices.c.invoice_date,
            invoices.c.net_amount,
            invoices.c.status.label("invoice_status"),
            patients.c.patient_id,
            patients.c.full_name.label("patient_name"),
            patients.c.patient_mrn.label("patient_mrn"),
            func.coalesce(payments_sq.c.paid_total, 0).label("paid_amount"),
            payments_sq.c.last_paid_at,
            case(
                (func.coalesce(payments_sq.c.paid_total, 0) >= invoices.c.net_amount, "PAID"),
                else_="UNPAID",
            ).label("billing_status"),
        )
        .select_from(
            invoices.join(
                patients,
                (invoices.c.hospital_id == patients.c.hospital_id)
                & (invoices.c.patient_id == patients.c.patient_id),
            ).outerjoin(
                payments_sq,
                invoices.c.invoice_id == payments_sq.c.invoice_id,
            )
        )
        .where(invoices.c.hospital_id == hospital_id)
        .order_by(invoices.c.invoice_date.desc(), invoices.c.invoice_id.desc())
        .limit(ledger_limit)
    )
    if month_start and month_end:
        ledger_query = ledger_query.where(invoices.c.invoice_date >= month_start).where(invoices.c.invoice_date < month_end)

    ledger_rows = db.execute(ledger_query).fetchall()
    ledger_items = [_serialize_row(r) for r in ledger_rows]

    invoice_services_revenue = 0.0
    invoice_revenue_query = (
        select(func.coalesce(func.sum(invoice_items.c.line_total), 0))
        .select_from(
            invoice_items.join(
                invoices,
                (invoice_items.c.hospital_id == invoices.c.hospital_id)
                & (invoice_items.c.invoice_id == invoices.c.invoice_id),
            )
        )
        .where(invoice_items.c.hospital_id == hospital_id)
    )
    if month_start and month_end:
        invoice_revenue_query = invoice_revenue_query.where(invoices.c.invoice_date >= month_start).where(invoices.c.invoice_date < month_end)
    invoice_services_revenue = float(db.execute(invoice_revenue_query).scalar() or 0)

    appointments_revenue = 0.0
    if models.TABLES.get("appointments") is not None and models.TABLES.get("doctor_details") is not None:
        appointments = models.TABLES["appointments"]
        doctor_details = models.TABLES["doctor_details"]
        appt_query = (
            select(func.coalesce(func.sum(doctor_details.c.consultation_fee), 0))
            .select_from(
                appointments.outerjoin(
                    doctor_details,
                    (appointments.c.hospital_id == doctor_details.c.hospital_id)
                    & (appointments.c.doctor_id == doctor_details.c.doctor_staff_id),
                )
            )
            .where(appointments.c.hospital_id == hospital_id)
        )
        if month_start and month_end:
            appt_query = appt_query.where(appointments.c.appointment_date >= month_start).where(appointments.c.appointment_date < month_end)
        appointments_revenue = float(db.execute(appt_query).scalar() or 0)

    pharmacy_revenue = 0.0
    if models.TABLES.get("pharmacy_sales") is not None:
        sales = models.TABLES["pharmacy_sales"]
        sale_query = select(func.coalesce(func.sum(sales.c.total_amount), 0)).where(sales.c.hospital_id == hospital_id)
        if month_start and month_end:
            sale_query = sale_query.where(sales.c.sale_date >= month_start).where(sales.c.sale_date < month_end)
        pharmacy_revenue = float(db.execute(sale_query).scalar() or 0)

    ai_revenue = 0.0
    ai_unit_charge = 150.0
    if models.TABLES.get("ai_diagnoses") is not None:
        diagnoses = models.TABLES["ai_diagnoses"]
        ai_query = select(func.count(diagnoses.c.diagnosis_id)).where(diagnoses.c.hospital_id == hospital_id)
        if month_start and month_end:
            ai_query = ai_query.where(diagnoses.c.created_at >= month_start).where(diagnoses.c.created_at < month_end)
        ai_count = int(db.execute(ai_query).scalar() or 0)
        ai_revenue = ai_count * ai_unit_charge

    expense_query = select(
        func.coalesce(func.sum(expenses.c.amount), 0).label("total_spend"),
        func.coalesce(
            func.sum(
                case(
                    (func.upper(expenses.c.category).in_(["STAFF_SALARY", "SALARY", "PAYROLL"]), expenses.c.amount),
                    else_=0,
                )
            ),
            0,
        ).label("staff_salary_spend"),
        func.coalesce(
            func.sum(
                case(
                    (func.upper(expenses.c.category).in_(["MEDICINE_STOCK", "STOCK_PURCHASE", "PHARMACY_STOCK"]), expenses.c.amount),
                    else_=0,
                )
            ),
            0,
        ).label("medicine_stock_spend"),
        func.coalesce(
            func.sum(
                case(
                    (func.upper(expenses.c.category).in_(["FLEET_FUEL", "FUEL", "AMBULANCE_FUEL"]), expenses.c.amount),
                    else_=0,
                )
            ),
            0,
        ).label("fleet_fuel_spend"),
        func.coalesce(
            func.sum(
                case(
                    (func.upper(expenses.c.category).in_(["OT_SUPPLIES", "OPERATING_THEATER_SUPPLIES", "ICU_SUPPLIES"]), expenses.c.amount),
                    else_=0,
                )
            ),
            0,
        ).label("ot_supplies_spend"),
    ).where(expenses.c.hospital_id == hospital_id)
    if month_start and month_end:
        expense_query = expense_query.where(expenses.c.date_incurred >= month_start).where(expenses.c.date_incurred < month_end)
    expense_row = db.execute(expense_query).first()

    total_revenue = float(invoice_services_revenue + appointments_revenue + pharmacy_revenue + ai_revenue)
    total_spend = float((expense_row.total_spend if expense_row else 0) or 0)
    net_profit = total_revenue - total_spend

    return {
        "month": month,
        "patient_revenue_ledger": {"count": len(ledger_items), "items": ledger_items},
        "financial_summary": {
            "total_revenue": total_revenue,
            "revenue_breakdown": {
                "invoice_services": float(invoice_services_revenue),
                "appointments": float(appointments_revenue),
                "pharmacy": float(pharmacy_revenue),
                "ai_diagnostics": float(ai_revenue),
                "ai_unit_charge": ai_unit_charge,
            },
            "total_operational_spend": total_spend,
            "spend_breakdown": {
                "staff_salaries": float((expense_row.staff_salary_spend if expense_row else 0) or 0),
                "medicine_stock": float((expense_row.medicine_stock_spend if expense_row else 0) or 0),
                "fleet_fuel": float((expense_row.fleet_fuel_spend if expense_row else 0) or 0),
                "ot_supplies": float((expense_row.ot_supplies_spend if expense_row else 0) or 0),
            },
            "net_profit": net_profit,
        },
    }


@app.post("/finance/expenses")
def finance_add_expense(
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_accounts_roles(current_user)

    hospital_id = current_user["hospital_id"]
    expenses = models.TABLES["expenses"]

    category = str(payload.get("category") or "").strip().upper().replace(" ", "_")
    amount = payload.get("amount")
    date_incurred = str(payload.get("date_incurred") or "").strip()
    description = (payload.get("description") or "").strip() or None

    if not category:
        raise HTTPException(status_code=400, detail="category is required")
    if amount is None:
        raise HTTPException(status_code=400, detail="amount is required")
    try:
        amount = float(amount)
    except Exception:
        raise HTTPException(status_code=400, detail="amount must be numeric")
    if amount <= 0:
        raise HTTPException(status_code=400, detail="amount must be greater than 0")
    if not date_incurred:
        date_incurred = date.today().isoformat()

    result = db.execute(
        insert(expenses).values(
            hospital_id=hospital_id,
            category=category,
            amount=amount,
            date_incurred=date_incurred,
            description=description,
            recorded_by_staff_id=_get_current_staff_id(db, current_user),
        )
    )
    db.commit()

    expense_id = result.inserted_primary_key[0] if result.inserted_primary_key else None
    row = db.execute(
        select(expenses)
        .where(expenses.c.hospital_id == hospital_id)
        .where(expenses.c.expense_id == expense_id)
    ).first()
    return {"status": "saved", "item": _serialize_row(row) if row else None}


@app.get("/finance/expenses")
def finance_list_expenses(
    month: Optional[str] = Query(default=None, description="YYYY-MM optional filter"),
    limit: int = Query(default=300, ge=1, le=2000),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_accounts_roles(current_user)

    hospital_id = current_user["hospital_id"]
    expenses = models.TABLES["expenses"]
    query = (
        select(expenses)
        .where(expenses.c.hospital_id == hospital_id)
        .order_by(expenses.c.date_incurred.desc(), expenses.c.expense_id.desc())
    )
    if month:
        try:
            base = datetime.strptime(f"{month}-01", "%Y-%m-%d")
            month_start = base.strftime("%Y-%m-%d")
            if base.month == 12:
                month_end = f"{base.year + 1}-01-01"
            else:
                month_end = f"{base.year}-{base.month + 1:02d}-01"
            query = query.where(expenses.c.date_incurred >= month_start).where(expenses.c.date_incurred < month_end)
        except Exception:
            raise HTTPException(status_code=400, detail="month must be YYYY-MM")

    rows = db.execute(query.limit(limit)).fetchall()
    return {"count": len(rows), "items": [_serialize_row(r) for r in rows]}


@app.post("/finance/payments/record")
def finance_record_payment(
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_accounts_roles(current_user)

    hospital_id = current_user["hospital_id"]
    invoices = models.TABLES["invoices"]
    payments = models.TABLES["payments"]

    invoice_id = int(payload.get("invoice_id") or 0)
    amount_paid = payload.get("amount_paid")
    payment_method = str(payload.get("payment_method") or "CASH").strip().upper()
    payment_reference = (payload.get("payment_reference") or "").strip() or None

    if invoice_id <= 0:
        raise HTTPException(status_code=400, detail="invoice_id is required")
    if amount_paid is None:
        raise HTTPException(status_code=400, detail="amount_paid is required")
    try:
        amount_paid = float(amount_paid)
    except Exception:
        raise HTTPException(status_code=400, detail="amount_paid must be numeric")
    if amount_paid <= 0:
        raise HTTPException(status_code=400, detail="amount_paid must be greater than 0")

    invoice = db.execute(
        select(invoices)
        .where(invoices.c.hospital_id == hospital_id)
        .where(invoices.c.invoice_id == invoice_id)
    ).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    result = db.execute(
        insert(payments).values(
            hospital_id=hospital_id,
            invoice_id=invoice_id,
            amount_paid=amount_paid,
            payment_method=payment_method,
            payment_reference=payment_reference,
            collected_by_staff_id=_get_current_staff_id(db, current_user),
        )
    )

    paid_total = float(
        db.execute(
            select(func.coalesce(func.sum(payments.c.amount_paid), 0))
            .where(payments.c.hospital_id == hospital_id)
            .where(payments.c.invoice_id == invoice_id)
        ).scalar()
        or 0
    )
    net_amount = float(invoice.net_amount or 0)
    if net_amount <= 0:
        next_status = "PAID"
    elif paid_total >= net_amount:
        next_status = "PAID"
    elif paid_total > 0:
        next_status = "PARTIAL"
    else:
        next_status = "UNPAID"

    db.execute(
        update(invoices)
        .where(invoices.c.hospital_id == hospital_id)
        .where(invoices.c.invoice_id == invoice_id)
        .values(status=next_status)
    )
    db.commit()

    payment_id = result.inserted_primary_key[0] if result.inserted_primary_key else None
    payment_row = db.execute(
        select(payments)
        .where(payments.c.hospital_id == hospital_id)
        .where(payments.c.payment_id == payment_id)
    ).first()

    return {
        "status": "recorded",
        "payment": _serialize_row(payment_row) if payment_row else None,
        "invoice": {
            "invoice_id": invoice_id,
            "invoice_number": invoice.invoice_number,
            "net_amount": net_amount,
            "paid_total": paid_total,
            "status": next_status,
        },
    }


@app.get("/finance/monthly-statement")
def finance_monthly_statement(
    month: Optional[str] = Query(default=None, description="YYYY-MM"),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_accounts_roles(current_user)

    statement_month = month or datetime.utcnow().strftime("%Y-%m")
    snapshot = finance_command_center(
        month=statement_month,
        ledger_limit=2000,
        db=db,
        current_user=current_user,
    )
    summary = snapshot["financial_summary"]
    ledger = snapshot["patient_revenue_ledger"]["items"]

    lines = [
        "Section,Metric,Value",
        f"Summary,Month,{statement_month}",
        f"Summary,Total Revenue,{summary['total_revenue']}",
        f"Summary,Revenue Appointments,{summary['revenue_breakdown']['appointments']}",
        f"Summary,Revenue Pharmacy,{summary['revenue_breakdown']['pharmacy']}",
        f"Summary,Revenue AI Diagnostics,{summary['revenue_breakdown']['ai_diagnostics']}",
        f"Summary,Total Operational Spend,{summary['total_operational_spend']}",
        f"Summary,Spend Staff Salaries,{summary['spend_breakdown']['staff_salaries']}",
        f"Summary,Spend Medicine Stock,{summary['spend_breakdown']['medicine_stock']}",
        f"Summary,Net Profit,{summary['net_profit']}",
        "",
        "Ledger,Invoice Number,Patient MRN,Patient Name,Net Amount,Paid Amount,Billing Status,Invoice Date",
    ]
    for row in ledger:
        lines.append(
            f"Ledger,{row.get('invoice_number')},{row.get('patient_mrn')},{row.get('patient_name')},{row.get('net_amount')},{row.get('paid_amount')},{row.get('billing_status')},{row.get('invoice_date')}"
        )

    csv_blob = "\n".join(lines)
    return {
        "file_name": f"medx_financial_statement_{statement_month}.csv",
        "month": statement_month,
        "summary": summary,
        "ledger_count": len(ledger),
        "csv": csv_blob,
    }


@app.get("/fleet/vehicles")
def fleet_list_vehicles(
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=300, ge=1, le=2000),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_fleet_roles(current_user)
    _ensure_fleet_auxiliary_tables(db)

    hospital_id = current_user["hospital_id"]
    fleet = models.TABLES["fleet_management"]
    trip_logs = models.TABLES["fleet_trip_logs"]
    fuel_logs = models.TABLES["fleet_fuel_logs"]
    query = (
        select(fleet)
        .where(fleet.c.hospital_id == hospital_id)
        .order_by(fleet.c.created_at.desc(), fleet.c.fleet_id.desc())
    )
    if status:
        query = query.where(fleet.c.status == _normalize_fleet_status(status))

    rows = db.execute(query.limit(limit)).fetchall()
    items: List[Dict[str, Any]] = []
    for r in rows:
        item = _serialize_row(r)
        fleet_id = int(item.get("fleet_id") or 0)
        total_trips = int(
            db.execute(
                select(func.count(trip_logs.c.trip_id))
                .where(trip_logs.c.hospital_id == hospital_id)
                .where(trip_logs.c.fleet_id == fleet_id)
            ).scalar()
            or 0
        )
        total_fuel_cost = float(
            db.execute(
                select(func.coalesce(func.sum(fuel_logs.c.cost_amount), 0))
                .where(fuel_logs.c.hospital_id == hospital_id)
                .where(fuel_logs.c.fleet_id == fleet_id)
            ).scalar()
            or 0
        )
        total_fuel_liters = float(
            db.execute(
                select(func.coalesce(func.sum(fuel_logs.c.liters), 0))
                .where(fuel_logs.c.hospital_id == hospital_id)
                .where(fuel_logs.c.fleet_id == fleet_id)
            ).scalar()
            or 0
        )
        last_trip = db.execute(
            select(trip_logs)
            .where(trip_logs.c.hospital_id == hospital_id)
            .where(trip_logs.c.fleet_id == fleet_id)
            .order_by(trip_logs.c.started_at.desc(), trip_logs.c.trip_id.desc())
            .limit(1)
        ).first()
        item["metrics"] = {
            "total_trips": total_trips,
            "total_fuel_cost": total_fuel_cost,
            "total_fuel_liters": total_fuel_liters,
        }
        item["last_trip"] = _serialize_row(last_trip) if last_trip else None
        items.append(item)

    summary = {
        "fleet_count": len(items),
        "total_trips": int(sum((i.get("metrics") or {}).get("total_trips", 0) for i in items)),
        "total_fuel_cost": float(sum((i.get("metrics") or {}).get("total_fuel_cost", 0) for i in items)),
        "total_fuel_liters": float(sum((i.get("metrics") or {}).get("total_fuel_liters", 0) for i in items)),
    }
    return {
        "count": len(items),
        "items": items,
        "summary": summary,
        "status_counts": {
            "FREE": len([x for x in items if x.get("status") == "FREE"]),
            "ON_MISSION": len([x for x in items if x.get("status") == "ON_MISSION"]),
            "IN_MAINTENANCE": len([x for x in items if x.get("status") == "IN_MAINTENANCE"]),
        },
    }


@app.post("/fleet/vehicles")
def fleet_register_vehicle(
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_fleet_roles(current_user)
    _ensure_fleet_auxiliary_tables(db)

    hospital_id = current_user["hospital_id"]
    fleet = models.TABLES["fleet_management"]

    plate_number = str(payload.get("plate_number") or "").strip().upper()
    vehicle_type = str(payload.get("vehicle_type") or "").strip().upper().replace(" ", "_")
    model_name = (payload.get("model_name") or "").strip() or None
    assigned_driver = (payload.get("assigned_driver") or "").strip() or None
    mission_patient_name = (payload.get("mission_patient_name") or "").strip() or None
    status = _normalize_fleet_status(payload.get("status") or "FREE")
    destination = (payload.get("destination") or "").strip() or None
    eta_return = (payload.get("eta_return") or "").strip() or None
    notes = (payload.get("notes") or "").strip() or None

    if not plate_number:
        raise HTTPException(status_code=400, detail="plate_number is required")
    if not vehicle_type:
        raise HTTPException(status_code=400, detail="vehicle_type is required")

    result = db.execute(
        insert(fleet).values(
            hospital_id=hospital_id,
            plate_number=plate_number,
            vehicle_type=vehicle_type,
            model_name=model_name,
            assigned_driver=assigned_driver,
            mission_patient_name=mission_patient_name,
            status=status,
            destination=destination,
            eta_return=eta_return,
            notes=notes,
            updated_at=datetime.utcnow().isoformat(),
        )
    )
    staff_id = _get_current_staff_id(db, current_user)
    _log_activity_audit(
        db,
        hospital_id=hospital_id,
        actor_user_id=current_user.get("user_id"),
        actor_staff_id=staff_id,
        actor_role=current_user.get("role_name"),
        module="FLEET",
        action="VEHICLE_REGISTERED",
        entity_type="FLEET_VEHICLE",
        entity_id=int(result.inserted_primary_key[0]) if result.inserted_primary_key else None,
        details={
            "plate_number": plate_number,
            "vehicle_type": vehicle_type,
            "status": status,
        },
    )
    db.commit()

    fleet_id = result.inserted_primary_key[0] if result.inserted_primary_key else None
    row = db.execute(
        select(fleet)
        .where(fleet.c.hospital_id == hospital_id)
        .where(fleet.c.fleet_id == fleet_id)
    ).first()
    return {"status": "registered", "item": _serialize_row(row) if row else None}


@app.post("/fleet/vehicles/{fleet_id}/status")
def fleet_update_vehicle_status(
    fleet_id: int,
    payload: Dict[str, Any] = Body(default={}),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_fleet_roles(current_user)
    _ensure_fleet_auxiliary_tables(db)

    hospital_id = current_user["hospital_id"]
    fleet = models.TABLES["fleet_management"]

    row = db.execute(
        select(fleet)
        .where(fleet.c.hospital_id == hospital_id)
        .where(fleet.c.fleet_id == fleet_id)
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Vehicle not found")

    next_status = _normalize_fleet_status(payload.get("status") or row.status)
    destination = (payload.get("destination") or "").strip() if payload.get("destination") is not None else row.destination
    eta_return = (payload.get("eta_return") or "").strip() if payload.get("eta_return") is not None else row.eta_return
    assigned_driver = (payload.get("assigned_driver") or "").strip() if payload.get("assigned_driver") is not None else row.assigned_driver
    mission_patient_name = (payload.get("mission_patient_name") or "").strip() if payload.get("mission_patient_name") is not None else row.mission_patient_name
    notes = (payload.get("notes") or "").strip() if payload.get("notes") is not None else row.notes

    if next_status == "FREE":
        destination = None
        eta_return = None
        mission_patient_name = None

    db.execute(
        update(fleet)
        .where(fleet.c.hospital_id == hospital_id)
        .where(fleet.c.fleet_id == fleet_id)
        .values(
            status=next_status,
            destination=destination or None,
            eta_return=eta_return or None,
            assigned_driver=assigned_driver or None,
            mission_patient_name=mission_patient_name or None,
            notes=notes or None,
            updated_at=datetime.utcnow().isoformat(),
        )
    )
    _log_activity_audit(
        db,
        hospital_id=hospital_id,
        actor_user_id=current_user.get("user_id"),
        actor_staff_id=_get_current_staff_id(db, current_user),
        actor_role=current_user.get("role_name"),
        module="FLEET",
        action="VEHICLE_STATUS_UPDATED",
        entity_type="FLEET_VEHICLE",
        entity_id=fleet_id,
        details={
            "status": next_status,
            "destination": destination,
            "assigned_driver": assigned_driver,
            "mission_patient_name": mission_patient_name,
        },
    )
    db.commit()

    updated = db.execute(
        select(fleet)
        .where(fleet.c.hospital_id == hospital_id)
        .where(fleet.c.fleet_id == fleet_id)
    ).first()
    return {"status": "updated", "item": _serialize_row(updated) if updated else None}


@app.post("/fleet/vehicles/{fleet_id}/trips")
def fleet_add_trip_log(
    fleet_id: int,
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_fleet_roles(current_user)
    _ensure_fleet_auxiliary_tables(db)

    hospital_id = current_user["hospital_id"]
    fleet = models.TABLES["fleet_management"]
    trip_logs = models.TABLES["fleet_trip_logs"]

    vehicle = db.execute(
        select(fleet)
        .where(fleet.c.hospital_id == hospital_id)
        .where(fleet.c.fleet_id == fleet_id)
    ).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")

    destination = (payload.get("destination") or "").strip() or None
    patient_name = (payload.get("patient_name") or "").strip() or None
    assigned_driver = (payload.get("assigned_driver") or "").strip() or vehicle.assigned_driver
    trip_status = str(payload.get("trip_status") or "COMPLETED").strip().upper()
    if trip_status not in {"ONGOING", "COMPLETED", "CANCELLED"}:
        raise HTTPException(status_code=400, detail="trip_status must be ONGOING, COMPLETED, or CANCELLED")

    result = db.execute(
        insert(trip_logs).values(
            hospital_id=hospital_id,
            fleet_id=fleet_id,
            destination=destination or vehicle.destination,
            patient_name=patient_name,
            assigned_driver=assigned_driver,
            trip_status=trip_status,
            started_at=(payload.get("started_at") or datetime.utcnow().isoformat()),
            ended_at=(payload.get("ended_at") or None),
            notes=(payload.get("notes") or None),
            created_by_staff_id=_get_current_staff_id(db, current_user),
            created_at=datetime.utcnow().isoformat(),
        )
    )

    next_fleet_status = "ON_MISSION" if trip_status == "ONGOING" else "FREE"
    db.execute(
        update(fleet)
        .where(fleet.c.hospital_id == hospital_id)
        .where(fleet.c.fleet_id == fleet_id)
        .values(
            status=next_fleet_status,
            destination=destination if next_fleet_status == "ON_MISSION" else None,
            assigned_driver=assigned_driver,
            mission_patient_name=patient_name if next_fleet_status == "ON_MISSION" else None,
            updated_at=datetime.utcnow().isoformat(),
        )
    )
    _log_activity_audit(
        db,
        hospital_id=hospital_id,
        actor_user_id=current_user.get("user_id"),
        actor_staff_id=_get_current_staff_id(db, current_user),
        actor_role=current_user.get("role_name"),
        module="FLEET",
        action="TRIP_LOGGED",
        entity_type="FLEET_VEHICLE",
        entity_id=fleet_id,
        details={"trip_status": trip_status, "destination": destination, "patient_name": patient_name},
    )
    db.commit()

    trip_id = result.inserted_primary_key[0] if result.inserted_primary_key else None
    row = db.execute(
        select(trip_logs)
        .where(trip_logs.c.hospital_id == hospital_id)
        .where(trip_logs.c.trip_id == trip_id)
    ).first()
    return {"status": "logged", "item": _serialize_row(row) if row else None}


@app.post("/fleet/vehicles/{fleet_id}/fuel-logs")
def fleet_add_fuel_log(
    fleet_id: int,
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_fleet_roles(current_user)
    _ensure_fleet_auxiliary_tables(db)

    hospital_id = current_user["hospital_id"]
    fleet = models.TABLES["fleet_management"]
    fuel_logs = models.TABLES["fleet_fuel_logs"]
    expenses = models.TABLES["expenses"]

    vehicle = db.execute(
        select(fleet)
        .where(fleet.c.hospital_id == hospital_id)
        .where(fleet.c.fleet_id == fleet_id)
    ).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")

    liters = float(payload.get("liters") or 0)
    cost_amount = float(payload.get("cost_amount") or 0)
    if liters <= 0:
        raise HTTPException(status_code=400, detail="liters must be greater than 0")
    if cost_amount <= 0:
        raise HTTPException(status_code=400, detail="cost_amount must be greater than 0")

    fuel_date = str(payload.get("fuel_date") or date.today().isoformat())
    notes = (payload.get("notes") or "").strip() or None
    staff_id = _get_current_staff_id(db, current_user)

    expense_result = db.execute(
        insert(expenses).values(
            hospital_id=hospital_id,
            category="FLEET_FUEL",
            amount=cost_amount,
            date_incurred=fuel_date,
            description=f"Fuel for {vehicle.plate_number}: {notes or 'Fleet refuel'}",
            recorded_by_staff_id=staff_id,
        )
    )
    expense_id = expense_result.inserted_primary_key[0] if expense_result.inserted_primary_key else None

    result = db.execute(
        insert(fuel_logs).values(
            hospital_id=hospital_id,
            fleet_id=fleet_id,
            liters=liters,
            cost_amount=cost_amount,
            fuel_date=fuel_date,
            notes=notes,
            expense_id=expense_id,
            created_by_staff_id=staff_id,
            created_at=datetime.utcnow().isoformat(),
        )
    )
    _log_activity_audit(
        db,
        hospital_id=hospital_id,
        actor_user_id=current_user.get("user_id"),
        actor_staff_id=staff_id,
        actor_role=current_user.get("role_name"),
        module="FLEET",
        action="FUEL_LOGGED",
        entity_type="FLEET_VEHICLE",
        entity_id=fleet_id,
        details={"liters": liters, "cost_amount": cost_amount, "fuel_date": fuel_date, "expense_id": expense_id},
    )
    db.commit()

    fuel_log_id = result.inserted_primary_key[0] if result.inserted_primary_key else None
    row = db.execute(
        select(fuel_logs)
        .where(fuel_logs.c.hospital_id == hospital_id)
        .where(fuel_logs.c.fuel_log_id == fuel_log_id)
    ).first()
    return {"status": "logged", "item": _serialize_row(row) if row else None, "expense_id": expense_id}


@app.get("/fleet/vehicles/{fleet_id}/history")
def fleet_vehicle_history(
    fleet_id: int,
    trip_limit: int = Query(default=100, ge=1, le=1000),
    fuel_limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_fleet_roles(current_user)
    _ensure_fleet_auxiliary_tables(db)

    hospital_id = current_user["hospital_id"]
    fleet = models.TABLES["fleet_management"]
    trip_logs = models.TABLES["fleet_trip_logs"]
    fuel_logs = models.TABLES["fleet_fuel_logs"]

    vehicle = db.execute(
        select(fleet)
        .where(fleet.c.hospital_id == hospital_id)
        .where(fleet.c.fleet_id == fleet_id)
    ).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")

    trips = db.execute(
        select(trip_logs)
        .where(trip_logs.c.hospital_id == hospital_id)
        .where(trip_logs.c.fleet_id == fleet_id)
        .order_by(trip_logs.c.started_at.desc(), trip_logs.c.trip_id.desc())
        .limit(trip_limit)
    ).fetchall()
    fuels = db.execute(
        select(fuel_logs)
        .where(fuel_logs.c.hospital_id == hospital_id)
        .where(fuel_logs.c.fleet_id == fleet_id)
        .order_by(fuel_logs.c.fuel_date.desc(), fuel_logs.c.fuel_log_id.desc())
        .limit(fuel_limit)
    ).fetchall()

    return {
        "vehicle": _serialize_row(vehicle),
        "trips": [_serialize_row(r) for r in trips],
        "fuel_logs": [_serialize_row(r) for r in fuels],
    }


def _staff_department_name(db: Session, hospital_id: int, staff_id: Optional[int]) -> Optional[str]:
    if not staff_id:
        return None
    staff = models.TABLES.get("staff")
    departments = models.TABLES.get("departments")
    if staff is None or departments is None:
        return None
    row = db.execute(
        select(departments.c.department_name)
        .select_from(
            staff.outerjoin(
                departments,
                (staff.c.hospital_id == departments.c.hospital_id)
                & (staff.c.department_id == departments.c.department_id),
            )
        )
        .where(staff.c.hospital_id == hospital_id)
        .where(staff.c.staff_id == int(staff_id))
    ).first()
    return str(row.department_name).strip() if row and row.department_name else None


@app.get("/operations/units")
def operations_list_units(
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_roles(current_user, {"OPERATIONS", "NURSE", "DOCTOR", "ADMIN", "SUPER_ADMIN"})
    _ensure_operational_units_table(db)

    hospital_id = current_user["hospital_id"]
    units = models.TABLES["operational_units"]
    beds = models.TABLES["beds"]
    ots = models.TABLES["operation_theaters"] if models.TABLES.get("operation_theaters") is not None else None

    rows = db.execute(
        select(units)
        .where(units.c.hospital_id == hospital_id)
        .where(units.c.is_active == 1)
        .order_by(units.c.unit_type.asc(), units.c.unit_name.asc())
    ).fetchall()

    items: List[Dict[str, Any]] = []
    for row in rows:
        item = _serialize_row(row)
        unit_type = str(item.get("unit_type") or "")
        unit_name = str(item.get("unit_name") or "")
        if unit_type in {"WARD", "ICU"}:
            counts = db.execute(
                select(
                    func.count(beds.c.bed_id).label("total_beds"),
                    func.coalesce(func.sum(case((beds.c.status == "FREE", 1), else_=0)), 0).label("free_beds"),
                    func.coalesce(func.sum(case((beds.c.status == "OCCUPIED", 1), else_=0)), 0).label("occupied_beds"),
                    func.coalesce(func.sum(case((beds.c.status == "CLEANING", 1), else_=0)), 0).label("cleaning_beds"),
                )
                .where(beds.c.hospital_id == hospital_id)
                .where(beds.c.unit_type == unit_type)
                .where(beds.c.ward_name == unit_name)
            ).first()
            item["bed_summary"] = {
                "total_beds": int((counts.total_beds if counts else 0) or 0),
                "free_beds": int((counts.free_beds if counts else 0) or 0),
                "occupied_beds": int((counts.occupied_beds if counts else 0) or 0),
                "cleaning_beds": int((counts.cleaning_beds if counts else 0) or 0),
            }
        else:
            ot_status = item.get("status") or "AVAILABLE"
            if ots is not None:
                ot_row = db.execute(
                    select(ots.c.status)
                    .where(ots.c.hospital_id == hospital_id)
                    .where(ots.c.room_number == unit_name)
                ).first()
                if ot_row and ot_row.status:
                    ot_status = ot_row.status
            item["status"] = ot_status
        items.append(item)

    return {"count": len(items), "items": items}


@app.post("/operations/units")
async def operations_create_unit(
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_roles(current_user, {"OPERATIONS", "ADMIN", "SUPER_ADMIN"})
    _ensure_operational_units_table(db)

    hospital_id = current_user["hospital_id"]
    units = models.TABLES["operational_units"]
    beds = models.TABLES["beds"]
    ots = models.TABLES["operation_theaters"] if models.TABLES.get("operation_theaters") is not None else None
    staff_id = _get_current_staff_id(db, current_user)

    unit_name = str(payload.get("unit_name") or "").strip()
    unit_type = _normalize_unit_type(payload.get("unit_type"))
    total_beds = int(payload.get("total_beds") or 0)
    if not unit_name:
        raise HTTPException(status_code=400, detail="unit_name is required")
    if unit_type in {"WARD", "ICU"} and total_beds <= 0:
        raise HTTPException(status_code=400, detail="total_beds must be greater than 0 for WARD/ICU")
    if unit_type == "OT":
        total_beds = 0

    existing = db.execute(
        select(units)
        .where(units.c.hospital_id == hospital_id)
        .where(units.c.unit_name == unit_name)
        .where(units.c.unit_type == unit_type)
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Unit with this name and type already exists")

    unit_status = "ACTIVE"
    if unit_type == "OT":
        unit_status = _normalize_ot_status(payload.get("status") or "AVAILABLE")

    result = db.execute(
        insert(units).values(
            hospital_id=hospital_id,
            unit_name=unit_name,
            unit_type=unit_type,
            total_beds=total_beds,
            status=unit_status,
            is_active=1,
            updated_at=datetime.utcnow().isoformat(),
        )
    )
    unit_id = result.inserted_primary_key[0] if result.inserted_primary_key else None

    if unit_type in {"WARD", "ICU"}:
        for index in range(1, total_beds + 1):
            bed_number = f"{unit_type[:1]}-{int(unit_id)}-{index:03d}"
            db.execute(
                insert(beds).values(
                    hospital_id=hospital_id,
                    unit_type=unit_type,
                    ward_name=unit_name,
                    bed_number=bed_number,
                    status="FREE",
                    is_occupied=0,
                    current_patient_id=None,
                    daily_charge=0,
                    updated_at=datetime.utcnow().isoformat(),
                )
            )
    elif unit_type == "OT" and ots is not None:
        existing_ot = db.execute(
            select(ots)
            .where(ots.c.hospital_id == hospital_id)
            .where(ots.c.room_number == unit_name)
        ).first()
        if existing_ot:
            db.execute(
                update(ots)
                .where(ots.c.hospital_id == hospital_id)
                .where(ots.c.ot_id == existing_ot.ot_id)
                .values(status=unit_status, is_active=1)
            )
        else:
            db.execute(
                insert(ots).values(
                    hospital_id=hospital_id,
                    room_number=unit_name,
                    status=unit_status,
                    hourly_charge=float(payload.get("hourly_charge") or 0),
                    is_active=1,
                )
            )

    _log_activity_audit(
        db,
        hospital_id=hospital_id,
        actor_user_id=current_user.get("user_id"),
        actor_staff_id=staff_id,
        actor_role=current_user.get("role_name"),
        module="OPERATIONS",
        action="UNIT_CREATED",
        entity_type="OPERATIONAL_UNIT",
        entity_id=int(unit_id or 0) or None,
        details={"unit_name": unit_name, "unit_type": unit_type, "total_beds": total_beds, "status": unit_status},
    )
    db.commit()

    created = db.execute(
        select(units)
        .where(units.c.hospital_id == hospital_id)
        .where(units.c.unit_id == unit_id)
    ).first()
    await bed_sync_hub.broadcast(
        hospital_id,
        "unit_config_updated",
        {"unit_id": unit_id, "unit_name": unit_name, "unit_type": unit_type, "action": "created"},
    )
    return {"status": "created", "item": _serialize_row(created) if created else None}


@app.put("/operations/units/{unit_id}")
async def operations_update_unit(
    unit_id: int,
    payload: Dict[str, Any] = Body(default={}),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_roles(current_user, {"OPERATIONS", "ADMIN", "SUPER_ADMIN"})
    _ensure_operational_units_table(db)

    hospital_id = current_user["hospital_id"]
    units = models.TABLES["operational_units"]
    beds = models.TABLES["beds"]
    ots = models.TABLES["operation_theaters"] if models.TABLES.get("operation_theaters") is not None else None

    unit_row = db.execute(
        select(units)
        .where(units.c.hospital_id == hospital_id)
        .where(units.c.unit_id == unit_id)
    ).first()
    if not unit_row:
        raise HTTPException(status_code=404, detail="Operational unit not found")

    unit_type = str(unit_row.unit_type or "")
    unit_name = str(payload.get("unit_name") or unit_row.unit_name).strip()
    next_status = payload.get("status")
    update_values: Dict[str, Any] = {"unit_name": unit_name, "updated_at": datetime.utcnow().isoformat()}

    if unit_type == "OT":
        update_values["status"] = _normalize_ot_status(next_status or unit_row.status or "AVAILABLE")
    else:
        update_values["status"] = str(next_status or unit_row.status or "ACTIVE").strip().upper()

    if unit_type in {"WARD", "ICU"} and payload.get("total_beds") is not None:
        target_beds = int(payload.get("total_beds") or 0)
        if target_beds <= 0:
            raise HTTPException(status_code=400, detail="total_beds must be greater than 0")

        current_beds = db.execute(
            select(beds)
            .where(beds.c.hospital_id == hospital_id)
            .where(beds.c.unit_type == unit_type)
            .where(beds.c.ward_name == unit_row.unit_name)
            .order_by(beds.c.bed_id.asc())
        ).fetchall()
        current_count = len(current_beds)
        if target_beds > current_count:
            for index in range(current_count + 1, target_beds + 1):
                bed_number = f"{unit_type[:1]}-{unit_id}-{index:03d}"
                db.execute(
                    insert(beds).values(
                        hospital_id=hospital_id,
                        unit_type=unit_type,
                        ward_name=unit_name,
                        bed_number=bed_number,
                        status="FREE",
                        is_occupied=0,
                        current_patient_id=None,
                        daily_charge=0,
                        updated_at=datetime.utcnow().isoformat(),
                    )
                )
        elif target_beds < current_count:
            removable = db.execute(
                select(beds.c.bed_id)
                .where(beds.c.hospital_id == hospital_id)
                .where(beds.c.unit_type == unit_type)
                .where(beds.c.ward_name == unit_row.unit_name)
                .where(beds.c.status == "FREE")
                .where(beds.c.is_occupied == 0)
                .order_by(beds.c.bed_id.desc())
                .limit(current_count - target_beds)
            ).fetchall()
            if len(removable) < (current_count - target_beds):
                raise HTTPException(status_code=400, detail="Reduce occupied/cleaning beds before lowering total bed count")
            removable_ids = [int(r.bed_id) for r in removable]
            if removable_ids:
                db.execute(
                    delete(beds)
                    .where(beds.c.hospital_id == hospital_id)
                    .where(beds.c.bed_id.in_(removable_ids))
                )
        update_values["total_beds"] = target_beds

    db.execute(
        update(units)
        .where(units.c.hospital_id == hospital_id)
        .where(units.c.unit_id == unit_id)
        .values(**update_values)
    )

    if unit_type in {"WARD", "ICU"} and (unit_name != str(unit_row.unit_name or "")):
        db.execute(
            update(beds)
            .where(beds.c.hospital_id == hospital_id)
            .where(beds.c.unit_type == unit_type)
            .where(beds.c.ward_name == unit_row.unit_name)
            .values(ward_name=unit_name, updated_at=datetime.utcnow().isoformat())
        )
    if unit_type == "OT" and ots is not None:
        db.execute(
            update(ots)
            .where(ots.c.hospital_id == hospital_id)
            .where(ots.c.room_number == unit_row.unit_name)
            .values(room_number=unit_name, status=update_values.get("status"), is_active=1)
        )

    _log_activity_audit(
        db,
        hospital_id=hospital_id,
        actor_user_id=current_user.get("user_id"),
        actor_staff_id=_get_current_staff_id(db, current_user),
        actor_role=current_user.get("role_name"),
        module="OPERATIONS",
        action="UNIT_UPDATED",
        entity_type="OPERATIONAL_UNIT",
        entity_id=unit_id,
        details={"unit_name": unit_name, "unit_type": unit_type, "changes": update_values},
    )
    db.commit()

    updated = db.execute(
        select(units)
        .where(units.c.hospital_id == hospital_id)
        .where(units.c.unit_id == unit_id)
    ).first()
    await bed_sync_hub.broadcast(
        hospital_id,
        "unit_config_updated",
        {"unit_id": unit_id, "unit_name": unit_name, "unit_type": unit_type, "action": "updated"},
    )
    return {"status": "updated", "item": _serialize_row(updated) if updated else None}


@app.get("/operations/beds")
def operations_list_beds(
    unit_type: Optional[str] = Query(default=None),
    ward_name: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=500, ge=1, le=2000),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_roles(current_user, {"OPERATIONS", "NURSE", "DOCTOR", "ADMIN", "SUPER_ADMIN"})
    _ensure_operational_units_table(db)

    hospital_id = current_user["hospital_id"]
    beds = models.TABLES["beds"]
    patients = models.TABLES["patients"]

    query = (
        select(
            beds,
            patients.c.full_name.label("patient_name"),
            patients.c.patient_mrn.label("patient_mrn"),
        )
        .select_from(
            beds.outerjoin(
                patients,
                (beds.c.hospital_id == patients.c.hospital_id)
                & (beds.c.current_patient_id == patients.c.patient_id),
            )
        )
        .where(beds.c.hospital_id == hospital_id)
        .order_by(beds.c.unit_type.asc(), beds.c.ward_name.asc(), beds.c.bed_number.asc())
    )
    if unit_type:
        query = query.where(beds.c.unit_type == _normalize_unit_type(unit_type))
    if ward_name:
        query = query.where(beds.c.ward_name == str(ward_name).strip())
    if status:
        query = query.where(beds.c.status == _normalize_bed_status(status))

    rows = db.execute(query.limit(limit)).fetchall()
    items = [_serialize_row(r) for r in rows]
    return {
        "count": len(items),
        "items": items,
        "summary": {
            "free": len([x for x in items if x.get("status") == "FREE"]),
            "occupied": len([x for x in items if x.get("status") == "OCCUPIED"]),
            "cleaning": len([x for x in items if x.get("status") == "CLEANING"]),
        },
    }


@app.post("/operations/beds/{bed_id}/status")
async def operations_update_bed_status(
    bed_id: int,
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_roles(current_user, {"OPERATIONS", "NURSE", "ADMIN", "SUPER_ADMIN"})
    _ensure_operational_units_table(db)

    hospital_id = current_user["hospital_id"]
    beds = models.TABLES["beds"]
    patients = models.TABLES["patients"]
    admissions = models.TABLES["admissions"]

    row = db.execute(
        select(beds)
        .where(beds.c.hospital_id == hospital_id)
        .where(beds.c.bed_id == bed_id)
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Bed not found")

    next_status = _normalize_bed_status(payload.get("status"))
    requested_patient_id = int(payload.get("patient_id") or 0) if payload.get("patient_id") not in [None, ""] else None
    if next_status == "OCCUPIED" and not requested_patient_id:
        raise HTTPException(status_code=400, detail="patient_id is required when status is OCCUPIED")
    if requested_patient_id:
        patient = db.execute(
            select(patients.c.patient_id)
            .where(patients.c.hospital_id == hospital_id)
            .where(patients.c.patient_id == requested_patient_id)
        ).first()
        if not patient:
            raise HTTPException(status_code=404, detail="Patient not found")

    old_patient_id = int(row.current_patient_id) if row.current_patient_id not in [None, ""] else None
    update_values: Dict[str, Any] = {
        "status": next_status,
        "is_occupied": 1 if next_status == "OCCUPIED" else 0,
        "current_patient_id": requested_patient_id if next_status == "OCCUPIED" else None,
        "updated_at": datetime.utcnow().isoformat(),
    }
    db.execute(
        update(beds)
        .where(beds.c.hospital_id == hospital_id)
        .where(beds.c.bed_id == bed_id)
        .values(**update_values)
    )

    staff_id = _get_current_staff_id(db, current_user)
    if next_status == "OCCUPIED" and requested_patient_id:
        active_admission = db.execute(
            select(admissions)
            .where(admissions.c.hospital_id == hospital_id)
            .where(admissions.c.patient_id == requested_patient_id)
            .where(admissions.c.status == "ADMITTED")
            .order_by(admissions.c.admission_id.desc())
            .limit(1)
        ).first()
        if active_admission:
            db.execute(
                update(admissions)
                .where(admissions.c.hospital_id == hospital_id)
                .where(admissions.c.admission_id == active_admission.admission_id)
                .values(bed_id=bed_id, admitted_by_staff_id=staff_id, status="ADMITTED")
            )
        else:
            db.execute(
                insert(admissions).values(
                    hospital_id=hospital_id,
                    patient_id=requested_patient_id,
                    bed_id=bed_id,
                    admitted_by_staff_id=staff_id,
                    admission_date=datetime.utcnow().isoformat(),
                    status="ADMITTED",
                )
            )
    elif old_patient_id:
        db.execute(
            update(admissions)
            .where(admissions.c.hospital_id == hospital_id)
            .where(admissions.c.patient_id == old_patient_id)
            .where(admissions.c.status == "ADMITTED")
            .values(status="DISCHARGED", discharge_date=datetime.utcnow().isoformat())
        )

    _log_activity_audit(
        db,
        hospital_id=hospital_id,
        actor_user_id=current_user.get("user_id"),
        actor_staff_id=staff_id,
        actor_role=current_user.get("role_name"),
        module="BED",
        action="BED_STATUS_UPDATED",
        entity_type="BED",
        entity_id=bed_id,
        details={
            "from_status": row.status,
            "to_status": next_status,
            "old_patient_id": old_patient_id,
            "patient_id": requested_patient_id,
            "notes": payload.get("notes"),
        },
    )
    db.commit()

    updated = db.execute(
        select(
            beds,
            patients.c.full_name.label("patient_name"),
            patients.c.patient_mrn.label("patient_mrn"),
        )
        .select_from(
            beds.outerjoin(
                patients,
                (beds.c.hospital_id == patients.c.hospital_id)
                & (beds.c.current_patient_id == patients.c.patient_id),
            )
        )
        .where(beds.c.hospital_id == hospital_id)
        .where(beds.c.bed_id == bed_id)
    ).first()
    payload_out = _serialize_row(updated) if updated else {}
    await bed_sync_hub.broadcast(
        hospital_id,
        "bed_status_changed",
        {
            "bed_id": bed_id,
            "bed_number": payload_out.get("bed_number"),
            "ward_name": payload_out.get("ward_name"),
            "unit_type": payload_out.get("unit_type"),
            "status": payload_out.get("status"),
            "patient_id": payload_out.get("current_patient_id"),
        },
    )
    return {"status": "updated", "item": payload_out}


@app.get("/nurse/ward-beds")
def nurse_ward_beds(
    ward_name: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_roles(current_user, {"NURSE", "DOCTOR", "OPERATIONS", "ADMIN", "SUPER_ADMIN"})
    _ensure_operational_units_table(db)

    hospital_id = current_user["hospital_id"]
    beds = models.TABLES["beds"]
    patients = models.TABLES["patients"]
    staff_id = _get_current_staff_id(db, current_user)

    selected_ward = (ward_name or "").strip()
    if not selected_ward and str(current_user.get("role_name") or "").upper() == "NURSE":
        inferred = _staff_department_name(db, hospital_id, staff_id)
        if inferred:
            selected_ward = inferred

    query = (
        select(
            beds,
            patients.c.full_name.label("patient_name"),
            patients.c.patient_mrn.label("patient_mrn"),
        )
        .select_from(
            beds.outerjoin(
                patients,
                (beds.c.hospital_id == patients.c.hospital_id)
                & (beds.c.current_patient_id == patients.c.patient_id),
            )
        )
        .where(beds.c.hospital_id == hospital_id)
        .where(beds.c.unit_type.in_(["WARD", "ICU"]))
        .order_by(beds.c.ward_name.asc(), beds.c.bed_number.asc())
    )
    if selected_ward:
        query = query.where(beds.c.ward_name == selected_ward)

    rows = db.execute(query.limit(1200)).fetchall()
    items = [_serialize_row(r) for r in rows]
    return {
        "ward_name": selected_ward or None,
        "count": len(items),
        "items": items,
        "summary": {
            "free": len([x for x in items if x.get("status") == "FREE"]),
            "occupied": len([x for x in items if x.get("status") == "OCCUPIED"]),
            "cleaning": len([x for x in items if x.get("status") == "CLEANING"]),
        },
    }


@app.get("/doctor/bed-availability")
def doctor_bed_availability(
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_roles(current_user, {"DOCTOR", "ADMIN", "SUPER_ADMIN"})
    _ensure_operational_units_table(db)

    hospital_id = current_user["hospital_id"]
    beds = models.TABLES["beds"]

    rows = db.execute(
        select(
            beds.c.unit_type,
            beds.c.ward_name,
            func.count(beds.c.bed_id).label("total_beds"),
            func.coalesce(func.sum(case((beds.c.status == "FREE", 1), else_=0)), 0).label("free_beds"),
            func.coalesce(func.sum(case((beds.c.status == "OCCUPIED", 1), else_=0)), 0).label("occupied_beds"),
            func.coalesce(func.sum(case((beds.c.status == "CLEANING", 1), else_=0)), 0).label("cleaning_beds"),
        )
        .where(beds.c.hospital_id == hospital_id)
        .where(beds.c.unit_type.in_(["WARD", "ICU"]))
        .group_by(beds.c.unit_type, beds.c.ward_name)
        .order_by(beds.c.unit_type.asc(), beds.c.ward_name.asc())
    ).fetchall()

    units: List[Dict[str, Any]] = []
    for row in rows:
        free_beds = db.execute(
            select(beds.c.bed_id, beds.c.bed_number)
            .where(beds.c.hospital_id == hospital_id)
            .where(beds.c.unit_type == row.unit_type)
            .where(beds.c.ward_name == row.ward_name)
            .where(beds.c.status == "FREE")
            .order_by(beds.c.bed_number.asc())
            .limit(20)
        ).fetchall()
        units.append(
            {
                "unit_type": row.unit_type,
                "ward_name": row.ward_name,
                "total_beds": int(row.total_beds or 0),
                "free_beds": int(row.free_beds or 0),
                "occupied_beds": int(row.occupied_beds or 0),
                "cleaning_beds": int(row.cleaning_beds or 0),
                "free_bed_options": [{"bed_id": int(b.bed_id), "bed_number": b.bed_number} for b in free_beds],
            }
        )

    return {
        "count": len(units),
        "items": units,
        "totals": {
            "total_beds": int(sum(u["total_beds"] for u in units)),
            "free_beds": int(sum(u["free_beds"] for u in units)),
            "occupied_beds": int(sum(u["occupied_beds"] for u in units)),
            "cleaning_beds": int(sum(u["cleaning_beds"] for u in units)),
        },
    }


@app.post("/doctor/transfer-to-ward")
async def doctor_transfer_to_ward(
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_roles(current_user, {"DOCTOR", "ADMIN", "SUPER_ADMIN"})
    _ensure_operational_units_table(db)

    hospital_id = current_user["hospital_id"]
    patient_id = int(payload.get("patient_id") or 0)
    bed_id = int(payload.get("bed_id") or 0)
    if patient_id <= 0 or bed_id <= 0:
        raise HTTPException(status_code=400, detail="patient_id and bed_id are required")

    beds = models.TABLES["beds"]
    patients = models.TABLES["patients"]
    admissions = models.TABLES["admissions"]

    patient = db.execute(
        select(patients.c.patient_id)
        .where(patients.c.hospital_id == hospital_id)
        .where(patients.c.patient_id == patient_id)
    ).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    target_bed = db.execute(
        select(beds)
        .where(beds.c.hospital_id == hospital_id)
        .where(beds.c.bed_id == bed_id)
    ).first()
    if not target_bed:
        raise HTTPException(status_code=404, detail="Target bed not found")
    if str(target_bed.status or "").upper() != "FREE":
        raise HTTPException(status_code=400, detail="Target bed is not free")

    previous_bed = db.execute(
        select(beds)
        .where(beds.c.hospital_id == hospital_id)
        .where(beds.c.current_patient_id == patient_id)
        .where(beds.c.bed_id != bed_id)
        .where(beds.c.status == "OCCUPIED")
        .limit(1)
    ).first()

    if previous_bed:
        db.execute(
            update(beds)
            .where(beds.c.hospital_id == hospital_id)
            .where(beds.c.bed_id == previous_bed.bed_id)
            .values(
                status="FREE",
                is_occupied=0,
                current_patient_id=None,
                updated_at=datetime.utcnow().isoformat(),
            )
        )

    db.execute(
        update(beds)
        .where(beds.c.hospital_id == hospital_id)
        .where(beds.c.bed_id == bed_id)
        .values(
            status="OCCUPIED",
            is_occupied=1,
            current_patient_id=patient_id,
            updated_at=datetime.utcnow().isoformat(),
        )
    )

    staff_id = _get_current_staff_id(db, current_user)
    active_admission = db.execute(
        select(admissions)
        .where(admissions.c.hospital_id == hospital_id)
        .where(admissions.c.patient_id == patient_id)
        .where(admissions.c.status == "ADMITTED")
        .order_by(admissions.c.admission_id.desc())
        .limit(1)
    ).first()
    if active_admission:
        db.execute(
            update(admissions)
            .where(admissions.c.hospital_id == hospital_id)
            .where(admissions.c.admission_id == active_admission.admission_id)
            .values(bed_id=bed_id, admitted_by_staff_id=staff_id, status="ADMITTED")
        )
    else:
        db.execute(
            insert(admissions).values(
                hospital_id=hospital_id,
                patient_id=patient_id,
                bed_id=bed_id,
                admitted_by_staff_id=staff_id,
                admission_date=datetime.utcnow().isoformat(),
                status="ADMITTED",
            )
        )

    _log_activity_audit(
        db,
        hospital_id=hospital_id,
        actor_user_id=current_user.get("user_id"),
        actor_staff_id=staff_id,
        actor_role=current_user.get("role_name"),
        module="BED",
        action="TRANSFER_TO_WARD",
        entity_type="PATIENT",
        entity_id=patient_id,
        details={
            "to_bed_id": bed_id,
            "from_bed_id": int(previous_bed.bed_id) if previous_bed else None,
            "notes": payload.get("notes"),
        },
    )
    db.commit()

    await bed_sync_hub.broadcast(
        hospital_id,
        "bed_transfer",
        {
            "patient_id": patient_id,
            "to_bed_id": bed_id,
            "from_bed_id": int(previous_bed.bed_id) if previous_bed else None,
        },
    )
    return {
        "status": "transferred",
        "patient_id": patient_id,
        "to_bed_id": bed_id,
        "from_bed_id": int(previous_bed.bed_id) if previous_bed else None,
    }


@app.get("/operations/activity-audit")
def operations_activity_audit(
    module: Optional[str] = Query(default=None),
    limit: int = Query(default=400, ge=1, le=2000),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_roles(current_user, {"OPERATIONS", "ADMIN", "SUPER_ADMIN"})
    _ensure_activity_audit_table(db)

    hospital_id = current_user["hospital_id"]
    audit = models.TABLES["activity_audit"]
    query = (
        select(audit)
        .where(audit.c.hospital_id == hospital_id)
        .order_by(audit.c.created_at.desc(), audit.c.activity_id.desc())
    )
    if module:
        query = query.where(audit.c.module == str(module).strip().upper())
    rows = db.execute(query.limit(limit)).fetchall()
    items = [_serialize_row(r) for r in rows]
    for item in items:
        try:
            item["details_json"] = json.loads(item.get("details_json") or "{}")
        except Exception:
            item["details_json"] = {}
    return {"count": len(items), "items": items}


# ======================= SUPER ADMIN CONTROL CENTER =======================


def _security_control_get(db: Session, key: str) -> Optional[str]:
    table = models.TABLES.get("system_security_controls")
    if table is None:
        return None
    row = db.execute(select(table).where(table.c.control_key == key)).first()
    return row.control_value if row else None


def _security_control_set(db: Session, key: str, value: str) -> None:
    table = models.TABLES["system_security_controls"]
    row = db.execute(select(table).where(table.c.control_key == key)).first()
    if row:
        db.execute(update(table).where(table.c.control_key == key).values(control_value=value, updated_at=datetime.utcnow().isoformat()))
    else:
        db.execute(insert(table).values(control_key=key, control_value=value))


@app.middleware("http")
async def enforce_force_logout(request: Request, call_next):
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth.split(" ", 1)[1].strip()
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            token_iat = int(payload.get("iat") or 0)
            from database import SessionLocal
            db = SessionLocal()
            try:
                user_id = int(payload.get("sub") or 0)

                global_cutoff_raw = _security_control_get(db, "force_logout_after_ts")
                if global_cutoff_raw:
                    global_cutoff = int(float(global_cutoff_raw))
                    if token_iat <= global_cutoff:
                        from fastapi.responses import JSONResponse
                        return JSONResponse(status_code=401, content={"detail": "Session expired by security policy. Please login again."})

                user_cutoff_raw = _security_control_get(db, f"force_logout_user_{user_id}")
                if user_cutoff_raw:
                    user_cutoff = int(float(user_cutoff_raw))
                    if token_iat <= user_cutoff:
                        from fastapi.responses import JSONResponse
                        return JSONResponse(status_code=401, content={"detail": "You have been logged out by administrator."})
            finally:
                db.close()
        except Exception:
            pass
    return await call_next(request)


@app.post("/super-admin/subscriptions/{subscription_id}/pause")
def super_admin_pause_subscription(
    subscription_id: int,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_super_admin(current_user)
    _ensure_hospital_subscription_columns(db)
    subs = models.TABLES["hospital_subscriptions"]
    existing = db.execute(select(subs).where(subs.c.subscription_id == subscription_id)).first()
    if not existing:
        raise HTTPException(status_code=404, detail="Subscription not found")

    values = {"status": "PAUSED"}
    if _table_has_column(subs, "suspended_at"):
        values["suspended_at"] = datetime.utcnow().isoformat()

    db.execute(update(subs).where(subs.c.subscription_id == subscription_id).values(**values))
    db.commit()
    return {"status": "paused", "subscription_id": subscription_id}


@app.post("/super-admin/subscriptions/{subscription_id}/resume")
def super_admin_resume_subscription(
    subscription_id: int,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_super_admin(current_user)
    _ensure_hospital_subscription_columns(db)
    subs = models.TABLES["hospital_subscriptions"]
    existing = db.execute(select(subs).where(subs.c.subscription_id == subscription_id)).first()
    if not existing:
        raise HTTPException(status_code=404, detail="Subscription not found")

    db.execute(update(subs).where(subs.c.subscription_id == subscription_id).values(status="ACTIVE"))
    db.commit()
    return {"status": "active", "subscription_id": subscription_id}


@app.post("/super-admin/security/force-logout-all")
def super_admin_force_logout_all(
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_super_admin(current_user)
    cutoff = str(int(datetime.utcnow().timestamp()))
    _security_control_set(db, "force_logout_after_ts", cutoff)
    db.commit()
    return {"status": "ok", "force_logout_after_ts": int(cutoff)}


@app.post("/super-admin/staff/{user_id}/block")
def super_admin_block_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_super_admin(current_user)
    users = models.TABLES["users"]
    db.execute(update(users).where(users.c.user_id == user_id).values(is_active=0))
    db.commit()
    return {"status": "blocked", "user_id": user_id}


@app.post("/super-admin/staff/{user_id}/unblock")
def super_admin_unblock_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_super_admin(current_user)
    users = models.TABLES["users"]
    db.execute(update(users).where(users.c.user_id == user_id).values(is_active=1))
    db.commit()
    return {"status": "active", "user_id": user_id}


@app.get("/super-admin/permissions")
def super_admin_permissions(
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_super_admin(current_user)
    table = models.TABLES["role_module_permissions"]
    rows = db.execute(select(table).order_by(table.c.source_role.asc(), table.c.target_module.asc())).fetchall()
    return {"count": len(rows), "items": [_serialize_row(r) for r in rows]}


@app.post("/super-admin/permissions/upsert")
def super_admin_permissions_upsert(
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_super_admin(current_user)
    source_role = (payload.get("source_role") or "").strip().upper()
    target_module = (payload.get("target_module") or "").strip().upper()
    if not source_role or not target_module:
        raise HTTPException(status_code=400, detail="source_role and target_module are required")

    table = models.TABLES["role_module_permissions"]
    existing = db.execute(
        select(table)
        .where(table.c.source_role == source_role)
        .where(table.c.target_module == target_module)
    ).first()

    values = {
        "can_view": 1 if payload.get("can_view", True) else 0,
        "can_edit": 1 if payload.get("can_edit", False) else 0,
        "updated_at": datetime.utcnow().isoformat(),
    }

    if existing:
        db.execute(
            update(table)
            .where(table.c.source_role == source_role)
            .where(table.c.target_module == target_module)
            .values(**values)
        )
    else:
        db.execute(insert(table).values(source_role=source_role, target_module=target_module, **values))
    db.commit()
    return {"status": "saved", "source_role": source_role, "target_module": target_module}


@app.get("/super-admin/logs/users")
def super_admin_user_logs(
    limit: int = Query(default=300, ge=1, le=2000),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_super_admin(current_user)
    users = models.TABLES["users"]
    rows = db.execute(select(users).order_by(users.c.created_at.desc()).limit(limit)).fetchall()
    return {"count": len(rows), "items": [_serialize_row(r) for r in rows]}


@app.get("/super-admin/logs/ai-diagnoses")
def super_admin_ai_diagnosis_logs(
    limit: int = Query(default=300, ge=1, le=2000),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_super_admin(current_user)
    table = models.TABLES["ai_diagnoses"]
    rows = db.execute(select(table).order_by(table.c.created_at.desc()).limit(limit)).fetchall()
    return {"count": len(rows), "items": [_serialize_row(r) for r in rows]}


@app.get("/super-admin/logs/audit")
def super_admin_audit_logs(
    limit: int = Query(default=300, ge=1, le=2000),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_super_admin(current_user)
    table = models.TABLES["audit_logs"]
    rows = db.execute(select(table).order_by(table.c.created_at.desc()).limit(limit)).fetchall()
    return {"count": len(rows), "items": [_serialize_row(r) for r in rows]}


@app.get("/super-admin/ai/models")
def super_admin_ai_models(
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_super_admin(current_user)
    table = models.TABLES["ai_model_registry"]

    has = db.execute(select(table.c.model_id).limit(1)).first()
    if not has:
        db.execute(insert(table).values(model_key="UCI_LAB", model_name="UCI Lab Model", is_active=1))
        db.execute(insert(table).values(model_key="CHAMPION", model_name="Champion Model", is_active=0))
        db.commit()

    rows = db.execute(select(table).order_by(table.c.model_name.asc())).fetchall()
    return {"count": len(rows), "items": [_serialize_row(r) for r in rows]}


@app.post("/super-admin/ai/models/activate")
def super_admin_activate_ai_model(
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_super_admin(current_user)
    model_key = (payload.get("model_key") or "").strip().upper()
    if not model_key:
        raise HTTPException(status_code=400, detail="model_key is required")

    table = models.TABLES["ai_model_registry"]
    db.execute(update(table).values(is_active=0))
    db.execute(update(table).where(table.c.model_key == model_key).values(is_active=1))
    db.commit()
    return {"status": "active_model_updated", "model_key": model_key}


@app.get("/super-admin/ai/accuracy")
def super_admin_ai_accuracy(
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_super_admin(current_user)
    metrics = models.TABLES["ai_model_metrics"]
    models_table = models.TABLES["ai_model_registry"]

    has = db.execute(select(metrics.c.metric_id).limit(1)).first()
    if not has:
        now = datetime.utcnow().isoformat()
        db.execute(insert(metrics).values(model_key="UCI_LAB", metric_name="accuracy", metric_value=0.89, measured_at=now))
        db.execute(insert(metrics).values(model_key="UCI_LAB", metric_name="false_positive_rate", metric_value=0.08, measured_at=now))
        db.execute(insert(metrics).values(model_key="CHAMPION", metric_name="accuracy", metric_value=0.94, measured_at=now))
        db.execute(insert(metrics).values(model_key="CHAMPION", metric_name="false_positive_rate", metric_value=0.04, measured_at=now))
        db.commit()

    active_model = db.execute(select(models_table).where(models_table.c.is_active == 1)).first()
    rows = db.execute(select(metrics).order_by(metrics.c.measured_at.desc())).fetchall()
    return {
        "active_model": _serialize_row(active_model) if active_model else None,
        "count": len(rows),
        "items": [_serialize_row(r) for r in rows],
    }


@app.get("/super-admin/ai/service/ping")
def super_admin_ai_service_ping(
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_super_admin(current_user)
    import urllib.request

    url = "http://127.0.0.1:8001/health"
    try:
        with urllib.request.urlopen(url, timeout=2) as resp:
            body = resp.read().decode("utf-8", errors="ignore")
            return {"status": "online", "service_url": url, "response": body[:300]}
    except Exception as exc:
        return {"status": "offline", "service_url": url, "error": str(exc)}


@app.post("/super-admin/ai/service/restart")
def super_admin_ai_service_restart(
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_super_admin(current_user)
    # Hook for future process manager integration (pm2/systemd/docker compose)
    return {"status": "accepted", "message": "Restart signal registered. Wire this endpoint to your process manager."}


@app.get("/super-admin/finance/global-revenue")
def super_admin_global_revenue(
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_super_admin(current_user)

    payments = models.TABLES["payments"]
    subs = models.TABLES["hospital_subscriptions"]
    invoices = models.TABLES["invoices"]

    payment_rows = db.execute(select(payments.c.amount_paid)).fetchall()
    sub_rows = db.execute(select(subs.c.amount_paid)).fetchall()
    invoice_rows = db.execute(select(invoices.c.net_amount)).fetchall()

    payments_total = float(sum((r.amount_paid or 0) for r in payment_rows))
    subscriptions_total = float(sum((r.amount_paid or 0) for r in sub_rows))
    invoiced_total = float(sum((r.net_amount or 0) for r in invoice_rows))

    return {
        "payments_collected": payments_total,
        "subscriptions_collected": subscriptions_total,
        "invoiced_total": invoiced_total,
        "combined_total": payments_total + subscriptions_total,
    }


@app.post("/super-admin/pricing/global-update")
def super_admin_pricing_global_update(
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_super_admin(current_user)
    target = (payload.get("target") or "").strip().lower()
    amount = payload.get("amount")
    if amount is None:
        raise HTTPException(status_code=400, detail="amount is required")

    amount = float(amount)

    if target == "doctor_consultation_fee":
        table = models.TABLES["doctor_details"]
        db.execute(update(table).values(consultation_fee=amount))
    elif target == "medicine_unit_price":
        table = models.TABLES["medicines"]
        db.execute(update(table).values(unit_price=amount))
    else:
        raise HTTPException(status_code=400, detail="target must be doctor_consultation_fee or medicine_unit_price")

    db.commit()
    return {"status": "updated", "target": target, "amount": amount}


@app.get("/super-admin/inventory/alerts")
def super_admin_inventory_alerts(
    threshold: int = Query(default=10, ge=0),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_super_admin(current_user)
    batches = models.TABLES["medicine_batches"]
    medicines = models.TABLES["medicines"]

    rows = db.execute(
        select(
            batches.c.hospital_id,
            batches.c.batch_id,
            batches.c.quantity,
            batches.c.expiry_date,
            medicines.c.medicine_name,
        )
        .select_from(
            batches.join(
                medicines,
                (batches.c.hospital_id == medicines.c.hospital_id)
                & (batches.c.medicine_id == medicines.c.medicine_id),
            )
        )
        .where(batches.c.quantity < threshold)
        .order_by(batches.c.quantity.asc())
    ).fetchall()

    return {"threshold": threshold, "count": len(rows), "items": [_serialize_row(r) for r in rows]}


@app.post("/super-admin/database/snapshot")
def super_admin_database_snapshot(
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_super_admin(current_user)
    import shutil
    from pathlib import Path

    source = Path(__file__).with_name("hospital_multi.db")
    if not source.exists():
        source = Path("hospital_multi.db")

    backup_dir = Path(__file__).resolve().parents[2] / "database_backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    target = backup_dir / f"hospital_multi_{stamp}.db"

    shutil.copy2(source, target)
    return {"status": "created", "path": str(target)}


@app.get("/super-admin/hospital-settings")
def super_admin_hospital_settings(
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_super_admin(current_user)
    settings = models.TABLES["hospital_settings"]
    rows = db.execute(select(settings).order_by(settings.c.hospital_id.asc())).fetchall()
    return {"count": len(rows), "items": [_serialize_row(r) for r in rows]}


@app.get("/super-admin/contact-messages")
def super_admin_contact_messages(
    limit: int = Query(default=300, ge=1, le=2000),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_super_admin(current_user)
    messages = models.TABLES["contact_messages"]
    rows = db.execute(select(messages).order_by(messages.c.created_at.desc()).limit(limit)).fetchall()
    return {"count": len(rows), "items": [_serialize_row(r) for r in rows]}

@app.post("/super-admin/hospital-settings/upsert")
def super_admin_hospital_settings_upsert(
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_super_admin(current_user)

    hospital_id = payload.get("hospital_id")
    hospital_name = (payload.get("hospital_name") or "").strip()
    if not hospital_id or not hospital_name:
        raise HTTPException(status_code=400, detail="hospital_id and hospital_name are required")

    settings = models.TABLES["hospital_settings"]
    existing = db.execute(select(settings).where(settings.c.hospital_id == int(hospital_id))).first()

    values = {
        "hospital_name": hospital_name,
        "address": payload.get("address"),
        "phone_contact": payload.get("phone_contact"),
        "email_contact": payload.get("email_contact"),
        "emergency_line": payload.get("emergency_line"),
        "opd_hours": payload.get("opd_hours"),
        "timezone": payload.get("timezone") or "Asia/Karachi",
    }

    if existing:
        db.execute(update(settings).where(settings.c.hospital_id == int(hospital_id)).values(**values))
        status = "updated"
    else:
        db.execute(insert(settings).values(hospital_id=int(hospital_id), **values))
        status = "created"

    db.commit()
    row = db.execute(select(settings).where(settings.c.hospital_id == int(hospital_id))).first()
    return {"status": status, "item": _serialize_row(row)}


@app.post("/public/subscriptions/onboard-admin")
def public_onboard_subscription_admin(
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    hospital_code = (payload.get("hospital_code") or "").strip()
    full_name = (payload.get("full_name") or "").strip()
    email = _normalize_email(payload.get("email"))
    password = (payload.get("password") or "").strip()
    phone_number = (payload.get("phone_number") or "").strip() or None
    department_name = (payload.get("department_name") or "Administration").strip() or "Administration"

    if not hospital_code or not full_name or not email or not password:
        raise HTTPException(status_code=400, detail="hospital_code, full_name, email and password are required")
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    hospitals = models.TABLES["hospitals"]
    subs = models.TABLES["hospital_subscriptions"]
    users = models.TABLES["users"]
    roles = models.TABLES["roles"]
    staff = models.TABLES["staff"]
    memberships = models.TABLES["hospital_user_memberships"]
    departments = models.TABLES["departments"]
    settings = models.TABLES["hospital_settings"]

    hospital = db.execute(select(hospitals).where(hospitals.c.hospital_code == hospital_code)).first()
    if not hospital:
        raise HTTPException(status_code=404, detail="Hospital code not found")

    active_sub = db.execute(
        select(subs)
        .where(subs.c.hospital_id == hospital.hospital_id)
        .where(subs.c.status.in_(["ACTIVE", "PAUSED"]))
        .order_by(subs.c.started_at.desc())
    ).first()
    if not active_sub:
        raise HTTPException(status_code=400, detail="No purchased subscription found for this hospital")

    existing_membership = db.execute(
        select(memberships.c.membership_id)
        .select_from(memberships.join(roles, memberships.c.role_id == roles.c.role_id))
        .where(memberships.c.hospital_id == hospital.hospital_id)
        .where(roles.c.role_name == "ADMIN")
    ).first()
    if existing_membership:
        raise HTTPException(status_code=400, detail="Admin already registered for this hospital")

    existing_user = db.execute(select(users).where(users.c.email == email)).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already exists")

    admin_role = db.execute(select(roles).where(roles.c.role_name == "ADMIN")).first()
    if not admin_role:
        db.execute(insert(roles).values(role_name="ADMIN"))
        db.commit()
        admin_role = db.execute(select(roles).where(roles.c.role_name == "ADMIN")).first()

    department = db.execute(
        select(departments)
        .where(departments.c.hospital_id == hospital.hospital_id)
        .where(departments.c.department_name == department_name)
    ).first()
    if not department:
        db.execute(
            insert(departments).values(
                hospital_id=hospital.hospital_id,
                department_name=department_name,
                location="Administration Block",
            )
        )
        db.commit()
        department = db.execute(
            select(departments)
            .where(departments.c.hospital_id == hospital.hospital_id)
            .where(departments.c.department_name == department_name)
        ).first()

    try:
        user_result = db.execute(
            insert(users).values(
                email=email,
                password_hash=pwd_context.hash(password),
                is_active=1,
            )
        )
        user_id = user_result.inserted_primary_key[0] if user_result.inserted_primary_key else None

        staff_result = db.execute(
            insert(staff).values(
                hospital_id=hospital.hospital_id,
                user_id=user_id,
                full_name=full_name,
                role="ADMIN",
                phone_number=phone_number,
                department_id=department.department_id,
                status="ACTIVE",
            )
        )
        staff_id = staff_result.inserted_primary_key[0] if staff_result.inserted_primary_key else None

        db.execute(
            insert(memberships).values(
                hospital_id=hospital.hospital_id,
                user_id=user_id,
                role_id=admin_role.role_id,
                staff_id=staff_id,
                is_primary=1,
            )
        )

        existing_setting = db.execute(select(settings).where(settings.c.hospital_id == hospital.hospital_id)).first()
        if not existing_setting:
            db.execute(
                insert(settings).values(
                    hospital_id=hospital.hospital_id,
                    hospital_name=hospital.hospital_name,
                    email_contact=email,
                    phone_contact=phone_number,
                    opd_hours="Mon-Sat: 9:00 AM - 5:00 PM",
                    timezone="Asia/Karachi",
                )
            )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Integrity error: {exc.orig}")

    return {
        "status": "onboarding_completed",
        "hospital_id": hospital.hospital_id,
        "hospital_name": hospital.hospital_name,
        "admin_email": email,
        "next": "Use these credentials on /login to access admin dashboard",
    }



def _log_user_access_action(
    db: Session,
    hospital_id: Optional[int],
    actor_user_id: Optional[int],
    target_user_id: int,
    action_type: str,
    reason: Optional[str] = None,
) -> None:
    table = models.TABLES.get("user_access_actions")
    if table is None:
        return
    db.execute(
        insert(table).values(
            hospital_id=hospital_id,
            actor_user_id=actor_user_id,
            target_user_id=target_user_id,
            action_type=action_type,
            reason=reason,
        )
    )


@app.post("/admin/users/{user_id}/force-logout")
def admin_force_logout_user(
    user_id: int,
    payload: Dict[str, Any] = Body(default={}),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_admin(current_user)

    memberships = models.TABLES["hospital_user_memberships"]
    hospital_id = current_user["hospital_id"]

    target = db.execute(
        select(memberships.c.membership_id)
        .where(memberships.c.hospital_id == hospital_id)
        .where(memberships.c.user_id == user_id)
    ).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found in this hospital")

    ts = str(int(datetime.utcnow().timestamp()))
    _security_control_set(db, f"force_logout_user_{user_id}", ts)
    _log_user_access_action(
        db,
        hospital_id=hospital_id,
        actor_user_id=current_user["user_id"],
        target_user_id=user_id,
        action_type="FORCE_LOGOUT",
        reason=payload.get("reason"),
    )
    db.commit()
    return {"status": "forced_logout", "user_id": user_id}


@app.post("/admin/users/{user_id}/block-permanent")
def admin_block_user_permanent(
    user_id: int,
    payload: Dict[str, Any] = Body(default={}),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_admin(current_user)

    hospital_id = current_user["hospital_id"]
    users = models.TABLES["users"]
    memberships = models.TABLES["hospital_user_memberships"]

    target = db.execute(
        select(memberships.c.membership_id)
        .where(memberships.c.hospital_id == hospital_id)
        .where(memberships.c.user_id == user_id)
    ).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found in this hospital")

    db.execute(update(users).where(users.c.user_id == user_id).values(is_active=0))
    _security_control_set(db, f"force_logout_user_{user_id}", str(int(datetime.utcnow().timestamp())))
    _log_user_access_action(
        db,
        hospital_id=hospital_id,
        actor_user_id=current_user["user_id"],
        target_user_id=user_id,
        action_type="BLOCK_PERMANENT",
        reason=payload.get("reason"),
    )
    db.commit()
    return {"status": "blocked", "user_id": user_id}


@app.post("/admin/users/{user_id}/unblock")
def admin_unblock_user(
    user_id: int,
    payload: Dict[str, Any] = Body(default={}),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_admin(current_user)

    hospital_id = current_user["hospital_id"]
    users = models.TABLES["users"]
    memberships = models.TABLES["hospital_user_memberships"]

    target = db.execute(
        select(memberships.c.membership_id)
        .where(memberships.c.hospital_id == hospital_id)
        .where(memberships.c.user_id == user_id)
    ).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found in this hospital")

    db.execute(update(users).where(users.c.user_id == user_id).values(is_active=1))
    _log_user_access_action(
        db,
        hospital_id=hospital_id,
        actor_user_id=current_user["user_id"],
        target_user_id=user_id,
        action_type="UNBLOCK",
        reason=payload.get("reason"),
    )
    db.commit()
    return {"status": "active", "user_id": user_id}


@app.get("/admin/users/blocked")
def admin_blocked_users(
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_admin(current_user)

    users = models.TABLES["users"]
    memberships = models.TABLES["hospital_user_memberships"]
    hospital_id = current_user["hospital_id"]

    rows = db.execute(
        select(users.c.user_id, users.c.email, users.c.is_active, memberships.c.hospital_id)
        .select_from(users.join(memberships, users.c.user_id == memberships.c.user_id))
        .where(memberships.c.hospital_id == hospital_id)
        .where(users.c.is_active == 0)
        .order_by(users.c.user_id.desc())
    ).fetchall()
    return {"count": len(rows), "items": [_serialize_row(r) for r in rows]}


@app.get("/admin/users/access-events")
def admin_user_access_events(
    limit: int = Query(default=300, ge=1, le=2000),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_admin(current_user)

    table = models.TABLES["user_access_actions"]
    users = models.TABLES["users"]
    actor_users = users.alias("actor_users")
    target_users = users.alias("target_users")
    rows = db.execute(
        select(
            table,
            actor_users.c.email.label("actor_email"),
            target_users.c.email.label("target_email"),
        )
        .select_from(
            table.outerjoin(actor_users, table.c.actor_user_id == actor_users.c.user_id).outerjoin(
                target_users, table.c.target_user_id == target_users.c.user_id
            )
        )
        .where(table.c.hospital_id == current_user["hospital_id"])
        .order_by(table.c.created_at.desc())
        .limit(limit)
    ).fetchall()
    return {"count": len(rows), "items": [_serialize_row(r) for r in rows]}


@app.get("/super-admin/users/blocked")
def super_admin_blocked_users(
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_super_admin(current_user)

    users = models.TABLES["users"]
    memberships = models.TABLES["hospital_user_memberships"]
    hospitals = models.TABLES["hospitals"]

    rows = db.execute(
        select(users.c.user_id, users.c.email, users.c.is_active, memberships.c.hospital_id, hospitals.c.hospital_name)
        .select_from(
            users.join(memberships, users.c.user_id == memberships.c.user_id).join(
                hospitals, memberships.c.hospital_id == hospitals.c.hospital_id
            )
        )
        .where(users.c.is_active == 0)
        .order_by(users.c.user_id.desc())
    ).fetchall()
    return {"count": len(rows), "items": [_serialize_row(r) for r in rows]}


@app.post("/super-admin/users/{user_id}/unblock")
def super_admin_unblock_user_global(
    user_id: int,
    payload: Dict[str, Any] = Body(default={}),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_super_admin(current_user)

    users = models.TABLES["users"]
    memberships = models.TABLES["hospital_user_memberships"]

    membership = db.execute(select(memberships).where(memberships.c.user_id == user_id)).first()
    if not membership:
        raise HTTPException(status_code=404, detail="User membership not found")

    db.execute(update(users).where(users.c.user_id == user_id).values(is_active=1))
    _log_user_access_action(
        db,
        hospital_id=membership.hospital_id,
        actor_user_id=current_user["user_id"],
        target_user_id=user_id,
        action_type="UNBLOCK_BY_SUPER_ADMIN",
        reason=payload.get("reason"),
    )
    db.commit()
    return {"status": "active", "user_id": user_id}


def _safe_table_rows(db: Session, table_name: str, filters: list):
    table = models.TABLES.get(table_name)
    if table is None:
        return []
    query = select(table)
    for cond in filters:
        query = query.where(cond)
    rows = db.execute(query.order_by(table.c[list(table.c.keys())[0]].desc())).fetchall()
    return [_serialize_row(r) for r in rows]


@app.get("/admin/patients/{patient_id}/history")
def admin_patient_history(
    patient_id: int,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_admin(current_user)
    hospital_id = current_user["hospital_id"]

    patients = models.TABLES["patients"]
    patient = db.execute(
        select(patients)
        .where(patients.c.hospital_id == hospital_id)
        .where(patients.c.patient_id == patient_id)
    ).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    appointments = _safe_table_rows(db, "appointments", [models.TABLES["appointments"].c.hospital_id == hospital_id, models.TABLES["appointments"].c.patient_id == patient_id]) if models.TABLES.get("appointments") is not None else []
    admissions = _safe_table_rows(db, "admissions", [models.TABLES["admissions"].c.hospital_id == hospital_id, models.TABLES["admissions"].c.patient_id == patient_id]) if models.TABLES.get("admissions") is not None else []
    lab_requests = _safe_table_rows(db, "lab_requests", [models.TABLES["lab_requests"].c.hospital_id == hospital_id, models.TABLES["lab_requests"].c.patient_id == patient_id]) if models.TABLES.get("lab_requests") is not None else []
    imaging_records = _safe_table_rows(db, "imaging_records", [models.TABLES["imaging_records"].c.hospital_id == hospital_id, models.TABLES["imaging_records"].c.patient_id == patient_id]) if models.TABLES.get("imaging_records") is not None else []
    ai_diagnoses = _safe_table_rows(db, "ai_diagnoses", [models.TABLES["ai_diagnoses"].c.hospital_id == hospital_id, models.TABLES["ai_diagnoses"].c.patient_id == patient_id]) if models.TABLES.get("ai_diagnoses") is not None else []
    ai_reports = _safe_table_rows(db, "ai_generated_reports", [models.TABLES["ai_generated_reports"].c.hospital_id == hospital_id, models.TABLES["ai_generated_reports"].c.patient_id == patient_id]) if models.TABLES.get("ai_generated_reports") is not None else []
    medications = _safe_table_rows(db, "doctor_medications", [models.TABLES["doctor_medications"].c.hospital_id == hospital_id, models.TABLES["doctor_medications"].c.patient_id == patient_id]) if models.TABLES.get("doctor_medications") is not None else []
    clinical_updates = _safe_table_rows(db, "doctor_clinical_updates", [models.TABLES["doctor_clinical_updates"].c.hospital_id == hospital_id, models.TABLES["doctor_clinical_updates"].c.patient_id == patient_id]) if models.TABLES.get("doctor_clinical_updates") is not None else []
    vitals = _safe_table_rows(db, "patient_vitals", [models.TABLES["patient_vitals"].c.hospital_id == hospital_id, models.TABLES["patient_vitals"].c.patient_id == patient_id]) if models.TABLES.get("patient_vitals") is not None else []
    feedback = _safe_table_rows(db, "patient_feedback", [models.TABLES["patient_feedback"].c.hospital_id == hospital_id, models.TABLES["patient_feedback"].c.patient_id == patient_id]) if models.TABLES.get("patient_feedback") is not None else []

    invoices_rows = []
    payments_rows = []
    invoices = models.TABLES.get("invoices")
    payments = models.TABLES.get("payments")
    if invoices is not None:
        invoices_raw = db.execute(
            select(invoices)
            .where(invoices.c.hospital_id == hospital_id)
            .where(invoices.c.patient_id == patient_id)
            .order_by(invoices.c.invoice_id.desc())
        ).fetchall()
        invoices_rows = [_serialize_row(r) for r in invoices_raw]

        if payments is not None and invoices_rows:
            invoice_ids = [r["invoice_id"] for r in invoices_rows]
            payments_raw = db.execute(
                select(payments)
                .where(payments.c.hospital_id == hospital_id)
                .where(payments.c.invoice_id.in_(invoice_ids))
                .order_by(payments.c.payment_id.desc())
            ).fetchall()
            payments_rows = [_serialize_row(r) for r in payments_raw]

    return {
        "patient": _serialize_row(patient),
        "history": {
            "appointments": appointments,
            "admissions": admissions,
            "lab_requests": lab_requests,
            "imaging_records": imaging_records,
            "ai_diagnoses": ai_diagnoses,
            "ai_reports": ai_reports,
            "medications": medications,
            "clinical_updates": clinical_updates,
            "vitals": vitals,
            "feedback": feedback,
            "invoices": invoices_rows,
            "payments": payments_rows,
        },
    }



@app.get("/doctor/patients/{patient_id}/history")
def doctor_patient_history(
    patient_id: int,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_roles(current_user, {"DOCTOR", "ADMIN", "SUPER_ADMIN"})
    hospital_id = current_user["hospital_id"]

    patients = models.TABLES["patients"]
    patient = db.execute(
        select(patients)
        .where(patients.c.hospital_id == hospital_id)
        .where(patients.c.patient_id == patient_id)
    ).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    has_appointments = models.TABLES.get("appointments") is not None
    has_admissions = models.TABLES.get("admissions") is not None
    has_lab_requests = models.TABLES.get("lab_requests") is not None
    has_imaging_records = models.TABLES.get("imaging_records") is not None
    has_ai_diagnoses = models.TABLES.get("ai_diagnoses") is not None
    has_medications = models.TABLES.get("doctor_medications") is not None
    has_clinical_updates = models.TABLES.get("doctor_clinical_updates") is not None
    has_vitals = models.TABLES.get("patient_vitals") is not None
    has_visit_logs = models.TABLES.get("reception_patient_visits") is not None

    appointments = _safe_table_rows(db, "appointments", [models.TABLES["appointments"].c.hospital_id == hospital_id, models.TABLES["appointments"].c.patient_id == patient_id]) if has_appointments else []
    admissions = _safe_table_rows(db, "admissions", [models.TABLES["admissions"].c.hospital_id == hospital_id, models.TABLES["admissions"].c.patient_id == patient_id]) if has_admissions else []
    lab_requests = _safe_table_rows(db, "lab_requests", [models.TABLES["lab_requests"].c.hospital_id == hospital_id, models.TABLES["lab_requests"].c.patient_id == patient_id]) if has_lab_requests else []
    imaging_records = _safe_table_rows(db, "imaging_records", [models.TABLES["imaging_records"].c.hospital_id == hospital_id, models.TABLES["imaging_records"].c.patient_id == patient_id]) if has_imaging_records else []
    ai_diagnoses = _safe_table_rows(db, "ai_diagnoses", [models.TABLES["ai_diagnoses"].c.hospital_id == hospital_id, models.TABLES["ai_diagnoses"].c.patient_id == patient_id]) if has_ai_diagnoses else []
    medications = _safe_table_rows(db, "doctor_medications", [models.TABLES["doctor_medications"].c.hospital_id == hospital_id, models.TABLES["doctor_medications"].c.patient_id == patient_id]) if has_medications else []
    clinical_updates = _safe_table_rows(db, "doctor_clinical_updates", [models.TABLES["doctor_clinical_updates"].c.hospital_id == hospital_id, models.TABLES["doctor_clinical_updates"].c.patient_id == patient_id]) if has_clinical_updates else []
    vitals = _safe_table_rows(db, "patient_vitals", [models.TABLES["patient_vitals"].c.hospital_id == hospital_id, models.TABLES["patient_vitals"].c.patient_id == patient_id]) if has_vitals else []
    visit_logs = _safe_table_rows(db, "reception_patient_visits", [models.TABLES["reception_patient_visits"].c.hospital_id == hospital_id, models.TABLES["reception_patient_visits"].c.patient_id == patient_id]) if has_visit_logs else []

    return {
        "patient": _serialize_row(patient),
        "history": {
            "appointments": appointments,
            "admissions": admissions,
            "lab_requests": lab_requests,
            "imaging_records": imaging_records,
            "ai_diagnoses": ai_diagnoses,
            "medications": medications,
            "clinical_updates": clinical_updates,
            "vitals": vitals,
            "visit_logs": visit_logs,
        },
    }
@app.get("/admin/staff/{staff_id}/history")
def admin_staff_history(
    staff_id: int,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_admin(current_user)
    hospital_id = current_user["hospital_id"]

    staff_table = models.TABLES["staff"]
    staff_row = db.execute(
        select(staff_table)
        .where(staff_table.c.hospital_id == hospital_id)
        .where(staff_table.c.staff_id == staff_id)
    ).first()
    if not staff_row:
        raise HTTPException(status_code=404, detail="Staff not found")

    user_profile = None
    users = models.TABLES.get("users")
    if users is not None and getattr(staff_row, "user_id", None):
        user_row = db.execute(select(users).where(users.c.user_id == staff_row.user_id)).first()
        if user_row:
            user_profile = _serialize_row(user_row)

    schedules = _safe_table_rows(db, "staff_schedules", [models.TABLES["staff_schedules"].c.hospital_id == hospital_id, models.TABLES["staff_schedules"].c.staff_id == staff_id]) if models.TABLES.get("staff_schedules") is not None else []
    leaves = _safe_table_rows(db, "leave_requests", [models.TABLES["leave_requests"].c.hospital_id == hospital_id, models.TABLES["leave_requests"].c.staff_id == staff_id]) if models.TABLES.get("leave_requests") is not None else []
    doctor_details = _safe_table_rows(db, "doctor_details", [models.TABLES["doctor_details"].c.hospital_id == hospital_id, models.TABLES["doctor_details"].c.doctor_staff_id == staff_id]) if models.TABLES.get("doctor_details") is not None else []

    appointments = _safe_table_rows(db, "appointments", [models.TABLES["appointments"].c.hospital_id == hospital_id, models.TABLES["appointments"].c.doctor_id == staff_id]) if models.TABLES.get("appointments") is not None else []
    lab_orders = _safe_table_rows(db, "lab_requests", [models.TABLES["lab_requests"].c.hospital_id == hospital_id, models.TABLES["lab_requests"].c.ordered_by_staff_id == staff_id]) if models.TABLES.get("lab_requests") is not None else []
    admissions = _safe_table_rows(db, "admissions", [models.TABLES["admissions"].c.hospital_id == hospital_id, models.TABLES["admissions"].c.admitted_by_staff_id == staff_id]) if models.TABLES.get("admissions") is not None else []
    ai_diagnoses = _safe_table_rows(db, "ai_diagnoses", [models.TABLES["ai_diagnoses"].c.hospital_id == hospital_id, models.TABLES["ai_diagnoses"].c.doctor_id == staff_id]) if models.TABLES.get("ai_diagnoses") is not None else []
    audit_actor = _safe_table_rows(db, "audit_logs", [models.TABLES["audit_logs"].c.hospital_id == hospital_id, models.TABLES["audit_logs"].c.actor_staff_id == staff_id]) if models.TABLES.get("audit_logs") is not None else []

    return {
        "staff": _serialize_row(staff_row),
        "user": user_profile,
        "history": {
            "schedules": schedules,
            "leave_requests": leaves,
            "doctor_details": doctor_details,
            "appointments": appointments,
            "lab_orders": lab_orders,
            "admissions": admissions,
            "ai_diagnoses": ai_diagnoses,
            "audit_logs": audit_actor,
        },
    }
