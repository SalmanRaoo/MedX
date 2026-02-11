import streamlit as st
import requests

# CONFIGURATION
API_URL = "http://127.0.0.1:8001"
st.set_page_config(page_title="MedX Intelligent ERP", page_icon="🏥", layout="wide")

# ======================= SESSION STATE =======================
if 'token' not in st.session_state:
    st.session_state['token'] = None

# ======================= HELPER FUNCTIONS =======================
def api_request(method, endpoint, data=None, files=None):
    try:
        url = f"{API_URL}{endpoint}"
        if method == "POST":
            if files: return requests.post(url, files=files)
            else: return requests.post(url, json=data)
        elif method == "GET": return requests.get(url)
    except Exception as e:
        st.error(f"❌ Connection Error: {e}")
        return None

def show_result(response):
    if response is None: return
    if response.status_code != 200:
        st.error(f"⚠️ Server Error: {response.text}")
        return
    try:
        data = response.json()
        if "result" in data:
            if "Healthy" in data['result'] or "Normal" in data['result']:
                st.success(f"✅ Result: {data['result']}")
            else:
                st.error(f"⚠️ Result: {data['result']}")
            
            if "confidence" in data:
                st.info(f"📊 Confidence: {data['confidence']}")
                
        elif "prediction" in data:
            st.success(f"✅ Predicted: {data['prediction']}")
        elif "diagnosis" in data:
            st.warning(f"🔍 Finding: {data['diagnosis']}")
    except:
        st.error("❌ Invalid JSON response")

# ======================= 1. LOGIN SCREEN =======================
if not st.session_state['token']:
    col1, col2 = st.columns([1, 2])
    with col1:
        st.title("🏥 MedX Login")
        st.markdown("Authorized Personnel Only")
        
        email = st.text_input("Username", "admin")
        password = st.text_input("Password", type="password")
        
        if st.button("Login", type="primary"):
            if email and password:
                st.session_state['token'] = "logged_in_secure"
                st.success("Login Successful!")
                st.rerun()
            else:
                st.error("Please enter credentials")
    with col2:
        st.info("System Status: Online 🟢")

