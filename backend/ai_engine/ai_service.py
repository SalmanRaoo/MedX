from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import joblib
import numpy as np
import os
import io
import warnings
try:
    import pandas as pd
except Exception:
    pd = None
# from PIL import Image # Uncomment if you have pillow installed for images

app = FastAPI(title="MedX Intelligent AI Service")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
# ==========================================
# 1. MODEL LOADING INFRASTRUCTURE
# ==========================================
MODEL_DIR = os.path.join("hospital_ai_assets", "models")
models = {}

# List of all models we expect from the "Champion" trainer
expected_models = [
    "diabetes_model", "heart_model", "kidney_model", "liver_model", 
    "maternal_model", "disease_predictor", 
    "parkinsons_model", "breast_cancer_model", "stroke_model", 
    "thyroid_model", "anemia_model", "jaundice_model", "malaria_model"
]

print("🏥 MEDX AI SERVICE STARTING...")
for name in expected_models:
    path = os.path.join(MODEL_DIR, f"{name}.pkl")
    if os.path.exists(path):
        try:
            models[name] = joblib.load(path)
            print(f"   ✅ Loaded: {name}")
        except Exception as e:
            print(f"   ❌ Failed to load {name}: {e}")
    else:
        print(f"   ⚠️  Missing: {name} (Run trainer script to fix)")
disease_predictor_cols = []
cols_path = os.path.join(MODEL_DIR, "disease_predictor_cols.pkl")
if os.path.exists(cols_path):
    try:
        disease_predictor_cols = joblib.load(cols_path)
        if hasattr(disease_predictor_cols, "tolist"):
            disease_predictor_cols = disease_predictor_cols.tolist()
        disease_predictor_cols = [str(c).strip().lower() for c in disease_predictor_cols]
        print(f"   ? Loaded: disease_predictor_cols ({len(disease_predictor_cols)} features)")
    except Exception as e:
        print(f"   ? Failed to load disease_predictor_cols: {e}")

if not disease_predictor_cols and "disease_predictor" in models:
    try:
        feature_names = getattr(models["disease_predictor"], "feature_names_in_", None)
        if feature_names is not None:
            if hasattr(feature_names, "tolist"):
                feature_names = feature_names.tolist()
            disease_predictor_cols = [str(c).strip().lower().replace(" ", "_") for c in feature_names if str(c).strip()]
            print(f"   ? Fallback loaded disease_predictor_cols from model.feature_names_in_ ({len(disease_predictor_cols)} features)")
    except Exception as e:
        print(f"   ? Failed fallback for disease_predictor_cols: {e}")

# ==========================================
# 2. HELPER FUNCTIONS
# ==========================================
class DataReq(BaseModel):
    values: list = None # For ordered arrays (Kidney, etc.)
    dict_data: dict = None # For named fields (Breast Cancer, etc.)

def get_prediction(model_name, data):
    if model_name not in models:
        return "Error: Model not loaded", 0.0
    
    model = models[model_name]
    try:
        shaped_input = [data]
        feature_names = getattr(model, "feature_names_in_", None)
        if pd is not None and feature_names is not None:
            try:
                cols = feature_names.tolist() if hasattr(feature_names, "tolist") else list(feature_names)
                if len(cols) == len(data):
                    shaped_input = pd.DataFrame([data], columns=cols)
            except Exception:
                shaped_input = [data]

        # Reshape for single prediction
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message="X does not have valid feature names*")
            prediction = model.predict(shaped_input)[0]
        
        # Try to get probability if supported
        try:
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", message="X does not have valid feature names*")
                proba = np.max(model.predict_proba(shaped_input))
            confidence = f"{proba*100:.1f}%"
        except:
            confidence = "N/A" # Some models (like SVM) might not support proba
            
        return str(prediction), confidence
    except Exception as e:
        return f"Error: {str(e)}", 0.0

# ==========================================
# 3. CLINICAL ENDPOINTS
# ==========================================

