# Data Sanity Auditor Agent

**Phase 1 Agent** in the AgentHive multi-agent pipeline.

## Purpose

The Data Sanity Auditor proactively validates datasets **before** any compute-heavy training begins. It prevents wasted GPU time and ensures data quality by catching:

- 🖼️ **Corrupted images** — files that cannot be opened or decoded
- 🔍 **Blurry images** — images with low Laplacian variance (below threshold)
- 📐 **Tiny images** — below minimum resolution (default: 16×16)
- ⚖️ **Class imbalance** — when one class has 10× more samples than another
- 🚫 **Insufficient classes** — fewer than 2 classes for classification

## Pipeline Position

```
Planner Agent → Dataset Agent → ★ Sanity Agent ★ → Trainer Agent → Evaluation → Deployment
  (8001)          (8002)            (8004)            (8003)
                      │                 │
              status: pending_sanity    status: pending_training
```

## How It Works

1. **Polls** Supabase for projects with `status = 'pending_sanity'` every 10s
2. **Downloads** the dataset `.zip` from GCS
3. **Extracts** and discovers the class directory structure (train/val/test splits)
4. **Inspects** up to 50 images per class for corruption, blur, and resolution
5. **Computes** class distribution and imbalance ratio
6. **Stores** a full sanity report in the project's `metadata.sanity_report` JSON
7. **Advances** the project to `pending_training` (pass) or `failed` (fail)

## Setup

```bash
cd Sanity-Agent/agent
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements.txt
cp .env.example .env         # Fill in your credentials
python main.py
```

## Configuration

Environment variables (with defaults):

| Variable | Default | Description |
|----------|---------|-------------|
| `SUPABASE_URL` | — | Supabase project URL |
| `SUPABASE_KEY` | — | Supabase service role key |
| `GCP_BUCKET_NAME` | — | GCS bucket name |
| `GOOGLE_APPLICATION_CREDENTIALS` | — | Path to GCP credentials JSON |
| `POLL_INTERVAL_SECONDS` | `10` | Polling interval in seconds |
| `IMBALANCE_RATIO_THRESHOLD` | `10.0` | Max acceptable class imbalance ratio |
| `MIN_IMAGES_PER_CLASS` | `5` | Minimum images per class to issue warning |
| `MIN_RESOLUTION` | `16` | Minimum width/height in pixels |
| `BLUR_VARIANCE_THRESHOLD` | `50.0` | Laplacian variance threshold for blur |
| `MAX_CORRUPT_PERCENT` | `10.0` | Hard fail if corruption exceeds this % |
| `MAX_BLURRY_PERCENT` | `30.0` | Warning if blur exceeds this % |

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/agents/sanity/start` | Manually trigger sanity check (`{project_id}`) |
| `GET` | `/agents/sanity/status/{project_id}` | Get sanity logs and report |
| `GET` | `/health` | Health check |
| `POST` | `/agents/sanity/polling/start` | Start auto-polling |
| `POST` | `/agents/sanity/polling/stop` | Stop auto-polling |

## Sanity Report Format

The report is stored in `projects.metadata.sanity_report` as JSON:

```json
{
  "passed": true,
  "total_images": 5000,
  "images_checked": 500,
  "num_classes": 5,
  "class_distribution": {"cat": 1100, "dog": 1050, "bird": 980, "fish": 950, "snake": 920},
  "splits_found": ["train", "val"],
  "corrupt_count": 2,
  "corrupt_percent": 0.4,
  "blurry_count": 15,
  "blurry_percent": 3.0,
  "tiny_count": 0,
  "imbalance_ratio": 1.2,
  "avg_resolution": "224x224",
  "warnings": [],
  "errors": [],
  "corrupt_files": ["train/cat/img_0042.jpg", "train/dog/img_0517.jpg"]
}
```

## Port

**8004** (configurable in `main.py`)
