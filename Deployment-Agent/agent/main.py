import os
import io
import time
import json
import zipfile
import asyncio
import httpx
import tempfile
import urllib.parse
from datetime import datetime, timezone
from typing import Dict, Any, List

from fastapi import FastAPI, BackgroundTasks, HTTPException
from supabase import create_client, Client
from google.cloud import storage

# Environment variables
from dotenv import load_dotenv
load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
GCP_CREDENTIALS = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
GCP_BUCKET_NAME = os.environ.get("GCP_BUCKET_NAME")

if not all([SUPABASE_URL, SUPABASE_KEY, GCP_CREDENTIALS, GCP_BUCKET_NAME]):
    print("Warning: Missing environment variables. Please check .env file.")

# Initialize clients
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
storage_client = storage.Client.from_service_account_json(GCP_CREDENTIALS)

app = FastAPI(title="Deployment Agent", port=8007)

AGENT_NAME = "deployment"


def log_to_supabase(project_id: str, message: str, level: str = "info"):
    try:
        supabase.table("agent_logs").insert({
            "project_id": project_id,
            "agent_name": AGENT_NAME,
            "message": message,
            "log_level": level
        }).execute()
    except Exception as e:
        print(f"Failed to log to Supabase: {e}")


def send_chat_message(user_id: str, message: str, sender: str = "Deployment Agent"):
    try:
        supabase.table("chat_messages").insert({
            "user_id": user_id,
            "message": message,
            "sender": sender,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }).execute()
    except Exception as e:
        print(f"Failed to send chat message: {e}")


def download_from_gcs(gcs_url: str, dest_path: str):
    parsed = urllib.parse.urlparse(gcs_url)
    bucket_name = parsed.netloc
    blob_path = parsed.path.lstrip('/')
    
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(blob_path)
    blob.download_to_filename(dest_path)


def upload_to_gcs(local_path: str, destination_blob_name: str) -> str:
    bucket = storage_client.bucket(GCP_BUCKET_NAME)
    blob = bucket.blob(destination_blob_name)
    blob.upload_from_filename(local_path)
    return f"gs://{GCP_BUCKET_NAME}/{destination_blob_name}"


def generate_docker_compose(project_name: str) -> str:
    # Create a safe service name
    service_name = project_name.lower().replace(" ", "-").replace("_", "-")
    import re
    service_name = re.sub(r'[^a-z0-9-]', '', service_name)
    if not service_name:
        service_name = "ml-model-service"
        
    return f"""version: '3.8'

services:
  {service_name}:
    build: .
    container_name: {service_name}
    ports:
      - "8000:8000"
    restart: unless-stopped
    environment:
      - MODEL_ENV=production
"""

def generate_dockerfile() -> str:
    return """FROM python:3.10-slim

WORKDIR /app

# Install system dependencies for OpenCV/PIL if needed
RUN apt-get update && apt-get install -y libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
"""


def generate_requirements() -> str:
    return """fastapi>=0.100.0
uvicorn[standard]>=0.23.0
python-multipart>=0.0.6
torch>=2.0.0 --index-url https://download.pytorch.org/whl/cpu
torchvision>=0.15.0 --index-url https://download.pytorch.org/whl/cpu
pillow>=10.0.0
"""


def generate_app_py(model_architecture: str, num_classes: int, class_labels: List[str]) -> str:
    labels_json = json.dumps(class_labels)
    
    return f"""import os
import io
import json
import torch
import torch.nn as nn
from torchvision import models, transforms
from PIL import Image
from fastapi import FastAPI, UploadFile, File, HTTPException

app = FastAPI(title="AutoML Deployed Model")

MODEL_ARCHITECTURE = "{model_architecture}"
NUM_CLASSES = {num_classes}
CLASS_LABELS = {labels_json}

device = torch.device("cpu")
model = None

transform = transforms.Compose([
    transforms.Resize(256),
    transforms.CenterCrop(224),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
])

@app.on_event("startup")
def load_model():
    global model
    if MODEL_ARCHITECTURE == "resnet18":
        model = models.resnet18(weights=None)
        model.fc = nn.Linear(model.fc.in_features, NUM_CLASSES)
    elif MODEL_ARCHITECTURE == "resnet50":
        model = models.resnet50(weights=None)
        model.fc = nn.Linear(model.fc.in_features, NUM_CLASSES)
    elif MODEL_ARCHITECTURE == "efficientnet_b0":
        model = models.efficientnet_b0(weights=None)
        model.classifier[1] = nn.Linear(model.classifier[1].in_features, NUM_CLASSES)
    elif MODEL_ARCHITECTURE == "mobilenet_v2":
        model = models.mobilenet_v2(weights=None)
        model.classifier[1] = nn.Linear(model.classifier[1].in_features, NUM_CLASSES)
    else:
        model = models.resnet18(weights=None)
        model.fc = nn.Linear(model.fc.in_features, NUM_CLASSES)
    model.load_state_dict(torch.load("model.pth", map_location=device))
    model.eval()

@app.get("/")
def health_check():
    return {{"status": "healthy", "model": MODEL_ARCHITECTURE}}

@app.post("/predict")
async def predict(file: UploadFile = File(...)):
    if not model:
        raise HTTPException(status_code=503, detail="Model not loaded")
    try:
        contents = await file.read()
        image = Image.open(io.BytesIO(contents)).convert('RGB')
        img_tensor = transform(image).unsqueeze(0).to(device)
        with torch.no_grad():
            outputs = model(img_tensor)
            probabilities = torch.nn.functional.softmax(outputs, dim=1)
            confidence, predicted = torch.max(probabilities, 1)
        class_idx = predicted.item()
        class_name = CLASS_LABELS[class_idx] if class_idx < len(CLASS_LABELS) else f"Class_{{class_idx}}"
        return {{"success": True, "prediction": class_name, "confidence": confidence.item()}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
"""


