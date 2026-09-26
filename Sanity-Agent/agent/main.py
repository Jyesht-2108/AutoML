"""
Data Sanity Auditor Agent
=========================
Phase 1 agent in the AgentHive pipeline.

Listens for projects with status 'pending_sanity', downloads the dataset
from GCS, runs quality checks (corruption, blur, class imbalance, resolution),
logs a detailed sanity report to Supabase, and advances the project to
'pending_training' if the dataset passes validation.

Architecture reference:
  docs/REPORTTTT.md — Chapter 5, Section 5.2 (The Shield Layer)

Port: 8004
Polls every 10 seconds by default.
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from supabase import create_client, Client
from google.cloud import storage
from dotenv import load_dotenv
import os
import io
import json
import tempfile
import shutil
import zipfile
import math
import traceback
from datetime import datetime, UTC
from collections import Counter
from pathlib import Path
import threading

# Load environment variables from .env file
load_dotenv()

app = FastAPI(
    title="Data Sanity Auditor Agent",
    description="AgentHive – Phase 1 Data Quality Validation Agent",
    version="1.0.0",
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
AGENT_NAME = "sanity"
AGENT_PORT = 8004
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL_SECONDS", "10"))

# Sanity thresholds (tuneable via env)
IMBALANCE_RATIO_THRESHOLD = float(os.getenv("IMBALANCE_RATIO_THRESHOLD", "10.0"))
MIN_IMAGES_PER_CLASS = int(os.getenv("MIN_IMAGES_PER_CLASS", "5"))
MIN_RESOLUTION = int(os.getenv("MIN_RESOLUTION", "16"))  # pixels
BLUR_VARIANCE_THRESHOLD = float(os.getenv("BLUR_VARIANCE_THRESHOLD", "50.0"))
MAX_CORRUPT_PERCENT = float(os.getenv("MAX_CORRUPT_PERCENT", "10.0"))
MAX_BLURRY_PERCENT = float(os.getenv("MAX_BLURRY_PERCENT", "30.0"))

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tiff", ".webp"}

# Global polling flag
polling_active = False

# ---------------------------------------------------------------------------
# Supabase client
# ---------------------------------------------------------------------------
supabase: Client = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_KEY"),
)

gcp_bucket_name = os.getenv("GCP_BUCKET_NAME")

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class SanityJobRequest(BaseModel):
    project_id: str


# ---------------------------------------------------------------------------
# Helper: Supabase logging
# ---------------------------------------------------------------------------

def log_to_supabase(project_id: str, message: str, level: str = "info"):
    """Write an entry to the agent_logs table."""
    try:
        supabase.table("agent_logs").insert({
            "project_id": project_id,
            "agent_name": AGENT_NAME,
            "message": message,
            "log_level": level,
            "created_at": datetime.now(UTC).isoformat(),
        }).execute()
    except Exception as e:
        print(f"[SANITY] Failed to log to Supabase: {e}")


def send_chat_message(user_id: str, content: str):
    """Send a message to the user via the messages table."""
    try:
        supabase.table("messages").insert({
            "user_id": user_id,
            "role": "assistant",
            "content": content,
            "created_at": datetime.now(UTC).isoformat(),
        }).execute()
    except Exception as e:
        print(f"[SANITY] Failed to send chat message: {e}")


# ---------------------------------------------------------------------------
# GCS helpers
# ---------------------------------------------------------------------------

def download_from_gcs(gcs_url: str, dest_path: str):
    """Download a file from GCS to a local path."""
    if not gcs_url.startswith("gs://"):
        raise ValueError(f"Invalid GCS URL: {gcs_url}")
    path = gcs_url[5:]
    bucket_name = path.split("/", 1)[0]
    blob_path = path.split("/", 1)[1]

    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_path)

    print(f"[SANITY] Downloading {gcs_url} -> {dest_path}")
    blob.download_to_filename(dest_path)
    print(f"[SANITY] ✅ Download complete ({os.path.getsize(dest_path) / (1024*1024):.1f} MB)")


# ---------------------------------------------------------------------------
# Image quality helpers (uses Pillow only – no OpenCV required)
# ---------------------------------------------------------------------------

def _is_image_file(filename: str) -> bool:
    """Check if a filename has an image extension."""
    return Path(filename).suffix.lower() in IMAGE_EXTENSIONS


def _check_image(filepath: str) -> dict:
    """
    Open an image and return a quality report dict.

    Returns:
        {
            "valid": bool,
            "width": int | None,
            "height": int | None,
            "is_blurry": bool,
            "error": str | None,
        }
    """
    from PIL import Image
    try:
        with Image.open(filepath) as img:
            img.verify()  # lightweight corruption check

        # Re-open for actual pixel data (verify() closes the file)
        with Image.open(filepath) as img:
            img.load()
            width, height = img.size

            # Resolution check
            if width < MIN_RESOLUTION or height < MIN_RESOLUTION:
                return {
                    "valid": False,
                    "width": width,
                    "height": height,
                    "is_blurry": False,
                    "error": f"Too small: {width}x{height}",
                }

            # Blur detection using Laplacian variance approximation
            # Convert to grayscale, compute variance of pixel differences
            is_blurry = False
            try:
                gray = img.convert("L")
                pixels = list(gray.getdata())
                w, h = gray.size
                if w > 2 and h > 2:
                    # Approximate Laplacian: sum of second-order differences
                    lap_values = []
                    for y in range(1, h - 1):
                        for x in range(1, w - 1):
                            idx = y * w + x
                            # Laplacian kernel: center*4 - up - down - left - right
                            val = (
                                4 * pixels[idx]
                                - pixels[(y - 1) * w + x]
                                - pixels[(y + 1) * w + x]
                                - pixels[y * w + (x - 1)]
                                - pixels[y * w + (x + 1)]
                            )
                            lap_values.append(val)
                    if lap_values:
                        mean_lap = sum(lap_values) / len(lap_values)
                        variance = sum((v - mean_lap) ** 2 for v in lap_values) / len(lap_values)
                        is_blurry = variance < BLUR_VARIANCE_THRESHOLD
            except Exception:
                pass  # blur detection is best-effort

            return {
                "valid": True,
                "width": width,
                "height": height,
                "is_blurry": is_blurry,
                "error": None,
            }
    except Exception as e:
        return {
            "valid": False,
            "width": None,
            "height": None,
            "is_blurry": False,
            "error": str(e),
        }


# ---------------------------------------------------------------------------
# Core sanity audit logic
# ---------------------------------------------------------------------------

def run_sanity_audit(extract_dir: str) -> dict:
    """
    Walk the extracted dataset directory, run image-level checks, and
    compute aggregate statistics.

    Expects a standard image classification layout:
        <root>/
            <class_A>/
                img1.jpg
                img2.jpg
            <class_B>/
                ...

    Or nested:
        <root>/train/<class>/...
        <root>/val/<class>/...
        <root>/test/<class>/...

    Returns a dict with the full sanity report.
    """

    # ----- Step 1: Discover the class directories -----
    # Try to find a 'train' folder first (most common layout)
    root = Path(extract_dir)
    candidate_dirs = []

    # Look for train/val/test splits
    for split_name in ["train", "training", "Train", "TRAIN"]:
        split_dir = None
        for p in root.rglob(split_name):
            if p.is_dir():
                split_dir = p
                break
        if split_dir:
            candidate_dirs.append(("train", split_dir))
            break

    for split_name in ["val", "valid", "validation", "Val", "VAL"]:
        split_dir = None
        for p in root.rglob(split_name):
            if p.is_dir():
                split_dir = p
                break
        if split_dir:
            candidate_dirs.append(("val", split_dir))
            break

    for split_name in ["test", "Test", "TEST", "testing"]:
        split_dir = None
        for p in root.rglob(split_name):
            if p.is_dir():
                split_dir = p
                break
        if split_dir:
            candidate_dirs.append(("test", split_dir))
            break

    # If no splits found, treat root children as class dirs
    if not candidate_dirs:
        candidate_dirs.append(("root", root))

    # ----- Step 2: Iterate over class folders and check images -----
    class_counts: Counter = Counter()
    total_images = 0
    corrupt_images = 0
    blurry_images = 0
    tiny_images = 0
    resolutions = []
    corrupt_files = []
    sample_limit = 50  # max images per class to do pixel-level checks (speed)

    splits_found = [name for name, _ in candidate_dirs]
    primary_split_dir = candidate_dirs[0][1]  # use first (train) for stats

    # Discover classes from the primary split
    class_dirs = [
        d for d in primary_split_dir.iterdir()
        if d.is_dir() and not d.name.startswith(".")
    ]

    if not class_dirs:
        # Maybe the images are directly in the root without class sub-dirs
        # This means it's not a classification dataset or has a flat structure
        all_images = [
            f for f in primary_split_dir.rglob("*")
            if f.is_file() and _is_image_file(f.name)
        ]
        return {
            "passed": len(all_images) > 0,
            "total_images": len(all_images),
            "num_classes": 0,
            "class_distribution": {},
            "splits_found": splits_found,
            "corrupt_count": 0,
            "corrupt_percent": 0.0,
            "blurry_count": 0,
            "blurry_percent": 0.0,
            "tiny_count": 0,
            "imbalance_ratio": 0.0,
            "avg_resolution": None,
            "warnings": ["No class sub-directories found. Dataset may not be in standard image classification format."],
            "errors": [],
            "corrupt_files": [],
        }

    warnings = []
    errors = []

    for cls_dir in class_dirs:
        cls_name = cls_dir.name
        cls_images = [
            f for f in cls_dir.iterdir()
            if f.is_file() and _is_image_file(f.name)
        ]
        count = len(cls_images)
        class_counts[cls_name] = count
        total_images += count

        if count < MIN_IMAGES_PER_CLASS:
            warnings.append(
                f"Class '{cls_name}' has only {count} images (minimum recommended: {MIN_IMAGES_PER_CLASS})"
            )

        # Pixel-level checks on a sample
        sample = cls_images[:sample_limit]
        for img_path in sample:
            report = _check_image(str(img_path))
            if not report["valid"]:
                corrupt_images += 1
                corrupt_files.append(str(img_path.relative_to(extract_dir)))
            else:
                if report["is_blurry"]:
                    blurry_images += 1
                if report["width"] and report["height"]:
                    if report["width"] < MIN_RESOLUTION or report["height"] < MIN_RESOLUTION:
                        tiny_images += 1
                    resolutions.append((report["width"], report["height"]))

    # ----- Step 3: Compute aggregate metrics -----
    num_classes = len(class_counts)
    checked_images = sum(min(class_counts[c], sample_limit) for c in class_counts)

    if class_counts:
        max_count = max(class_counts.values())
        min_count = min(class_counts.values())
        imbalance_ratio = max_count / min_count if min_count > 0 else float("inf")
    else:
        imbalance_ratio = 0.0

    corrupt_percent = (corrupt_images / checked_images * 100) if checked_images > 0 else 0.0
    blurry_percent = (blurry_images / checked_images * 100) if checked_images > 0 else 0.0

    avg_res = None
    if resolutions:
        avg_w = sum(r[0] for r in resolutions) / len(resolutions)
        avg_h = sum(r[1] for r in resolutions) / len(resolutions)
        avg_res = f"{int(avg_w)}x{int(avg_h)}"

    # ----- Step 4: Determine pass / fail -----
    if imbalance_ratio > IMBALANCE_RATIO_THRESHOLD:
        warnings.append(
            f"Severe class imbalance detected: ratio {imbalance_ratio:.1f}:1 "
            f"(threshold: {IMBALANCE_RATIO_THRESHOLD}:1)"
        )

    if corrupt_percent > MAX_CORRUPT_PERCENT:
        errors.append(
            f"Corruption rate {corrupt_percent:.1f}% exceeds threshold ({MAX_CORRUPT_PERCENT}%)"
        )

    if blurry_percent > MAX_BLURRY_PERCENT:
        warnings.append(
            f"Blurry image rate {blurry_percent:.1f}% exceeds threshold ({MAX_BLURRY_PERCENT}%)"
        )

    if num_classes < 2:
        errors.append(
            f"Only {num_classes} class(es) found. Need at least 2 for classification."
        )

    # Pass if there are no hard errors
    passed = len(errors) == 0

    return {
        "passed": passed,
        "total_images": total_images,
        "images_checked": checked_images,
        "num_classes": num_classes,
        "class_distribution": dict(class_counts),
        "splits_found": splits_found,
        "corrupt_count": corrupt_images,
        "corrupt_percent": round(corrupt_percent, 2),
        "blurry_count": blurry_images,
        "blurry_percent": round(blurry_percent, 2),
        "tiny_count": tiny_images,
        "imbalance_ratio": round(imbalance_ratio, 2) if imbalance_ratio != float("inf") else "Infinity",
        "avg_resolution": avg_res,
        "warnings": warnings,
        "errors": errors,
        "corrupt_files": corrupt_files[:20],  # cap list for readability
    }


# ---------------------------------------------------------------------------
# Orchestration: process a single project
# ---------------------------------------------------------------------------

def process_project(project_id: str):
    """
    Full sanity workflow for one project:
      1. Fetch project & dataset metadata from Supabase
      2. Download the dataset zip from GCS
      3. Extract and run sanity audit
      4. Store report in project metadata
      5. Update status to 'pending_training' (pass) or 'failed' (fail)
    """
    try:
        print(f"\n[SANITY] ===== Processing project: {project_id} =====")
        log_to_supabase(project_id, "Data Sanity Auditor started", "info")

        # Fetch project
        project_resp = supabase.table("projects").select("*").eq("id", project_id).execute()
        if not project_resp.data:
            print(f"[SANITY] Project {project_id} not found")
            return
        project = project_resp.data[0]
        user_id = project["user_id"]

        send_chat_message(user_id, "🔍 Data Sanity Auditor is now inspecting your dataset...")

        # Fetch dataset
        dataset_resp = supabase.table("datasets").select("*").eq("project_id", project_id).execute()
        if not dataset_resp.data:
            log_to_supabase(project_id, "No dataset found for project", "error")
            print(f"[SANITY] No dataset found for project {project_id}")
            supabase.table("projects").update({
                "status": "failed",
                "updated_at": datetime.now(UTC).isoformat(),
            }).eq("id", project_id).execute()
            send_chat_message(user_id, "❌ Sanity check failed: No dataset found for this project.")
            return

        dataset = dataset_resp.data[0]
        gcs_url = dataset.get("gcs_url", "")

        if not gcs_url:
            log_to_supabase(project_id, "Dataset has no GCS URL", "error")
            supabase.table("projects").update({
                "status": "failed",
                "updated_at": datetime.now(UTC).isoformat(),
            }).eq("id", project_id).execute()
            return

        # Download & extract
        with tempfile.TemporaryDirectory() as temp_dir:
            zip_path = os.path.join(temp_dir, "dataset.zip")
            extract_dir = os.path.join(temp_dir, "extracted")
            os.makedirs(extract_dir, exist_ok=True)

            log_to_supabase(project_id, f"Downloading dataset from {gcs_url}", "info")
            download_from_gcs(gcs_url, zip_path)

            log_to_supabase(project_id, "Extracting dataset archive", "info")
            try:
                with zipfile.ZipFile(zip_path, "r") as zf:
                    zf.extractall(extract_dir)
                print(f"[SANITY] Extracted to {extract_dir}")
            except zipfile.BadZipFile:
                log_to_supabase(project_id, "Dataset archive is corrupted (BadZipFile)", "error")
                supabase.table("projects").update({
                    "status": "failed",
                    "updated_at": datetime.now(UTC).isoformat(),
                }).eq("id", project_id).execute()
                send_chat_message(user_id, "❌ Sanity check failed: Dataset archive is corrupted.")
                return

            # Run the audit
            log_to_supabase(project_id, "Running sanity checks (corruption, blur, imbalance)...", "info")
            report = run_sanity_audit(extract_dir)

        # Log detailed results
        summary_parts = [
            f"Images: {report['total_images']}",
            f"Classes: {report['num_classes']}",
            f"Corrupt: {report['corrupt_count']} ({report['corrupt_percent']}%)",
            f"Blurry: {report['blurry_count']} ({report['blurry_percent']}%)",
            f"Imbalance ratio: {report['imbalance_ratio']}",
        ]
        summary_msg = " | ".join(summary_parts)
        log_to_supabase(project_id, f"Sanity report: {summary_msg}", "info")

        for w in report["warnings"]:
            log_to_supabase(project_id, f"⚠️ Warning: {w}", "warning")
        for e in report["errors"]:
            log_to_supabase(project_id, f"❌ Error: {e}", "error")

        # Store report in project metadata
        metadata = project.get("metadata", {}) or {}
        metadata["sanity_report"] = report
        supabase.table("projects").update({
            "metadata": metadata,
            "updated_at": datetime.now(UTC).isoformat(),
        }).eq("id", project_id).execute()

        if report["passed"]:
            # ✅ Advance the pipeline
            log_to_supabase(project_id, "✅ Dataset passed sanity checks", "info")
            supabase.table("projects").update({
                "status": "pending_training",
                "updated_at": datetime.now(UTC).isoformat(),
            }).eq("id", project_id).execute()

            # Build user message
            warning_text = ""
            if report["warnings"]:
                warning_text = "\n⚠️ Warnings:\n" + "\n".join(f"  • {w}" for w in report["warnings"])

            send_chat_message(
                user_id,
                f"✅ Data Sanity Check Passed!\n"
                f"📊 {report['total_images']} images across {report['num_classes']} classes\n"
                f"🔍 Corrupt: {report['corrupt_percent']}% | Blurry: {report['blurry_percent']}%\n"
                f"📐 Avg resolution: {report['avg_resolution'] or 'N/A'}"
                f"{warning_text}\n"
                f"🚀 Proceeding to Training Agent...",
            )
            print(f"[SANITY] ✅ Project {project_id} PASSED sanity checks")
        else:
            # ❌ Block the pipeline
            log_to_supabase(project_id, "❌ Dataset FAILED sanity checks", "error")
            supabase.table("projects").update({
                "status": "failed",
                "updated_at": datetime.now(UTC).isoformat(),
            }).eq("id", project_id).execute()

            error_text = "\n".join(f"  • {e}" for e in report["errors"])
            send_chat_message(
                user_id,
                f"❌ Data Sanity Check Failed!\n"
                f"The dataset has critical issues that must be resolved:\n{error_text}\n\n"
                f"Please try with a different dataset or fix the issues above.",
            )
            print(f"[SANITY] ❌ Project {project_id} FAILED sanity checks")

    except Exception as exc:
        error_msg = traceback.format_exc()
        print(f"[SANITY] ❌ Exception processing {project_id}: {exc}")
        print(f"[SANITY] Traceback:\n{error_msg}")
        log_to_supabase(project_id, f"Sanity audit error: {str(exc)}", "error")

        try:
            supabase.table("projects").update({
                "status": "failed",
                "updated_at": datetime.now(UTC).isoformat(),
            }).eq("id", project_id).execute()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Polling loop
# ---------------------------------------------------------------------------

def poll_pending_projects():
    """Background thread: poll for projects with status='pending_sanity'."""
    global polling_active
    print("\n" + "=" * 60)
    print("🔬 DATA SANITY AUDITOR — AUTO-POLLING STARTED")
    print("=" * 60)
    print(f"Watching for projects with status='pending_sanity' (every {POLL_INTERVAL}s)")
    print("Press Ctrl+C to stop the agent\n")

    import time

    while polling_active:
        try:
            response = (
                supabase.table("projects")
                .select("*")
                .eq("status", "pending_sanity")
                .execute()
            )

            if response.data:
                print(f"[SANITY] Found {len(response.data)} pending project(s)")
                for project in response.data:
                    project_id = project["id"]
                    project_name = project.get("name", "Unknown")
                    print(f"[SANITY] Processing: {project_name} ({project_id})")
                    process_project(project_id)

            time.sleep(POLL_INTERVAL)

        except KeyboardInterrupt:
            print("\n[SANITY] Polling stopped by user")
            polling_active = False
            break
        except Exception as e:
            print(f"[SANITY] Polling error: {e}")
            time.sleep(POLL_INTERVAL)

    print("[SANITY] Polling stopped")


# ---------------------------------------------------------------------------
# FastAPI endpoints
# ---------------------------------------------------------------------------

@app.post("/agents/sanity/start")
async def start_sanity_job(job: SanityJobRequest):
    """Manually trigger sanity check for a project."""
    project_id = job.project_id

    # Verify project exists
    project_resp = supabase.table("projects").select("*").eq("id", project_id).execute()
    if not project_resp.data:
        raise HTTPException(status_code=404, detail="Project not found")

    # Run in a background thread so we don't block the request
    thread = threading.Thread(target=process_project, args=(project_id,), daemon=True)
    thread.start()

    return {
        "success": True,
        "message": f"Sanity audit started for project {project_id}",
    }


@app.get("/agents/sanity/status/{project_id}")
async def get_sanity_status(project_id: str):
    """Get sanity audit status and logs for a project."""
    try:
        logs_resp = (
            supabase.table("agent_logs")
            .select("*")
            .eq("project_id", project_id)
            .eq("agent_name", AGENT_NAME)
            .order("created_at", desc=True)
            .limit(20)
            .execute()
        )

        # Try to get sanity_report from project metadata
        project_resp = supabase.table("projects").select("metadata").eq("id", project_id).execute()
        sanity_report = None
        if project_resp.data:
            metadata = project_resp.data[0].get("metadata", {}) or {}
            sanity_report = metadata.get("sanity_report")

        return {
            "logs": logs_resp.data,
            "sanity_report": sanity_report,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "agent": AGENT_NAME,
        "auto_polling": polling_active,
    }


@app.post("/agents/sanity/polling/start")
async def start_polling():
    """Start automatic polling."""
    global polling_active
    if polling_active:
        return {"success": False, "message": "Polling already active"}
    polling_active = True
    thread = threading.Thread(target=poll_pending_projects, daemon=True)
    thread.start()
    return {"success": True, "message": "Auto-polling started"}


@app.post("/agents/sanity/polling/stop")
async def stop_polling():
    """Stop automatic polling."""
    global polling_active
    polling_active = False
    return {"success": True, "message": "Auto-polling stopped"}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    auto_start = os.getenv("AUTO_POLL_ON_START", "true").lower() == "true"
    if auto_start:
        polling_active = True
        poll_thread = threading.Thread(target=poll_pending_projects, daemon=True)
        poll_thread.start()

    uvicorn.run(app, host="0.0.0.0", port=AGENT_PORT)
