import os
import requests

# CONFIG
DEST_DIR = os.path.join("hospital_ai_assets", "harvested_data")
os.makedirs(DEST_DIR, exist_ok=True)

# ROBUST SOURCE LIST (Main + Backups)
# We try multiple repositories for the same disease to guarantee a hit.
TARGETS = {
    "kidney_disease.csv": [
        "https://raw.githubusercontent.com/mansi1711/Kidney-Disease-Prediction/master/kidney_disease.csv",
        "https://raw.githubusercontent.com/iamrishabsharma/Chronic-Kidney-Disease-Prediction/master/kidney_disease.csv",
        "https://raw.githubusercontent.com/venugopalkadamba/Multi_Disease_Predictor/master/Dataset/kidney_disease.csv"
    ],
    "liver_disease.csv": [
        "https://raw.githubusercontent.com/NiranjanKumar/Liver-Disease-Prediction/master/indian_liver_patient.csv",
        "https://raw.githubusercontent.com/kavyak08/Liver_disease_prediction/master/indian_liver_patient.csv",
        "https://raw.githubusercontent.com/venugopalkadamba/Multi_Disease_Predictor/master/Dataset/indian_liver_patient.csv"
    ],
    "parkinsons.csv": [
        "https://raw.githubusercontent.com/gpingali/Parkinsons-Disease-Prediction/master/parkinsons.data",
        "https://raw.githubusercontent.com/cowlet/parkinsons/master/parkinsons.data",
        "https://raw.githubusercontent.com/samagra44/Multiple-Disease-Prediction-System/master/dataset/parkinsons.csv"
    ],
    "diabetes.csv": [
        "https://raw.githubusercontent.com/jbrownlee/Datasets/master/pima-indians-diabetes.data.csv",
        "https://raw.githubusercontent.com/plotly/datasets/master/diabetes.csv"
    ],
    "breast_cancer.csv": [
        "https://raw.githubusercontent.com/mwaskom/seaborn-data/master/breast_cancer.csv",
        "https://raw.githubusercontent.com/plotly/datasets/master/breast-cancer.csv"
    ]
}

def download_robust():
    print("🚑 STARTING ROBUST DATA RESCUE (MULTI-SOURCE)...\n")
    
    success_count = 0
    
    for filename, urls in TARGETS.items():
        print(f"   🔍 Hunting for {filename}...", end=" ")
        downloaded = False
        
        for i, url in enumerate(urls):
            try:
                # Try downloading
                r = requests.get(url, timeout=5)
                if r.status_code == 200:
                    # Save it
                    save_path = os.path.join(DEST_DIR, f"recovered_{filename}")
                    with open(save_path, 'wb') as f:
                        f.write(r.content)
                    print(f"✅ FOUND! (Source {i+1})")
                    downloaded = True
                    success_count += 1
                    break # Stop trying other links for this disease
            except:
                continue # Try next link
        
        if not downloaded:
            print("❌ ALL SOURCES FAILED.")

    print("\n" + "="*50)
    print(f"🎉 RESCUE COMPLETE. Recovered {success_count}/{len(TARGETS)} datasets.")
    print("👉 NOW RUN: 'python train_champion_models.py' again.")
    print("="*50)

if __name__ == "__main__":
    download_robust()