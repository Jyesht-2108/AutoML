"""
Evaluation service for trained models.

This module handles model evaluation, metric computation, and bundle creation
for end users.
"""

import os
import json
import shutil
import zipfile
import torch
import numpy as np
import torch.nn as nn
from torch.utils.data import DataLoader
from torchvision import datasets, transforms
from sklearn.metrics import accuracy_score, precision_recall_fscore_support, classification_report
from typing import Dict, Any, List

from services.database_service import db_service
from services.storage_service import storage_service
from training.model_factory import create_model
from config import settings


async def execute_evaluation(project_id: str) -> Dict[str, Any]:
    """
    Execute the complete evaluation workflow for a trained model.
    
    Steps:
    1. Fetch project, model, and dataset metadata
    2. Download model and dataset from GCP
    3. Load model and run inference on test set
    4. Compute metrics (accuracy, precision, recall, F1)
    5. Create user bundle (model + predict.py + labels.json + README)
    6. Upload bundle to GCP
    7. Update database with metrics and bundle URL
    8. Update project status to 'completed'
    
    Args:
        project_id: UUID of the project to evaluate
        
    Returns:
        Dictionary containing success status, metrics, and bundle_url
    """
    temp_files = []
    
    try:
        # Step 1: Fetch metadata
        db_service.log_agent_activity(
            project_id,
            "Evaluation workflow initiated",
            "info"
        )
        
        project = db_service.get_project(project_id)
        if not project:
            error_msg = f"Project {project_id} not found"
            db_service.log_agent_activity(project_id, error_msg, "error")
            return {"success": False, "error": error_msg}
        
        if project.get("status") != "pending_evaluation":
            error_msg = f"Project status is '{project.get('status')}', expected 'pending_evaluation'"
            db_service.log_agent_activity(project_id, error_msg, "error")
            return {"success": False, "error": error_msg}
        
        # Route based on task_type
        task_type = project.get("task_type", "image_classification")
        if task_type in ("tabular_classification", "tabular_regression", "text_classification"):
            db_service.log_agent_activity(project_id, f"Routing to sklearn evaluation (task_type={task_type})", "info")
            from services.tabular_evaluation_service import execute_sklearn_evaluation
            return await execute_sklearn_evaluation(project_id)

        # Update status to 'evaluating'
        db_service.update_project_status(project_id, "evaluating")
        
        # Get model metadata
        model_record = db_service.get_model_by_project(project_id)
        if not model_record:
            error_msg = f"Model not found for project {project_id}"
            db_service.log_agent_activity(project_id, error_msg, "error")
            db_service.update_project_status(project_id, "failed")
            return {"success": False, "error": error_msg}
        
        # Get dataset metadata
        dataset = db_service.get_dataset(project_id)
        if not dataset:
            error_msg = f"Dataset not found for project {project_id}"
            db_service.log_agent_activity(project_id, error_msg, "error")
            db_service.update_project_status(project_id, "failed")
            return {"success": False, "error": error_msg}
        
        db_service.log_agent_activity(
            project_id,
            f"Metadata retrieved - Model: {model_record.get('name')}, Dataset: {dataset.get('name')}",
            "info"
        )
        
        # Extract project info
        project_name = project.get("name", "model")
        project_metadata = project.get("metadata", {})
        model_architecture = project_metadata.get("preferred_model", "resnet18")
        
        # Step 2: Download model and dataset (Windows compatible)
        import tempfile
        temp_dir = os.path.join(tempfile.gettempdir(), f"evaluation_{project_id}")
        os.makedirs(temp_dir, exist_ok=True)
        temp_files.append(temp_dir)
        
        model_path = os.path.join(temp_dir, "model.pth")
        dataset_zip_path = os.path.join(temp_dir, "dataset.zip")
        dataset_extract_dir = os.path.join(temp_dir, "dataset")
        
        temp_files.extend([model_path, dataset_zip_path, dataset_extract_dir])
        
        db_service.log_agent_activity(
            project_id,
            f"Downloading model from {model_record.get('gcs_url')}",
            "info"
        )
        
        storage_service.download_model(model_record.get("gcs_url"), model_path)
        
        db_service.log_agent_activity(
            project_id,
            f"Downloading dataset from {dataset.get('gcs_url')}",
            "info"
        )
        
        storage_service.download_dataset(dataset.get("gcs_url"), dataset_zip_path)
        
        # Extract dataset
        from utils.file_utils import (
            unzip_dataset, 
            auto_flatten_dataset, 
            normalize_folder_names,
            validate_dataset_structure,
            create_val_from_train,
            auto_split_dataset
        )
        
        unzip_dataset(dataset_zip_path, dataset_extract_dir)
        auto_flatten_dataset(dataset_extract_dir)
        normalize_folder_names(dataset_extract_dir)
        
        # Check if we have train and test but no val
        has_train = os.path.exists(os.path.join(dataset_extract_dir, 'train'))
        has_test = os.path.exists(os.path.join(dataset_extract_dir, 'test'))
        has_val = os.path.exists(os.path.join(dataset_extract_dir, 'val'))
        
        if has_train and has_test and not has_val:
            # Create val from train
            db_service.log_agent_activity(
                project_id,
                "Found train/test but no val - creating validation set from training data",
                "info"
            )
            create_val_from_train(dataset_extract_dir, val_ratio=0.2)
        
        # Validate dataset structure - if not valid, auto-split
        if not validate_dataset_structure(dataset_extract_dir):
            db_service.log_agent_activity(
                project_id,
                "No train/val/test structure found - auto-splitting dataset",
                "info"
            )
            
            try:
                auto_split_dataset(dataset_extract_dir, train_ratio=0.7, val_ratio=0.2)
                db_service.log_agent_activity(
                    project_id,
                    "Dataset auto-split completed successfully",
                    "info"
                )
            except Exception as e:
                error_msg = f"Failed to auto-split dataset: {str(e)}"
                db_service.log_agent_activity(project_id, error_msg, "error")
                db_service.update_project_status(project_id, "failed")
                return {"success": False, "error": error_msg}
        
        test_dir = os.path.join(dataset_extract_dir, "test")
        if not os.path.exists(test_dir):
            error_msg = "Test directory not found in dataset after processing"
            db_service.log_agent_activity(project_id, error_msg, "error")
            db_service.update_project_status(project_id, "failed")
            return {"success": False, "error": error_msg}
        
        # Step 3: Load model and run evaluation
        db_service.log_agent_activity(
            project_id,
            "Loading model and preparing test data",
            "info"
        )
        
        metrics = evaluate_model(
            model_path=model_path,
            test_dir=test_dir,
            model_architecture=model_architecture,
            project_id=project_id
        )
        
        db_service.log_agent_activity(
            project_id,
            f"Evaluation complete - Accuracy: {metrics['accuracy']:.2%}",
            "info"
        )
        
        # Step 4: Create user bundle
        db_service.log_agent_activity(
            project_id,
            "Creating downloadable user bundle",
            "info"
        )
        
        bundle_url = create_user_bundle(
            project_id=project_id,
            project_name=project_name,
            model_path=model_path,
            model_architecture=model_architecture,
            class_labels=metrics["class_labels"],
            num_classes=metrics["num_classes"],
            project_metadata=project_metadata
        )
        
        db_service.log_agent_activity(
            project_id,
            f"Bundle uploaded to {bundle_url}",
            "info"
        )
        
        # Step 5: Update database
        db_service.update_model_metrics(
            model_id=model_record.get("id"),
            accuracy=metrics["accuracy"],
            metadata=metrics["detailed_metrics"]
        )
        
        # Update project with bundle URL
        project_metadata["bundle_url"] = bundle_url
        project_metadata["metrics"] = {
            "accuracy": float(metrics["accuracy"]),
            "precision": float(metrics["precision"]),
            "recall": float(metrics["recall"]),
            "f1_score": float(metrics["f1_score"]),
            "classification_report": metrics["detailed_metrics"]
        }
        project_metadata["evaluation_metrics"] = metrics["detailed_metrics"]
        
        # Upload Grad-CAM preview if available
        gradcam_path = metrics.get("gradcam_preview_path")
        if gradcam_path and os.path.exists(gradcam_path):
            import time
            from google.cloud import storage
            client = storage.Client()
            bucket = client.bucket(settings.gcp_bucket_name)
            blob_path = f"evaluations/{project_id}/gradcam_{int(time.time())}.png"
            blob = bucket.blob(blob_path)
            blob.upload_from_filename(gradcam_path)
            
            gradcam_url = f"gs://{settings.gcp_bucket_name}/{blob_path}"
            project_metadata["gradcam_preview_url"] = gradcam_url
            db_service.log_agent_activity(project_id, f"Uploaded Grad-CAM heatmaps to {gradcam_url}", "info")

        
        db_service.update_project_metadata(project_id, project_metadata)
        db_service.update_project_status(project_id, "pending_evaluation_review")
        
        db_service.log_agent_activity(
            project_id,
            "Evaluation workflow completed, waiting for user review",
            "info"
        )
        
        return {
            "success": True,
            "accuracy": metrics["accuracy"],
            "bundle_url": bundle_url,
            "metrics": metrics["detailed_metrics"]
        }
        
    except Exception as e:
        error_msg = f"Evaluation failed: {str(e)}"
        db_service.log_agent_activity(project_id, error_msg, "error")
        
        try:
            db_service.update_project_status(project_id, "failed")
        except:
            pass
        
        return {"success": False, "error": error_msg}
    
    finally:
        # Cleanup
        from utils.file_utils import cleanup_temp_files
        cleanup_temp_files(temp_files)