# --- A. DIABETES ---
@app.post("/predict/diabetes")
def predict_diabetes(req: dict):
    # Inputs: pregnancies, glucose, bp, skin, insulin, bmi, dpf, age
    glucose = req.get("glucose")
    bp = req.get("bp")
    insulin = req.get("insulin")
    bmi = req.get("bmi")

    if glucose is None or bp is None or insulin is None or bmi is None:
        raise HTTPException(
            status_code=400,
            detail="glucose, bp, insulin, and bmi are required for diabetes prediction",
        )

    data = [
        req.get("pregnancies", 0),
        glucose,
        bp,
        req.get("skin", 0),
        insulin,
        bmi,
        req.get("dpf", 0),
        req.get("age", 0),
    ]
    res, conf = get_prediction("diabetes_model", data)
    label = "Diabetic" if res == "1" else "Healthy"
    return {"result": label, "confidence": conf}

# --- B. HEART DISEASE ---
@app.post("/predict/heart")
def predict_heart(req: dict):
    # Preferred feature set (heart failure model)
    current_fields = [
        "age", "anaemia", "creatinine_phosphokinase", "diabetes",
        "ejection_fraction", "high_blood_pressure", "platelets",
        "serum_creatinine", "serum_sodium", "sex", "smoking", "time"
    ]
    # Legacy feature set (old CAD form) kept for backward compatibility
    legacy_fields = [
        "age", "sex", "cp", "trestbps", "chol", "fbs", "restecg",
        "thalach", "exang", "oldpeak", "slope", "ca", "thal"
    ]

    if all(k in req for k in current_fields):
        data = [req[k] for k in current_fields]
    elif all(k in req for k in legacy_fields):
        data = [req[k] for k in legacy_fields]
    else:
        missing_current = [k for k in current_fields if k not in req]
        missing_legacy = [k for k in legacy_fields if k not in req]
        raise HTTPException(
            status_code=400,
            detail=(
                "Heart prediction payload mismatch. "
                f"Missing current-set fields: {missing_current}. "
                f"Missing legacy-set fields: {missing_legacy}."
            ),
        )

    res, conf = get_prediction("heart_model", data)
    label = "Heart Risk Detected" if str(res) in {"1", "True", "true", "positive"} else "Healthy"
    return {"result": label, "confidence": conf}

# --- C. KIDNEY (WITH HYBRID EXPERT RULES) ---
@app.post("/predict/kidney")
def predict_kidney(req: dict):
    # Takes a list called "values" from frontend
    vals = req['values']
    
    # === HYBRID SAFETY LAYER ===
    # Index 3 is Albumin. If Albumin >= 4, FORCE SICK.
    try:
        albumin = vals[3]
        hemo = vals[14]
        if albumin >= 4.0:
            return {"result": "CKD Detected", "confidence": "100% (Critical Albumin)"}
        if hemo < 9.0:
            return {"result": "CKD Detected", "confidence": "100% (Critical Anemia)"}
    except:
        pass # If indices change, skip rule
        
    res, conf = get_prediction("kidney_model", vals)
    label = "CKD Detected" if res == "1" else "Healthy"
    return {"result": label, "confidence": conf}

# --- D. LIVER ---
@app.post("/predict/liver")
def predict_liver(req: dict):
    vals = req['values']
    res, conf = get_prediction("liver_model", vals)
    label = "Liver Disease" if res == "1" else "Healthy"
    return {"result": label, "confidence": conf}

# --- E. MATERNAL HEALTH ---
@app.post("/predict/maternal")
def predict_maternal(req: dict):
    vals = req['values']
    res, conf = get_prediction("maternal_model", vals)
    if res == "2": label = "High Risk"
    elif res == "1": label = "Mid Risk"
    else: label = "Low Risk"
    return {"result": label, "confidence": conf}

# --- F. PARKINSON'S (NEW) ---
@app.post("/predict/parkinsons")
def predict_parkinsons(req: dict):
    # Expects a list of vocal features
    vals = req['values']
    res, conf = get_prediction("parkinsons_model", vals)
    label = "Parkinson's Detected" if res == "1" else "Healthy"
    return {"result": label, "confidence": conf}

# --- G. BREAST CANCER (NEW) ---
@app.post("/predict/breast_cancer")
def predict_bc(req: dict):
    # Inputs: radius, texture, perimeter, area, smoothness
    data = [req['radius'], req['texture'], req['perimeter'], req['area'], req['smoothness']]
    res, conf = get_prediction("breast_cancer_model", data)
    # Note: Logic depends on dataset (0=Malignant or 1=Malignant). 
    # Usually in Sklearn: 0=Malignant, 1=Benign. In CSVs: 1=Malignant.
    # We assume 1 = Malignant (Standard CSV format)
    label = "Malignant (Cancer)" if res == "1" else "Benign (Safe)"
    return {"result": label, "confidence": conf}

