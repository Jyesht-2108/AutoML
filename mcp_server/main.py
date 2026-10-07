import os
import sys
import logging
from fastapi import FastAPI, HTTPException, Form, File, UploadFile, Request
from pydantic import BaseModel
from pydantic_settings import BaseSettings

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))

from tools import user_tools, chat_tools
from ai_client import generate_from_prompt
from supabase_client import init_supabase

class Settings(BaseSettings):
    GEMINI_API_KEY: str
    SUPABASE_URL: str
    SUPABASE_SERVICE_ROLE_KEY: str
    PLANNER_AGENT_URL: str = "http://127.0.0.1:8001"
    DATASET_AGENT_URL: str = "http://127.0.0.1:8002"
    TRAINING_AGENT_URL: str = "http://127.0.0.1:8003"
    SANITY_AGENT_URL: str = "http://127.0.0.1:8004"
    PRIVACY_AGENT_URL: str = "http://127.0.0.1:8005"
    GOOGLE_APPLICATION_CREDENTIALS: str = ""
    GCP_BUCKET_NAME: str = ""
    PORT: int = 8000

    class Config:
        env_file = ".env"
        extra = "ignore"  # Ignore extra fields in .env

settings = Settings()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

@app.on_event("startup")
async def startup_event():
    init_supabase(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)

class ChatRequest(BaseModel):
    user_id: str
    message: str
    metadata: dict | None = None
    user_name: str | None = None
    user_email: str | None = None

@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.post("/mcp/query")
async def mcp_query(request: ChatRequest):
    user_id = request.user_id
    user_message = request.message
    user_name = request.user_name
    user_email = request.user_email
    logger.info(f"Received chat request from user {user_id} (name: {user_name}, email: {user_email})")

    try:
        # 1. Get or create user profile with name/email
        logger.info("Getting/creating user profile...")
        logger.info(f"Calling get_user_profile with: firebase_uid={user_id}, email={user_email}, name={user_name}")
        user = user_tools.get_user_profile(user_id, user_email, user_name)
        logger.info(f"User profile result: {user}")

        # 2. Get chat history
        logger.info("Getting chat history...")
        chat_history = chat_tools.get_chat_history(user_id)
        logger.info(f"Chat history: {chat_history}")
        print(f"DEBUG: MCP server returning chat history: {chat_history}")

        # 3. Generate response with user context
        logger.info("Generating AI response...")
        assistant_response = generate_from_prompt(user_message, chat_history, user_name)
        logger.info(f"Assistant response generated successfully")

        # 4. Store messages
        logger.info("Storing user message...")
        chat_tools.store_message(user_id, "user", user_message)
        logger.info("Storing assistant message...")
        chat_tools.store_message(user_id, "assistant", assistant_response)
        logger.info("Messages stored successfully")

        # 5. Return response
        return {"reply": assistant_response}
    except Exception as e:
        logger.error(f"Error processing chat request for user {user_id}: {str(e)}")
        logger.error(f"Error type: {type(e).__name__}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/mcp/history")