def evaluate_model(
    model_path: str,
    test_dir: str,
    model_architecture: str,
    project_id: str
) -> Dict[str, Any]:
    """
    Load model and evaluate on test set.
    
    Args:
        model_path: Path to model .pth file
        test_dir: Path to test directory with class folders
        model_architecture: Model architecture name
        project_id: Project ID for logging
        
    Returns:
        Dictionary with accuracy, class labels, and detailed metrics
    """
    # Setup device
    if torch.backends.mps.is_available():
        device = torch.device("mps")
    elif torch.cuda.is_available():
        device = torch.device("cuda")
    else:
        device = torch.device("cpu")
    
    db_service.log_agent_activity(project_id, f"Using device: {device}", "info")
    
    # Load test dataset
    transform = transforms.Compose([
        transforms.Resize(256),
        transforms.CenterCrop(224),
        transforms.ToTensor(),
        transforms.Normalize(
            mean=[0.485, 0.456, 0.406],
            std=[0.229, 0.224, 0.225]
        )
    ])
    
    test_dataset = datasets.ImageFolder(test_dir, transform=transform)
    test_loader = DataLoader(
        test_dataset,
        batch_size=64,
        shuffle=False,
        num_workers=0
    )
    
    num_classes = len(test_dataset.classes)
    class_labels = test_dataset.classes
    
    db_service.log_agent_activity(
        project_id,
        f"Test dataset loaded: {len(test_dataset)} images, {num_classes} classes",
        "info"
    )
    
    # Load model
    model = create_model(model_architecture, num_classes)
    model.load_state_dict(torch.load(model_path, map_location=device))
    model.to(device)
    model.eval()
    
    # Run inference
    y_true = []
    y_pred = []
    
    with torch.no_grad():
        for inputs, labels in test_loader:
            inputs = inputs.to(device)
            labels = labels.to(device)
            
            outputs = model(inputs)
            _, preds = torch.max(outputs, 1)
            
            y_true.extend(labels.cpu().numpy())
            y_pred.extend(preds.cpu().numpy())
    
    # Compute metrics
    accuracy = accuracy_score(y_true, y_pred)
    precision, recall, f1, support = precision_recall_fscore_support(
        y_true, y_pred, average='weighted', zero_division=0
    )
    
    # Detailed classification report
    report = classification_report(
        y_true, y_pred,
        target_names=class_labels,
        output_dict=True,
        zero_division=0
    )
    
    # Generate Grad-CAM preview
    db_service.log_agent_activity(project_id, "Generating XAI Grad-CAM heatmaps...", "info")
    gradcam_preview_path = generate_gradcam_preview(model, test_dataset, device)
    
    return {
        "accuracy": accuracy,
        "precision": precision,
        "recall": recall,
        "f1_score": f1,
        "num_classes": num_classes,
        "class_labels": class_labels,
        "detailed_metrics": report,
        "gradcam_preview_path": gradcam_preview_path
    }


