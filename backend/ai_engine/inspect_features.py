import argparse
import os
import pickle
from typing import Any, Dict, List

try:
    import joblib  # type: ignore
except Exception:
    joblib = None


MODEL_SPECS = [
    ("diabetes_model", "diabetes_model.pkl", "diabetes_model_cols.pkl"),
    ("heart_model", "heart_model.pkl", "heart_model_cols.pkl"),
    ("liver_model", "liver_model.pkl", "liver_model_cols.pkl"),
    ("breast_cancer_model", "breast_cancer_model.pkl", None),
    ("parkinsons_model", "parkinsons_model.pkl", None),
    ("maternal_model", "maternal_model.pkl", "maternal_model_cols.pkl"),
    ("kidney_model", "kidney_model.pkl", "kidney_model_cols.pkl"),
    ("disease_predictor", "disease_predictor.pkl", "disease_predictor_cols.pkl"),
]


def _to_list(value: Any) -> List[str]:
    if value is None:
        return []
    if hasattr(value, "tolist"):
        value = value.tolist()
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value]
    return [str(value)]


def _load_pickle(path: str) -> Any:
    if not os.path.exists(path):
        return None
    if joblib is not None:
        try:
            return joblib.load(path)
        except Exception:
            pass
    try:
        with open(path, "rb") as f:
            return pickle.load(f)
    except Exception:
        return None


def inspect_models(models_dir: str) -> Dict[str, Dict[str, Any]]:
    results: Dict[str, Dict[str, Any]] = {}
    for model_key, model_file, cols_file in MODEL_SPECS:
        model_path = os.path.join(models_dir, model_file)
        cols_path = os.path.join(models_dir, cols_file) if cols_file else None

        info: Dict[str, Any] = {
            "model_file": model_file,
            "cols_file": cols_file,
            "feature_names_in_": [],
            "cols_features": [],
            "resolved_feature_order": [],
        }

        model_obj = _load_pickle(model_path)
        if model_obj is not None and hasattr(model_obj, "feature_names_in_"):
            info["feature_names_in_"] = _to_list(getattr(model_obj, "feature_names_in_"))

        if cols_path:
            cols_obj = _load_pickle(cols_path)
            info["cols_features"] = _to_list(cols_obj)

        resolved = info["feature_names_in_"] or info["cols_features"]
        info["resolved_feature_order"] = resolved
        results[model_key] = info
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect MedX AI model feature requirements.")
    parser.add_argument(
        "--models-dir",
        default=os.path.join(os.path.dirname(__file__), "hospital_ai_assets", "models"),
        help="Path to folder containing model .pkl and *_cols.pkl files",
    )
    args = parser.parse_args()

    print(f"Inspecting models in: {args.models_dir}")
    print("=" * 80)
    data = inspect_models(args.models_dir)

    for model_key, info in data.items():
        print(f"\nModel: {model_key}")
        print(f"  model_file: {info['model_file']}")
        print(f"  cols_file: {info['cols_file']}")
        print(f"  feature_names_in_: {len(info['feature_names_in_'])}")
        if info["feature_names_in_"]:
            print("   - " + ", ".join(info["feature_names_in_"]))
        print(f"  cols_features: {len(info['cols_features'])}")
        if info["cols_features"]:
            print("   - " + ", ".join(info["cols_features"]))
        print(f"  resolved_feature_order: {len(info['resolved_feature_order'])}")
        if info["resolved_feature_order"]:
            print("   - " + ", ".join(info["resolved_feature_order"]))


if __name__ == "__main__":
    main()

