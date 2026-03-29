from backend.core_hospital.database import engine
from sqlalchemy import text
import backend.core_hospital.models as models

# This script forces a complete wipe of the database schema
# It fixes the "DependentObjectsStillExist" error by using CASCADE.

def wipe_and_rebuild():
    with engine.connect() as connection:
        trans = connection.begin()
        try:
            print("🚨 Wiping entire database schema (Nuclear Option)...")
            
            # 1. Drop the entire 'public' folder where tables live
            connection.execute(text("DROP SCHEMA public CASCADE;"))
            
            # 2. Re-create the empty folder
            connection.execute(text("CREATE SCHEMA public;"))
            
            # 3. Give permission back to the main user
            connection.execute(text("GRANT ALL ON SCHEMA public TO postgres;"))
            connection.execute(text("GRANT ALL ON SCHEMA public TO public;"))
            
            trans.commit()
            print("✅ Database wiped clean.")
        except Exception as e:
            trans.rollback()
            print(f"❌ Error during wipe: {e}")
            return

    # 4. Ask SQLAlchemy to rebuild all tables from models.py
    print("🏗️ Rebuilding 31 Tables from scratch...")
    models.Base.metadata.create_all(bind=engine)
    print("🎉 Success! Database is brand new and ready.")

if __name__ == "__main__":
    wipe_and_rebuild()