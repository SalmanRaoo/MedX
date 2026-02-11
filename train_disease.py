import pandas as pd
import numpy as np
from sklearn.tree import DecisionTreeClassifier
import joblib
import os

# CONFIG
ASSET_DIR = os.path.join("hospital_ai_assets", "models")
if not os.path.exists(ASSET_DIR): os.makedirs(ASSET_DIR)

print("🩺 Generating Disease Prediction Model...")

# 1. THE KNOWLEDGE BASE (Real Medical Data Mappings)
# This mimics the structure of large datasets found on Kaggle/GitHub
data = [
    # Viral / General
    {"fever": 1, "cough": 1, "fatigue": 1, "body_pain": 1, "runny_nose": 1, "disease": "Viral Flu"},
    {"fever": 1, "cough": 1, "chills": 1, "headache": 1, "disease": "Common Cold"},
    {"fatigue": 1, "weight_loss": 1, "cough": 1, "high_fever": 1, "disease": "Tuberculosis"},
    
    # Bacterial / Infection
    {"fever": 1, "chills": 1, "sweating": 1, "headache": 1, "nausea": 1, "disease": "Malaria"},
    {"fever": 1, "joint_pain": 1, "vomiting": 1, "rash": 1, "disease": "Dengue"},
    {"fever": 1, "abdominal_pain": 1, "diarrhea": 1, "headache": 1, "disease": "Typhoid"},
    
    # Organ Specific
    {"vomiting": 1, "yellowish_skin": 1, "abdominal_pain": 1, "fatigue": 1, "disease": "Jaundice"},
    {"chest_pain": 1, "breathlessness": 1, "sweating": 1, "vomiting": 0, "disease": "Heart Attack"},
    {"itching": 1, "skin_rash": 1, "bumps": 1, "disease": "Fungal Infection"},
    
    # Gastro
    {"vomiting": 1, "acidity": 1, "indigestion": 1, "burning_chest": 1, "disease": "GERD"},
    {"vomiting": 1, "abdominal_pain": 1, "swelling": 1, "fever": 1, "disease": "Appendicitis"}
]

# 2. FORMATTING
df = pd.DataFrame(data).fillna(0)
X = df.drop(columns=["disease"])
y = df["disease"]

# 3. BUILDING THE BRAIN
model = DecisionTreeClassifier()
model.fit(X, y)

# 4. SAVING TO DISK
joblib.dump(model, os.path.join(ASSET_DIR, "disease_predictor.pkl"))
joblib.dump(list(X.columns), os.path.join(ASSET_DIR, "disease_predictor_cols.pkl"))

print(f"✅ SUCCESS: 'disease_predictor.pkl' created.")
print(f"   - Knowledge: {len(y.unique())} Diseases")
print(f"   - Inputs: {len(X.columns)} Symptoms")