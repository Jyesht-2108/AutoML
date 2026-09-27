"""
Text Training Service — TF-IDF + SVM / sklearn based text classification.

Uses lightweight sklearn pipelines (TF-IDF vectorizer + classifier).
No heavy transformer dependencies required.

This module is called from training_service.py when task_type is text_classification.
"""

import os
import csv
import json
import time
import pickle
import traceback
from typing import Dict, Any
from pathlib import Path

from services.database_service import db_service
from services.storage_service import storage_service


def _find_text_files(directory: str) -> list:
    """Find CSV/text files in the directory tree."""
    files = []
    for dirpath, _, filenames in os.walk(directory):
        for f in filenames:
            if Path(f).suffix.lower() in {".csv", ".tsv", ".jsonl", ".txt"}:
                files.append(os.path.join(dirpath, f))
    return files


def _detect_columns(headers: list, metadata: dict) -> tuple:
    """Detect text and label columns."""
    sanity_report = metadata.get("sanity_report", {})

    text_col = sanity_report.get("text_column")
    label_col = sanity_report.get("label_column")

    if not text_col:
        text_candidates = ["text", "sentence", "review", "comment", "content", "body", "message", "tweet"]
        for col in headers:
            if col.lower() in text_candidates:
                text_col = col
                break

    if not label_col:
        label_candidates = ["label", "sentiment", "class", "target", "category"]
        for col in headers:
            if col.lower() in label_candidates:
                label_col = col
                break

    if not text_col and headers:
        # Fallback: longest avg text column
        text_col = headers[0]
    if not label_col and len(headers) > 1:
        label_col = [h for h in headers if h != text_col][0]

    return text_col, label_col


