"""
Tabular Training Service — scikit-learn based training for CSV/tabular datasets.

Supports:
  - tabular_classification: Random Forest, XGBoost, Gradient Boosting
  - tabular_regression: Random Forest, XGBoost, Gradient Boosting

This module is called from training_service.py when task_type is tabular_*.
"""

import os
import csv
import json
import time
import pickle
import traceback
from typing import Dict, Any, List, Optional
from pathlib import Path

from services.database_service import db_service
from services.storage_service import storage_service


def _find_csv_files(directory: str) -> list:
    """Find all CSV files in the directory tree."""
    csv_files = []
    for dirpath, _, filenames in os.walk(directory):
        for f in filenames:
            if Path(f).suffix.lower() in {".csv", ".tsv", ".parquet"}:
                csv_files.append(os.path.join(dirpath, f))
    return csv_files


def _load_csv_data(filepath: str) -> tuple:
    """Load CSV data using stdlib csv. Returns (headers, rows_as_dicts)."""
    rows = []
    headers = []
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        for row in reader:
            rows.append(row)
    return headers, rows


def _detect_target_column(headers: list, metadata: dict) -> str:
    """Detect the target column from metadata or common names."""
    # Check if explicitly specified in sanity report
    sanity_report = metadata.get("sanity_report", {})
    if sanity_report.get("detected_target"):
        return sanity_report["detected_target"]

    # Check common target names
    target_names = ["target", "label", "class", "y", "output", "price",
                    "salary", "survived", "churn", "default"]
    for col in headers:
        if col.lower() in target_names:
            return col

    # Default to last column
    return headers[-1] if headers else ""


def _encode_features(rows: list, headers: list, target_col: str, task_type: str) -> tuple:
    """
    Encode features and target into numeric arrays using pure Python + sklearn.
    Returns (X_list, y_list, feature_names, label_encoder_or_None)
    """
    from sklearn.preprocessing import LabelEncoder
    import numpy as np

    feature_cols = [h for h in headers if h != target_col]
    feature_names = feature_cols

    # Encode target
    y_raw = [r.get(target_col, "") for r in rows]
    label_encoder = None

    if task_type == "tabular_classification":
        label_encoder = LabelEncoder()
        y = label_encoder.fit_transform(y_raw)
    else:
        # Regression — convert to float
        y = []
        for val in y_raw:
            try:
                y.append(float(val))
            except (ValueError, TypeError):
                y.append(0.0)
        y = np.array(y)

    # Encode features
    col_encoders = {}
    X_encoded = []
    for row in rows:
        encoded_row = []
        for col in feature_cols:
            val = row.get(col, "")
            try:
                encoded_row.append(float(val))
            except (ValueError, TypeError):
                # Categorical — use label encoding
                if col not in col_encoders:
                    col_encoders[col] = LabelEncoder()
                    all_vals = [r.get(col, "unknown") for r in rows]
                    col_encoders[col].fit(all_vals)
                try:
                    encoded_row.append(float(col_encoders[col].transform([val])[0]))
                except ValueError:
                    encoded_row.append(0.0)
        X_encoded.append(encoded_row)

    X = np.array(X_encoded)
    return X, y, feature_names, label_encoder


