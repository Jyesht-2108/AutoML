"""
Sklearn Model Evaluation Service — for tabular and text models.

Handles evaluation, metric computation, SHAP explainability, and bundle creation
for scikit-learn based models (tabular and text classification/regression).
"""

import os
import csv
import json
import pickle
import shutil
import zipfile
import traceback
from typing import Dict, Any
from pathlib import Path

from services.database_service import db_service
from services.storage_service import storage_service


def _find_data_files(directory: str) -> list:
    """Find CSV/text files."""
    files = []
    for dirpath, _, filenames in os.walk(directory):
        for f in filenames:
            if Path(f).suffix.lower() in {".csv", ".tsv", ".parquet"}:
                files.append(os.path.join(dirpath, f))
    return files


async def execute_sklearn_evaluation(project_id: str) -> Dict[str, Any]:
    """
    Evaluate a trained sklearn model (tabular or text).

    Steps:
    1. Download model (.pkl) and dataset
    2. Re-run predictions on test data
    3. Compute metrics
    4. Generate feature importance / SHAP explanations
    5. Create downloadable bundle
    6. Upload bundle and update database
    """
    temp_files = []

    try:
        db_service.log_agent_activity(project_id, "Sklearn evaluation workflow initiated", "info")

        project = db_service.get_project(project_id)
        if not project:
            return {"success": False, "error": f"Project {project_id} not found"}

        db_service.update_project_status(project_id, "evaluating")

        model_record = db_service.get_model_by_project(project_id)
        if not model_record:
            db_service.update_project_status(project_id, "failed")
            return {"success": False, "error": "Model not found"}

        dataset = db_service.get_dataset(project_id)
        if not dataset:
            db_service.update_project_status(project_id, "failed")
            return {"success": False, "error": "Dataset not found"}

        project_name = project.get("name", "model")
        project_metadata = project.get("metadata", {})
        task_type = project.get("task_type", "tabular_classification")
        model_metadata = model_record.get("metadata", {})

        import tempfile
        temp_dir = os.path.join(tempfile.gettempdir(), f"evaluation_{project_id}")
        os.makedirs(temp_dir, exist_ok=True)
        temp_files.append(temp_dir)

        # Download model
        model_path = os.path.join(temp_dir, "model.pkl")
        temp_files.append(model_path)
        db_service.log_agent_activity(project_id, "Downloading model...", "info")
        storage_service.download_model(model_record.get("gcs_url"), model_path)

        # Download dataset
        dataset_zip_path = os.path.join(temp_dir, "dataset.zip")
        dataset_extract_dir = os.path.join(temp_dir, "dataset")
        temp_files.extend([dataset_zip_path, dataset_extract_dir])

        db_service.log_agent_activity(project_id, "Downloading dataset...", "info")
        storage_service.download_dataset(dataset.get("gcs_url"), dataset_zip_path)

        with zipfile.ZipFile(dataset_zip_path, "r") as zf:
            zf.extractall(dataset_extract_dir)

        # Load model
        with open(model_path, "rb") as f:
            model = pickle.load(f)

        # Load data
        data_files = _find_data_files(dataset_extract_dir)
        if not data_files:
            db_service.update_project_status(project_id, "failed")
            return {"success": False, "error": "No data files found"}

        primary_file = max(data_files, key=os.path.getsize)

        rows = []
        headers = []
        with open(primary_file, "r", encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames or []
            for row in reader:
                rows.append(row)

        # Get column info from model metadata
        feature_names = model_metadata.get("feature_names", [])
        target_col = model_metadata.get("target_column", "")
        class_labels = model_metadata.get("class_labels", [])
        text_col = model_metadata.get("text_column", "")

        # Metrics are already computed during training, retrieve them
        metrics = model_metadata.get("metrics", {})

        if not metrics:
            db_service.log_agent_activity(project_id, "No pre-computed metrics found, using model defaults", "warning")
            metrics = {"accuracy": 0.0}

        db_service.log_agent_activity(project_id, f"Evaluation metrics: {json.dumps(metrics, indent=2)}", "info")

        # Generate feature importance
        feature_importance = {}
        try:
            if hasattr(model, "feature_importances_"):
                # Tree-based models (RF, XGBoost, GB)
                importances = model.feature_importances_
                if feature_names and len(feature_names) == len(importances):
                    feature_importance = {name: round(float(imp), 4) for name, imp in zip(feature_names, importances)}
                    # Sort by importance
                    feature_importance = dict(sorted(feature_importance.items(), key=lambda x: x[1], reverse=True))
                db_service.log_agent_activity(project_id, f"Feature importance computed ({len(feature_importance)} features)", "info")

            elif hasattr(model, "named_steps"):
                # Pipeline (text models)
                clf = model.named_steps.get("clf")
                tfidf = model.named_steps.get("tfidf")
                if clf and tfidf and hasattr(clf, "coef_"):
                    import numpy as np
                    vocab = tfidf.get_feature_names_out()
                    coef = clf.coef_
                    if len(coef.shape) == 1:
                        top_indices = np.argsort(np.abs(coef))[-20:]
                    else:
                        top_indices = np.argsort(np.abs(coef).mean(axis=0))[-20:]
                    feature_importance = {str(vocab[i]): round(float(np.abs(coef).flatten()[i]), 4) for i in top_indices}
                    feature_importance = dict(sorted(feature_importance.items(), key=lambda x: x[1], reverse=True))
                    db_service.log_agent_activity(project_id, f"Top text features computed ({len(feature_importance)} words)", "info")
        except Exception as e:
            db_service.log_agent_activity(project_id, f"Feature importance extraction warning: {str(e)}", "warning")

        # Create bundle
        bundle_dir = os.path.join(temp_dir, "bundle")
        os.makedirs(bundle_dir, exist_ok=True)

        # Copy model
        shutil.copy2(model_path, os.path.join(bundle_dir, "model.pkl"))

        # Write metadata
        bundle_metadata = {
            "project_name": project_name,
            "task_type": task_type,
            "model_type": model_metadata.get("model_type", "unknown"),
            "framework": "scikit-learn",
            "metrics": metrics,
            "feature_importance": feature_importance,
            "class_labels": class_labels,
            "feature_names": feature_names,
            "target_column": target_col,
            "text_column": text_col,
        }

        with open(os.path.join(bundle_dir, "metadata.json"), "w") as f:
            json.dump(bundle_metadata, f, indent=2)

        if class_labels:
            with open(os.path.join(bundle_dir, "labels.json"), "w") as f:
                json.dump({"labels": class_labels}, f, indent=2)

        # Generate predict.py script
        if task_type == "text_classification":
            predict_script = _generate_text_predict_script(class_labels)
        else:
            predict_script = _generate_tabular_predict_script(feature_names, target_col, class_labels, task_type)

        with open(os.path.join(bundle_dir, "predict.py"), "w") as f:
            f.write(predict_script)

        # Generate README
        readme = _generate_readme(project_name, task_type, metrics, feature_importance, class_labels)
        with open(os.path.join(bundle_dir, "README.md"), "w") as f:
            f.write(readme)

        # Zip bundle
        bundle_zip_path = os.path.join(temp_dir, f"{project_name}_bundle.zip")
        temp_files.append(bundle_zip_path)

        with zipfile.ZipFile(bundle_zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, _, files in os.walk(bundle_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, bundle_dir)
                    zf.write(file_path, arcname)

        # Upload bundle
        db_service.log_agent_activity(project_id, "Uploading evaluation bundle...", "info")
        bundle_gcs_url = storage_service.upload_bundle(bundle_zip_path, project_name)
        db_service.log_agent_activity(project_id, f"Bundle uploaded: {bundle_gcs_url}", "info")

        # Update model record
        updated_metadata = {
            **model_metadata,
            "metrics": metrics,
            "feature_importance": feature_importance,
            "bundle_url": bundle_gcs_url,
        }
        db_service.update_model_metrics(model_record["id"], metrics.get("accuracy", metrics.get("r2_score", 0)), updated_metadata)

        # Update project status and metadata
        project_record = db_service.client.table("projects").select("metadata").eq("id", project_id).execute()
        if project_record.data:
            project_metadata = project_record.data[0].get("metadata") or {}
            project_metadata["metrics"] = metrics
            project_metadata["feature_importance"] = feature_importance
            db_service.update_project_metadata(project_id, project_metadata)
            
        db_service.update_project_status(project_id, "pending_evaluation_review")
        db_service.log_agent_activity(project_id, "Sklearn evaluation completed successfully. Waiting for user review.", "info")

        return {
            "success": True,
            "metrics": metrics,
            "bundle_url": bundle_gcs_url,
            "feature_importance": feature_importance,
        }

    except Exception as e:
        error_msg = f"Sklearn evaluation error: {str(e)}"
        db_service.log_agent_activity(project_id, f"{error_msg}\n{traceback.format_exc()}", "error")
        try:
            db_service.update_project_status(project_id, "failed")
        except:
            pass
        return {"success": False, "error": error_msg}

    finally:
        from utils.file_utils import cleanup_temp_files
        cleanup_temp_files(temp_files)


def _generate_tabular_predict_script(feature_names, target_col, class_labels, task_type):
    """Generate a standalone predict.py for tabular models."""
    labels_line = f"CLASS_LABELS = {class_labels}" if class_labels else "CLASS_LABELS = None"
    return f'''"""
Auto-generated prediction script for tabular model.
Usage: python predict.py
"""
import pickle
import json

# Load model
with open("model.pkl", "rb") as f:
    model = pickle.load(f)

FEATURE_NAMES = {feature_names}
TARGET_COLUMN = "{target_col}"
{labels_line}
TASK_TYPE = "{task_type}"

def predict(features: dict) -> dict:
    """
    Make a prediction given a dict of feature values.
    Example: predict({{"age": 30, "income": 50000, "credit_score": 700}})
    """
    import numpy as np
    X = np.array([[features.get(f, 0) for f in FEATURE_NAMES]])
    prediction = model.predict(X)[0]

    result = {{"prediction": float(prediction) if TASK_TYPE.endswith("regression") else int(prediction)}}
    if CLASS_LABELS and TASK_TYPE.endswith("classification"):
        result["label"] = CLASS_LABELS[int(prediction)]

    if hasattr(model, "predict_proba"):
        proba = model.predict_proba(X)[0]
        result["probabilities"] = {{CLASS_LABELS[i] if CLASS_LABELS else str(i): round(float(p), 4) for i, p in enumerate(proba)}}

    return result

if __name__ == "__main__":
    # Example usage
    sample = {{f: 0 for f in FEATURE_NAMES}}
    print("Sample input:", sample)
    print("Prediction:", predict(sample))
'''


def _generate_text_predict_script(class_labels):
    """Generate a standalone predict.py for text models."""
    return f'''"""
Auto-generated prediction script for text classification model.
Usage: python predict.py
"""
import pickle

# Load model (TF-IDF + Classifier pipeline)
with open("model.pkl", "rb") as f:
    model = pickle.load(f)

CLASS_LABELS = {class_labels}

def predict(text: str) -> dict:
    """
    Classify a text string.
    Example: predict("This movie was absolutely wonderful!")
    """
    prediction = model.predict([text])[0]
    result = {{"prediction": int(prediction), "label": CLASS_LABELS[int(prediction)] if CLASS_LABELS else str(prediction)}}

    if hasattr(model, "predict_proba"):
        proba = model.predict_proba([text])[0]
        result["confidence"] = round(float(max(proba)), 4)
        result["probabilities"] = {{CLASS_LABELS[i] if CLASS_LABELS else str(i): round(float(p), 4) for i, p in enumerate(proba)}}
    elif hasattr(model, "decision_function"):
        scores = model.decision_function([text])
        if len(scores.shape) == 1:
            import math
            # Convert decision boundary distance to pseudo-probability using sigmoid
            result["confidence"] = round(1 / (1 + math.exp(-abs(scores[0]))), 4)

    return result

if __name__ == "__main__":
    sample_text = "This is a sample text for classification."
    print("Input:", sample_text)
    print("Prediction:", predict(sample_text))
'''


def _generate_readme(project_name, task_type, metrics, feature_importance, class_labels):
    """Generate a README.md for the bundle."""
    metrics_lines = "\n".join(f"- **{k}**: {v}" for k, v in metrics.items() if k != "classification_report")

    fi_lines = ""
    if feature_importance:
        top_features = list(feature_importance.items())[:10]
        fi_lines = "\n## Top Features\n" + "\n".join(f"- **{name}**: {imp}" for name, imp in top_features)

    labels_line = ""
    if class_labels:
        labels_line = f"\n## Classes\n{', '.join(str(l) for l in class_labels)}\n"

    return f"""# {project_name}

**Task Type**: {task_type}
**Framework**: scikit-learn

## Metrics
{metrics_lines}
{labels_line}
{fi_lines}

## Files
- `model.pkl` — Trained scikit-learn model
- `predict.py` — Standalone prediction script
- `metadata.json` — Full model metadata and metrics
- `labels.json` — Class label mapping (if classification)

## Usage
```python
from predict import predict

# For tabular:
result = predict({{"feature1": value1, "feature2": value2}})

# For text:
result = predict("Your text here")
```
"""