async def mcp_history(user_id: str):
    logger.info(f"Fetching chat history for user {user_id}")
    try:
        chat_history = chat_tools.get_chat_history(user_id)
        return chat_history
    except Exception as e:
        logger.error(f"Error fetching chat history for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.delete("/mcp/clear-chat")
async def mcp_clear_chat(user_id: str):
    logger.info(f"Clearing chat history for user {user_id}")
    try:
        result = chat_tools.clear_chat_history(user_id)
        logger.info(f"Successfully cleared chat history for user {user_id}")
        return {"message": "Chat history cleared successfully", "result": result}
    except Exception as e:
        logger.error(f"Error clearing chat history for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

# ============= ML Project Endpoints =============

class MLProjectRequest(BaseModel):
    user_id: str
    message: str
    user_name: str | None = None
    user_email: str | None = None

@app.post("/api/ml/planner")
async def ml_planner(request: MLProjectRequest):
    """
    Planner Agent endpoint - Creates ML project from user description
    """
    logger.info(f"ML Planner request from user {request.user_id}: {request.message}")
    
    try:
        import httpx
        
        # Call the Planner Agent service
        planner_url = settings.PLANNER_AGENT_URL
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{planner_url}/agents/planner/handle_message",
                json={
                    "user_id": request.user_id,
                    "session_id": request.user_id,  # Using user_id as session_id for now
                    "message_text": request.message
                }
            )
            
            if response.status_code != 200:
                logger.error(f"Planner Agent error: {response.text}")
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Planner Agent error: {response.text}"
                )
            
            result = response.json()
            project_id = result.get('project_id')
            
            logger.info(f"Planner Agent created project {project_id} for user {request.user_id}")
            
            # Dataset Agent auto-polling is enabled, so no need to manually trigger
            # The agent will automatically pick up projects with status='pending_dataset'
            logger.info(f"Project {project_id} created. Dataset Agent will auto-process it.")
            
            return {
                "reply": result.get("message", "Project created successfully!"),
                "projectId": project_id,
                "status": "pending_dataset",
                "plan": result.get("plan")
            }
            
    except httpx.RequestError as e:
        logger.error(f"Failed to connect to Planner Agent: {str(e)}")
        raise HTTPException(
            status_code=503,
            detail=f"Planner Agent service unavailable. Make sure it's running on port 8001. Error: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Error in ML Planner: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))

def get_user_uuid_from_firebase_uid(firebase_uid: str) -> str:
    """Convert Firebase UID to User UUID from database"""
    from supabase_client import get_supabase_client
    supabase = get_supabase_client()
    
    result = supabase.table("users").select("id").eq("firebase_uid", firebase_uid).execute()
    
    if result.data and len(result.data) > 0:
        return result.data[0]["id"]
    
    # User doesn't exist, create new one
    new_user = supabase.table("users").insert({
        "firebase_uid": firebase_uid
    }).execute()
    
    return new_user.data[0]["id"]


@app.get("/api/ml/projects")
async def get_ml_projects(user_id: str, all: str = "false"):
    """
    Get all ML projects for a user.
    If all=true and user is admin, returns projects from all users.
    """
    logger.info(f"Fetching ML projects for user {user_id} (all={all})")
    
    try:
        from supabase_client import get_supabase_client
        supabase = get_supabase_client()
        
        # Convert Firebase UID to User UUID
        user_uuid = get_user_uuid_from_firebase_uid(user_id)
        
        # If requesting all projects, check admin status
        if all.lower() == "true":
            user = supabase.table("users").select("is_admin").eq("id", user_uuid).execute()
            is_admin = user.data and user.data[0].get("is_admin", False)
            
            if is_admin:
                logger.info(f"Admin user {user_id} fetching all projects")
                # Fetch all projects with owner info
                result = supabase.table("projects").select("*, users(email, name)").order("created_at", desc=True).execute()
                
                projects = result.data if result.data else []
                # Flatten user info into project for easier frontend consumption
                for project in projects:
                    user_info = project.pop("users", None)
                    if user_info:
                        project["owner_email"] = user_info.get("email", "Unknown")
                        project["owner_name"] = user_info.get("name", "")
                    else:
                        project["owner_email"] = "Unknown"
                        project["owner_name"] = ""
                
                logger.info(f"Admin: Found {len(projects)} total projects")
                return {"projects": projects}
            else:
                logger.warning(f"Non-admin user {user_id} attempted to fetch all projects")
        
        # Default: fetch only user's own projects
        result = supabase.table("projects").select("*").eq("user_id", user_uuid).order("created_at", desc=True).execute()
        
        projects = result.data if result.data else []
        logger.info(f"Found {len(projects)} projects for user {user_id}")
        
        return {"projects": projects}
    except Exception as e:
        logger.error(f"Error fetching ML projects: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.patch("/api/ml/projects/{project_id}/status")
async def update_project_status(project_id: str, request: Request):
    try:
        from supabase_client import get_supabase_client
        supabase = get_supabase_client()
        
        body = await request.json()
        new_status = body.get("status")
        
        if not new_status:
            raise HTTPException(status_code=400, detail="Status is required")
            
        supabase.table("projects").update({"status": new_status}).eq("id", project_id).execute()
        return {"success": True, "status": new_status}
    except Exception as e:
        logger.error(f"Error updating project status: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/ml/projects/{project_id}/ai-insights")
async def get_ai_insights(project_id: str):
    """
    Generate AI-powered insights by feeding full project context to Gemini.
    Gathers: project metadata, metrics, agent logs, training config, sanity/privacy results.
    Returns: structured LLM analysis with suggestions.
    """
    try:
        from supabase_client import get_supabase_client
        import json as json_lib
        supabase = get_supabase_client()

        # 1. Fetch project
        project = supabase.table("projects").select("*").eq("id", project_id).execute()
        if not project.data:
            raise HTTPException(status_code=404, detail="Project not found")
        project_data = project.data[0]

        # 2. Fetch model record
        model_record = supabase.table("models").select("*").eq("project_id", project_id).execute()
        model_data = model_record.data[0] if model_record.data else {}

        # 3. Fetch agent logs (last 100)
        logs = supabase.table("agent_logs").select("agent_name, message, log_level, created_at").eq("project_id", project_id).order("created_at", desc=False).limit(100).execute()
        log_entries = logs.data if logs.data else []

        # 4. Build context
        metadata = project_data.get("metadata") or {}
        metrics = metadata.get("metrics") or metadata.get("evaluation_metrics") or {}
        feature_importance = metadata.get("feature_importance") or {}
        sanity_report = metadata.get("sanity_report") or {}
        privacy_report = metadata.get("privacy_report") or {}
        training_config = {
            "preferred_model": metadata.get("preferred_model"),
            "epochs": metadata.get("epochs"),
            "learning_rate": metadata.get("learning_rate"),
            "batch_size": metadata.get("batch_size"),
            "optimizer": metadata.get("optimizer"),
        }

        # Format logs for LLM
        log_summary = "\n".join([
            f"[{l.get('agent_name','?')}] ({l.get('log_level','info')}) {l.get('message','')}"
            for l in log_entries[-50:]  # Last 50 logs
        ])

        context_prompt = f"""You are an expert ML engineer reviewing an AutoML pipeline run. Analyze everything below and provide actionable insights.

## Project Info
- Name: {project_data.get('name')}
- Task Type: {project_data.get('task_type')}
- Framework: {project_data.get('framework', 'PyTorch')}
- Current Status: {project_data.get('status')}

## Training Configuration Used
{json_lib.dumps(training_config, indent=2)}

## Evaluation Metrics
{json_lib.dumps(metrics, indent=2)}

## Feature Importance (if tabular)
{json_lib.dumps(dict(list(feature_importance.items())[:15]), indent=2) if feature_importance else "N/A"}

## Sanity Agent Report
{json_lib.dumps(sanity_report, indent=2) if sanity_report else "No sanity issues found."}

## Privacy Agent Report
{json_lib.dumps(privacy_report, indent=2) if privacy_report else "No privacy issues found."}

## Agent Activity Log (chronological)
{log_summary if log_summary else "No logs available."}

## Model Record
- Architecture: {model_data.get('metadata', {}).get('architecture', 'unknown') if model_data else 'N/A'}
- Accuracy: {model_data.get('accuracy', 'N/A') if model_data else 'N/A'}

---

Based on ALL of the above context, respond in the following JSON format ONLY (no markdown, no code fences, just raw JSON):
{{
  "overall_verdict": "deploy" or "retrain" or "investigate",
  "confidence_in_verdict": "high" or "medium" or "low",
  "summary": "2-3 sentence executive summary of the model's performance and pipeline health",
  "metrics_analysis": "Detailed interpretation of accuracy, precision, recall, F1. Which classes are weak? Is there class imbalance?",
  "data_quality_analysis": "Analysis of what the sanity and privacy agents found. Were there data issues that could affect model quality?",
  "training_analysis": "Was the training config appropriate? Were enough epochs used? Is the learning rate suitable?",
  "strengths": ["strength 1", "strength 2", ...],
  "weaknesses": ["weakness 1", "weakness 2", ...],
  "retrain_suggestions": {{
    "preferred_model": "suggested model architecture or null",
    "epochs": suggested_number_or_null,
    "learning_rate": suggested_lr_or_null,
    "batch_size": suggested_bs_or_null,
    "reasoning": "Why these specific parameters would improve results"
  }},
  "next_steps": ["actionable step 1", "actionable step 2", ...]
}}"""

        # Call Gemini
        import google.generativeai as genai
        genai.configure(api_key=settings.GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-3.5-flash')
        response = await model.generate_content_async(context_prompt)
        raw_text = response.text.strip()

        # Parse JSON from response (handle markdown code fences)
        if raw_text.startswith("```"):
            # Strip ```json ... ```
            lines = raw_text.split("\n")
            raw_text = "\n".join(lines[1:-1])
        
        try:
            insights = json_lib.loads(raw_text)
        except json_lib.JSONDecodeError:
            # Fallback: return raw text as summary
            insights = {
                "overall_verdict": "investigate",
                "confidence_in_verdict": "low",
                "summary": raw_text[:500],
                "metrics_analysis": "Could not parse structured response.",
                "data_quality_analysis": "",
                "training_analysis": "",
                "strengths": [],
                "weaknesses": [],
                "retrain_suggestions": {},
                "next_steps": ["Review the raw AI analysis above."]
            }

        # Save insights to database
        metadata["ai_insights"] = insights
        supabase.table("projects").update({"metadata": metadata}).eq("id", project_id).execute()

        return {"success": True, "insights": insights}

    except Exception as e:
        logger.error(f"Error generating AI insights: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/ml/projects/{project_id}")
async def get_ml_project(project_id: str, user_id: str):
    """
    Get specific ML project details
    """
    logger.info(f"Fetching project {project_id} for user {user_id}")
    
    try:
        from supabase_client import get_supabase_client
        supabase = get_supabase_client()
        
        # Convert Firebase UID to User UUID
        user_uuid = get_user_uuid_from_firebase_uid(user_id)
        
        result = supabase.table("projects").select("*").eq("id", project_id).eq("user_id", user_uuid).execute()
        
        if not result.data:
            raise HTTPException(status_code=404, detail="Project not found")
        
        project = result.data[0]
        
        # Also fetch related datasets and models
        datasets = supabase.table("datasets").select("*").eq("project_id", project_id).execute()
        models = supabase.table("models").select("*").eq("project_id", project_id).execute()
        
        project["datasets"] = datasets.data if datasets.data else []
        project["models"] = models.data if models.data else []
        
        return {"project": project}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching project: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/ml/projects/{project_id}/logs")
async def get_project_logs(project_id: str, user_id: str):
    """
    Get agent logs for a project
    """
    logger.info(f"Fetching logs for project {project_id}")
    
    try:
        from supabase_client import get_supabase_client
        supabase = get_supabase_client()
        
        # Convert Firebase UID to User UUID
        user_uuid = get_user_uuid_from_firebase_uid(user_id)
        
        # Verify project belongs to user
        project = supabase.table("projects").select("id").eq("id", project_id).eq("user_id", user_uuid).execute()
        if not project.data:
            raise HTTPException(status_code=404, detail="Project not found")
        
        logs = supabase.table("agent_logs").select("*").eq("project_id", project_id).order("created_at", desc=False).execute()
        
        return {"logs": logs.data if logs.data else []}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching logs: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/ml/projects/{project_id}/download")
async def download_model(project_id: str, user_id: str):
    """
    Download trained model bundle from GCP
    """
    logger.info(f"Download request for project {project_id}")
    
    try:
        from supabase_client import get_supabase_client
        from fastapi.responses import StreamingResponse
        from google.cloud import storage
        import io
        
        supabase = get_supabase_client()
        
        # Convert Firebase UID to User UUID
        user_uuid = get_user_uuid_from_firebase_uid(user_id)
        
        # Check if user is admin
        user = supabase.table("users").select("is_admin").eq("id", user_uuid).execute()
        is_admin = user.data and user.data[0].get("is_admin", False)
        
        # Verify project and get bundle URL
        if is_admin:
            # Admin can download any project
            project = supabase.table("projects").select("*").eq("id", project_id).execute()
        else:
            # Regular user can only download their own projects
            project = supabase.table("projects").select("*").eq("id", project_id).eq("user_id", user_uuid).execute()
        
        if not project.data:
            raise HTTPException(status_code=404, detail="Project not found")
        
        project_data = project.data[0]
        if project_data["status"] not in ["completed", "export_ready"]:
            raise HTTPException(status_code=400, detail="Model not ready for download. Current status: " + project_data["status"])
        
        # Get model from models table
        model = supabase.table("models").select("*").eq("project_id", project_id).execute()
        
        if not model.data:
            raise HTTPException(status_code=404, detail="No trained model found for this project")
        
        model_data = model.data[0]
        model_url = model_data.get("gcs_url")
        
        if not model_url:
            raise HTTPException(status_code=404, detail="Model GCS URL not found")
        
        # Parse GCS URL (format: gs://bucket-name/path/to/file.pth)
        if not model_url.startswith("gs://"):
            raise HTTPException(status_code=400, detail="Invalid model URL format")
        
        # Extract bucket name
        # Extract bucket name from model_url as fallback
        gcs_path = model_url.replace("gs://", "")
        bucket_name = gcs_path.split("/")[0]
        
        # Determine the target download URL from metadata (priority: deployment > bundle > raw model)
        metadata = project_data.get("metadata", {}) or {}
        target_gcs_url = metadata.get("deployment_url") or metadata.get("bundle_url") or model_url
        
        target_path = target_gcs_url.replace("gs://", "")
        target_bucket_name = target_path.split("/")[0]
        target_blob_path = "/".join(target_path.split("/")[1:])
        
        logger.info(f"Targeting download URL: {target_gcs_url}")
        
        # Download from GCP with explicit credentials
        gcp_credentials_path = settings.GOOGLE_APPLICATION_CREDENTIALS
        logger.info(f"GCP credentials path: {gcp_credentials_path}")
        
        if gcp_credentials_path and gcp_credentials_path.strip():
            logger.info(f"Using credentials from settings: {gcp_credentials_path}")
            
            if os.path.exists(gcp_credentials_path):
                logger.info("Credentials file found, using explicit authentication")
                storage_client = storage.Client.from_service_account_json(gcp_credentials_path)
            else:
                logger.error(f"Credentials file not found at: {gcp_credentials_path}")
                raise HTTPException(status_code=500, detail=f"GCP credentials file not found at: {gcp_credentials_path}")
        else:
            logger.error("GOOGLE_APPLICATION_CREDENTIALS not set in .env file")
            raise HTTPException(status_code=500, detail="GCP credentials not configured in .env file")
        
        bucket = storage_client.bucket(target_bucket_name)
        
        blob = bucket.blob(target_blob_path)
        if not blob.exists():
            raise HTTPException(status_code=404, detail=f"File not found in GCP storage: {target_blob_path}")
            
        filename = blob.name.split("/")[-1]
        
        if filename.endswith('.zip'):
            content_type = "application/zip"
        else:
            content_type = "application/octet-stream"
            if not filename.endswith('.pth'):
                project_name_clean = project_data.get('name', 'model').replace(' ', '_')
                filename = f"{project_name_clean}_model.pth"
        
        # Generate a Signed URL instead of downloading to memory
        import datetime
        signed_url = blob.generate_signed_url(
            version="v4",
            expiration=datetime.timedelta(minutes=15),
            method="GET",
            response_disposition=f'attachment; filename="{filename}"'
        )
        
        logger.info(f"Generated signed URL for: {filename}")
        
        return {"download_url": signed_url}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading model: {str(e)}")
        import traceback
        error_trace = traceback.format_exc()
        logger.error(f"Full traceback:\n{error_trace}")
        raise HTTPException(status_code=500, detail=f"Download failed: {str(e)}")

@app.get("/api/ml/projects/{project_id}/gradcam")
async def get_gradcam_url(project_id: str, user_id: str):
    try:
        from supabase_client import get_supabase_client
        supabase = get_supabase_client()
        
        project = supabase.table("projects").select("*").eq("id", project_id).execute()
        if not project.data:
            raise HTTPException(status_code=404, detail="Project not found")
        
        metadata = project.data[0].get("metadata") or {}
        gradcam_url = metadata.get("gradcam_preview_url")
        if not gradcam_url or not gradcam_url.startswith("gs://"):
            raise HTTPException(status_code=404, detail="No Grad-CAM preview found")
            
        gcs_path = gradcam_url.replace("gs://", "")
        bucket_name = gcs_path.split("/")[0]
        blob_path = "/".join(gcs_path.split("/")[1:])
        
        from google.cloud import storage
        gcp_credentials_path = settings.GOOGLE_APPLICATION_CREDENTIALS
        if gcp_credentials_path and gcp_credentials_path.strip() and os.path.exists(gcp_credentials_path):
            client = storage.Client.from_service_account_json(gcp_credentials_path)
        else:
            client = storage.Client()
            
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_path)
        
        import datetime
        signed_url = blob.generate_signed_url(
            version="v4",
            expiration=datetime.timedelta(minutes=60),
            method="GET",
        )
        return {"download_url": signed_url}
    except Exception as e:
        logger.error(f"Error getting Grad-CAM URL: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

class GradCAM:
    """Simple hook-based Grad-CAM implementation for PyTorch CNNs."""
    def __init__(self, model):
        self.model = model
        self.gradients = None
        self.activations = None
        import torch
        self.target_layer = self._find_target_layer(torch)
        if self.target_layer:
            self.target_layer.register_forward_hook(self.save_activation)
            self.target_layer.register_full_backward_hook(self.save_gradient)

    def _find_target_layer(self, torch):
        target = None
        for module in self.model.modules():
            if isinstance(module, torch.nn.Conv2d):
                target = module
        return target

    def save_activation(self, module, input, output):
        self.activations = output

    def save_gradient(self, module, grad_input, grad_output):
        self.gradients = grad_output[0]

    def generate(self, input_tensor, target_class=None):
        if not self.target_layer:
            return None
            
        import numpy as np
        self.model.zero_grad()
        output = self.model(input_tensor)
        
        if target_class is None:
            target_class = output.argmax(dim=1).item()
            
        target = output[0, target_class]
        target.backward()
        
        gradients = self.gradients.detach().cpu().numpy()[0]
        activations = self.activations.detach().cpu().numpy()[0]
        
        weights = np.mean(gradients, axis=(1, 2))
        
        cam = np.zeros(activations.shape[1:], dtype=np.float32)
        for i, w in enumerate(weights):
            cam += w * activations[i]
            
        cam = np.maximum(cam, 0)
        if np.max(cam) > 0:
            cam = cam - np.min(cam)
            cam = cam / np.max(cam)
        return cam

@app.post("/api/ml/projects/{project_id}/test")
async def test_model(project_id: str, user_id: str = Form(...), file: UploadFile = File(...)):
    """
    Test model with uploaded image
    """
    logger.info(f"Test request for project {project_id}")
    
    try:
        from supabase_client import get_supabase_client
        from google.cloud import storage
        from PIL import Image
        import io
        import torch
        import torch.nn as nn
        from torchvision import models, transforms
        import json
        
        supabase = get_supabase_client()
        
        # Convert Firebase UID to User UUID
        user_uuid = get_user_uuid_from_firebase_uid(user_id)
        
        # Check if user is admin
        user_check = supabase.table("users").select("is_admin").eq("id", user_uuid).execute()
        is_admin = user_check.data and user_check.data[0].get("is_admin", False)
        
        # Verify project ownership (admin can test any project)
        if is_admin:
            project = supabase.table("projects").select("*").eq("id", project_id).execute()
        else:
            project = supabase.table("projects").select("*").eq("id", project_id).eq("user_id", user_uuid).execute()
        if not project.data:
            raise HTTPException(status_code=404, detail="Project not found")
        
        project_data = project.data[0]
        
        # Get model info
        model_record = supabase.table("models").select("*").eq("project_id", project_id).execute()
        if not model_record.data:
            raise HTTPException(status_code=404, detail="No trained model found for this project")
        
        model_data = model_record.data[0]
        model_url = model_data.get("gcs_url")
        model_metadata = model_data.get("metadata", {})
        if model_metadata is None:
            model_metadata = {}
        model_architecture = model_metadata.get("architecture", "resnet18")
        num_classes = model_metadata.get("num_classes", 2)
        
        # Resolve model name aliases (matching Trainer-Agent's model_factory)
        model_aliases = {
            "efficientnet": "efficientnet_b0",
            "mobilenet": "mobilenet_v2",
            "resnet": "resnet18"
        }
        model_architecture = model_aliases.get(model_architecture.lower(), model_architecture.lower())
        
        logger.info(f"Loading model: {model_architecture} with {num_classes} classes")
        
        # Download model from GCP
        gcp_credentials_path = settings.GOOGLE_APPLICATION_CREDENTIALS
        if gcp_credentials_path and gcp_credentials_path.strip() and os.path.exists(gcp_credentials_path):
            storage_client = storage.Client.from_service_account_json(gcp_credentials_path)
        else:
            raise HTTPException(status_code=500, detail="GCP credentials not configured")
        
        # Parse GCS URL
        gcs_path = model_url.replace("gs://", "")
        bucket_name = gcs_path.split("/")[0]
        blob_path = "/".join(gcs_path.split("/")[1:])
        
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_path)
        
        # Download model to memory
        model_bytes = io.BytesIO()
        blob.download_to_file(model_bytes)
        model_bytes.seek(0)
        
        # Load model
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        logger.info(f"Using device: {device}")
        
        # Peek at state_dict keys to auto-detect architecture if metadata is wrong
        state_dict = torch.load(model_bytes, map_location=device)
        model_bytes.seek(0)  # Reset for potential re-read
        
        state_dict_keys = list(state_dict.keys())
        detected_architecture = None
        if any(k.startswith("features.") and "block" in k for k in state_dict_keys):
            # EfficientNet has keys like "features.X.Y.block..."
            if any("fc1" in k or "fc2" in k for k in state_dict_keys):
                detected_architecture = "efficientnet_b0"
            else:
                detected_architecture = "mobilenet_v2"
        elif any(k.startswith("layer") for k in state_dict_keys):
            # ResNet variants have keys like "layer1...", "layer2..."
            # Distinguish by number of parameters
            if any("layer4.1" in k for k in state_dict_keys):
                if any("layer4.2" in k for k in state_dict_keys):
                    detected_architecture = "resnet50"
                elif any("layer3.5" in k for k in state_dict_keys):
                    detected_architecture = "resnet34"
                else:
                    detected_architecture = "resnet18"
            else:
                detected_architecture = "resnet18"
        elif any(k.startswith("features.") for k in state_dict_keys):
            detected_architecture = "mobilenet_v2"
        
        if detected_architecture and detected_architecture != model_architecture:
            logger.warning(
                f"Architecture mismatch: metadata says '{model_architecture}' "
                f"but state_dict keys indicate '{detected_architecture}'. "
                f"Using detected architecture."
            )
            model_architecture = detected_architecture
        
        # Auto-detect num_classes from the output layer in state_dict
        detected_num_classes = None
        if "fc.weight" in state_dict:
            # ResNet: fc layer
            detected_num_classes = state_dict["fc.weight"].shape[0]
        elif "classifier.1.weight" in state_dict:
            # EfficientNet / MobileNet: classifier[1] layer
            detected_num_classes = state_dict["classifier.1.weight"].shape[0]
        
        if detected_num_classes and detected_num_classes != num_classes:
            logger.warning(
                f"num_classes mismatch: metadata says {num_classes} "
                f"but state_dict indicates {detected_num_classes}. "
                f"Using detected value."
            )
            num_classes = detected_num_classes
        
        # Create model architecture
        if model_architecture == "resnet18":
            model = models.resnet18(weights=None)
            model.fc = nn.Linear(model.fc.in_features, num_classes)
        elif model_architecture == "resnet34":
            model = models.resnet34(weights=None)
            model.fc = nn.Linear(model.fc.in_features, num_classes)
        elif model_architecture == "resnet50":
            model = models.resnet50(weights=None)
            model.fc = nn.Linear(model.fc.in_features, num_classes)
        elif model_architecture == "mobilenet_v2":
            model = models.mobilenet_v2(weights=None)
            model.classifier[1] = nn.Linear(model.classifier[1].in_features, num_classes)
        elif model_architecture == "efficientnet_b0":
            model = models.efficientnet_b0(weights=None)
            model.classifier[1] = nn.Linear(model.classifier[1].in_features, num_classes)
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported model architecture: {model_architecture}")
        
        # Load weights
        model.load_state_dict(state_dict)
        model.to(device)
        model.eval()
        
        # Get class labels - try multiple sources
        class_labels = None
        
        # 1. Try from model metadata
        if "class_labels" in model_metadata:
            class_labels = model_metadata["class_labels"]
            logger.info(f"Using class labels from model metadata: {class_labels}")
        
        # 2. Try from project metadata
        if not class_labels:
            project_meta = project_data.get("metadata") or {}
            if "class_labels" in project_meta:
                class_labels = project_meta["class_labels"]
                logger.info(f"Using class labels from project metadata: {class_labels}")
        
        # 3. Try to extract from dataset's GCS .zip file
        if not class_labels:
            try:
                dataset_record = supabase.table("datasets").select("gcs_url").eq("project_id", project_id).execute()
                if dataset_record.data:
                    dataset_gcs_url = dataset_record.data[0].get("gcs_url", "")
                    if dataset_gcs_url and dataset_gcs_url.endswith(".zip"):
                        logger.info(f"Extracting class labels from dataset zip: {dataset_gcs_url}")
                        import tempfile
                        import zipfile
                        
                        ds_path = dataset_gcs_url.replace("gs://", "")
                        ds_bucket_name = ds_path.split("/")[0]
                        ds_blob_path = "/".join(ds_path.split("/")[1:])
                        
                        ds_bucket = storage_client.bucket(ds_bucket_name)
                        ds_blob = ds_bucket.blob(ds_blob_path)
                        
                        with tempfile.NamedTemporaryFile(suffix=".zip") as temp_zip:
                            ds_blob.download_to_filename(temp_zip.name)
                            
                            with zipfile.ZipFile(temp_zip.name, 'r') as z:
                                paths = z.namelist()
                                
                                # Find train directory prefix
                                train_prefix = None
                                for p in paths:
                                    if '/train/' in p.lower() or p.lower().startswith('train/'):
                                        train_prefix = p[:p.lower().find('train/') + 6]
                                        break
                                
                                if train_prefix:
                                    # Extract class names
                                    classes = set()
                                    for p in paths:
                                        if p.startswith(train_prefix) and p != train_prefix:
                                            rel_path = p[len(train_prefix):]
                                            if '/' in rel_path:
                                                cls_name = rel_path.split('/')[0]
                                                if cls_name:
                                                    classes.add(cls_name)
                                    
                                    if classes:
                                        class_labels = sorted(list(classes))
                                        logger.info(f"Found {len(class_labels)} classes in zip: {class_labels}")
                                        
                                        # Save to model metadata to cache it for future requests
                                        model_metadata["class_labels"] = class_labels
                                        supabase.table("models").update({"metadata": model_metadata}).eq("id", model_data["id"]).execute()
                                        logger.info("Saved extracted class labels to model metadata")
            except Exception as e:
                logger.warning(f"Failed to extract class labels from GCS zip: {e}")
        
        # 4. Fallback to generic labels
        if not class_labels:
            class_labels = [f"Class_{i}" for i in range(num_classes)]
            logger.info(f"Using generic class labels: {class_labels}")
        
        # Preprocess image
        file_bytes = await file.read()
        image = Image.open(io.BytesIO(file_bytes)).convert('RGB')
        
        transform = transforms.Compose([
            transforms.Resize(256),
            transforms.CenterCrop(224),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
        ])
        
        img_tensor = transform(image).unsqueeze(0).to(device)
        
        # Run inference and Grad-CAM
        model.eval()
        grad_cam = GradCAM(model)
        
        # Calculate Grad-CAM BEFORE torch.no_grad()
        heatmap_base64 = None
        try:
            if grad_cam.target_layer:
                heatmap = grad_cam.generate(img_tensor)
                
                if heatmap is not None:
                    import cv2
                    import numpy as np
                    import base64
                    
                    # Prepare display image
                    img_display = img_tensor[0].cpu().numpy().transpose(1, 2, 0)
                    mean = np.array([0.485, 0.456, 0.406])
                    std = np.array([0.229, 0.224, 0.225])
                    img_display = std * img_display + mean
                    img_display = np.clip(img_display, 0, 1)
                    
                    # Resize heatmap
                    heatmap = cv2.resize(heatmap, (img_display.shape[1], img_display.shape[0]))
                    heatmap = np.uint8(255 * heatmap)
                    heatmap = cv2.applyColorMap(heatmap, cv2.COLORMAP_JET)
                    heatmap = np.float32(heatmap) / 255
                    heatmap = heatmap[:, :, ::-1] # BGR to RGB
                    
                    cam_result = heatmap * 0.4 + img_display * 0.6
                    cam_result = np.clip(cam_result, 0, 1)
                    
                    # Convert to base64
                    cam_result_uint8 = np.uint8(255 * cam_result)
                    cam_result_bgr = cam_result_uint8[:, :, ::-1] # RGB to BGR for cv2
                    _, buffer = cv2.imencode('.jpg', cam_result_bgr)
                    heatmap_base64 = "data:image/jpeg;base64," + base64.b64encode(buffer).decode('utf-8')
        except Exception as e:
            logger.warning(f"Grad-CAM generation failed: {e}")

        # Final inference
        with torch.no_grad():
            outputs = model(img_tensor)
            probabilities = torch.nn.functional.softmax(outputs, dim=1)
            confidence, predicted = torch.max(probabilities, 1)
        
        predicted_class_idx = predicted.item()
        confidence_score = confidence.item()
        
        # Get class name
        if predicted_class_idx < len(class_labels):
            predicted_class = class_labels[predicted_class_idx]
        else:
            predicted_class = f"Class_{predicted_class_idx}"
        
        logger.info(f"Prediction: {predicted_class} ({confidence_score:.2%})")
        
        return {
            "success": True,
            "prediction": predicted_class,
            "class": predicted_class,
            "confidence": confidence_score,
            "class_index": predicted_class_idx,
            "heatmap_base64": heatmap_base64
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error testing model: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


# --- Sanity Agent: Human-in-the-Loop Approval ---

class SanityApprovalPayload(BaseModel):
    actions: dict  # {"remove_corrupt": true, "remove_blurry": false, "auto_split": true, "augment_balance": true}

@app.post("/api/ml/projects/{project_id}/sanity-approve")
async def approve_sanity_actions(project_id: str, payload: SanityApprovalPayload, user_id: str = None):
    """
    Human-in-the-loop: user approves/skips sanity fix actions.
    Forwards the decision to the Sanity Agent.
    """
    logger.info(f"Sanity approval for project {project_id}: {payload.actions}")
    try:
        import httpx
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{settings.SANITY_AGENT_URL}/agents/sanity/approve",
                json={"project_id": project_id, "actions": payload.actions}
            )
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as e:
        logger.error(f"Sanity agent returned error: {e.response.text}")
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except Exception as e:
        logger.error(f"Error forwarding sanity approval: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to forward sanity approval: {str(e)}")


# --- Privacy Agent: Human-in-the-Loop Approval ---

class PrivacyApprovalPayload(BaseModel):
    actions: dict

@app.post("/api/ml/projects/{project_id}/privacy-approve")
async def approve_privacy_actions(project_id: str, payload: PrivacyApprovalPayload, user_id: str = None):
    """
    Human-in-the-loop: user approves/skips privacy masking actions.
    Forwards the decision to the Privacy Agent.
    """
    logger.info(f"Privacy approval for project {project_id}: {payload.actions}")
    try:
        import httpx
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{settings.PRIVACY_AGENT_URL}/agents/privacy/approve",
                json={"project_id": project_id, "actions": payload.actions}
            )
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as e:
        logger.error(f"Privacy agent returned error: {e.response.text}")
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except Exception as e:
        logger.error(f"Error forwarding privacy approval: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to forward privacy approval: {str(e)}")


# --- Trainer Agent: Human-in-the-Loop Config ---

class TrainingConfigPayload(BaseModel):
    model: str
    epochs: int
    learning_rate: float
    batch_size: int

@app.post("/api/ml/projects/{project_id}/training-config")
async def save_training_config(project_id: str, payload: TrainingConfigPayload, user_id: str = None):
    """
    Human-in-the-loop: user configures training parameters.
    Saves to metadata and transitions to pending_training.
    """
    logger.info(f"Training config for project {project_id}: {payload}")
    try:
        from supabase_client import get_supabase_client
        supabase = get_supabase_client()
        
        project_resp = supabase.table("projects").select("*").eq("id", project_id).execute()
        if not project_resp.data:
            raise HTTPException(status_code=404, detail="Project not found")
            
        project = project_resp.data[0]
        metadata = project.get("metadata", {}) or {}
        
        # Update training config
        metadata["preferred_model"] = payload.model
        metadata["epochs"] = payload.epochs
        metadata["learning_rate"] = payload.learning_rate
        metadata["batch_size"] = payload.batch_size
        
        # Save and transition to training
        supabase.table("projects").update({
            "metadata": metadata,
            "status": "pending_training",
            "updated_at": "now()"
        }).eq("id", project_id).execute()
        
        # Log activity
        supabase.table("agent_logs").insert({
            "project_id": project_id,
            "agent_name": "planner",
            "message": f"User configured training: {payload.model}, {payload.epochs} epochs",
            "log_level": "info"
        }).execute()
        
        return {"success": True, "message": "Training configuration saved"}
    except Exception as e:
        logger.error(f"Error saving training config: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to save training config: {str(e)}")


# Admin Endpoints
@app.get("/api/admin/stats")
async def get_admin_stats(user_id: str):
    """
    Get overall system statistics for admin dashboard
    """
    logger.info(f"Admin stats request from user {user_id}")
    
    try:
        # Check if user is admin
        from supabase_client import get_supabase_client
        supabase = get_supabase_client()
        
        # Convert Firebase UID to User UUID and check admin status
        user_uuid = get_user_uuid_from_firebase_uid(user_id)
        user = supabase.table("users").select("is_admin").eq("id", user_uuid).execute()
        
        if not user.data or not user.data[0].get("is_admin", False):
            raise HTTPException(status_code=403, detail="Access denied. Admin privileges required.")
        
        # Get counts
        users_count = supabase.table("users").select("id", count="exact").execute()
        projects_count = supabase.table("projects").select("id", count="exact").execute()
        datasets_count = supabase.table("datasets").select("id", count="exact").execute()
        models_count = supabase.table("models").select("id", count="exact").execute()
        
        # Get status breakdown
        status_breakdown = {}
        statuses = ["draft", "pending_dataset", "pending_sanity", "pending_sanity_review", "pending_sanity_fix", "pending_training", "pending_evaluation", "completed", "failed"]
        for status in statuses:
            count = supabase.table("projects").select("id", count="exact").eq("status", status).execute()
            status_breakdown[status] = count.count
        
        # Get recent activity (last 24 hours)
        from datetime import datetime, timedelta
        yesterday = (datetime.utcnow() - timedelta(days=1)).isoformat()
        recent_projects = supabase.table("projects").select("id", count="exact").gte("created_at", yesterday).execute()
        
        return {
            "total_users": users_count.count,
            "total_projects": projects_count.count,
            "total_datasets": datasets_count.count,
            "total_models": models_count.count,
            "status_breakdown": status_breakdown,
            "recent_projects_24h": recent_projects.count
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching admin stats: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/admin/users")
async def get_all_users(user_id: str):
    """
    Get all users with their project counts
    """
    logger.info(f"Admin users request from user {user_id}")
    
    try:
        from supabase_client import get_supabase_client
        supabase = get_supabase_client()
        
        # Check if user is admin
        user_uuid = get_user_uuid_from_firebase_uid(user_id)
        user = supabase.table("users").select("is_admin").eq("id", user_uuid).execute()
        
        if not user.data or not user.data[0].get("is_admin", False):
            raise HTTPException(status_code=403, detail="Access denied. Admin privileges required.")
        
        # Get all users
        users = supabase.table("users").select("*").order("created_at", desc=True).execute()
        
        # Get project counts for each user
        users_with_counts = []
        for user in users.data:
            projects = supabase.table("projects").select("id", count="exact").eq("user_id", user["id"]).execute()
            users_with_counts.append({
                **user,
                "project_count": projects.count
            })
        
        return {"users": users_with_counts}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching users: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/admin/projects")
async def get_all_projects(user_id: str, limit: int = 50):
    """
    Get all projects across all users
    """
    logger.info(f"Admin projects request from user {user_id}")
    
    try:
        from supabase_client import get_supabase_client
        supabase = get_supabase_client()
        
        # Check if user is admin
        user_uuid = get_user_uuid_from_firebase_uid(user_id)
        user = supabase.table("users").select("is_admin").eq("id", user_uuid).execute()
        
        if not user.data or not user.data[0].get("is_admin", False):
            raise HTTPException(status_code=403, detail="Access denied. Admin privileges required.")
        
        # Get all projects with user info
        projects = supabase.table("projects").select("*, users(firebase_uid, email)").order("created_at", desc=True).limit(limit).execute()
        
        return {"projects": projects.data}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching projects: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/admin/logs")
async def get_all_logs(user_id: str, limit: int = 100):
    """
    Get recent agent logs across all projects
    """
    logger.info(f"Admin logs request from user {user_id}")
    
    try:
        from supabase_client import get_supabase_client
        supabase = get_supabase_client()
        
        # Check if user is admin
        user_uuid = get_user_uuid_from_firebase_uid(user_id)
        user = supabase.table("users").select("is_admin").eq("id", user_uuid).execute()
        
        if not user.data or not user.data[0].get("is_admin", False):
            raise HTTPException(status_code=403, detail="Access denied. Admin privileges required.")
        
        # Get recent logs
        logs = supabase.table("agent_logs").select("*, projects(name)").order("created_at", desc=True).limit(limit).execute()
        
        return {"logs": logs.data}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error testing model: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# ============= Custom Dataset Upload Endpoint =============

@app.post("/api/ml/upload-dataset")
async def upload_custom_dataset(
    dataset: UploadFile = File(...),
    user_id: str = Form(...),
    project_name: str = Form(...),
    task_type: str = Form("image_classification"),
    preferred_model: str = Form("resnet18"),
    description: str = Form(""),
    user_name: str = Form(""),
    user_email: str = Form(""),
    run_sanity: str = Form("false"),
    run_privacy: str = Form("false")
):
    """
    Upload a custom dataset ZIP file for quick training.
    
    Flow: Upload ZIP → Create project → Upload to GCS → Update DB → Training Agent auto-picks it up
    
    The ZIP should contain train/ and val/ directories with class subdirectories.
    """
    logger.info(f"Custom dataset upload from user {user_id}: {dataset.filename} ({project_name})")
    
    try:
        from supabase_client import get_supabase_client
        from google.cloud import storage
        from datetime import datetime, timezone
        import tempfile
        import zipfile
        
        supabase = get_supabase_client()
        
        # 1. Validate file
        if not dataset.filename:
            raise HTTPException(status_code=400, detail="No file uploaded")
        
        filename_lower = dataset.filename.lower()
        if not (filename_lower.endswith('.zip') or filename_lower.endswith('.tar.gz') or filename_lower.endswith('.rar') or filename_lower.endswith('.csv')):
            raise HTTPException(status_code=400, detail="Only .zip, .tar.gz, .rar, and .csv files are supported")
        
        # 2. Get or create user
        user_uuid = get_user_uuid_from_firebase_uid(user_id)
        logger.info(f"User UUID: {user_uuid}")
        
        # 3. Create project in database
        project_data = {
            "user_id": user_uuid,
            "name": project_name,
            "task_type": task_type,
            "framework": "pytorch",
            "dataset_source": "custom_upload",
            "status": "pending_dataset",
            "metadata": {
                "description": description or f"Custom dataset upload: {dataset.filename}",
                "search_keywords": [project_name.lower().replace(" ", "_")],
                "preferred_model": preferred_model,
                "target_metric": "accuracy",
                "target_value": 0.9,
                "upload_filename": dataset.filename,
                "source": "custom_upload"
            },
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        
        project_result = supabase.table("projects").insert(project_data).execute()
        if not project_result.data:
            raise HTTPException(status_code=500, detail="Failed to create project in database")
        
        project_id = project_result.data[0]["id"]
        logger.info(f"Created project {project_id}")
        
        # Log to agent_logs
        supabase.table("agent_logs").insert({
            "project_id": project_id,
            "agent_name": "dataset",
            "message": f"Custom dataset upload started: {dataset.filename}",
            "log_level": "info",
            "created_at": datetime.now(timezone.utc).isoformat()
        }).execute()
        
        # 4. Save uploaded file to temp and upload to GCS
        file_content = await dataset.read()
        file_size_bytes = len(file_content)
        file_size_mb = file_size_bytes / (1024 * 1024)
        
        logger.info(f"Dataset file size: {file_size_mb:.1f}MB")
        
        # Validate size (500MB max)
        if file_size_mb > 500:
            # Clean up the project we just created
            supabase.table("projects").delete().eq("id", project_id).execute()
            raise HTTPException(status_code=400, detail=f"File too large ({file_size_mb:.1f}MB). Maximum is 500MB.")
        
        # Try to extract class labels from ZIP
        class_labels = None
        if filename_lower.endswith('.zip'):
            try:
                import io
                with zipfile.ZipFile(io.BytesIO(file_content), 'r') as z:
                    paths = z.namelist()
                    
                    # Find train directory
                    train_prefix = None
                    for p in paths:
                        if '/train/' in p.lower() or p.lower().startswith('train/'):
                            train_prefix = p[:p.lower().find('train/') + 6]
                            break
                    
                    if train_prefix:
                        classes = set()
                        for p in paths:
                            if p.startswith(train_prefix) and p != train_prefix:
                                rel_path = p[len(train_prefix):]
                                if '/' in rel_path:
                                    cls_name = rel_path.split('/')[0]
                                    if cls_name and not cls_name.startswith('.'):
                                        classes.add(cls_name)
                        
                        if classes:
                            class_labels = sorted(list(classes))
                            logger.info(f"Extracted {len(class_labels)} classes from ZIP: {class_labels}")
            except Exception as e:
                logger.warning(f"Could not extract class labels from ZIP: {e}")
        
        # Upload to GCS
        gcp_credentials_path = settings.GOOGLE_APPLICATION_CREDENTIALS
        if not gcp_credentials_path or not os.path.exists(gcp_credentials_path):
            # Clean up
            supabase.table("projects").delete().eq("id", project_id).execute()
            raise HTTPException(status_code=500, detail="GCP credentials not configured")
        
        storage_client = storage.Client.from_service_account_json(gcp_credentials_path)
        bucket_name = settings.GCP_BUCKET_NAME
        bucket = storage_client.bucket(bucket_name)
        
        # Upload to raw/custom_uploads/<project_id>/<filename>
        safe_filename = dataset.filename.replace(" ", "_")
        gcs_destination = f"raw/custom_uploads/{project_id}/{safe_filename}"
        
        blob = bucket.blob(gcs_destination)
        blob.upload_from_string(file_content, timeout=300)
        
        gcs_url = f"gs://{bucket_name}/{gcs_destination}"
        logger.info(f"Uploaded to GCS: {gcs_url}")
        
        supabase.table("agent_logs").insert({
            "project_id": project_id,
            "agent_name": "dataset",
            "message": f"Dataset uploaded to GCS: {gcs_url} ({file_size_mb:.1f}MB)",
            "log_level": "info",
            "created_at": datetime.now(timezone.utc).isoformat()
        }).execute()
        
        # 5. Create dataset record
        dataset_record = {
            "project_id": project_id,
            "name": dataset.filename,
            "gcs_url": gcs_url,
            "size": f"{file_size_mb:.2f} MB" if file_size_mb < 1024 else f"{file_size_mb / 1024:.2f} GB",
            "source": "custom_upload",
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
        supabase.table("datasets").insert(dataset_record).execute()
        logger.info(f"Dataset record created for project {project_id}")
        
        # 6. Update project metadata with class labels and set status to pending_training
        update_metadata = project_data["metadata"].copy()
        if class_labels:
            update_metadata["class_labels"] = class_labels
            update_metadata["num_classes"] = len(class_labels)
        
        target_status = "pending_training_config"
        if run_sanity.lower() == "true":
            target_status = "pending_sanity"
        elif run_privacy.lower() == "true":
            target_status = "pending_privacy"

        supabase.table("projects").update({
            "status": target_status,
            "metadata": update_metadata,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }).eq("id", project_id).execute()
        
        logger.info(f"Project {project_id} status set to {target_status}")
        
        supabase.table("agent_logs").insert({
            "project_id": project_id,
            "agent_name": "dataset",
            "message": f"Custom dataset processed successfully. Status → pending_training. Classes: {class_labels or 'auto-detect during training'}",
            "log_level": "info",
            "created_at": datetime.now(timezone.utc).isoformat()
        }).execute()
        
        # 7. Return success
        return {
            "success": True,
            "projectId": project_id,
            "message": f"Dataset '{dataset.filename}' uploaded successfully! Project '{project_name}' created and queued for training.",
            "dataset": {
                "filename": dataset.filename,
                "size_mb": round(file_size_mb, 1),
                "gcs_url": gcs_url,
                "class_labels": class_labels
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading custom dataset: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))

