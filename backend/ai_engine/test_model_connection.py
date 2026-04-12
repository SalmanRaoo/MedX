import argparse
import json
import os
from typing import Any, Dict, List, Tuple

import requests


def _print_result(label: str, ok: bool, status: int, payload: Any) -> None:
    marker = "PASS" if ok else "FAIL"
    print(f"[{marker}] {label} (status={status})")
    if isinstance(payload, (dict, list)):
        print("  " + json.dumps(payload, ensure_ascii=False))
    else:
        print(f"  {payload}")


def _ai_test_cases() -> List[Tuple[str, str, Dict[str, Any]]]:
    return [
        (
            "Diabetes",
            "/predict/diabetes",
            {"pregnancies": 2, "glucose": 130, "bp": 82, "skin": 28, "insulin": 120, "bmi": 29.4, "dpf": 0.62, "age": 41},
        ),
        (
            "Heart",
            "/predict/heart",
            {"age": 52, "anaemia": 0, "creatinine_phosphokinase": 220, "diabetes": 1, "ejection_fraction": 38, "high_blood_pressure": 1, "platelets": 255000, "serum_creatinine": 1.1, "serum_sodium": 137, "sex": 1, "smoking": 0, "time": 120},
        ),
        (
            "Liver",
            "/predict/liver",
            {"values": [45, 1, 1.2, 0.3, 110, 32, 30, 7.1, 3.8, 1.1]},
        ),
        (
            "Breast Cancer",
            "/predict/breast_cancer",
            {"radius": 14.1, "texture": 19.2, "perimeter": 92.0, "area": 650.0, "smoothness": 0.1},
        ),
        (
            "Parkinsons",
            "/predict/parkinsons",
            {"values": [119.9, 157.3, 74.9, 0.004, 0.00003, 0.002, 0.0025, 0.006, 0.03, 0.29, 0.012, 0.015, 0.02, 0.036, 0.02, 21.1, 0.42, 0.72, -4.8, 0.26, 2.3, 0.28]},
        ),
        (
            "Maternal",
            "/predict/maternal",
            {"values": [30, 120, 80, 7.0, 98.6, 85]},
        ),
        (
            "Kidney",
            "/predict/kidney",
            {"values": [48, 80, 1.02, 1, 0, 0, 1, 0, 0, 121, 36, 1.2, 140, 4.2, 13.1, 40, 7800, 5.2, 1, 0, 0, 1, 0, 0]},
        ),
        (
            "General Disease",
            "/predict/disease",
            {"symptoms": ["fever", "cough", "fatigue"]},
        ),
    ]


def test_ai_service(ai_base_url: str) -> bool:
    print(f"Testing AI service: {ai_base_url}")
    all_ok = True
    for name, path, payload in _ai_test_cases():
        try:
            res = requests.post(f"{ai_base_url}{path}", json=payload, timeout=20)
            ok = 200 <= res.status_code < 300
            data = res.json() if res.headers.get("content-type", "").startswith("application/json") else res.text
            _print_result(f"AI {name}", ok, res.status_code, data)
            all_ok = all_ok and ok
        except Exception as exc:
            _print_result(f"AI {name}", False, 0, str(exc))
            all_ok = False
    return all_ok


def test_backend_bridge(api_base_url: str, token: str, patient_id: int) -> bool:
    print(f"\nTesting backend bridge: {api_base_url} (patient_id={patient_id})")
    headers = {"Authorization": f"Bearer {token}"}
    all_ok = True

    smart_payloads = [
        {
            "model_code": "DIABETES",
            "clinical_inputs": {"pregnancies": 2, "glucose": 130, "bp": 82, "skin": 28, "insulin": 120, "bmi": 29.4, "dpf": 0.62, "age": 41},
            "selected_symptoms": [],
        },
        {
            "model_code": "HEART",
            "clinical_inputs": {"age": 52, "anaemia": 0, "creatinine_phosphokinase": 220, "diabetes": 1, "ejection_fraction": 38, "high_blood_pressure": 1, "platelets": 255000, "serum_creatinine": 1.1, "serum_sodium": 137, "sex": 1, "smoking": 0, "time": 120},
            "selected_symptoms": [],
        },
        {
            "model_code": "GENERAL_DISEASE",
            "clinical_inputs": {},
            "selected_symptoms": ["fever", "cough", "fatigue"],
        },
    ]

    for case in smart_payloads:
        payload = {
            "patient_id": patient_id,
            "patient_age": 40,
            "test_type": case["model_code"],
            "specimen_type": "Serum",
            "collection_timestamp": "2026-01-01T10:00",
            "clinical_notes": "Connectivity test run",
            "clinical_inputs": case["clinical_inputs"],
            "selected_symptoms": case["selected_symptoms"],
            "standard_markers": [
                {"key": "cbc_wbc", "marker_name": "WBC", "result_value": 7.2, "units": "x10^9/L"},
                {"key": "cbc_rbc", "marker_name": "RBC", "result_value": 4.8, "units": "x10^12/L"},
                {"key": "cbc_haemoglobin", "marker_name": "Haemoglobin", "result_value": 13.7, "units": "g/dL"},
                {"key": "cbc_platelets", "marker_name": "Platelets", "result_value": 240, "units": "x10^9/L"},
            ],
        }
        try:
            res = requests.post(f"{api_base_url}/lab/smart-records", json=payload, headers=headers, timeout=25)
            ok = 200 <= res.status_code < 300
            data = res.json() if res.headers.get("content-type", "").startswith("application/json") else res.text
            _print_result(f"Bridge {case['model_code']}", ok, res.status_code, data)
            all_ok = all_ok and ok
        except Exception as exc:
            _print_result(f"Bridge {case['model_code']}", False, 0, str(exc))
            all_ok = False
    return all_ok


def main() -> None:
    parser = argparse.ArgumentParser(description="Connectivity test for MedX AI models and backend bridge.")
    parser.add_argument("--ai-url", default="http://127.0.0.1:8001", help="AI service base URL")
    parser.add_argument("--api-url", default="http://127.0.0.1:8000", help="Main backend API base URL")
    parser.add_argument("--token", default=os.getenv("MEDX_TOKEN", ""), help="JWT token for backend bridge test")
    parser.add_argument("--patient-id", type=int, default=int(os.getenv("MEDX_PATIENT_ID", "0") or 0), help="Patient ID for backend bridge test")
    args = parser.parse_args()

    ai_ok = test_ai_service(args.ai_url.rstrip("/"))
    bridge_ok = True
    bridge_state = "OK"
    if args.token and args.patient_id > 0:
        bridge_ok = test_backend_bridge(args.api_url.rstrip("/"), args.token, args.patient_id)
        bridge_state = "OK" if bridge_ok else "FAILED"
    else:
        print("\nSkipping backend bridge test (provide --token and --patient-id).")
        bridge_state = "SKIPPED"

    print("\nSummary")
    print(f"  AI endpoints: {'OK' if ai_ok else 'FAILED'}")
    print(f"  Backend bridge: {bridge_state}")


if __name__ == "__main__":
    main()