async def execute_text_training(project_id: str) -> Dict[str, Any]:
    """
    Execute text classification training using TF-IDF + SVM/MultinomialNB.
    """
    temp_files = []

    try:
        db_service.log_agent_activity(project_id, "Text training workflow initiated", "info")

        project = db_service.get_project(project_id)
        if not project:
            return {"success": False, "error": f"Project {project_id} not found"}

        if project.get("status") != "pending_training":
            return {"success": False, "error": f"Status is '{project.get('status')}', expected 'pending_training'"}

        db_service.update_project_status(project_id, "training")

        dataset = db_service.get_dataset(project_id)
        if not dataset:
            db_service.update_project_status(project_id, "failed")
            return {"success": False, "error": "Dataset not found"}

        project_name = project.get("name", "model")
        project_metadata = project.get("metadata", {})
        preferred_model = project_metadata.get("preferred_model", "tfidf_svm")

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

        dataset_extract_dir = os.path.join(temp_dir, "dataset")
        temp_files.append(dataset_extract_dir)

        import zipfile
        with zipfile.ZipFile(dataset_zip_path, "r") as zf:
            zf.extractall(dataset_extract_dir)

        # Find text file
        text_files = _find_text_files(dataset_extract_dir)
        if not text_files:
            db_service.update_project_status(project_id, "failed")
            return {"success": False, "error": "No CSV/text files found in the dataset"}

        primary_file = max(text_files, key=os.path.getsize)
        db_service.log_agent_activity(project_id, f"Using: {os.path.basename(primary_file)}", "info")

        # Load data
        rows = []
        headers = []
        with open(primary_file, "r", encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames or []
            for row in reader:
                rows.append(row)

        text_col, label_col = _detect_columns(headers, project_metadata)

        if not text_col or not label_col:
            db_service.update_project_status(project_id, "failed")
            return {"success": False, "error": "Could not detect text and label columns"}

        # Extract X and y
        texts = []
        labels = []
        for r in rows:
            t = r.get(text_col, "").strip()
            l = r.get(label_col, "").strip()
            if t and l:
                texts.append(t)
                labels.append(l)

        if len(texts) < 10:
            db_service.update_project_status(project_id, "failed")
            return {"success": False, "error": f"Only {len(texts)} valid text samples found (minimum 10)"}

        db_service.log_agent_activity(project_id, f"Text col: '{text_col}', Label col: '{label_col}', Samples: {len(texts)}", "info")

        # Build pipeline
        from sklearn.model_selection import train_test_split
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import LabelEncoder
        from sklearn.metrics import accuracy_score, precision_recall_fscore_support, classification_report

        le = LabelEncoder()
        y = le.fit_transform(labels)
        class_labels = le.classes_.tolist()

        X_train, X_test, y_train, y_test = train_test_split(texts, y, test_size=0.2, random_state=42, stratify=y)
        db_service.log_agent_activity(project_id, f"Train: {len(X_train)}, Test: {len(X_test)}, Classes: {len(class_labels)}", "info")

        # Choose classifier
        if preferred_model in ("tfidf_svm", "svm"):
            from sklearn.svm import LinearSVC
            clf = LinearSVC(max_iter=2000)
            model_name = "TF-IDF + LinearSVC"
        elif preferred_model in ("tfidf_nb", "naive_bayes"):
            from sklearn.naive_bayes import MultinomialNB
            clf = MultinomialNB()
            model_name = "TF-IDF + MultinomialNB"
        else:
            from sklearn.linear_model import LogisticRegression
            clf = LogisticRegression(max_iter=1000)
            model_name = "TF-IDF + LogisticRegression"

        pipeline = Pipeline([
            ("tfidf", TfidfVectorizer(max_features=20000, ngram_range=(1, 2), sublinear_tf=True)),
            ("clf", clf),
        ])

        db_service.log_agent_activity(project_id, f"Training {model_name}...", "info")

        training_start = time.time()
        pipeline.fit(X_train, y_train)
        training_time = time.time() - training_start

        # Evaluate
        y_pred = pipeline.predict(X_test)
        accuracy = float(accuracy_score(y_test, y_pred))
        precision, recall, f1, _ = precision_recall_fscore_support(y_test, y_pred, average="weighted", zero_division=0)
        report_dict = classification_report(y_test, y_pred, target_names=class_labels, zero_division=0, output_dict=True)

        metrics = {
            "accuracy": round(accuracy, 4),
            "precision": round(float(precision), 4),
            "recall": round(float(recall), 4),
            "f1_score": round(float(f1), 4),
            "classification_report": report_dict,
        }

        db_service.log_agent_activity(project_id, f"Training complete: accuracy={accuracy:.4f}, f1={f1:.4f}, time={training_time:.1f}s", "info")

        # Save model
        model_save_path = os.path.join(temp_dir, f"{project_name}_model.pkl")
        temp_files.append(model_save_path)
        with open(model_save_path, "wb") as f:
            pickle.dump(pipeline, f)

        model_meta = {
            "task_type": "text_classification",
            "model_type": model_name,
            "preferred_model": preferred_model,
            "text_column": text_col,
            "label_column": label_col,
            "class_labels": class_labels,
            "num_classes": len(class_labels),
            "training_time_seconds": int(training_time),
            "metrics": metrics,
        }

        # Upload
        db_service.log_agent_activity(project_id, "Uploading trained model to GCP", "info")
        model_gcs_url = storage_service.upload_model(model_save_path, project_name)

        # Insert model record
        from models.schemas import ModelData
        model_data = ModelData(
            project_id=project_id,
            name=f"{project_name}_model",
            framework="scikit-learn",
            gcs_url=model_gcs_url,
            metadata=model_meta,
        )
        db_service.insert_model(model_data)

        db_service.update_project_status(project_id, "pending_evaluation")
        db_service.log_agent_activity(project_id, "Text training workflow completed successfully", "info")

        return {"success": True, "model_url": model_gcs_url, "metrics": metrics}

    except Exception as e:
        error_msg = f"Text training error: {str(e)}"
        db_service.log_agent_activity(project_id, f"{error_msg}\n{traceback.format_exc()}", "error")
        try:
            db_service.update_project_status(project_id, "failed")
        except:
            pass
        return {"success": False, "error": error_msg}

    finally:
        from utils.file_utils import cleanup_temp_files
        cleanup_temp_files(temp_files)
