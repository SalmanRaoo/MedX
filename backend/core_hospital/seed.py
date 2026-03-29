from sqlalchemy.orm import Session
from database import SessionLocal, engine
import models
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def seed_data():
    db = SessionLocal()
    # 1. Create System Admin
    admin_user = models.User(
        email="admin@medx.com",
        password_hash=pwd_context.hash("admin123"),
        user_type="Admin"
    )
    
    # 2. Create Dr. Sarah Jenkins
    dr_staff = models.Staff(full_name="Dr. Sarah Jenkins", role="Cardiologist", phone_number="0321-1234567")
    
    # 3. Create MedX Neural Engine (AI Service)
    ai_engine = models.Staff(full_name="MedX Neural Engine", role="System Service", phone_number="N/A")

    # 4. Create John Smith
    receptionist = models.Staff(full_name="John Smith", role="Receptionist", phone_number="0300-9876543")

    try:
        db.add_all([admin_user, dr_staff, ai_engine, receptionist])
        db.commit()
        print("🚀 MedX Database Seeded Successfully!")
    except Exception as e:
        print(f"Error seeding: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    seed_data()