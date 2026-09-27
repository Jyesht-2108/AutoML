"""
Data Sanity Auditor Agent — v2 (Auto-Fix + Human-in-the-Loop)
==============================================================
Phase 1 agent in the AgentHive pipeline.

Two-phase workflow:
  Phase A — AUDIT:
    1. Downloads dataset zip from GCS
    2. Extracts and discovers class structure
    3. Checks for corruption, blur, resolution, imbalance
    4. Generates a sanity_report with proposed_actions
    5. Sets status to 'pending_sanity_review' (waits for human approval)

  Phase B — FIX:
    1. Reads user-approved actions from metadata.sanity_actions
    2. Removes corrupt/blurry images
    3. Auto-creates train/val/test splits if missing
    4. Augments minority classes to fix imbalance
    5. Re-zips and re-uploads the sanitized dataset to GCS
    6. Sets status to 'pending_training'

Port: 8004
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from supabase import create_client, Client
from google.cloud import storage
from dotenv import load_dotenv
import os
import io
import json
import random
import tempfile
import shutil
import zipfile
import math
import traceback
from datetime import datetime, UTC
from collections import Counter
from pathlib import Path
import threading

load_dotenv()

app = FastAPI(
    title="Data Sanity Auditor Agent",
    description="AgentHive — Phase 1 Data Quality Validation + Auto-Fix Agent",
    version="2.0.0",
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
AGENT_NAME = "sanity"
AGENT_PORT = 8004
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL_SECONDS", "10"))

# Sanity thresholds
IMBALANCE_RATIO_THRESHOLD = float(os.getenv("IMBALANCE_RATIO_THRESHOLD", "10.0"))
MIN_IMAGES_PER_CLASS = int(os.getenv("MIN_IMAGES_PER_CLASS", "5"))
MIN_RESOLUTION = int(os.getenv("MIN_RESOLUTION", "16"))
BLUR_VARIANCE_THRESHOLD = float(os.getenv("BLUR_VARIANCE_THRESHOLD", "50.0"))
MAX_CORRUPT_PERCENT = float(os.getenv("MAX_CORRUPT_PERCENT", "10.0"))
MAX_BLURRY_PERCENT = float(os.getenv("MAX_BLURRY_PERCENT", "30.0"))
TARGET_IMBALANCE_RATIO = float(os.getenv("TARGET_IMBALANCE_RATIO", "2.0"))

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tiff", ".webp"}

polling_active = False

# ---------------------------------------------------------------------------
# Supabase + GCS clients
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


class SanityApprovalRequest(BaseModel):
    project_id: str
    actions: dict  # {"remove_corrupt": true, "remove_blurry": true, "auto_split": true, "augment_balance": true}


# ---------------------------------------------------------------------------
# Logging helpers
# ---------------------------------------------------------------------------
def log_to_supabase(project_id: str, message: str, level: str = "info"):
    try:
        supabase.table("agent_logs").insert({
            "project_id": project_id,
            "agent_name": AGENT_NAME,
            "message": message,
            "log_level": level,
            "created_at": datetime.now(UTC).isoformat(),
        }).execute()
    except Exception as e:
        print(f"[SANITY] Failed to log: {e}")


def send_chat_message(user_id: str, content: str):
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


def upload_to_gcs(local_path: str, destination_blob: str) -> str:
    """Upload a local file to GCS and return the gs:// URL."""
    file_size_mb = os.path.getsize(local_path) / (1024 * 1024)
    print(f"[SANITY] Uploading {file_size_mb:.1f}MB -> gs://{gcp_bucket_name}/{destination_blob}")
    client = storage.Client()
    bucket = client.bucket(gcp_bucket_name)
    chunk_size = 10 * 1024 * 1024
    blob = bucket.blob(destination_blob, chunk_size=chunk_size)
    timeout = max(300, int(file_size_mb * 5))
    blob.upload_from_filename(local_path, timeout=timeout)
    url = f"gs://{gcp_bucket_name}/{destination_blob}"
    print(f"[SANITY] ✅ Upload complete: {url}")
    return url


# ---------------------------------------------------------------------------
# Image quality helpers (Pillow only)
# ---------------------------------------------------------------------------
def _is_image_file(filename: str) -> bool:
    return Path(filename).suffix.lower() in IMAGE_EXTENSIONS


