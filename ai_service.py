from fastapi import FastAPI, UploadFile, File
from pydantic import BaseModel
import joblib
import numpy as np
import tensorflow as tf
from PIL import Image
import io
import os

# ======================= CONFIGURATION =======================
app = FastAPI(title="MedX AI Engine", version="PRODUCTION")

# Path Setup (Locates the 'hospital_ai_assets' folder automatically)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSET_DIR = os.path.join(BASE_DIR, "hospital_ai_assets", "models")

# Global Model Storage
models = {}
vision_models = {}

# ======================= 1. LOAD MODELS =======================
# These exact filenames must exist in hospital_ai_assets/models/
pkl_files = [
    "diabetes_model", 
    "heart_model", 
    "kidney_model", 
    "liver_model", 
    "maternal_model", 
    "disease_predictor"
]

print("\n" + "="*50)
print(f"📂 LOADING MODELS FROM: {ASSET_DIR}")

for name in pkl_files:
    try:
        path = os.path.join(ASSET_DIR, f"{name}.pkl")
        if os.path.exists(path):
            models[name] = joblib.load(path)
            print(f"   ✅ LOADED: {name}.pkl")
        else:
            print(f"   ❌ MISSING: {name}.pkl")
        
        # Load Columns if available
        col_path = os.path.join(ASSET_DIR, f"{name}_cols.pkl")
        if os.path.exists(col_path):
            models[f"{name}_cols"] = joblib.load(col_path)

    except Exception as e:
        print(f"   ⚠️ ERROR loading {name}: {e}")

# Load Vision Models
vision_files = {"pneumonia": "pneumonia_model.h5", "brain_tumor": "brain_tumor_model.h5"}
for key, filename in vision_files.items():
    try:
        path = os.path.join(ASSET_DIR, filename)
        if os.path.exists(path):
            vision_models[key] = tf.keras.models.load_model(path)
            print(f"   ✅ LOADED VISION: {filename}")
    except:
        print(f"   ⚠️ ERROR loading {filename}")

print("="*50 + "\n")

# ======================= SCHEMAS =======================
class DataReq(BaseModel): values: list[float]
class SymptomReq(BaseModel): symptoms: list[str]

# ======================= HELPER =======================
def get_prediction(model_name, input_data):
    """Safely runs prediction on any loaded .pkl model"""
    model = models.get(model_name)
    if not model: return "Model Offline", "0.00"
    try:
        pred = model.predict([input_data])[0]
        # Try to get confidence score
        confidence = "0.95"
        if hasattr(model, "predict_proba"):
            try:
                probs = model.predict_proba([input_data])[0]
                confidence = f"{max(probs):.2f}"
            except: pass
        return str(pred), confidence
    except Exception as e:
        return f"Error: {str(e)}", "0.00"

def process_image(file_bytes):
    image = Image.open(io.BytesIO(file_bytes)).convert('RGB')
    image = image.resize((224, 224))
    img_array = np.array(image) / 255.0
    img_array = np.expand_dims(img_array, axis=0)
    return img_array

# ======================= API ENDPOINTS (FIXED PATHS) =======================

@app.get("/")
def home(): return {"status": "AI Service Online", "loaded": list(models.keys())}

# --- 1. DIABETES (Fixed: /predict/diabetes) ---
@app.post("/predict/diabetes")
def predict_diabetes(d: dict):
    # Mapping dict keys to list for model
    try:
        # Order: Pregnancies, Glucose, BP, Skin, Insulin, BMI, DPF, Age
        data = [
            d.get('pregnancies', 0), d.get('glucose', 120), d.get('bp', 70), 
            d.get('skin', 20), d.get('insulin', 79), d.get('bmi', 32.0), 
            d.get('dpf', 0.5), d.get('age', 33)
        ]
        res, conf = get_prediction("diabetes_model", data)
        label = "Diabetic" if res == "1" else "Healthy"
        return {"result": label, "confidence": conf}
    except Exception as e:
        return {"result": "Error", "detail": str(e)}