# --- H. STROKE (NEW) ---
@app.post("/predict/stroke")
def predict_stroke(req: dict):
    data = [req['age'], req['glucose'], req['bmi'], req['smoking']]
    res, conf = get_prediction("stroke_model", data)
    label = "High Stroke Risk" if res == "1" else "Low Risk"
    return {"result": label, "confidence": conf}

# --- I. THYROID (NEW) ---
@app.post("/predict/thyroid")
def predict_thyroid(req: dict):
    data = [req['tsh'], req['t3'], req['t4']]
    res, conf = get_prediction("thyroid_model", data)
    label = "Thyroid Disorder" if res == "1" else "Normal"
    return {"result": label, "confidence": conf}

# --- J. ANEMIA (NEW) ---
@app.post("/predict/anemia")
def predict_anemia(req: dict):
    data = [req['gender'], req['hemo']]
    res, conf = get_prediction("anemia_model", data)
    label = "Anemic" if res == "1" else "Healthy"
    return {"result": label, "confidence": conf}

# --- K. JAUNDICE (NEW) ---
@app.post("/predict/jaundice")
def predict_jaundice(req: dict):
    vals = req['values'] # List of inputs
    res, conf = get_prediction("jaundice_model", vals)
    label = "Jaundice Detected" if res == "1" else "Healthy"
    return {"result": label, "confidence": conf}

# --- L. GENERAL SYMPTOMS ---
@app.post("/predict/disease")
def predict_disease(req: dict):
    if "disease_predictor" not in models:
        raise HTTPException(status_code=503, detail="disease_predictor model is not loaded")
    if not disease_predictor_cols:
        raise HTTPException(status_code=503, detail="disease_predictor_cols are not loaded")

    raw_symptoms = req.get("symptoms", [])
    if not isinstance(raw_symptoms, list) or not raw_symptoms:
        raise HTTPException(status_code=400, detail="symptoms must be a non-empty list")

    normalized_input = set()
    for symptom in raw_symptoms:
        key = str(symptom).strip().lower().replace(" ", "_")
        key = "_".join([chunk for chunk in key.split("_") if chunk])
        normalized_input.add(key)

    vector = [1 if col in normalized_input else 0 for col in disease_predictor_cols]
    model = models["disease_predictor"]
    prediction = model.predict([vector])[0]

    confidence = None
    try:
        probs = model.predict_proba([vector])[0]
        confidence = float(np.max(probs))
    except Exception:
        confidence = None

    known = set(disease_predictor_cols)
    matched = [c for c in disease_predictor_cols if c in normalized_input]
    unknown = sorted(list(normalized_input - known))

    return {
        "prediction": str(prediction),
        "confidence": f"{(confidence * 100):.1f}%" if confidence is not None else "N/A",
        "matched_features": matched,
        "matched_count": len(matched),
        "unknown_symptoms": unknown,
    }

# ==========================================
# 4. VISION ENDPOINTS (Placeholders)
# ==========================================
# --- ADD THESE IMPORTS AT THE VERY TOP OF ai_service.py ---
import io
from PIL import Image
try:
    from tensorflow.keras.models import load_model
    from tensorflow.keras.preprocessing.image import img_to_array
    TF_AVAILABLE = True
except ImportError:
    TF_AVAILABLE = False
    print("⚠️ TensorFlow not installed. Vision models will not load.")

# --- ADD THIS TO SECTION 1 (MODEL LOADING INFRASTRUCTURE) ---
vision_models = {}
if TF_AVAILABLE:
    for v_model in ["brain_tumor_model", "pneumonia_model"]:
        path = os.path.join(MODEL_DIR, f"{v_model}.h5")
        if os.path.exists(path):
            try:
                vision_models[v_model] = load_model(path)
                print(f"   👁️ Loaded Deep Learning Vision Model: {v_model}.h5")
            except Exception as e:
                print(f"   ❌ Failed to load {v_model}.h5: {e}")