class GradCAM:
    """Simple hook-based Grad-CAM implementation for PyTorch CNNs."""
    def __init__(self, model):
        self.model = model
        self.gradients = None
        self.activations = None
        self.target_layer = self._find_target_layer()
        if self.target_layer:
            self.target_layer.register_forward_hook(self.save_activation)
            self.target_layer.register_full_backward_hook(self.save_gradient)

    def _find_target_layer(self):
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

def generate_gradcam_preview(model, test_dataset, device, num_samples=5) -> str:
    """Generate Grad-CAM heatmaps for a few test samples and return path to the saved preview image."""
    try:
        import cv2
        import numpy as np
        import matplotlib.pyplot as plt
    except ImportError:
        return None

    model.eval()
    grad_cam = GradCAM(model)
    if not grad_cam.target_layer:
        return None
        
    indices = np.random.choice(len(test_dataset), min(num_samples, len(test_dataset)), replace=False)
    fig, axes = plt.subplots(num_samples, 2, figsize=(10, 4 * num_samples))
    if num_samples == 1:
        axes = [axes]
        
    for i, idx in enumerate(indices):
        img_tensor, label = test_dataset[idx]
        img_tensor = img_tensor.unsqueeze(0).to(device)
        
        img_display = img_tensor[0].cpu().numpy().transpose(1, 2, 0)
        mean = np.array([0.485, 0.456, 0.406])
        std = np.array([0.229, 0.224, 0.225])
        img_display = std * img_display + mean
        img_display = np.clip(img_display, 0, 1)
        
        # Calculate Grad-CAM
        heatmap = grad_cam.generate(img_tensor)
        
        if heatmap is not None:
            heatmap = cv2.resize(heatmap, (img_display.shape[1], img_display.shape[0]))
            heatmap = np.uint8(255 * heatmap)
            heatmap = cv2.applyColorMap(heatmap, cv2.COLORMAP_JET)
            heatmap = np.float32(heatmap) / 255
            heatmap = heatmap[:, :, ::-1] # BGR to RGB
            
            cam_result = heatmap * 0.4 + img_display * 0.6
            cam_result = np.clip(cam_result, 0, 1)
        else:
            cam_result = img_display
            
        with torch.no_grad():
            pred = model(img_tensor).argmax(dim=1).item()
            
        true_label = test_dataset.classes[label]
        pred_label = test_dataset.classes[pred]
        title = f"True: {true_label} | Pred: {pred_label}"
        
        axes[i][0].imshow(img_display)
        axes[i][0].set_title(title)
        axes[i][0].axis('off')
        
        axes[i][1].imshow(cam_result)
        axes[i][1].set_title("Grad-CAM Heatmap")
        axes[i][1].axis('off')
        
    plt.tight_layout()
    import tempfile
    save_path = os.path.join(tempfile.gettempdir(), f"gradcam_preview_{np.random.randint(1000)}.png")
    plt.savefig(save_path)
    plt.close()
    
    return save_path


