import joblib
import os

path = "hospital_ai_assets/models/kidney_model_cols.pkl"
if os.path.exists(path):
    cols = joblib.load(path)
    print("YOUR KIDNEY MODEL EXPECTS THESE INPUTS:")
    print(cols)
else:
    print("Could not find column file.")