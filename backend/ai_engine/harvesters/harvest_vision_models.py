import os
import gdown

MODEL_DIR = os.path.join("hospital_ai_assets", "models")
os.makedirs(MODEL_DIR, exist_ok=True)

print("🛸 CONTACTING GOOGLE DRIVE FOR VISION MODELS...")

# The exact links extracted from the author's code
MODELS = {
    "brain_tumor_model.h5": '1SVzcoWXlVO-J8z-zusC7C4LouHDIqic1',
    "pneumonia_model.h5": '1KgQyE7-sDnOhMQIlLpjPr63oUfU6W9SX',
    "tuberculosis_model.h5": '1t5L-Od5WnETF4VHlWcfY5QjWMtNxZVCW' # Bonus model!
}

for name, drive_id in MODELS.items():
    print(f"\n   ⬇️ Downloading {name}...")
    dest = os.path.join(MODEL_DIR, name)
    
    if os.path.exists(dest):
        print("      ✅ Already exists. Skipping.")
        continue
        
    url = f'https://drive.google.com/uc?id={drive_id}'
    try:
        gdown.download(url, dest, quiet=False)
        print("      ✅ SUCCESS!")
    except Exception as e:
        print(f"      ❌ Failed: {e}")

print("\n" + "="*50)
print("🎉 VISION HARVEST COMPLETE. You now have Deep Learning models.")
print("="*50)