def _create_model(preferred_model: str, task_type: str):
    """Create a scikit-learn model based on preference and task type."""
    is_classification = task_type == "tabular_classification"

    model_name = preferred_model.lower()

    if model_name == "xgboost":
        try:
            if is_classification:
                from xgboost import XGBClassifier
                return XGBClassifier(
                    n_estimators=100, max_depth=6, learning_rate=0.1,
                    use_label_encoder=False, eval_metric="logloss"
                )
            else:
                from xgboost import XGBRegressor
                return XGBRegressor(
                    n_estimators=100, max_depth=6, learning_rate=0.1
                )
        except ImportError:
            # Fallback to gradient_boosting if xgboost not installed
            model_name = "gradient_boosting"

    if model_name == "gradient_boosting":
        if is_classification:
            from sklearn.ensemble import GradientBoostingClassifier
            return GradientBoostingClassifier(n_estimators=100, max_depth=5, learning_rate=0.1)
        else:
            from sklearn.ensemble import GradientBoostingRegressor
            return GradientBoostingRegressor(n_estimators=100, max_depth=5, learning_rate=0.1)

    # Default: Random Forest
    if is_classification:
        from sklearn.ensemble import RandomForestClassifier
        return RandomForestClassifier(n_estimators=100, max_depth=10, random_state=42)
    else:
        from sklearn.ensemble import RandomForestRegressor
        return RandomForestRegressor(n_estimators=100, max_depth=10, random_state=42)