# ==========================================
# 4. REAL VISION ENDPOINTS (DEEP LEARNING)
# ==========================================
# --- ADD THESE IMPORTS AT THE TOP OF ai_service.py ---
import io
from PIL import Image, ImageOps
try:
    from tensorflow.keras.models import load_model
    from tensorflow.keras.preprocessing.image import img_to_array
    TF_AVAILABLE = True
except ImportError:
    TF_AVAILABLE = False
    print("⚠️ TensorFlow not installed. Vision models will not load.")

# --- ADD THIS TO SECTION 1 (MODEL LOADING) IN ai_service.py ---
vision_models = {}
if TF_AVAILABLE:
    for v_model in ["brain_tumor_model", "pneumonia_model"]:
        path = os.path.join(MODEL_DIR, f"{v_model}.h5")
        if os.path.exists(path):
            vision_models[v_model] = load_model(path)
            print(f"   👁️ Loaded DL Vision Model: {v_model}.h5")

# ==========================================
# 4. REAL VISION ENDPOINTS (Deep Learning)
# ==========================================
def _prepare_vision_input(contents: bytes, model, default_hw: tuple[int, int]):
    img = Image.open(io.BytesIO(contents))

    expected_h, expected_w = default_hw
    expected_channels = 3
    input_shape = getattr(model, "input_shape", None)
    if isinstance(input_shape, list) and input_shape:
        input_shape = input_shape[0]
    if isinstance(input_shape, tuple) and len(input_shape) >= 4:
        h, w, c = input_shape[-3], input_shape[-2], input_shape[-1]
        if isinstance(h, int) and h > 0:
            expected_h = h
        if isinstance(w, int) and w > 0:
            expected_w = w
        if isinstance(c, int) and c in (1, 3):
            expected_channels = c

    img_mode = "L" if expected_channels == 1 else "RGB"
    img = img.convert(img_mode)
    img = img.resize((expected_w, expected_h))

    img_array = img_to_array(img) / 255.0
    img_array = np.expand_dims(img_array, axis=0)
    return img_array


@app.post("/predict/pneumonia")
async def predict_pneumonia(file: UploadFile = File(...)):
    if not TF_AVAILABLE or "pneumonia_model" not in vision_models:
         return {"result": "System Error: Vision AI offline", "confidence": "0%"}
         
    contents = await file.read()
    model = vision_models["pneumonia_model"]

    # Auto-match the loaded model input shape (channels + resolution).
    try:
        img_array = _prepare_vision_input(contents, model, default_hw=(150, 150))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid image upload: {exc}")
    
    prediction = model.predict(img_array)[0][0]
    
    if prediction >= 0.5:
        return {"result": "Pneumonia Detected", "confidence": f"{prediction*100:.1f}%"}
    else:
        return {"result": "Healthy Lungs", "confidence": f"{(1-prediction)*100:.1f}%"}


@app.post("/predict/brain_tumor")
async def predict_brain(file: UploadFile = File(...)):
    if not TF_AVAILABLE or "brain_tumor_model" not in vision_models:
         return {"result": "System Error: Vision AI offline", "confidence": "0%"}
         
    contents = await file.read()
    model = vision_models["brain_tumor_model"]

    # Auto-match the loaded model input shape (channels + resolution).
    try:
        img_array = _prepare_vision_input(contents, model, default_hw=(224, 224))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid image upload: {exc}")
    
    # Predict (This outputs an array of 4 probabilities)
    predictions = model.predict(img_array)[0]
    predicted_class_index = np.argmax(predictions)
    highest_confidence = predictions[predicted_class_index]
    
    # The 4 specific classes the author trained on
    class_labels = ["Glioma Tumor", "Meningioma Tumor", "No Tumor Detected", "Pituitary Tumor"]
    result_label = class_labels[predicted_class_index]
    
    return {"result": result_label, "confidence": f"{highest_confidence*100:.1f}%"}
@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": "medx-ai-engine",
        "loaded_ml_models": len(models),
        "loaded_vision_models": len(vision_models),
    }


@app.get("/")
def ai_home():
    return {
        "service": "MedX Intelligent AI Service",
        "status": "online",
        "health_endpoint": "/health",
    }