import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import LabelEncoder
import joblib
import os
import requests
import io

MODEL_DIR = os.path.join("hospital_ai_assets", "models")
DATA_DIR = os.path.join("hospital_ai_assets", "harvested_data")
os.makedirs(MODEL_DIR, exist_ok=True)

# 1. TRAIN PARKINSON'S (Real Data)
print("🧠 Training Parkinson's Model...")
p_file = os.path.join(DATA_DIR, "uci_recovered_parkinsons.csv")
if os.path.exists(p_file):
    df = pd.read_csv(p_file)
    # Target is 'status', drop the patient 'name' column
    X = df.drop(columns=['name', 'status'])
    y = df['status']
    
    model = RandomForestClassifier(n_estimators=100, random_state=42)
    model.fit(X, y)
    joblib.dump(model, os.path.join(MODEL_DIR, "parkinsons_model.pkl"))
    print("   ✅ SAVED: parkinsons_model.pkl")

# 2. TRAIN BREAST CANCER (Real Data)
print("🎀 Training Breast Cancer Model...")
b_file = os.path.join(DATA_DIR, "uci_recovered_breast_cancer.csv")
if os.path.exists(b_file):
    # UCI data has no headers. Col 1 is the Target (M=Malignant, B=Benign)
    df = pd.read_csv(b_file, header=None)
    X = df.iloc[:, 2:] # Features start at column 2
    y = df.iloc[:, 1]  
    
    y = LabelEncoder().fit_transform(y) # Convert M/B to 1/0
    
    model = RandomForestClassifier(n_estimators=100, random_state=42)
    model.fit(X, y)
    joblib.dump(model, os.path.join(MODEL_DIR, "breast_cancer_model.pkl"))
    print("   ✅ SAVED: breast_cancer_model.pkl")

# 3. GET AND TRAIN KIDNEY (Real Data via 2025 Repo)
print("💧 Fetching & Training Kidney Model...")
kidney_url = "https://raw.githubusercontent.com/Hassan123j/Chronic-Kidney-Disease-CKD-Predictor-App/main/kidney_disease.csv"
try:
    s = requests.get(kidney_url).content
    df = pd.read_csv(io.StringIO(s.decode('utf-8')))
    
    df = df.drop(columns=['id'])
    # Fill missing medical records to prevent crashes
    df = df.ffill().bfill() 
    
    target_col = 'classification'
    X = df.drop(columns=[target_col])
    y = df[target_col]
    
    # Encode all text to numbers
    for col in X.columns:
        if X[col].dtype == 'object':
            X[col] = LabelEncoder().fit_transform(X[col].astype(str))
            
    y = LabelEncoder().fit_transform(y.astype(str))
    
    model = RandomForestClassifier(n_estimators=100, random_state=42)
    model.fit(X, y)
    joblib.dump(model, os.path.join(MODEL_DIR, "kidney_model.pkl"))
    print("   ✅ SAVED: kidney_model.pkl")
except Exception as e:
    print(f"   ❌ Kidney failed: {e}")

print("\n🏁 ALL REAL TABULAR MODELS ARE NOW READY!")