# --- 2. HEART (Fixed: /predict/heart) ---
@app.post("/predict/heart")
def predict_heart(d: dict):
    try:
        # Order: age, sex, cp, trestbps, chol, fbs, restecg, thalach, exang, oldpeak, slope, ca, thal
        data = [
            d.get('age', 50), d.get('sex', 1), d.get('cp', 0), d.get('trestbps', 130), 
            d.get('chol', 250), d.get('fbs', 0), d.get('restecg', 1), d.get('thalach', 150), 
            d.get('exang', 0), d.get('oldpeak', 1.0), d.get('slope', 1), d.get('ca', 0), d.get('thal', 2)
        ]
        res, conf = get_prediction("heart_model", data)
        label = "Heart Disease Risk" if res == "1" else "Normal"
        return {"result": label, "confidence": conf}
    except Exception as e:
        return {"result": "Error", "detail": str(e)}

# --- 3. DISEASE (Fixed: /predict/disease) ---
@app.post("/predict/disease")
def predict_disease(req: SymptomReq):
    model = models.get("disease_predictor")
    cols = models.get("disease_predictor_cols")
    if not model or not cols: return {"error": "Model not loaded"}

    # Convert symptoms list to 0/1 vector
    input_vector = [0] * len(cols)
    for s in req.symptoms:
        if s in cols: input_vector[cols.index(s)] = 1
            
    pred = model.predict([input_vector])[0]
    return {"prediction": str(pred), "confidence": "High"}

# --- 4. KIDNEY (With Expert Rule Override) ---
@app.post("/predict/kidney")
def predict_kidney(req: DataReq):
    # DataReq.values is a list. Based on your frontend:
    # Index 3 is Albumin (0, 1, 2, 3, 4, 5)
    # Index 14 is Hemoglobin
    
    albumin_level = req.values[3]
    hemoglobin_level = req.values[14]

    # === EXPERT RULE OVERRIDE (Hybrid AI) ===
    # If Albumin is dangerously high (>3), force detection.
    if albumin_level >= 3:
        return {
            "result": "CKD Detected", 
            "confidence": "0.99 (Critical Marker Override)"
        }
    
    # If Hemoglobin is dangerously low (<10), force detection.
    if hemoglobin_level < 10.0:
        return {
            "result": "CKD Detected", 
            "confidence": "0.98 (Critical Marker Override)"
        }

    # === STANDARD AI PREDICTION ===
    # Only use the AI model if there are no immediate critical flags
    res, conf = get_prediction("kidney_model", req.values)
    label = "CKD Detected" if res == "1" else "Healthy"
    
    return {"result": label, "confidence": conf}

# --- 5. LIVER (Fixed: /predict/liver) ---
@app.post("/predict/liver")
def predict_liver(req: DataReq):
    res, conf = get_prediction("liver_model", req.values)
    label = "Liver Issue" if res == "1" else "Healthy"
    return {"result": label, "confidence": conf}

# --- 6. MATERNAL (Fixed: /predict/maternal) ---
@app.post("/predict/maternal")
def predict_maternal(req: DataReq):
    res, conf = get_prediction("maternal_model", req.values)
    labels = {"0": "Low Risk", "1": "Mid Risk", "2": "High Risk"}
    return {"result": labels.get(res, f"Risk Level {res}"), "confidence": conf}

# --- 7. VISION MODELS ---
@app.post("/predict/pneumonia")
async def predict_pneumonia_api(file: UploadFile = File(...)):
    model = vision_models.get("pneumonia")
    if not model: return {"diagnosis": "Model Missing"}
    try:
        img = process_image(await file.read())
        score = float(model.predict(img)[0][0])
        label = "PNEUMONIA" if score > 0.5 else "NORMAL"
        return {"diagnosis": label, "confidence": f"{score:.2f}"}
    except: return {"diagnosis": "Error"}

@app.post("/predict/brain_tumor")
async def predict_brain_api(file: UploadFile = File(...)):
    model = vision_models.get("brain_tumor")
    if not model: return {"result": "Model Missing"}
    try:
        img = process_image(await file.read())
        score = float(model.predict(img)[0][0])
        label = "TUMOR DETECTED" if score > 0.5 else "NO TUMOR"
        return {"result": label, "confidence": f"{score:.2f}"}
    except: return {"result": "Error"}