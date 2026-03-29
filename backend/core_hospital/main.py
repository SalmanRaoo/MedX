import json
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

from fastapi import Body, Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from sqlalchemy import insert, select, update
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

    for role_name in ["SUPER_ADMIN", "ADMIN", "DOCTOR", "NURSE", "RECEPTIONIST", "PHARMACY", "LAB", "FINANCE", "OPERATIONS"]:
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
    finally:
        db.close()


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> Dict[str, Any]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid authentication token")

    user_id = payload.get("sub")
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

    existing_user = db.execute(select(users_table).where(users_table.c.email == req.email)).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already exists")

    existing_hospital = db.execute(select(hospitals_table).where(hospitals_table.c.hospital_code == req.hospital_code)).first()
    if existing_hospital:
        raise HTTPException(status_code=400, detail="Hospital code already exists")

    admin_role = db.execute(select(roles_table).where(roles_table.c.role_name == "ADMIN")).first()

    try:
        db.execute(insert(hospitals_table).values(hospital_code=req.hospital_code, hospital_name=req.hospital_name, status="ACTIVE"))
        hospital = db.execute(select(hospitals_table).where(hospitals_table.c.hospital_code == req.hospital_code)).first()

        db.execute(insert(users_table).values(email=req.email, password_hash=pwd_context.hash(req.password), is_active=1))
        user = db.execute(select(users_table).where(users_table.c.email == req.email)).first()

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
    user = db.execute(select(users_table).where(users_table.c.email == req.email)).first()

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
            "sub": str(user.user_id),
            "email": user.email,
            "hospital_id": selected["hospital_id"],
            "hospital_name": selected["hospital_name"],
            "role_name": selected["role_name"],
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
        item["features"] = json.loads(item.get("features_json") or "[]")
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

    subs = models.TABLES["hospital_subscriptions"]
    plans = models.TABLES["subscription_plans"]
    hospitals = models.TABLES["hospitals"]

    rows = db.execute(
        select(
            subs.c.subscription_id,
            subs.c.status,
            subs.c.billing_cycle,
            subs.c.started_at,
            subs.c.expires_at,
            subs.c.amount_paid,
            subs.c.purchased_by_email,
            hospitals.c.hospital_id,
            hospitals.c.hospital_name,
            plans.c.plan_code,
            plans.c.plan_name,
        )
        .select_from(
            subs.join(hospitals, subs.c.hospital_id == hospitals.c.hospital_id).join(plans, subs.c.plan_id == plans.c.plan_id)
        )
        .order_by(subs.c.expires_at.asc())
    ).fetchall()

    return {"count": len(rows), "items": [_serialize_row(r) for r in rows]}


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
        query = select(table)
        if _table_has_column(table, "hospital_id"):
            query = query.where(table.c.hospital_id == current_user["hospital_id"])

        rows = db.execute(query.limit(limit).offset(offset)).fetchall()
        return {
            "table": table_name,
            "hospital_id": current_user["hospital_id"],
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

    alias = {"RECEPTION": "RECEPTIONIST"}
    role_name = alias.get(role_name, role_name)

    users_table = models.TABLES["users"]
    roles_table = models.TABLES["roles"]
    staff_table = models.TABLES["staff"]
    memberships_table = models.TABLES["hospital_user_memberships"]
    departments_table = models.TABLES["departments"]

    existing_user = db.execute(select(users_table).where(users_table.c.email == email)).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already exists")

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

    try:
        db.execute(
            insert(users_table).values(
                email=email,
                password_hash=pwd_context.hash(password),
                is_active=1,
            )
        )
        db.commit()

        user = db.execute(select(users_table).where(users_table.c.email == email)).first()

        db.execute(
            insert(staff_table).values(
                hospital_id=hospital_id,
                user_id=user.user_id,
                full_name=full_name,
                role=role_name,
                phone_number=phone_number,
                department_id=department_id,
                license_number=license_number,
                status="ACTIVE",
            )
        )
        db.commit()

        staff = db.execute(
            select(staff_table)
            .where(staff_table.c.hospital_id == hospital_id)
            .where(staff_table.c.user_id == user.user_id)
        ).first()

        db.execute(
            insert(memberships_table).values(
                hospital_id=hospital_id,
                user_id=user.user_id,
                role_id=role.role_id,
                staff_id=staff.staff_id,
                is_primary=0,
            )
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Integrity error: {exc.orig}")

    return {
        "status": "created",
        "user_id": user.user_id,
        "staff_id": staff.staff_id,
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


@app.get("/pharmacy/medication-queue")
def pharmacy_medication_queue(
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_roles(current_user, {"PHARMACY", "ADMIN", "SUPER_ADMIN"})

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
    return {"count": len(rows), "items": [_serialize_row(r) for r in rows]}


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
    email = (payload.get("email") or "").strip().lower()
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
    receipt = {
        "receipt_no": f"REC-{hospital_id}-{patient_id}-{datetime.utcnow().strftime('%H%M%S')}",
        "created_at": created_at,
        "hospital_id": hospital_id,
        "patient_id": patient_id,
        "patient_name": full_name,
        "patient_mrn": mrn,
        "portal_email": email,
        "visit_type": (payload.get("visit_type") or "OPD"),
        "chief_complaint": (payload.get("chief_complaint") or None),
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

        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Integrity error: {exc.orig}")

    patient = db.execute(
        select(patients_table)
        .where(patients_table.c.hospital_id == hospital_id)
        .where(patients_table.c.patient_id == patient_id)
    ).first()

    receipt = {
        "receipt_no": f"REC-{hospital_id}-{patient_id}-{datetime.utcnow().strftime('%H%M%S')}",
        "created_at": datetime.utcnow().isoformat(),
        "hospital_id": hospital_id,
        "patient_id": patient_id,
        "patient_name": full_name,
        "patient_mrn": mrn,
        "portal_email": email,
        "visit_type": (payload.get("visit_type") or "OPD"),
        "chief_complaint": (payload.get("chief_complaint") or None),
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
def reception_register_admission(
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_roles(current_user, {"RECEPTIONIST", "ADMIN", "SUPER_ADMIN"})

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
        bed_result = db.execute(
            insert(beds_table).values(
                hospital_id=hospital_id,
                ward_name=ward_name,
                bed_number=bed_number,
                is_occupied=1,
                daily_charge=0,
            )
        )
        bed_id = bed_result.inserted_primary_key[0] if bed_result.inserted_primary_key else None
    else:
        bed_id = bed.bed_id
        db.execute(
            update(beds_table)
            .where(beds_table.c.hospital_id == hospital_id)
            .where(beds_table.c.bed_id == bed_id)
            .values(is_occupied=1, ward_name=ward_name)
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
    db.commit()

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
    subs = models.TABLES["hospital_subscriptions"]
    db.execute(update(subs).where(subs.c.subscription_id == subscription_id).values(status="PAUSED"))
    db.commit()
    return {"status": "paused", "subscription_id": subscription_id}


@app.post("/super-admin/subscriptions/{subscription_id}/resume")
def super_admin_resume_subscription(
    subscription_id: int,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_super_admin(current_user)
    subs = models.TABLES["hospital_subscriptions"]
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
    email = (payload.get("email") or "").strip().lower()
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
    rows = db.execute(
        select(table)
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
    if invoices:
        invoices_raw = db.execute(
            select(invoices)
            .where(invoices.c.hospital_id == hospital_id)
            .where(invoices.c.patient_id == patient_id)
            .order_by(invoices.c.invoice_id.desc())
        ).fetchall()
        invoices_rows = [_serialize_row(r) for r in invoices_raw]

        if payments and invoices_rows:
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
    has_ai_diagnoses = models.TABLES.get("ai_diagnoses") is not None
    has_medications = models.TABLES.get("doctor_medications") is not None
    has_clinical_updates = models.TABLES.get("doctor_clinical_updates") is not None
    has_visit_logs = models.TABLES.get("reception_patient_visits") is not None

    appointments = _safe_table_rows(db, "appointments", [models.TABLES["appointments"].c.hospital_id == hospital_id, models.TABLES["appointments"].c.patient_id == patient_id]) if has_appointments else []
    admissions = _safe_table_rows(db, "admissions", [models.TABLES["admissions"].c.hospital_id == hospital_id, models.TABLES["admissions"].c.patient_id == patient_id]) if has_admissions else []
    lab_requests = _safe_table_rows(db, "lab_requests", [models.TABLES["lab_requests"].c.hospital_id == hospital_id, models.TABLES["lab_requests"].c.patient_id == patient_id]) if has_lab_requests else []
    ai_diagnoses = _safe_table_rows(db, "ai_diagnoses", [models.TABLES["ai_diagnoses"].c.hospital_id == hospital_id, models.TABLES["ai_diagnoses"].c.patient_id == patient_id]) if has_ai_diagnoses else []
    medications = _safe_table_rows(db, "doctor_medications", [models.TABLES["doctor_medications"].c.hospital_id == hospital_id, models.TABLES["doctor_medications"].c.patient_id == patient_id]) if has_medications else []
    clinical_updates = _safe_table_rows(db, "doctor_clinical_updates", [models.TABLES["doctor_clinical_updates"].c.hospital_id == hospital_id, models.TABLES["doctor_clinical_updates"].c.patient_id == patient_id]) if has_clinical_updates else []
    visit_logs = _safe_table_rows(db, "reception_patient_visits", [models.TABLES["reception_patient_visits"].c.hospital_id == hospital_id, models.TABLES["reception_patient_visits"].c.patient_id == patient_id]) if has_visit_logs else []

    return {
        "patient": _serialize_row(patient),
        "history": {
            "appointments": appointments,
            "admissions": admissions,
            "lab_requests": lab_requests,
            "ai_diagnoses": ai_diagnoses,
            "medications": medications,
            "clinical_updates": clinical_updates,
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
    if users and staff_row.user_id:
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











