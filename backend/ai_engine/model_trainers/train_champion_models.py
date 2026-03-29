import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import LabelEncoder
import joblib
import os
import glob

# CONFIG
DATA_DIR = os.path.join("hospital_ai_assets", "harvested_data")
MODEL_DIR = os.path.join("hospital_ai_assets", "models")
os.makedirs(MODEL_DIR, exist_ok=True)

print("🏆 INITIALIZING CHAMPION MODEL TRAINING...\n")

def train_champion(keywords, model_name, target_override=None):
    """
    Finds ALL datasets matching the keyword, picks the LARGEST one, and trains.
    """
    # 1. Find Candidates
    candidates = []
    for k in keywords:
        candidates.extend(glob.glob(os.path.join(DATA_DIR, f"*{k}*.csv")))
    
    if not candidates:
        print(f"   ⚠️  Skipping {model_name}: No datasets found.")
        return

    # 2. Pick the Champion (Largest File Size)
    champion_file = max(candidates, key=os.path.getsize)
    champion_source = os.path.basename(champion_file)
    
    print(f"   ⚔️  Training {model_name}...")
    print(f"       Unknown Candidate: {len(candidates)} files found.")
    print(f"       🏆 WINNER: {champion_source} (Best Dataset Selected)")

    try:
        df = pd.read_csv(champion_file)
        
        # 3. Cleaning & Standardization
        df.columns = df.columns.str.strip().str.lower().str.replace(' ', '_')
        
        # Drop useless columns if they exist
        drop_list = ['id', 'name', 'unnamed:_32', 'patient_id']
        df.drop(columns=[c for c in drop_list if c in df.columns], inplace=True)

        # Detect Target
        target_col = df.columns[-1]
        if target_override and target_override in df.columns:
            target_col = target_override

        # Label Encode (Text -> Numbers)
        le = LabelEncoder()
        for col in df.columns:
            if df[col].dtype == 'object':
                df[col] = le.fit_transform(df[col].astype(str))

        # 4. Train
        X = df.drop(columns=[target_col])
        y = df[target_col]
        
        model = RandomForestClassifier(n_estimators=150, random_state=42)
        model.fit(X, y)
        
        # 5. Save
        joblib.dump(model, os.path.join(MODEL_DIR, f"{model_name}.pkl"))
        print(f"       ✅ SAVED: {model_name}.pkl")

    except Exception as e:
        print(f"       ❌ Training Failed: {e}")

# ==================================================
# EXECUTE: TRAIN 12 MODELS USING "BEST" DATA
# ==================================================

# 1. Heart Disease
train_champion(["heart"], "heart_model")

# 2. Diabetes
train_champion(["diabetes"], "diabetes_model")

# 3. Kidney Disease (Chronic)
train_champion(["kidney"], "kidney_model")

# 4. Liver Disease
train_champion(["liver"], "liver_model")

# 5. Parkinson's (Samagra usually wins this)
train_champion(["parkinson"], "parkinsons_model")

# 6. Breast Cancer (Eda usually wins this)
train_champion(["breast", "cancer"], "breast_cancer_model")

# 7. Malaria (Karan usually wins this)
train_champion(["malaria"], "malaria_model")

# 8. Pneumonia (Tabular version if available, otherwise handled by CNN)
train_champion(["pneumonia"], "pneumonia_tabular_model")

# 9. Stroke
train_champion(["stroke"], "stroke_model")

# 10. Jaundice
train_champion(["jaundice"], "jaundice_model")

# 11. Thyroid
train_champion(["thyroid"], "thyroid_model")

# 12. Anemia
train_champion(["anemia"], "anemia_model")

print("\n" + "="*50)
print("🏁 DONE! Your system is now running on the BEST datasets found.")
print(f"📂 Models Location: {MODEL_DIR}")
print("="*50)