def create_user_bundle(
    project_id: str,
    project_name: str,
    model_path: str,
    model_architecture: str,
    class_labels: List[str],
    num_classes: int,
    project_metadata: Dict[str, Any] = None
) -> str:
    """
    Create a downloadable bundle with model, predict script, and labels.
    
    Args:
        project_id: Project UUID
        project_name: Name of the project
        model_path: Path to trained model
        model_architecture: Model architecture name
        class_labels: List of class names
        num_classes: Number of classes
        
    Returns:
        GCS URL of the uploaded bundle
    """
    import tempfile
    export_dir = os.path.join(tempfile.gettempdir(), f"export_{project_id}")
    os.makedirs(export_dir, exist_ok=True)
    
    # 1. Copy model
    shutil.copy(model_path, os.path.join(export_dir, "model.pth"))
    
    # 2. Create labels.json
    labels_dict = {str(i): label for i, label in enumerate(class_labels)}
    with open(os.path.join(export_dir, "labels.json"), "w") as f:
        json.dump(labels_dict, f, indent=2)
    
    # 3. Create predict.py
    predict_code = f'''"""
Inference script for trained model.

Usage:
    python predict.py path/to/image.jpg
"""

import torch
import json
import sys
from torchvision import models, transforms
from PIL import Image

# Load labels
with open('labels.json') as f:
    labels = json.load(f)

# Load model
def load_model():
    import torch
    import torch.nn as nn
    from torchvision import models
    
    # Load the model architecture
    if "{model_architecture}".lower().startswith("yolo"):
        try:
            from ultralytics import YOLO
            weight_file = "yolov8s-cls.pt" if "s_cls" in "{model_architecture}".lower() else "yolov8n-cls.pt"
            yolo = YOLO(weight_file)
            base = yolo.model
            base.model[-1].linear = nn.Linear(base.model[-1].linear.in_features, {num_classes})
            class YOLOWrapper(nn.Module):
                def __init__(self, m):
                    super().__init__()
                    self.base_model = m
                    self.fc = self.base_model.model[-1].linear
                def forward(self, x):
                    o = self.base_model(x)
                    return o[0] if isinstance(o, (tuple, list)) else o
            model = YOLOWrapper(base)
        except Exception:
            from torchvision import models
            model = models.resnet18(weights=None)
            model.fc = nn.Linear(model.fc.in_features, {num_classes})
    else:
        model = models.{model_architecture}(weights=None)
        # Modify final layer for number of classes
        if hasattr(model, 'fc'):
            model.fc = nn.Linear(model.fc.in_features, {num_classes})
        elif hasattr(model, 'classifier'):
            if isinstance(model.classifier, nn.Sequential):
                model.classifier[-1] = nn.Linear(model.classifier[-1].in_features, {num_classes})
            else:
                model.classifier = nn.Linear(model.classifier.in_features, {num_classes})
    
    model.load_state_dict(torch.load('model.pth', map_location='cpu'))
    model.eval()
    return model

model = load_model()

# Image preprocessing
transform = transforms.Compose([
    transforms.Resize(256),
    transforms.CenterCrop(224),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
])

def predict(image_path):
    """Predict class for a single image."""
    img = Image.open(image_path).convert('RGB')
    img_tensor = transform(img).unsqueeze(0)
    
    with torch.no_grad():
        outputs = model(img_tensor)
        probabilities = torch.nn.functional.softmax(outputs, dim=1)
        confidence, predicted = torch.max(probabilities, 1)
    
    predicted_class = labels[str(predicted.item())]
    confidence_score = confidence.item()
    
    print(f"Prediction: {{predicted_class}}")
    print(f"Confidence: {{confidence_score:.2%}}")
    
    return predicted_class, confidence_score

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python predict.py <image_path>")
        sys.exit(1)
    
    image_path = sys.argv[1]
    predict(image_path)
'''
    
    with open(os.path.join(export_dir, "predict.py"), "w") as f:
        f.write(predict_code)
    
    
    # Check if we have metadata to generate a justification report
    if project_metadata is None:
        project_metadata = {}
        
    # Write metadata as JSON
    with open(os.path.join(export_dir, "metadata.json"), "w") as f:
        json.dump(project_metadata, f, indent=2)
        
    # Extract rationales and steps
    planner_rationale = project_metadata.get("planner_rationale", "No planner rationale provided.")
    sanity_results = project_metadata.get("sanity_fix_results", {})
    privacy_results = project_metadata.get("privacy_fix_results", {})
    
    sanity_text = "\\n- ".join([f"{k}: {v}" for k, v in sanity_results.items()]) if sanity_results else "No sanity actions taken."
    privacy_text = "\\n- ".join([f"{k}: {v}" for k, v in privacy_results.items()]) if privacy_results else "No privacy actions taken."
    
    # 4. Create README
    readme = f"""# {project_name} - Trained Model Bundle

## Contents
- `model.pth`: Trained PyTorch model weights
- `labels.json`: Class labels mapping
- `metadata.json`: Complete project execution metadata and logs
- `predict.py`: Inference script
- `README.md`: This file

## AI Justification & Pipeline Steps
### 1. AI Planner Strategy
The AI Planner selected this architecture and training approach based on your request:
> {planner_rationale}

### 2. Data Sanity Audits & Fixes
The Sanity Agent performed the following auto-fixes on the dataset:
- {sanity_text}

### 3. Privacy Audits & Masking
The Privacy Agent executed the following PII masking steps:
- {privacy_text}

### 4. Final Training Configuration
- Architecture: {model_architecture}
- Number of classes: {num_classes}
- Epochs: {project_metadata.get("epochs", "N/A")}
- Learning Rate: {project_metadata.get("learning_rate", "N/A")}
- Batch Size: {project_metadata.get("batch_size", "N/A")}

---

## Requirements
```bash
pip install torch torchvision pillow
```

## Usage
```bash
python predict.py path/to/your/image.jpg
```

## Classes
{', '.join(class_labels)}

## Notes
- The model expects RGB images
- Images are automatically resized to 224x224
- Predictions include confidence scores
"""
    
    with open(os.path.join(export_dir, "README.md"), "w") as f:
        f.write(readme)
    
    # 5. Create zip file
    zip_filename = f"{project_name.replace(' ', '_')}_bundle.zip"
    zip_path = os.path.join(tempfile.gettempdir(), zip_filename)
    
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(export_dir):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, export_dir)
                zf.write(file_path, arcname)
    
    # 6. Upload to GCP
    bundle_gcs_url = storage_service.upload_bundle(zip_path, zip_filename)
    
    # Cleanup
    shutil.rmtree(export_dir, ignore_errors=True)
    os.remove(zip_path)
    
    return bundle_gcs_url