async def execute_tabular_training(project_id: str) -> Dict[str, Any]:
    """
    Execute the full tabular training workflow:
    1. Download & extract dataset
    2. Detect target column
    3. Encode features
    4. Train/test split
    5. Train model
    6. Evaluate metrics
    7. Save & upload model
    8. Update database
    """
    temp_files = []

    try:
        db_service.log_agent_activity(project_id, "Tabular training workflow initiated", "info")

        project = db_service.get_project(project_id)
        if not project:
            return {"success": False, "error": f"Project {project_id} not found"}

        if project.get("status") != "pending_training":
            return {"success": False, "error": f"Project status is '{project.get('status')}', expected 'pending_training'"}

        db_service.update_project_status(project_id, "training")

        dataset = db_service.get_dataset(project_id)
        if not dataset:
            db_service.update_project_status(project_id, "failed")
            return {"success": False, "error": "Dataset not found"}

        project_name = project.get("name", "model")
        project_metadata = project.get("metadata", {})
        task_type = project.get("task_type", "tabular_classification")
        preferred_model = project_metadata.get("preferred_model", "random_forest")

        # Download dataset
        gcs_url = dataset.get("gcs_url")
        if not gcs_url:
            db_service.update_project_status(project_id, "failed")
            return {"success": False, "error": "Dataset gcs_url is missing"}

        import tempfile
        temp_dir = os.path.join(tempfile.gettempdir(), f"training_{project_id}")
        os.makedirs(temp_dir, exist_ok=True)
        temp_files.append(temp_dir)

        dataset_zip_path = os.path.join(temp_dir, "dataset.zip")
        temp_files.append(dataset_zip_path)

        db_service.log_agent_activity(project_id, f"Downloading dataset from {gcs_url}", "info")
        storage_service.download_dataset(gcs_url, dataset_zip_path)

        # Extract
        dataset_extract_dir = os.path.join(temp_dir, "dataset")
        temp_files.append(dataset_extract_dir)

        import zipfile
        with zipfile.ZipFile(dataset_zip_path, "r") as zf:
            zf.extractall(dataset_extract_dir)

        # Find CSV file
        csv_files = _find_csv_files(dataset_extract_dir)
        if not csv_files:
            db_service.update_project_status(project_id, "failed")
            return {"success": False, "error": "No CSV files found in the dataset"}

        primary_csv = max(csv_files, key=os.path.getsize)
        db_service.log_agent_activity(project_id, f"Using primary CSV: {os.path.basename(primary_csv)}", "info")

        # Load data
        headers, rows = _load_csv_data(primary_csv)
        target_col = _detect_target_column(headers, project_metadata)
        db_service.log_agent_activity(project_id, f"Target column: {target_col}, Features: {len(headers)-1}, Rows: {len(rows)}", "info")

        # Encode
        from sklearn.model_selection import train_test_split
        X, y, feature_names, label_encoder = _encode_features(rows, headers, target_col, task_type)

        # Split
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
        db_service.log_agent_activity(project_id, f"Train: {len(X_train)} samples, Test: {len(X_test)} samples", "info")

        # Create and train model
        model = _create_model(preferred_model, task_type)
        model_type_name = type(model).__name__
        db_service.log_agent_activity(project_id, f"Training {model_type_name}...", "info")

        training_start = time.time()
        model.fit(X_train, y_train)
        training_time = time.time() - training_start

        # Evaluate
        y_pred = model.predict(X_test)

        if task_type == "tabular_classification":
            from sklearn.metrics import accuracy_score, precision_recall_fscore_support, classification_report
            import numpy as np

            accuracy = accuracy_score(y_test, y_pred)
            precision, recall, f1, _ = precision_recall_fscore_support(y_test, y_pred, average="weighted", zero_division=0)

            class_labels = label_encoder.classes_.tolist() if label_encoder else []
            report_str = classification_report(y_test, y_pred, target_names=class_labels, zero_division=0, output_dict=True)

            metrics = {
                "accuracy": round(float(accuracy), 4),
                "precision": round(float(precision), 4),
                "recall": round(float(recall), 4),
                "f1_score": round(float(f1), 4),
                "classification_report": report_str,
            }
            best_metric = accuracy
            db_service.log_agent_activity(project_id, f"Training complete: accuracy={accuracy:.4f}, f1={f1:.4f}, time={training_time:.1f}s", "info")
        else:
            from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
            import numpy as np

            rmse = float(np.sqrt(mean_squared_error(y_test, y_pred)))
            mae = float(mean_absolute_error(y_test, y_pred))
            r2 = float(r2_score(y_test, y_pred))

            metrics = {
                "rmse": round(rmse, 4),
                "mae": round(mae, 4),
                "r2_score": round(r2, 4),
            }
            best_metric = r2
            class_labels = []
            db_service.log_agent_activity(project_id, f"Training complete: RMSE={rmse:.4f}, R²={r2:.4f}, time={training_time:.1f}s", "info")

        # Save model
        model_save_path = os.path.join(temp_dir, f"{project_name}_model.pkl")
        temp_files.append(model_save_path)
        with open(model_save_path, "wb") as f:
            pickle.dump(model, f)

        # Also save metadata
        model_meta = {
            "task_type": task_type,
            "model_type": model_type_name,
            "preferred_model": preferred_model,
            "feature_names": feature_names,
            "target_column": target_col,
            "class_labels": class_labels,
            "training_time_seconds": int(training_time),
            "metrics": metrics,
        }
        meta_path = os.path.join(temp_dir, "model_metadata.json")
        with open(meta_path, "w") as f:
            json.dump(model_meta, f, indent=2)

        # Upload model
        db_service.log_agent_activity(project_id, "Uploading trained model to GCP", "info")
        model_gcs_url = storage_service.upload_model(model_save_path, project_name)
        db_service.log_agent_activity(project_id, f"Model uploaded: {model_gcs_url}", "info")

        # Insert model record
        from models.schemas import ModelData
        model_data = ModelData(
            project_id=project_id,
            name=f"{project_name}_model",
            framework="scikit-learn",
            gcs_url=model_gcs_url,
            metadata={
                **model_meta,
                "num_classes": len(class_labels) if class_labels else 0,
            }
        )
        db_service.insert_model(model_data)

        # Update project
        db_service.update_project_status(project_id, "pending_evaluation")
        db_service.log_agent_activity(project_id, "Tabular training workflow completed successfully", "info")

        return {
            "success": True,
            "model_url": model_gcs_url,
            "metrics": metrics,
        }

    except Exception as e:
        error_msg = f"Tabular training error: {str(e)}"
        db_service.log_agent_activity(project_id, f"{error_msg}\n{traceback.format_exc()}", "error")
        try:
            db_service.update_project_status(project_id, "failed")
        except:
            pass
        return {"success": False, "error": error_msg}

    finally:
        from utils.file_utils import cleanup_temp_files
        cleanup_temp_files(temp_files)