# ======================= 2. MAIN DASHBOARD =======================
else:
    st.sidebar.title("MedX Navigation")
    menu = st.sidebar.radio("Modules:", ["🏥 Clinical AI", "💊 Pharmacy", "🚪 Logout"])
    
    if menu == "🚪 Logout":
        st.session_state['token'] = None
        st.rerun()

    if menu == "🏥 Clinical AI":
        st.title("🩺 AI Diagnostic Center")
        
        tabs = st.tabs([
            "🩸 Diabetes", "🫀 Heart", "🦠 Disease", 
            "🧪 Kidney", "🦴 Pneumonia", "🧠 Brain Tumor"
        ])
        
        # --- 1. DIABETES (FULL FORM RESTORED) ---
        with tabs[0]:
            st.subheader("Diabetes Risk Assessment")
            c1, c2, c3, c4 = st.columns(4)
            preg = c1.number_input("Pregnancies", 0, 20, 1)
            gluc = c2.number_input("Glucose", 0, 300, 120)
            bp = c3.number_input("BP", 0, 200, 72)
            skin = c4.number_input("Skin Thickness", 0, 100, 20)
            
            c5, c6, c7, c8 = st.columns(4)
            ins = c5.number_input("Insulin", 0, 900, 79)
            bmi = c6.number_input("BMI", 0.0, 70.0, 32.0)
            dpf = c7.number_input("Diabetes Pedigree", 0.0, 3.0, 0.5)
            age = c8.number_input("Age", 0, 120, 33)
            
            if st.button("Analyze Diabetes"):
                payload = {"pregnancies": preg, "glucose": gluc, "bp": bp, "skin": skin, "insulin": ins, "bmi": bmi, "dpf": dpf, "age": age}
                res = api_request("POST", "/predict/diabetes", data=payload)
                show_result(res)

        # --- 2. HEART (FULL FORM RESTORED) ---
        with tabs[1]:
            st.subheader("Heart Disease Risk")
            h1, h2, h3, h4 = st.columns(4)
            age_h = h1.number_input("Age", 20, 100, 55)
            sex = h2.selectbox("Sex", [1, 0], format_func=lambda x: "Male" if x==1 else "Female")
            cp = h3.selectbox("Chest Pain Type", [0, 1, 2, 3])
            trstbps = h4.number_input("Resting BP", 90, 200, 130)
            
            h5, h6, h7, h8 = st.columns(4)
            chol = h5.number_input("Cholesterol", 100, 600, 250)
            fbs = h6.selectbox("Fasting BS > 120", [1, 0])
            restecg = h7.selectbox("Rest ECG", [0, 1, 2])
            thalach = h8.number_input("Max Heart Rate", 60, 220, 150)
            
            h9, h10, h11, h12 = st.columns(4)
            exang = h9.selectbox("Exercise Angina", [1, 0])
            oldpeak = h10.number_input("ST Depression", 0.0, 10.0, 1.0)
            slope = h11.selectbox("ST Slope", [0, 1, 2])
            thal = h12.selectbox("Thal", [0, 1, 2, 3])
            
            if st.button("Analyze Heart"):
                payload = {
                    "age": age_h, "sex": sex, "cp": cp, "trestbps": trstbps, 
                    "chol": chol, "fbs": fbs, "restecg": restecg, "thalach": thalach, 
                    "exang": exang, "oldpeak": oldpeak, "slope": slope, "ca": 0, "thal": thal
                }
                res = api_request("POST", "/predict/heart", data=payload)
                show_result(res)

        # --- 3. DISEASE ---
        with tabs[2]:
            st.subheader("General Symptom Checker")
            symptoms_list = [
                "fever", "cough", "fatigue", "body_pain", "runny_nose", "chills", "headache", 
                "sweating", "nausea", "joint_pain", "vomiting", "rash", "abdominal_pain", 
                "diarrhea", "chest_pain", "breathlessness", "itching", "skin_rash", "acidity"
            ]
            selected = st.multiselect("Select Symptoms", symptoms_list)
            if st.button("Check Disease"):
                res = api_request("POST", "/predict/disease", data={"symptoms": selected})
                show_result(res)

        # --- 4. KIDNEY (FIXED - EXPOSED HEMOGLOBIN) ---
        with tabs[3]:
            st.subheader("Chronic Kidney Disease (CKD)")
            st.info("Adjust Hemoglobin to test severity (Low = Sick)")
            
            k1, k2, k3 = st.columns(3)
            age_k = k1.number_input("Age (Kidney)", 10, 100, 40)
            bp_k = k2.number_input("Blood Pressure", 50, 180, 80)
            sg = k3.selectbox("Specific Gravity", [1.005, 1.010, 1.015, 1.020, 1.025], index=3)
            
            k4, k5, k6 = st.columns(3)
            al = k4.selectbox("Albumin (0=Normal)", [0, 1, 2, 3, 4, 5], index=0)
            su = k5.selectbox("Sugar (0=Normal)", [0, 1, 2, 3, 4, 5], index=0)
            # CRITICAL FIX: Expose Hemoglobin so user can force a 'Sick' result
            hemo = k6.number_input("Hemoglobin (Normal: 12-16)", 3.0, 18.0, 15.0)

            if st.button("Analyze Kidney"):
                # HIDDEN VALUES (Defaults)
                # We use the visible 'hemo' value instead of hardcoding 15.0
                
                full_values = [
                    age_k, bp_k, sg, al, su, 1,     # Visible + RBC(1=Normal)
                    1, 0, 0, 90, 20, 0.8, 140, 4.0, # Biochemical Normals
                    hemo, 45, 8000, 5.0,            # Hemoglobin (USER INPUT), Cells
                    0, 0, 0, 1, 0, 0                # History
                ]
                
                res = api_request("POST", "/predict/kidney", data={"values": full_values})
                show_result(res)

        # --- 5. VISION MODELS ---
        with tabs[4]:
            st.subheader("Pneumonia Detection")
            f = st.file_uploader("Upload Chest X-Ray", key="xray")
            if f and st.button("Scan X-Ray"):
                res = api_request("POST", "/predict/pneumonia", files={"file": f.getvalue()})
                show_result(res)

        with tabs[5]:
            st.subheader("Brain Tumor Detection")
            f2 = st.file_uploader("Upload Brain MRI", key="mri")
            if f2 and st.button("Scan MRI"):
                res = api_request("POST", "/predict/brain_tumor", files={"file": f2.getvalue()})
                show_result(res)