def generate_sklearn_requirements() -> str:
    return """fastapi>=0.100.0
uvicorn[standard]>=0.23.0
scikit-learn>=1.3.0
xgboost>=2.0.0
numpy>=1.24.0,<2.0.0
"""


def generate_sklearn_dockerfile() -> str:
    return """FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
"""


def generate_tabular_app_py(feature_names: list, class_labels: list, target_col: str, task_type: str) -> str:
    features_json = json.dumps(feature_names)
    labels_json = json.dumps(class_labels)

    return f"""import pickle
import json
import numpy as np
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, Any

app = FastAPI(title="AutoML Deployed Model — Tabular")

FEATURE_NAMES = {features_json}
CLASS_LABELS = {labels_json}
TARGET_COLUMN = "{target_col}"
TASK_TYPE = "{task_type}"

# Load model
with open("model.pkl", "rb") as f:
    model = pickle.load(f)

class PredictionInput(BaseModel):
    features: Dict[str, Any]

@app.get("/")
def health_check():
    return {{"status": "healthy", "task_type": TASK_TYPE, "features": FEATURE_NAMES}}

@app.post("/predict")
async def predict(data: PredictionInput):
    try:
        X = np.array([[float(data.features.get(f, 0)) for f in FEATURE_NAMES]])
        prediction = model.predict(X)[0]
        
        result = {{"success": True}}
        
        if TASK_TYPE.endswith("regression"):
            result["prediction"] = float(prediction)
        else:
            result["prediction"] = int(prediction)
            if CLASS_LABELS:
                result["label"] = CLASS_LABELS[int(prediction)]
            
            if hasattr(model, "predict_proba"):
                proba = model.predict_proba(X)[0]
                result["probabilities"] = {{
                    CLASS_LABELS[i] if i < len(CLASS_LABELS) else str(i): round(float(p), 4)
                    for i, p in enumerate(proba)
                }}
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
"""


def generate_text_app_py(class_labels: list) -> str:
    labels_json = json.dumps(class_labels)

    return f"""import pickle
import json
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="AutoML Deployed Model — Text Classification")

CLASS_LABELS = {labels_json}

# Load pipeline (TF-IDF + Classifier)
with open("model.pkl", "rb") as f:
    model = pickle.load(f)

class TextInput(BaseModel):
    text: str

@app.get("/")
def health_check():
    return {{"status": "healthy", "task_type": "text_classification", "labels": CLASS_LABELS}}

@app.post("/predict")
async def predict(data: TextInput):
    try:
        prediction = model.predict([data.text])[0]
        label = CLASS_LABELS[int(prediction)] if int(prediction) < len(CLASS_LABELS) else str(prediction)
        
        result = {{
            "success": True,
            "prediction": int(prediction),
            "label": label
        }}
        
        if hasattr(model, "predict_proba"):
            proba = model.predict_proba([data.text])[0]
            result["confidence"] = round(float(max(proba)), 4)
            result["probabilities"] = {{
                CLASS_LABELS[i] if i < len(CLASS_LABELS) else str(i): round(float(p), 4)
                for i, p in enumerate(proba)
            }}
        elif hasattr(model, "decision_function"):
            scores = model.decision_function([data.text])
            if len(scores.shape) == 1:
                import math
                result["confidence"] = round(1 / (1 + math.exp(-abs(scores[0]))), 4)
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
"""


