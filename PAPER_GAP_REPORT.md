# AgentHive Project Gap Report vs. Research Paper

This report outlines the discrepancies between the currently implemented codebase and the proposed architecture in the AgentHive research paper, along with a roadmap for integrating new agents and supporting additional dataset types (Text and Tabular).

## 1. Incomplete Agents from the Research Paper

The research paper describes a **7-agent ecosystem**, but the current codebase only implements a subset of these agents.

### Implemented Agents
- ✅ **Planner Agent**: Implemented and functioning (Parses user intent, initializes project state in Supabase).
- ✅ **Dataset Agent**: Implemented and functioning (Fetches dataset from Kaggle, uploads to GCP).
- 🔄 **Trainer Agent**: Implemented but seems to still be undergoing integration/testing. Runs PyTorch templates.
- 🔄 **Evaluation Agent**: Code exists as a service inside the `Trainer-Agent` (`evaluation_service.py`), but the paper describes it as a standalone agent. Currently, it evaluates accuracy but lacks the native Grad-CAM Explainable AI (XAI) feature mentioned in the paper.

### Missing Agents (To Be Implemented)
- ❌ **Data Sanity Auditor (Phase 1)**: Missing. Supposed to detect class imbalances, corrupted files, and statistical anomalies before training.
- ❌ **Privacy Agent (Phase 1)**: Missing. Supposed to redact PII (face blurring) and strip metadata (EXIF data) from datasets.
- ❌ **Deployment Agent (Phase 3)**: Missing. Supposed to automatically package the trained model weights into a Dockerized FastAPI container.

---

## 2. Adding the New Agents (When and How)

To adhere to the paper's architecture, the workflow pipeline (managed by Supabase states) needs to be expanded. Here is how and when to add the missing agents:

### 1. Data Sanity Auditor
- **When**: Executes immediately after the **Dataset Agent** finishes.
- **Workflow State Change**: Dataset Agent updates status to `pending_sanity`. Data Sanity Auditor picks it up, validates data, and updates status to `pending_privacy`.
- **Implementation (How)**: Create a new agent (Port 8005) that downloads the raw dataset from GCP, uses `pandas` (for tabular data) or image validation libraries to check for corrupted images, missing values, or class imbalances. If issues exceed a threshold, it halts the pipeline or logs a warning in Supabase.

### 2. Privacy Agent
- **When**: Executes immediately after the **Data Sanity Auditor**.
- **Workflow State Change**: Sanity Auditor updates status to `pending_privacy`. Privacy Agent processes it and updates to `pending_training`.
- **Implementation (How)**: Create a new agent (Port 8006). For images, use lightweight models (like OpenCV cascades or MTCNN) to blur human faces and `exifread` to strip metadata. For text data, use Microsoft Presidio to redact names, emails, and phone numbers. It then overwrites the sanitized data in the GCP bucket.

### 3. Evaluation Agent (Extraction & Enhancement)
- **When**: After Training Agent completes (`pending_evaluation`).
- **Implementation (How)**: Decouple `evaluation_service.py` from `Trainer-Agent` into its own standalone agent (Port 8004). Add **Grad-CAM** hooks (via `torch-cam`) to generate and upload explainability heatmaps for image classification tasks.

### 4. Deployment Agent
- **When**: Executes after the **Evaluation Agent** completes.
- **Workflow State Change**: Evaluation Agent updates status to `pending_deployment`.
- **Implementation (How)**: Create a new agent (Port 8007) that pulls the evaluation metrics and model. It generates a dynamic `Dockerfile`, `requirements.txt`, and a standardized `FastAPI` script. It zips these into a deployment-ready container package and saves it in GCP.

---

## 3. Integrating Text and Tabular Dataset Features

Currently, the `Trainer-Agent` is hardcoded for **Image Classification** (using `torchvision` models like ResNet, EfficientNet, and MobileNet, alongside `transforms` like `Resize`, `CenterCrop`).

To expand the platform to **Text** and **Tabular** data, the following modifications are required across the agents:

### 1. Planner Agent (Intent & Config Updates)
- Update the prompt parsing logic to detect `task_type` as `text_classification`, `tabular_classification`, or `tabular_regression`.
- Ensure the `optimization_config` JSON dynamically specifies backbones relevant to the data type (e.g., `distilbert` for text, `xgboost` or `pytorch_tabular` for tables).

### 2. Dataset Agent (Handling non-image formats)
- The Dataset Agent must be configured to parse and handle `.csv`, `.json`, and `.txt` files instead of just unzipping image directories.
- It should identify the target column/label column for tabular data (the Planner Agent should extract this from the user's prompt).

### 3. Data Sanity Auditor (Data-Type Specific Checks)
- **Text**: Check for minimum sequence lengths, empty strings, and language validation.
- **Tabular**: Check for NaN/Null values, outlier detection, and categorical vs. numerical feature detection.

### 4. Privacy Agent (Text-based PII)
- Integrate NLP-based Named Entity Recognition (NER) to redact names, phone numbers, SSNs, and emails from text/tabular datasets using tools like `presidio-analyzer` and `presidio-anonymizer`.

### 5. Trainer Agent (New Backbones & Pipelines)
The `Trainer-Agent` needs separate micro-services or pipelines for different modalities:
- **Text Classification**: 
  - Integrate HuggingFace `transformers` and `datasets`.
  - Use tokenizers and models like `DistilBERT` or `RoBERTa`.
- **Tabular Classification/Regression**:
  - Integrate `scikit-learn`, `XGBoost`, or `LightGBM`.
  - For deep learning, use `PyTorch Tabular` for architectures like TabNet or standard Feed-Forward Neural Networks (FFNNs).
  - Add preprocessing logic for one-hot encoding categorical variables and scaling numerical variables.

### 6. Evaluation Agent (New Metrics & Explainability)
- **Text**: Output attention maps (highlighting important words) instead of Grad-CAM. Compute NLP metrics like ROUGE, BLEU (if generative), or standard F1-scores.
- **Tabular**: Use `SHAP` (SHapley Additive exPlanations) to generate feature importance plots, providing the same level of trust-aware explainability as Grad-CAM does for images.
