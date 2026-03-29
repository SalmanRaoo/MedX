import os
import urllib.request
import ssl

# CONFIG
DEST_DIR = os.path.join("hospital_ai_assets", "harvested_data")
os.makedirs(DEST_DIR, exist_ok=True)

# Bypass SSL in case your local network/ISP is blocking the requests
try:
    _create_unverified_https_context = ssl._create_unverified_context
except AttributeError:
    pass
else:
    ssl._create_default_https_context = _create_unverified_https_context

# OFFICIAL UCI MACHINE LEARNING REPOSITORY LINKS (Unbreakable)
# Note: UCI uses ".data" extensions, but they are actually CSV files.
TARGETS = {
    "uci_recovered_breast_cancer.csv": "https://archive.ics.uci.edu/ml/machine-learning-databases/breast-cancer-wisconsin/wdbc.data",
    "uci_recovered_parkinsons.csv": "https://archive.ics.uci.edu/ml/machine-learning-databases/parkinsons/parkinsons.data",
    "uci_recovered_liver.csv": "https://archive.ics.uci.edu/ml/machine-learning-databases/00225/Indian%20Liver%20Patient%20Dataset%20(ILPD).csv",
    # Stable GitHub mirror for Kidney since UCI uses an annoying ARFF format
    "mirror_recovered_kidney.csv": "https://raw.githubusercontent.com/NishikantTiwari/Chronic-Kidney-Disease-Prediction/master/kidney_disease.csv"
}

def download_bulletproof():
    print("🏥 CONTACTING UCI MEDICAL DATABASES...\n")
    
    success = 0
    for filename, url in TARGETS.items():
        print(f"   ⬇️ Downloading {filename}...", end=" ")
        save_path = os.path.join(DEST_DIR, filename)
        
        try:
            # Download the file
            urllib.request.urlretrieve(url, save_path)
            print("✅ SUCCESS!")
            success += 1
        except Exception as e:
            print(f"❌ FAILED. Error: {e}")

    print("\n" + "="*50)
    print(f"🎉 OPERATION COMPLETE. Secured {success}/{len(TARGETS)} datasets.")
    print("👉 NOW RUN: 'python train_champion_models.py' again.")
    print("="*50)

if __name__ == "__main__":
    download_bulletproof()