from database import engine
import models

print("Dropping old tables...")
models.Base.metadata.drop_all(bind=engine)
print("Old tables deleted.")

print("Creating new tables...")
models.Base.metadata.create_all(bind=engine)
print("New tables created successfully with all columns!")