def process_pending_deployment(project_id: str):
    print(f"\n[DEPLOYMENT] Starting deployment packaging for {project_id}...")
    try:
        project_resp = supabase.table("projects").select("*, users(*)").eq("id", project_id).execute()
        if not project_resp.data:
            return
            
        project = project_resp.data[0]
        user_id = project["user_id"]
        project_name = project["name"]
        metadata = project.get("metadata", {}) or {}
        task_type = project.get("task_type", "image_classification")
        
        # Get Model
        model_resp = supabase.table("models").select("*").eq("project_id", project_id).execute()
        if not model_resp.data:
            raise Exception("No trained model found to deploy.")
            
        model_data = model_resp.data[0]
        model_gcs_url = model_data.get("gcs_url")
        model_meta = model_data.get("metadata", {})
        
        model_architecture = model_meta.get("architecture", metadata.get("preferred_model", "resnet18"))
        num_classes = model_meta.get("num_classes", 2)
        class_labels = model_meta.get("class_labels", [f"Class_{i}" for i in range(num_classes)])
        feature_names = model_meta.get("feature_names", [])
        target_col = model_meta.get("target_column", "")
        
        # Normalize architecture aliases (as in MCP server)
        model_aliases = {
            "efficientnet": "efficientnet_b0",
            "mobilenet": "mobilenet_v2",
            "resnet": "resnet18"
        }
        model_architecture = model_aliases.get(model_architecture.lower(), model_architecture.lower())
        
        log_to_supabase(project_id, f"Generating deployment package (task_type={task_type})...", "info")
        send_chat_message(user_id, "🐳 Packaging your AI model into a production-ready Docker container...")
        
        with tempfile.TemporaryDirectory() as temp_dir:
            # Download bundle or model
            bundle_url = model_meta.get("bundle_url") or metadata.get("bundle_url")
            if bundle_url:
                log_to_supabase(project_id, f"Downloading evaluation bundle from {bundle_url}...", "info")
                bundle_path = os.path.join(temp_dir, "bundle.zip")
                download_from_gcs(bundle_url, bundle_path)
                with zipfile.ZipFile(bundle_path, 'r') as zf:
                    zf.extractall(temp_dir)
                os.remove(bundle_path)
            else:
                # Download model directly
                if task_type in ("tabular_classification", "tabular_regression", "text_classification"):
                    model_path = os.path.join(temp_dir, "model.pkl")
                else:
                    model_path = os.path.join(temp_dir, "model.pth")
                log_to_supabase(project_id, f"Downloading model from {model_gcs_url}...", "info")
                download_from_gcs(model_gcs_url, model_path)
            
            # Generate deployment files based on task type
            if task_type in ("tabular_classification", "tabular_regression"):
                dockerfile_content = generate_sklearn_dockerfile()
                requirements_content = generate_sklearn_requirements()
                app_content = generate_tabular_app_py(feature_names, class_labels, target_col, task_type)
            elif task_type == "text_classification":
                dockerfile_content = generate_sklearn_dockerfile()
                requirements_content = generate_sklearn_requirements()
                app_content = generate_text_app_py(class_labels)
            else:
                # Image classification (original)
                dockerfile_content = generate_dockerfile()
                requirements_content = generate_requirements()
                app_content = generate_app_py(model_architecture, num_classes, class_labels)
            
            docker_compose_content = generate_docker_compose(project_name)
            
            with open(os.path.join(temp_dir, "Dockerfile"), "w") as f:
                f.write(dockerfile_content)
                
            with open(os.path.join(temp_dir, "requirements.txt"), "w") as f:
                f.write(requirements_content)
                
            with open(os.path.join(temp_dir, "app.py"), "w") as f:
                f.write(app_content)
                
            with open(os.path.join(temp_dir, "docker-compose.yml"), "w") as f:
                f.write(docker_compose_content)
                
            log_to_supabase(project_id, "Zipping Docker container files...", "info")
            
            zip_filename = f"{project_name.replace(' ', '_')}_deployment.zip"
            zip_path = os.path.join(tempfile.gettempdir(), zip_filename)
            
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                for root, _, files in os.walk(temp_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, temp_dir)
                        zf.write(file_path, arcname)
                
            log_to_supabase(project_id, "Uploading deployment package to GCP...", "info")
            gcs_dest_path = f"deployments/{project_id}/{zip_filename}"
            deployment_url = upload_to_gcs(zip_path, gcs_dest_path)
            
            # Cleanup
            if os.path.exists(zip_path):
                os.remove(zip_path)
                
            metadata["deployment_url"] = deployment_url
            
            # Transition to completed
            supabase.table("projects").update({
                "status": "completed",
                "metadata": metadata,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }).eq("id", project_id).execute()
            
            log_to_supabase(project_id, f"Deployment package ready: {deployment_url}", "info")
            send_chat_message(user_id, f"✅ Done! Your model is fully trained and deployed. You can download the Docker deployment package now.")
            
    except Exception as e:
        print(f"[DEPLOYMENT ERROR] {e}")
        log_to_supabase(project_id, f"Deployment failed: {e}", "error")
        supabase.table("projects").update({"status": "failed"}).eq("id", project_id).execute()
        send_chat_message(user_id, f"❌ Deployment failed: {e}")


async def poll_supabase():
    print("Deployment Agent polling started...")
    while True:
        try:
            resp = supabase.table("projects").select("id").eq("status", "pending_deployment").execute()
            
            if resp.data:
                for proj in resp.data:
                    proj_id = proj["id"]
                    # Mark as deploying to prevent double-processing
                    supabase.table("projects").update({
                        "status": "deploying",
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }).eq("id", proj_id).execute()
                    
                    process_pending_deployment(proj_id)
        except Exception as e:
            print(f"Polling error: {e}")
            
        await asyncio.sleep(5)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(poll_supabase())

@app.get("/health")
def health_check():
    return {"status": "healthy", "agent": "Deployment Agent"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8007, reload=True)