def _check_image(filepath: str) -> dict:
    """Open an image and return a quality report."""
    from PIL import Image
    try:
        with Image.open(filepath) as img:
            img.verify()
        with Image.open(filepath) as img:
            img.load()
            width, height = img.size
            if width < MIN_RESOLUTION or height < MIN_RESOLUTION:
                return {"valid": False, "width": width, "height": height,
                        "is_blurry": False, "error": f"Too small: {width}x{height}"}

            # Blur detection via Laplacian variance approximation
            is_blurry = False
            try:
                gray = img.convert("L")
                pixels = list(gray.getdata())
                w, h = gray.size
                if w > 4 and h > 4:
                    # Sub-sample for speed on large images
                    step = max(1, (w * h) // 10000)
                    lap_values = []
                    for i in range(w + 1, (h - 1) * w - 1, step):
                        y, x = divmod(i, w)
                        if 0 < x < w - 1 and 0 < y < h - 1:
                            val = (4 * pixels[i] - pixels[i - w] - pixels[i + w]
                                   - pixels[i - 1] - pixels[i + 1])
                            lap_values.append(val)
                    if lap_values:
                        mean_lap = sum(lap_values) / len(lap_values)
                        variance = sum((v - mean_lap) ** 2 for v in lap_values) / len(lap_values)
                        is_blurry = variance < BLUR_VARIANCE_THRESHOLD
            except Exception:
                pass

            return {"valid": True, "width": width, "height": height,
                    "is_blurry": is_blurry, "error": None}
    except Exception as e:
        return {"valid": False, "width": None, "height": None,
                "is_blurry": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Phase A: AUDIT — scan the dataset and produce a report
# ---------------------------------------------------------------------------

def discover_class_dirs(root: Path):
    """Find the primary split directory and class sub-dirs."""
    # Try standard split names
    for split_name in ["train", "training", "Train", "TRAIN"]:
        for p in root.rglob(split_name):
            if p.is_dir():
                class_dirs = [d for d in p.iterdir() if d.is_dir() and not d.name.startswith(".")]
                if class_dirs:
                    return p, "train", class_dirs
    # No splits — check if root children are class dirs
    class_dirs = [d for d in root.iterdir() if d.is_dir() and not d.name.startswith(".")]
    if class_dirs:
        # Check if these are class folders (contain images)
        has_images = any(
            any(_is_image_file(f.name) for f in d.iterdir() if f.is_file())
            for d in class_dirs[:3]
        )
        if has_images:
            return root, "none", class_dirs
    return root, "none", []


def has_split_structure(root: Path) -> bool:
    """Check if dataset already has train/val or train/test splits."""
    split_names = {"train", "training", "val", "valid", "validation", "test", "testing"}
    children = {d.name.lower() for d in root.iterdir() if d.is_dir()}
    return bool(children & split_names)


def find_dataset_root(extract_dir: Path) -> Path:
    """Navigate into nested folders to find the actual dataset root."""
    root = extract_dir
    # Sometimes zip extracts into a single top-level folder
    while True:
        children = [d for d in root.iterdir() if d.is_dir() and not d.name.startswith(".")]
        files = [f for f in root.iterdir() if f.is_file() and _is_image_file(f.name)]
        if len(children) == 1 and len(files) == 0:
            root = children[0]
        else:
            break
    return root


def run_audit(extract_dir: str) -> dict:
    """
    Scan the dataset and produce a full sanity report with proposed_actions.
    """
    root = find_dataset_root(Path(extract_dir))
    has_splits = has_split_structure(root)
    primary_dir, split_type, class_dirs = discover_class_dirs(root)

    sample_limit = 50  # images per class for pixel-level checks
    class_counts = Counter()
    total_images = 0
    corrupt_files = []
    blurry_files = []
    tiny_files = []
    resolutions = []

    if not class_dirs:
        all_images = [f for f in root.rglob("*") if f.is_file() and _is_image_file(f.name)]
        return {
            "passed": len(all_images) > 0,
            "total_images": len(all_images),
            "num_classes": 0,
            "class_distribution": {},
            "has_splits": has_splits,
            "corrupt_count": 0, "corrupt_percent": 0.0,
            "blurry_count": 0, "blurry_percent": 0.0,
            "tiny_count": 0,
            "imbalance_ratio": 0.0,
            "avg_resolution": None,
            "warnings": ["No class sub-directories found."],
            "errors": ["Cannot determine class structure. Dataset must have class sub-folders."],
            "corrupt_files": [], "blurry_files": [],
            "proposed_actions": {},
        }

    warnings = []
    errors = []
    proposed_actions = {}

    for cls_dir in class_dirs:
        cls_name = cls_dir.name
        cls_images = [f for f in cls_dir.iterdir() if f.is_file() and _is_image_file(f.name)]
        count = len(cls_images)
        class_counts[cls_name] = count
        total_images += count

        if count < MIN_IMAGES_PER_CLASS:
            warnings.append(f"Class '{cls_name}' has only {count} images (min: {MIN_IMAGES_PER_CLASS})")

        sample = cls_images[:sample_limit]
        for img_path in sample:
            report = _check_image(str(img_path))
            rel_path = str(img_path.relative_to(extract_dir))
            if not report["valid"]:
                corrupt_files.append(rel_path)
            else:
                if report["is_blurry"]:
                    blurry_files.append(rel_path)
                if report["width"] and report["height"]:
                    if report["width"] < MIN_RESOLUTION or report["height"] < MIN_RESOLUTION:
                        tiny_files.append(rel_path)
                    resolutions.append((report["width"], report["height"]))

    num_classes = len(class_counts)
    checked_images = sum(min(class_counts[c], sample_limit) for c in class_counts)

    max_count = max(class_counts.values()) if class_counts else 0
    min_count = min(class_counts.values()) if class_counts else 0
    imbalance_ratio = max_count / min_count if min_count > 0 else float("inf")

    corrupt_percent = (len(corrupt_files) / checked_images * 100) if checked_images > 0 else 0.0
    blurry_percent = (len(blurry_files) / checked_images * 100) if checked_images > 0 else 0.0

    avg_res = None
    if resolutions:
        avg_res = f"{int(sum(r[0] for r in resolutions)/len(resolutions))}x{int(sum(r[1] for r in resolutions)/len(resolutions))}"

    # --- Determine proposed_actions ---
    if corrupt_files:
        proposed_actions["remove_corrupt"] = {
            "description": f"Remove {len(corrupt_files)} corrupt/unreadable image(s)",
            "count": len(corrupt_files),
            "recommended": True,
        }
    if blurry_files:
        proposed_actions["remove_blurry"] = {
            "description": f"Remove {len(blurry_files)} blurry image(s) (Laplacian variance < {BLUR_VARIANCE_THRESHOLD})",
            "count": len(blurry_files),
            "recommended": len(blurry_files) < total_images * 0.5,  # don't recommend if > half are blurry
        }
    if not has_splits:
        proposed_actions["auto_split"] = {
            "description": "Auto-create train/val/test splits (70%/15%/15%)",
            "recommended": True,
        }
    if imbalance_ratio > TARGET_IMBALANCE_RATIO and num_classes >= 2:
        proposed_actions["augment_balance"] = {
            "description": f"Augment minority classes to reduce imbalance (current ratio: {imbalance_ratio:.1f}:1)",
            "target_ratio": TARGET_IMBALANCE_RATIO,
            "recommended": True,
        }

    # Hard errors
    if num_classes < 2:
        errors.append(f"Only {num_classes} class(es) found. Need at least 2.")
    if corrupt_percent > MAX_CORRUPT_PERCENT and "remove_corrupt" not in proposed_actions:
        errors.append(f"Corruption rate {corrupt_percent:.1f}% exceeds {MAX_CORRUPT_PERCENT}%")

    if blurry_percent > MAX_BLURRY_PERCENT:
        warnings.append(f"Blurry rate {blurry_percent:.1f}% exceeds {MAX_BLURRY_PERCENT}%")
    if imbalance_ratio > IMBALANCE_RATIO_THRESHOLD:
        warnings.append(f"Severe imbalance: {imbalance_ratio:.1f}:1 (threshold: {IMBALANCE_RATIO_THRESHOLD}:1)")

    passed = len(errors) == 0

    return {
        "passed": passed,
        "total_images": total_images,
        "images_checked": checked_images,
        "num_classes": num_classes,
        "class_distribution": dict(class_counts),
        "has_splits": has_splits,
        "corrupt_count": len(corrupt_files),
        "corrupt_percent": round(corrupt_percent, 2),
        "blurry_count": len(blurry_files),
        "blurry_percent": round(blurry_percent, 2),
        "tiny_count": len(tiny_files),
        "imbalance_ratio": round(imbalance_ratio, 2) if imbalance_ratio != float("inf") else "Infinity",
        "avg_resolution": avg_res,
        "warnings": warnings,
        "errors": errors,
        "corrupt_files": corrupt_files[:30],
        "blurry_files": blurry_files[:30],
        "proposed_actions": proposed_actions,
    }


# ---------------------------------------------------------------------------
# Phase B: FIX — apply user-approved corrections
# ---------------------------------------------------------------------------

def fix_remove_corrupt(extract_dir: str, corrupt_files: list) -> int:
    """Delete corrupt images from the extracted directory. Returns count deleted."""
    deleted = 0
    for rel_path in corrupt_files:
        full_path = os.path.join(extract_dir, rel_path)
        if os.path.exists(full_path):
            os.remove(full_path)
            deleted += 1
    return deleted


def fix_remove_blurry(extract_dir: str, blurry_files: list) -> int:
    """Delete blurry images. Returns count deleted."""
    deleted = 0
    for rel_path in blurry_files:
        full_path = os.path.join(extract_dir, rel_path)
        if os.path.exists(full_path):
            os.remove(full_path)
            deleted += 1
    return deleted


def fix_auto_split(extract_dir: str, train_ratio=0.70, val_ratio=0.15, test_ratio=0.15) -> dict:
    """
    If the dataset has class folders but no train/val/test splits,
    randomly split images into train/val/test directories.
    Returns stats dict.
    """
    root = find_dataset_root(Path(extract_dir))

    # Ensure no splits exist already
    if has_split_structure(root):
        return {"skipped": True, "reason": "Splits already exist"}

    class_dirs = [d for d in root.iterdir() if d.is_dir() and not d.name.startswith(".")]
    if not class_dirs:
        return {"skipped": True, "reason": "No class directories"}

    train_dir = root / "train"
    val_dir = root / "val"
    test_dir = root / "test"

    stats = {"train": 0, "val": 0, "test": 0}

    for cls_dir in class_dirs:
        cls_name = cls_dir.name
        images = [f for f in cls_dir.iterdir() if f.is_file() and _is_image_file(f.name)]
        random.shuffle(images)

        n = len(images)
        n_train = max(1, int(n * train_ratio))
        n_val = max(0, int(n * val_ratio))
        n_test = n - n_train - n_val

        splits = {
            "train": images[:n_train],
            "val": images[n_train:n_train + n_val],
            "test": images[n_train + n_val:],
        }

        for split_name, split_images in splits.items():
            split_cls_dir = root / split_name / cls_name
            split_cls_dir.mkdir(parents=True, exist_ok=True)
            for img in split_images:
                shutil.move(str(img), str(split_cls_dir / img.name))
                stats[split_name] += 1

        # Remove the now-empty original class directory
        if cls_dir.exists() and cls_dir != train_dir and cls_dir != val_dir and cls_dir != test_dir:
            shutil.rmtree(cls_dir, ignore_errors=True)

    return stats


def fix_augment_balance(extract_dir: str, target_ratio: float = 2.0) -> dict:
    """
    Augment minority classes using Pillow transforms (flip, rotate, brightness)
    until no class is more than target_ratio times smaller than the largest class.
    Returns stats dict.
    """
    from PIL import Image, ImageEnhance

    root = find_dataset_root(Path(extract_dir))

    # Find the train directory (or root if no splits)
    train_dir = None
    for name in ["train", "training", "Train"]:
        candidate = root / name
        if candidate.is_dir():
            train_dir = candidate
            break
    if not train_dir:
        train_dir = root

    class_dirs = [d for d in train_dir.iterdir() if d.is_dir() and not d.name.startswith(".")]
    if not class_dirs:
        return {"skipped": True, "reason": "No class directories in train"}

    # Count images per class
    class_counts = {}
    for cls_dir in class_dirs:
        imgs = [f for f in cls_dir.iterdir() if f.is_file() and _is_image_file(f.name)]
        class_counts[cls_dir.name] = {"dir": cls_dir, "images": imgs, "count": len(imgs)}

    max_count = max(info["count"] for info in class_counts.values())
    target_min = int(max_count / target_ratio)

    augment_transforms = [
        lambda img: img.transpose(Image.FLIP_LEFT_RIGHT),
        lambda img: img.rotate(random.randint(5, 30), expand=False, fillcolor=(0, 0, 0)),
        lambda img: img.rotate(random.randint(-30, -5), expand=False, fillcolor=(0, 0, 0)),
        lambda img: ImageEnhance.Brightness(img).enhance(random.uniform(0.7, 1.3)),
        lambda img: ImageEnhance.Contrast(img).enhance(random.uniform(0.7, 1.3)),
    ]

    stats = {"augmented_classes": 0, "total_new_images": 0}

    for cls_name, info in class_counts.items():
        if info["count"] >= target_min:
            continue

        needed = target_min - info["count"]
        generated = 0
        source_images = info["images"]

        if not source_images:
            continue

        stats["augmented_classes"] += 1

        for i in range(needed):
            src = random.choice(source_images)
            try:
                with Image.open(str(src)) as img:
                    img = img.convert("RGB")
                    # Apply 1-2 random transforms
                    num_transforms = random.randint(1, 2)
                    for _ in range(num_transforms):
                        transform = random.choice(augment_transforms)
                        img = transform(img)

                    # Save with a unique name
                    new_name = f"aug_{i:04d}_{src.name}"
                    new_path = info["dir"] / new_name
                    img.save(str(new_path), quality=95)
                    generated += 1
            except Exception:
                continue

        stats["total_new_images"] += generated

    return stats


def repackage_and_upload(extract_dir: str, original_gcs_url: str, project_id: str) -> str:
    """Re-zip the sanitized dataset and upload to GCS. Returns new gs:// URL."""
    # Create zip
    zip_path = os.path.join(tempfile.gettempdir(), f"sanitized_{project_id}.zip")
    print(f"[SANITY] Re-packaging sanitized dataset...")

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root_dir, dirs, files in os.walk(extract_dir):
            # Skip hidden directories
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for file in files:
                if file.startswith("."):
                    continue
                file_path = os.path.join(root_dir, file)
                arcname = os.path.relpath(file_path, extract_dir)
                zf.write(file_path, arcname)

    # Upload to GCS (use sanitized/ prefix)
    # Derive a clean name from the original URL
    original_name = original_gcs_url.split("/")[-1] if "/" in original_gcs_url else "dataset.zip"
    destination = f"sanitized/{original_name}"
    new_url = upload_to_gcs(zip_path, destination)

    # Clean up temp zip
    if os.path.exists(zip_path):
        os.remove(zip_path)

    return new_url


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def process_audit(project_id: str):
    """Phase A: Run audit, store report, set status to pending_sanity_review."""
    try:
        print(f"\n[SANITY] ===== AUDIT Phase for project: {project_id} =====")
        log_to_supabase(project_id, "Data Sanity Auditor started (Audit Phase)", "info")

        project_resp = supabase.table("projects").select("*").eq("id", project_id).execute()
        if not project_resp.data:
            print(f"[SANITY] Project {project_id} not found")
            return
        project = project_resp.data[0]
        user_id = project["user_id"]

        send_chat_message(user_id, "🔬 Data Sanity Auditor is inspecting your dataset...")

        dataset_resp = supabase.table("datasets").select("*").eq("project_id", project_id).execute()
        if not dataset_resp.data:
            log_to_supabase(project_id, "No dataset found", "error")
            supabase.table("projects").update({
                "status": "failed", "updated_at": datetime.now(UTC).isoformat(),
            }).eq("id", project_id).execute()
            send_chat_message(user_id, "❌ Sanity check failed: No dataset found.")
            return

        gcs_url = dataset_resp.data[0].get("gcs_url", "")
        if not gcs_url:
            log_to_supabase(project_id, "Dataset has no GCS URL", "error")
            supabase.table("projects").update({
                "status": "failed", "updated_at": datetime.now(UTC).isoformat(),
            }).eq("id", project_id).execute()
            return

        with tempfile.TemporaryDirectory() as temp_dir:
            zip_path = os.path.join(temp_dir, "dataset.zip")
            extract_dir = os.path.join(temp_dir, "extracted")
            os.makedirs(extract_dir, exist_ok=True)

            log_to_supabase(project_id, f"Downloading dataset from GCS", "info")
            download_from_gcs(gcs_url, zip_path)

            log_to_supabase(project_id, "Extracting archive", "info")
            try:
                with zipfile.ZipFile(zip_path, "r") as zf:
                    zf.extractall(extract_dir)
            except zipfile.BadZipFile:
                log_to_supabase(project_id, "Dataset archive is corrupted", "error")
                supabase.table("projects").update({
                    "status": "failed", "updated_at": datetime.now(UTC).isoformat(),
                }).eq("id", project_id).execute()
                send_chat_message(user_id, "❌ Sanity check failed: Archive is corrupted.")
                return

            log_to_supabase(project_id, "Running sanity checks...", "info")
            report = run_audit(extract_dir)

        # Store report in project metadata
        metadata = project.get("metadata", {}) or {}
        metadata["sanity_report"] = report
        # Clear any previous actions
        metadata.pop("sanity_actions", None)

        # Log summary
        summary_parts = [
            f"Images: {report['total_images']}", f"Classes: {report['num_classes']}",
            f"Corrupt: {report['corrupt_count']} ({report['corrupt_percent']}%)",
            f"Blurry: {report['blurry_count']} ({report['blurry_percent']}%)",
            f"Imbalance: {report['imbalance_ratio']}",
            f"Has splits: {report.get('has_splits', 'N/A')}",
        ]
        log_to_supabase(project_id, f"Audit results: {' | '.join(summary_parts)}", "info")

        for w in report["warnings"]:
            log_to_supabase(project_id, f"⚠️ {w}", "warning")
        for e in report["errors"]:
            log_to_supabase(project_id, f"❌ {e}", "error")

        if not report["passed"]:
            # Hard fail — cannot fix these errors
            log_to_supabase(project_id, "❌ Dataset FAILED — unrecoverable errors", "error")
            metadata["sanity_report"] = report
            supabase.table("projects").update({
                "metadata": metadata,
                "status": "failed",
                "updated_at": datetime.now(UTC).isoformat(),
            }).eq("id", project_id).execute()
            error_text = "\n".join(f"  • {e}" for e in report["errors"])
            send_chat_message(user_id,
                f"❌ Data Sanity Check Failed!\n{error_text}\n\nPlease try with a different dataset.")
            return

        # Check if there are any proposed actions (need human approval)
        if report["proposed_actions"]:
            log_to_supabase(project_id, f"Proposed {len(report['proposed_actions'])} fix action(s) — awaiting user approval", "info")
            supabase.table("projects").update({
                "metadata": metadata,
                "status": "pending_sanity_review",
                "updated_at": datetime.now(UTC).isoformat(),
            }).eq("id", project_id).execute()

            # Build user message listing proposed actions
            action_lines = []
            for key, action in report["proposed_actions"].items():
                rec = "✅ Recommended" if action.get("recommended") else "⚠️ Optional"
                action_lines.append(f"  • {action['description']} [{rec}]")
            actions_text = "\n".join(action_lines)

            send_chat_message(user_id,
                f"🔬 Data Sanity Audit Complete!\n"
                f"📊 {report['total_images']} images, {report['num_classes']} classes\n\n"
                f"The following fixes are available:\n{actions_text}\n\n"
                f"👉 Please review and approve/skip each action in the project details panel.")
            print(f"[SANITY] ⏳ Waiting for user approval (pending_sanity_review)")
        else:
            # No issues — pass through directly
            log_to_supabase(project_id, "✅ Dataset is clean — no fixes needed", "info")
            supabase.table("projects").update({
                "metadata": metadata,
                "status": "pending_training_config",
                "updated_at": datetime.now(UTC).isoformat(),
            }).eq("id", project_id).execute()
            send_chat_message(user_id,
                f"✅ Data Sanity Check Passed!\n"
                f"📊 {report['total_images']} images, {report['num_classes']} classes — No issues found.\n"
                f"⚙️ Please configure training settings...")
            print(f"[SANITY] ✅ Clean dataset — advancing to training config")

    except Exception as exc:
        print(f"[SANITY] ❌ Audit error: {exc}")
        print(traceback.format_exc())
        log_to_supabase(project_id, f"Audit error: {str(exc)}", "error")
        try:
            supabase.table("projects").update({
                "status": "failed", "updated_at": datetime.now(UTC).isoformat(),
            }).eq("id", project_id).execute()
        except Exception:
            pass


def process_fix(project_id: str):
    """Phase B: Apply user-approved fixes, repackage, re-upload, advance to training."""
    try:
        print(f"\n[SANITY] ===== FIX Phase for project: {project_id} =====")
        log_to_supabase(project_id, "Data Sanity Auditor started (Fix Phase)", "info")

        project_resp = supabase.table("projects").select("*").eq("id", project_id).execute()
        if not project_resp.data:
            return
        project = project_resp.data[0]
        user_id = project["user_id"]
        metadata = project.get("metadata", {}) or {}
        sanity_report = metadata.get("sanity_report", {})
        sanity_actions = metadata.get("sanity_actions", {})

        if not sanity_actions:
            # User skipped all actions
            log_to_supabase(project_id, "User skipped all fixes — advancing to training config", "info")
            supabase.table("projects").update({
                "status": "pending_training_config",
                "updated_at": datetime.now(UTC).isoformat(),
            }).eq("id", project_id).execute()
            send_chat_message(user_id, "⏭️ Sanity fixes skipped. Please configure training settings...")
            return

        send_chat_message(user_id, "🔧 Applying approved data fixes...")

        # Download dataset again for fixing
        dataset_resp = supabase.table("datasets").select("*").eq("project_id", project_id).execute()
        if not dataset_resp.data:
            log_to_supabase(project_id, "No dataset found for fixes", "error")
            supabase.table("projects").update({
                "status": "failed", "updated_at": datetime.now(UTC).isoformat(),
            }).eq("id", project_id).execute()
            return

        gcs_url = dataset_resp.data[0].get("gcs_url", "")

        with tempfile.TemporaryDirectory() as temp_dir:
            zip_path = os.path.join(temp_dir, "dataset.zip")
            extract_dir = os.path.join(temp_dir, "extracted")
            os.makedirs(extract_dir, exist_ok=True)

            download_from_gcs(gcs_url, zip_path)
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(extract_dir)

            fix_results = {}

            # 1. Remove corrupt images
            if sanity_actions.get("remove_corrupt"):
                corrupt_list = sanity_report.get("corrupt_files", [])
                deleted = fix_remove_corrupt(extract_dir, corrupt_list)
                fix_results["remove_corrupt"] = f"Removed {deleted} corrupt image(s)"
                log_to_supabase(project_id, f"🗑️ Removed {deleted} corrupt image(s)", "info")

            # 2. Remove blurry images
            if sanity_actions.get("remove_blurry"):
                blurry_list = sanity_report.get("blurry_files", [])
                deleted = fix_remove_blurry(extract_dir, blurry_list)
                fix_results["remove_blurry"] = f"Removed {deleted} blurry image(s)"
                log_to_supabase(project_id, f"🗑️ Removed {deleted} blurry image(s)", "info")

            # 3. Auto-split
            if sanity_actions.get("auto_split"):
                split_stats = fix_auto_split(extract_dir)
                if split_stats.get("skipped"):
                    fix_results["auto_split"] = f"Skipped: {split_stats['reason']}"
                else:
                    fix_results["auto_split"] = (
                        f"Split: train={split_stats['train']}, "
                        f"val={split_stats['val']}, test={split_stats['test']}"
                    )
                log_to_supabase(project_id, f"📂 Auto-split: {fix_results['auto_split']}", "info")

            # 4. Augment for balance
            if sanity_actions.get("augment_balance"):
                aug_stats = fix_augment_balance(extract_dir, TARGET_IMBALANCE_RATIO)
                if aug_stats.get("skipped"):
                    fix_results["augment_balance"] = f"Skipped: {aug_stats['reason']}"
                else:
                    fix_results["augment_balance"] = (
                        f"Augmented {aug_stats['augmented_classes']} class(es), "
                        f"generated {aug_stats['total_new_images']} new image(s)"
                    )
                log_to_supabase(project_id, f"🔄 Augmentation: {fix_results['augment_balance']}", "info")

            # 5. Re-package and upload sanitized dataset
            log_to_supabase(project_id, "📦 Re-packaging sanitized dataset...", "info")
            new_gcs_url = repackage_and_upload(extract_dir, gcs_url, project_id)

            # Update the dataset record with sanitized URL
            dataset_id = dataset_resp.data[0]["id"]
            supabase.table("datasets").update({
                "gcs_url": new_gcs_url,
            }).eq("id", dataset_id).execute()
            log_to_supabase(project_id, f"✅ Sanitized dataset uploaded: {new_gcs_url}", "info")

        # Store fix results in metadata
        metadata["sanity_fix_results"] = fix_results
        supabase.table("projects").update({
            "metadata": metadata,
            "status": "pending_training_config",
            "updated_at": datetime.now(UTC).isoformat(),
        }).eq("id", project_id).execute()

        # Build user summary
        fix_lines = [f"  • {v}" for v in fix_results.values()]
        send_chat_message(user_id,
            f"✅ Dataset sanitized successfully!\n"
            f"Applied fixes:\n" + "\n".join(fix_lines) + "\n\n"
            f"⚙️ Please configure training settings...")
        log_to_supabase(project_id, "✅ Fix phase complete — advancing to training config", "info")
        print(f"[SANITY] ✅ Fix phase complete for {project_id}")

    except Exception as exc:
        print(f"[SANITY] ❌ Fix error: {exc}")
        print(traceback.format_exc())
        log_to_supabase(project_id, f"Fix error: {str(exc)}", "error")
        try:
            supabase.table("projects").update({
                "status": "failed", "updated_at": datetime.now(UTC).isoformat(),
            }).eq("id", project_id).execute()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Polling loop — watches for BOTH phases
# ---------------------------------------------------------------------------

def poll_pending_projects():
    global polling_active
    print("\n" + "=" * 60)
    print("🔬 DATA SANITY AUDITOR v2 — AUTO-POLLING STARTED")
    print("=" * 60)
    print(f"  Phase A: Watching status='pending_sanity' (audit)")
    print(f"  Phase B: Watching status='pending_sanity_fix' (apply fixes)")
    print(f"  Interval: {POLL_INTERVAL}s")
    print("=" * 60 + "\n")

    import time

    while polling_active:
        try:
            # Phase A: Audit
            resp_a = supabase.table("projects").select("*").eq("status", "pending_sanity").execute()
            if resp_a.data:
                print(f"[SANITY] Found {len(resp_a.data)} project(s) for AUDIT")
                for proj in resp_a.data:
                    process_audit(proj["id"])

            # Phase B: Fix (after user approval)
            resp_b = supabase.table("projects").select("*").eq("status", "pending_sanity_fix").execute()
            if resp_b.data:
                print(f"[SANITY] Found {len(resp_b.data)} project(s) for FIX")
                for proj in resp_b.data:
                    process_fix(proj["id"])

            time.sleep(POLL_INTERVAL)

        except KeyboardInterrupt:
            print("\n[SANITY] Stopped by user")
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
    """Manually trigger audit for a project."""
    project_resp = supabase.table("projects").select("id").eq("id", job.project_id).execute()
    if not project_resp.data:
        raise HTTPException(status_code=404, detail="Project not found")
    thread = threading.Thread(target=process_audit, args=(job.project_id,), daemon=True)
    thread.start()
    return {"success": True, "message": f"Sanity audit started for {job.project_id}"}


@app.post("/agents/sanity/approve")
async def approve_sanity_actions(req: SanityApprovalRequest):
    """
    Receive user-approved actions and advance to fix phase.
    Called from frontend via MCP server.
    """
    project_resp = supabase.table("projects").select("*").eq("id", req.project_id).execute()
    if not project_resp.data:
        raise HTTPException(status_code=404, detail="Project not found")

    project = project_resp.data[0]
    if project["status"] != "pending_sanity_review":
        raise HTTPException(status_code=400, detail=f"Project status is '{project['status']}', expected 'pending_sanity_review'")

    metadata = project.get("metadata", {}) or {}
    metadata["sanity_actions"] = req.actions

    # Check if any action is approved
    any_approved = any(v for v in req.actions.values())

    if any_approved:
        # Advance to fix phase
        supabase.table("projects").update({
            "metadata": metadata,
            "status": "pending_sanity_fix",
            "updated_at": datetime.now(UTC).isoformat(),
        }).eq("id", req.project_id).execute()
        log_to_supabase(req.project_id, f"User approved actions: {req.actions}", "info")
        return {"success": True, "message": "Fix phase triggered", "status": "pending_sanity_fix"}
    else:
        # Skip all — go straight to training config
        supabase.table("projects").update({
            "metadata": metadata,
            "status": "pending_training_config",
            "updated_at": datetime.now(UTC).isoformat(),
        }).eq("id", req.project_id).execute()
        log_to_supabase(req.project_id, "User skipped all fixes — advancing to training config", "info")
        return {"success": True, "message": "Skipped fixes — advancing to training config", "status": "pending_training_config"}


@app.get("/agents/sanity/status/{project_id}")
async def get_sanity_status(project_id: str):
    logs_resp = (
        supabase.table("agent_logs").select("*")
        .eq("project_id", project_id).eq("agent_name", AGENT_NAME)
        .order("created_at", desc=True).limit(20).execute()
    )
    project_resp = supabase.table("projects").select("metadata").eq("id", project_id).execute()
    sanity_report = None
    if project_resp.data:
        metadata = project_resp.data[0].get("metadata", {}) or {}
        sanity_report = metadata.get("sanity_report")
    return {"logs": logs_resp.data, "sanity_report": sanity_report}


@app.get("/health")
async def health_check():
    return {"status": "healthy", "agent": AGENT_NAME, "version": "2.0", "auto_polling": polling_active}


@app.post("/agents/sanity/polling/start")
async def start_polling():
    global polling_active
    if polling_active:
        return {"success": False, "message": "Already active"}
    polling_active = True
    thread = threading.Thread(target=poll_pending_projects, daemon=True)
    thread.start()
    return {"success": True, "message": "Polling started"}


@app.post("/agents/sanity/polling/stop")
async def stop_polling():
    global polling_active
    polling_active = False
    return {"success": True, "message": "Polling stopped"}


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
