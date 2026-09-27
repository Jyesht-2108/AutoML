"""
Privacy Agent — (Auto-Mask + Human-in-the-Loop)
===============================================
Phase 2 agent in the AgentHive pipeline.

Two-phase workflow:
  Phase A — AUDIT:
    1. Downloads dataset zip from GCS
    2. Scans images for Personally Identifiable Information (PII), e.g., faces
    3. Generates a privacy_report with proposed actions
    4. Sets status to 'pending_privacy_review' (waits for human approval)

  Phase B — FIX:
    1. Reads user-approved actions from metadata.privacy_actions
    2. Applies privacy masks (blurring faces)
    3. Re-zips and re-uploads the sanitized dataset to GCS
    4. Sets status to 'pending_training_config'

Port: 8005
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from supabase import create_client, Client
from google.cloud import storage
from dotenv import load_dotenv
import os
import tempfile
import zipfile
import traceback
from datetime import datetime, UTC
from pathlib import Path
import threading
import cv2
import numpy as np
from PIL import Image

load_dotenv()

app = FastAPI(
    title="Privacy Agent",
    description="AgentHive — Phase 2 Data Privacy & Masking Agent",
    version="1.0.0",
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
AGENT_NAME = "privacy"
AGENT_PORT = 8005
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL_SECONDS", "10"))
FACE_BLUR_INTENSITY = int(os.getenv("FACE_BLUR_INTENSITY", "15"))
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tiff", ".webp"}

polling_active = False

supabase: Client = create_client(
    os.environ["SUPABASE_URL"],
    os.environ["SUPABASE_KEY"]
)

def log_to_supabase(project_id: str, message: str, level: str = "info"):
    try:
        supabase.table("agent_logs").insert({
            "project_id": project_id,
            "agent_name": AGENT_NAME,
            "message": message,
            "log_level": level
        }).execute()
        print(f"[PRIVACY] [{level.upper()}] {message}")
    except Exception as e:
        print(f"[PRIVACY] Failed to log: {e}")

def send_chat_message(user_id: str, content: str, role: str = "assistant"):
    try:
        supabase.table("chat_messages").insert({
            "user_id": user_id,
            "role": role,
            "content": content,
            "agent_name": "Privacy Agent"
        }).execute()
    except Exception as e:
        print(f"[PRIVACY] Failed to send chat message: {e}")

# ---------------------------------------------------------------------------
# GCS Helpers
# ---------------------------------------------------------------------------
def download_from_gcs(gcs_url: str, local_path: str):
    if not gcs_url.startswith("gs://"):
        raise ValueError(f"Invalid GCS URL: {gcs_url}")
    path_parts = gcs_url[5:].split("/", 1)
    bucket_name = path_parts[0]
    blob_name = path_parts[1]
    
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    blob.download_to_filename(local_path)
    print(f"[PRIVACY] ✅ Downloaded {gcs_url} to {local_path}")

def repackage_and_upload(extract_dir: str, original_gcs_url: str, project_id: str) -> str:
    path_parts = original_gcs_url[5:].split("/", 1)
    gcp_bucket_name = path_parts[0]
    old_blob_name = path_parts[1]
    
    filename = old_blob_name.split("/")[-1]
    destination_blob = f"privacy_masked/{project_id}/{filename}"
    
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
        zip_path = tmp.name
        
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root_dir, _, files in os.walk(extract_dir):
            for file in files:
                file_path = os.path.join(root_dir, file)
                arcname = os.path.relpath(file_path, extract_dir)
                zf.write(file_path, arcname)
                
    file_size_mb = os.path.getsize(zip_path) / (1024 * 1024)
    client = storage.Client()
    bucket = client.bucket(gcp_bucket_name)
    blob = bucket.blob(destination_blob)
    timeout = max(300, int(file_size_mb * 5))
    blob.upload_from_filename(zip_path, timeout=timeout)
    
    os.remove(zip_path)
    url = f"gs://{gcp_bucket_name}/{destination_blob}"
    print(f"[PRIVACY] ✅ Upload complete: {url}")
    return url

def _is_image_file(filename: str) -> bool:
    return Path(filename).suffix.lower() in IMAGE_EXTENSIONS

# ---------------------------------------------------------------------------
# OpenCV Face Detection & Blurring
# ---------------------------------------------------------------------------
# Load Haar cascade globally
CASCADE_PATH = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
face_cascade = cv2.CascadeClassifier(CASCADE_PATH)

def detect_faces(filepath: str) -> list:
    """Returns list of bounding boxes [x, y, w, h] for faces."""
    try:
        # Load image via cv2 directly or via numpy (to handle weird characters in path)
        img = cv2.imread(filepath)
        if img is None:
            return []
            
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # Detect faces
        faces = face_cascade.detectMultiScale(
            gray, 
            scaleFactor=1.1, 
            minNeighbors=5, 
            minSize=(30, 30)
        )
        return faces.tolist() if len(faces) > 0 else []
    except Exception as e:
        print(f"[PRIVACY] Error detecting faces in {filepath}: {e}")
        return []

def blur_faces(filepath: str, faces: list):
    """Applies Gaussian blur to face bounding boxes and saves over the original."""
    try:
        img = cv2.imread(filepath)
        if img is None:
            return
            
        for (x, y, w, h) in faces:
            # Extract ROI
            roi = img[y:y+h, x:x+w]
            
            # Create blur kernel size based on ROI size
            k_w = int(w / FACE_BLUR_INTENSITY) | 1
            k_h = int(h / FACE_BLUR_INTENSITY) | 1
            k_w = max(3, k_w)
            k_h = max(3, k_h)
            
            # Apply blur
            blurred_roi = cv2.GaussianBlur(roi, (k_w, k_h), 0)
            
            # Put back
            img[y:y+h, x:x+w] = blurred_roi
            
        cv2.imwrite(filepath, img)
    except Exception as e:
        print(f"[PRIVACY] Error blurring faces in {filepath}: {e}")

# ---------------------------------------------------------------------------
# Tabular & Text Privacy Audit
# ---------------------------------------------------------------------------
import re
import csv

PII_PATTERNS = {
    "email": re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'),
    "phone": re.compile(r'\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b'),
    "ssn": re.compile(r'\b\d{3}[-]?\d{2}[-]?\d{4}\b'),
}

PII_COLUMN_NAMES = {"name", "first_name", "last_name", "full_name", "email", "phone", 
                     "address", "ssn", "social_security", "credit_card", "dob", "date_of_birth",
                     "passport", "license", "ip_address"}


def audit_tabular_privacy(extract_dir: str) -> dict:
    """Scan CSV columns for PII patterns and sensitive column names."""
    from pathlib import Path
    csv_files = []
    for dirpath, _, filenames in os.walk(extract_dir):
        for f in filenames:
            if Path(f).suffix.lower() in {".csv", ".tsv"}:
                csv_files.append(os.path.join(dirpath, f))

    if not csv_files:
        return {"total_files": 0, "pii_columns": [], "pii_samples": {}, "proposed_actions": {}}

    primary = max(csv_files, key=os.path.getsize)
    rows = []
    headers = []
    try:
        with open(primary, "r", encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames or []
            for i, row in enumerate(reader):
                rows.append(row)
                if i >= 5000:
                    break
    except Exception:
        return {"total_files": len(csv_files), "pii_columns": [], "pii_samples": {}, "proposed_actions": {}}

    pii_columns = []
    pii_samples = {}

    # Check column names
    for col in headers:
        if col.lower().replace(" ", "_") in PII_COLUMN_NAMES:
            pii_columns.append(col)
            pii_samples[col] = {"reason": "Column name matches PII pattern", "sample_count": len(rows)}

    # Check column values with regex
    sample_rows = rows[:500]
    for col in headers:
        if col in pii_columns:
            continue
        for pattern_name, pattern in PII_PATTERNS.items():
            matches = sum(1 for r in sample_rows if pattern.search(r.get(col, "")))
            if matches > len(sample_rows) * 0.1:  # >10% match rate
                pii_columns.append(col)
                pii_samples[col] = {"reason": f"Contains {pattern_name} patterns ({matches}/{len(sample_rows)} rows)", "pattern": pattern_name}
                break

    proposed_actions = {}
    if pii_columns:
        proposed_actions["mask_pii_columns"] = {
            "description": f"Mask {len(pii_columns)} column(s) containing PII: {pii_columns}",
            "columns": pii_columns,
            "recommended": True,
        }

    return {
        "total_files": len(csv_files),
        "total_rows": len(rows),
        "pii_columns": pii_columns,
        "pii_samples": pii_samples,
        "proposed_actions": proposed_actions,
    }


def audit_text_privacy(extract_dir: str) -> dict:
    """Scan text data for PII (emails, phone numbers, names)."""
    from pathlib import Path
    text_files = []
    for dirpath, _, filenames in os.walk(extract_dir):
        for f in filenames:
            if Path(f).suffix.lower() in {".csv", ".tsv", ".jsonl", ".txt"}:
                text_files.append(os.path.join(dirpath, f))

    if not text_files:
        return {"total_files": 0, "pii_found": 0, "proposed_actions": {}}

    primary = max(text_files, key=os.path.getsize)
    rows = []
    headers = []
    try:
        with open(primary, "r", encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames or []
            for i, row in enumerate(reader):
                rows.append(row)
                if i >= 5000:
                    break
    except Exception:
        return {"total_files": len(text_files), "pii_found": 0, "proposed_actions": {}}

    # Find the text column
    text_candidates = ["text", "sentence", "review", "comment", "content", "body", "message", "tweet"]
    text_col = None
    for col in headers:
        if col.lower() in text_candidates:
            text_col = col
            break
    if not text_col:
        avg_lengths = {}
        for col in headers:
            lengths = [len(r.get(col, "")) for r in rows[:100]]
            avg_lengths[col] = sum(lengths) / len(lengths) if lengths else 0
        text_col = max(avg_lengths, key=avg_lengths.get) if avg_lengths else (headers[0] if headers else None)

    if not text_col:
        return {"total_files": len(text_files), "pii_found": 0, "proposed_actions": {}}

    pii_count = 0
    sample_rows = rows[:1000]
    for r in sample_rows:
        text = r.get(text_col, "")
        for pattern in PII_PATTERNS.values():
            if pattern.search(text):
                pii_count += 1
                break

    proposed_actions = {}
    if pii_count > 0:
        pii_pct = (pii_count / len(sample_rows)) * 100
        proposed_actions["redact_text_pii"] = {
            "description": f"Redact PII from ~{pii_count} text entries ({pii_pct:.1f}% of sampled rows)",
            "text_column": text_col,
            "recommended": True,
        }

    return {
        "total_files": len(text_files),
        "total_rows": len(rows),
        "text_column": text_col,
        "pii_found": pii_count,
        "proposed_actions": proposed_actions,
    }


# ---------------------------------------------------------------------------
# Phase A: AUDIT
# ---------------------------------------------------------------------------
def process_pending_privacy(project_id: str):
    print(f"\n[PRIVACY] Processing Phase A (Audit) for {project_id}...")
    try:
        project_resp = supabase.table("projects").select("*, users(*)").eq("id", project_id).execute()
        if not project_resp.data:
            return
            
        project = project_resp.data[0]
        user_id = project["user_id"]
        metadata = project.get("metadata", {}) or {}
        task_type = project.get("task_type", "image_classification")
        
        dataset_resp = supabase.table("datasets").select("*").eq("project_id", project_id).execute()
        if not dataset_resp.data:
            log_to_supabase(project_id, "Dataset not found", "error")
            supabase.table("projects").update({"status": "failed"}).eq("id", project_id).execute()
            return
            
        gcs_url = dataset_resp.data[0].get("gcs_url", "")
        
        with tempfile.TemporaryDirectory() as temp_dir:
            zip_path = os.path.join(temp_dir, "dataset.zip")
            extract_dir = os.path.join(temp_dir, "extracted")
            os.makedirs(extract_dir, exist_ok=True)
            
            download_from_gcs(gcs_url, zip_path)
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(extract_dir)

            # Route based on task type
            if task_type in ("tabular_classification", "tabular_regression"):
                log_to_supabase(project_id, "Scanning tabular data for PII columns...", "info")
                send_chat_message(user_id, "🔍 Scanning your tabular data for PII (emails, phones, names)...")
                privacy_result = audit_tabular_privacy(extract_dir)
                report = {
                    "data_type": "tabular",
                    **privacy_result,
                }
                has_issues = bool(privacy_result.get("proposed_actions"))

            elif task_type == "text_classification":
                log_to_supabase(project_id, "Scanning text data for PII...", "info")
                send_chat_message(user_id, "🔍 Scanning your text data for PII (emails, phone numbers)...")
                privacy_result = audit_text_privacy(extract_dir)
                report = {
                    "data_type": "text",
                    **privacy_result,
                }
                has_issues = bool(privacy_result.get("proposed_actions"))

            else:
                # Image: existing face detection
                log_to_supabase(project_id, "Scanning dataset for privacy risks (faces)...", "info")
                send_chat_message(user_id, f"🔍 Scanning dataset for privacy risks (e.g., human faces)...")
                
                images_with_faces = []
                total_images = 0
                total_faces = 0
                
                for root, _, files in os.walk(extract_dir):
                    for f in files:
                        if _is_image_file(f):
                            total_images += 1
                            filepath = os.path.join(root, f)
                            faces = detect_faces(filepath)
                            if faces:
                                rel_path = os.path.relpath(filepath, extract_dir)
                                images_with_faces.append({
                                    "file": rel_path,
                                    "faces": faces
                                })
                                total_faces += len(faces)
                
                report = {
                    "data_type": "image",
                    "total_images": total_images,
                    "images_with_faces_count": len(images_with_faces),
                    "total_faces_detected": total_faces,
                    "images_with_faces": images_with_faces
                }
                
                if len(images_with_faces) > 0:
                    report["proposed_actions"] = {
                        "blur_faces": {
                            "description": f"Apply Gaussian blur to {total_faces} detected faces across {len(images_with_faces)} images.",
                            "recommended": True
                        }
                    }
                has_issues = len(images_with_faces) > 0
            
            metadata["privacy_report"] = report
            
            if has_issues:
                proposed = report.get("proposed_actions", {})
                log_to_supabase(project_id, f"Privacy risks found. {len(proposed)} action(s) proposed. Awaiting user review.", "warning")
                
                supabase.table("projects").update({
                    "metadata": metadata,
                    "status": "pending_privacy_review",
                    "updated_at": datetime.now(UTC).isoformat(),
                }).eq("id", project_id).execute()
                
                action_lines = [f"  • {a['description']}" for a in proposed.values()]
                send_chat_message(user_id,
                    f"⚠️ Privacy risks detected!\n"
                    + "\n".join(action_lines) + "\n\n"
                    f"👉 Please review and approve privacy masking in the project details panel.")
                print(f"[PRIVACY] ⏳ Waiting for user approval (pending_privacy_review)")
            else:
                # No PII found, advance to training config
                log_to_supabase(project_id, "✅ No privacy risks found — dataset is clear", "info")
                supabase.table("projects").update({
                    "metadata": metadata,
                    "status": "pending_training_config",
                    "updated_at": datetime.now(UTC).isoformat(),
                }).eq("id", project_id).execute()
                
                send_chat_message(user_id,
                    f"✅ Data Privacy Check Passed!\n"
                    f"No PII detected in the dataset.\n"
                    f"⚙️ Please configure training settings...")
                print(f"[PRIVACY] ✅ Clean dataset — advancing to training config")

    except Exception as exc:
        print(f"[PRIVACY] ❌ Audit error: {exc}")
        print(traceback.format_exc())
        log_to_supabase(project_id, f"Audit error: {str(exc)}", "error")
        supabase.table("projects").update({"status": "failed"}).eq("id", project_id).execute()

# ---------------------------------------------------------------------------
# Phase B: FIX
# ---------------------------------------------------------------------------
def process_pending_privacy_fix(project_id: str):
    print(f"\n[PRIVACY] Processing Phase B (Fix) for {project_id}...")
    try:
        project_resp = supabase.table("projects").select("*, users(*)").eq("id", project_id).execute()
        if not project_resp.data:
            return
            
        project = project_resp.data[0]
        user_id = project["user_id"]
        metadata = project.get("metadata", {}) or {}
        
        privacy_report = metadata.get("privacy_report", {})
        privacy_actions = metadata.get("privacy_actions", {})
        
        if not privacy_actions or not privacy_actions.get("blur_faces"):
            # User skipped actions
            log_to_supabase(project_id, "User skipped privacy masking — advancing to training config", "info")
            supabase.table("projects").update({
                "status": "pending_training_config",
                "updated_at": datetime.now(UTC).isoformat(),
            }).eq("id", project_id).execute()
            send_chat_message(user_id, "⏭️ Privacy masking skipped. Please configure training settings...")
            return
            
        send_chat_message(user_id, "🛡️ Applying privacy masks (blurring faces)...")
        
        # Download again
        dataset_resp = supabase.table("datasets").select("*").eq("project_id", project_id).execute()
        gcs_url = dataset_resp.data[0].get("gcs_url", "")
        
        with tempfile.TemporaryDirectory() as temp_dir:
            zip_path = os.path.join(temp_dir, "dataset.zip")
            extract_dir = os.path.join(temp_dir, "extracted")
            os.makedirs(extract_dir, exist_ok=True)
            
            download_from_gcs(gcs_url, zip_path)
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(extract_dir)
                
            images_with_faces = privacy_report.get("images_with_faces", [])
            blurred_count = 0
            
            for item in images_with_faces:
                rel_path = item["file"]
                faces = item["faces"]
                full_path = os.path.join(extract_dir, rel_path)
                
                if os.path.exists(full_path):
                    blur_faces(full_path, faces)
                    blurred_count += len(faces)
            
            fix_results = {
                "blur_faces": f"Blurred {blurred_count} faces across {len(images_with_faces)} images"
            }
            log_to_supabase(project_id, fix_results["blur_faces"], "info")
            
            # Re-upload
            log_to_supabase(project_id, "📦 Re-packaging masked dataset...", "info")
            new_gcs_url = repackage_and_upload(extract_dir, gcs_url, project_id)
            
            # Update dataset URL
            dataset_id = dataset_resp.data[0]["id"]
            supabase.table("datasets").update({"gcs_url": new_gcs_url}).eq("id", dataset_id).execute()
            log_to_supabase(project_id, f"✅ Masked dataset uploaded: {new_gcs_url}", "info")
            
        metadata["privacy_fix_results"] = fix_results
        supabase.table("projects").update({
            "metadata": metadata,
            "status": "pending_training_config",
            "updated_at": datetime.now(UTC).isoformat(),
        }).eq("id", project_id).execute()
        
        send_chat_message(user_id,
            f"✅ Privacy masking successful!\n"
            f"Applied fixes: {fix_results['blur_faces']}\n\n"
            f"⚙️ Please configure training settings...")
        log_to_supabase(project_id, "✅ Privacy phase complete — advancing to training config", "info")
        print(f"[PRIVACY] ✅ Phase B complete for {project_id}")

    except Exception as exc:
        print(f"[PRIVACY] ❌ Fix error: {exc}")
        print(traceback.format_exc())
        log_to_supabase(project_id, f"Privacy Fix error: {str(exc)}", "error")
        supabase.table("projects").update({"status": "failed"}).eq("id", project_id).execute()

# ---------------------------------------------------------------------------
# Background Polling
# ---------------------------------------------------------------------------
def background_poller():
    global polling_active
    while polling_active:
        try:
            # Poll Phase A (Audit)
            res_audit = supabase.table("projects").select("id").eq("status", "pending_privacy").execute()
            for p in res_audit.data:
                supabase.table("projects").update({"status": "processing_privacy"}).eq("id", p["id"]).execute()
                process_pending_privacy(p["id"])
                
            # Poll Phase B (Fix)
            res_fix = supabase.table("projects").select("id").eq("status", "pending_privacy_fix").execute()
            for p in res_fix.data:
                supabase.table("projects").update({"status": "processing_privacy_fix"}).eq("id", p["id"]).execute()
                process_pending_privacy_fix(p["id"])
                
        except Exception as e:
            print(f"[PRIVACY] Polling error: {e}")
            
        import time
        time.sleep(POLL_INTERVAL)

@app.on_event("startup")
def startup_event():
    global polling_active
    polling_active = True
    t = threading.Thread(target=background_poller, daemon=True)
    t.start()
    print(f"[PRIVACY] 🚀 Privacy Agent started on port {AGENT_PORT}")

@app.on_event("shutdown")
def shutdown_event():
    global polling_active
    polling_active = False

# ---------------------------------------------------------------------------
# HITL API Endpoint (Called by MCP)
# ---------------------------------------------------------------------------
class PrivacyApprovalRequest(BaseModel):
    project_id: str
    actions: dict  # e.g. {"blur_faces": True}

@app.post("/agents/privacy/approve")
def approve_privacy_actions(req: PrivacyApprovalRequest):
    """MCP Server calls this to trigger Phase B"""
    try:
        res = supabase.table("projects").select("metadata").eq("id", req.project_id).execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="Project not found")
            
        metadata = res.data[0].get("metadata", {}) or {}
        metadata["privacy_actions"] = req.actions
        
        # Check if user actually approved anything
        if any(req.actions.values()):
            supabase.table("projects").update({
                "metadata": metadata,
                "status": "pending_privacy_fix",
                "updated_at": datetime.now(UTC).isoformat(),
            }).eq("id", req.project_id).execute()
            log_to_supabase(req.project_id, f"User approved actions: {req.actions}", "info")
            return {"success": True, "message": "Fix phase triggered", "status": "pending_privacy_fix"}
        else:
            # Skipped all
            supabase.table("projects").update({
                "metadata": metadata,
                "status": "pending_training_config",
                "updated_at": datetime.now(UTC).isoformat(),
            }).eq("id", req.project_id).execute()
            log_to_supabase(req.project_id, "User skipped all privacy fixes", "info")
            return {"success": True, "message": "Skipped fixes", "status": "pending_training_config"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
