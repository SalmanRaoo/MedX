import os
import requests

MODEL_DIR = os.path.join("hospital_ai_assets", "models")
os.makedirs(MODEL_DIR, exist_ok=True)

# Direct link to a pre-trained Pneumonia H5 model from an open-source medical repo
PNEUMONIA_URL = "https://raw.githubusercontent.com/tushar2704/Pneumonia-Detection-from-Chest-X-Ray-Images/main/models/pneumonia_model.h5"
SAVE_PATH = os.path.join(MODEL_DIR, "pneumonia_model.h5")

print("📸 DOWNLOADING REAL PNEUMONIA VISION MODEL...")
try:
    r = requests.get(PNEUMONIA_URL)
    if r.status_code == 200:
        with open(SAVE_PATH, 'wb') as f:
            f.write(r.content)
        print("✅ SUCCESS: pneumonia_model.h5 saved!")
    else:
        print(f"❌ Failed. GitHub returned status: {r.status_code}")
        print("If this fails, download any 'pneumonia.h5' from Kaggle and drop it in the models folder.")
except Exception as e:
    print(f"❌ Error: {e}")
    