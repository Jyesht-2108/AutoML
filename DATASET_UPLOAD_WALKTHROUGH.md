# 📤 Custom Dataset Upload Feature

## Overview
Upload your own small dataset (ZIP) for fast model training and evaluation — bypassing Kaggle search entirely.

**Flow:**
```
Upload ZIP → Project created → Uploaded to GCS → Training Agent auto-picks up → Evaluation
```

---

## How to Use

1. Log in to the app
2. Click the **"Upload Dataset"** tab (or the purple card on Home)
3. Drag & drop your ZIP file (or click to browse)
4. Fill in **Project Name** and select a **Model Architecture**
5. Click **"Upload & Start Training"**
6. Switch to the **ML Projects** tab to monitor progress

---

## Dataset Format

Your ZIP file should follow this folder structure:

```
dataset.zip/
├── train/
│   ├── class_1/   (images: .jpg, .png, etc.)
│   ├── class_2/
│   └── class_3/
└── val/
    ├── class_1/
    ├── class_2/
    └── class_3/
```

- Each subfolder under `train/` and `val/` is a **class label**
- Place images for that class inside its folder
- Class names are auto-extracted from the folder names

---

## Limits
- **Max file size:** 500 MB
- **Accepted formats:** `.zip`, `.tar.gz`, `.rar`
- **Task type:** Image Classification (currently supported)

---

## Model Options
| Model | Speed | Accuracy | Best For |
|-------|-------|----------|----------|
| ResNet-18 | ⚡ Fast | Good | Quick testing |
| ResNet-34 | Medium | Better | Balanced |
| ResNet-50 | Slower | Best | High accuracy |
| MobileNet V2 | ⚡ Fast | Good | Lightweight/mobile |
| EfficientNet-B0 | Medium | Great | Efficiency |

---

## Files Changed

### New
- `frontend/src/components/DatasetUploader.jsx` — Upload UI component

### Modified
- `frontend/src/services/mlApi.js` — Added `uploadCustomDataset()` API call
- `frontend/src/pages/Dashboard.jsx` — Added "Upload Dataset" tab + home card
- `backend/src/routes/ml.js` — Added `POST /ml/upload-dataset` proxy route
- `mcp_server/main.py` — Added `POST /api/ml/upload-dataset` endpoint

---

## API Endpoints

### `POST /api/ml/upload-dataset`
**Content-Type:** `multipart/form-data`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `dataset` | File | ✅ | ZIP file containing the dataset |
| `user_id` | string | ✅ | Firebase UID |
| `project_name` | string | ✅ | Name for the project |
| `task_type` | string | ❌ | Default: `image_classification` |
| `preferred_model` | string | ❌ | Default: `resnet18` |
| `description` | string | ❌ | Project description |

**Response:**
```json
{
  "success": true,
  "projectId": "uuid-...",
  "message": "Dataset uploaded successfully!",
  "dataset": {
    "filename": "cats_dogs.zip",
    "size_mb": 45.2,
    "gcs_url": "gs://bucket/raw/custom_uploads/...",
    "class_labels": ["cat", "dog"]
  }
}
```

---

## What Happens Behind the Scenes

1. **Frontend** sends the ZIP + metadata via multipart form
2. **Express backend** proxies to MCP server with auth context
3. **MCP server:**
   - Creates project with `dataset_source='custom_upload'`
   - Uploads ZIP to `gs://<bucket>/raw/custom_uploads/<project_id>/`
   - Extracts class labels from `train/` folder structure
   - Creates `datasets` DB record
   - Sets status to `pending_training`
   - Logs all steps to `agent_logs`
4. **Training Agent** auto-polls and picks up the project
5. **Evaluation** runs after training completes
