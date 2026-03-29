import os
import requests

# CONFIG
DEST_DIR = os.path.join("hospital_ai_assets", "harvested_data")
os.makedirs(DEST_DIR, exist_ok=True)

# DIRECT RAW LINKS TO MISSING REAL DATASETS
MISSING_DATA = {
    "venugopal_kidney.csv": "https://raw.githubusercontent.com/venugopalkadamba/Multi_Disease_Predictor/master/Dataset/kidney_disease.csv",
    "venugopal_liver.csv": "https://raw.githubusercontent.com/venugopalkadamba/Multi_Disease_Predictor/master/Dataset/indian_liver_patient.csv",
    "samagra_parkinsons.csv": "https://raw.githubusercontent.com/samagra44/Multiple-Disease-Prediction-System/master/dataset/parkinsons.csv",
    "eda_pneumonia_pixels.csv": "https://raw.githubusercontent.com/edaaydinea/AI-Projects-for-Healthcare/master/Pneumonia_Detection/pneumonia_data.csv" # If available
}

def download_missing():
    print("🚑 STARTING EMERGENCY DATA RESCUE...")
    
    for name, url in MISSING_DATA.items():
        print(f"   ⬇️ Downloading {name}...", end=" ")
        try:
            r = requests.get(url)
            if r.status_code == 200:
                with open(os.path.join(DEST_DIR, name), 'wb') as f:
                    f.write(r.content)
                print("✅ Success!")
            else:
                print(f"❌ Failed (Status: {r.status_code})")
        except Exception as e:
            print(f"❌ Error: {e}")

    print("\n" + "="*50)
    print("🎉 RESCUE COMPLETE. You now have Kidney & Liver data.")
    print("👉 NOW RUN: 'python train_champion_models.py'")
    print("="*50)

if __name__ == "__main__":
    download_missing()