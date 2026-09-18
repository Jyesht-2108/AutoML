# 🚀 START HERE - Planner Agent Quick Guide

## ✅ What's Working

Your Planner Agent (architecture1.md) is **fully functional** and ready to use!

## 🎯 How to Use (3 Simple Ways)

### 1️⃣ Quick Submit (Easiest - One Command)

```bash
py quick_submit.py "Train a model to detect plant diseases"
```

**Result:** Project created instantly and sent to Supabase with `status='pending_dataset'`

### 2️⃣ Interactive Mode (Best for Testing)

```bash
py auto_planner.py
```

Then type prompts one by one:
```
💬 Enter your prompt: Train a tomato disease classifier
✅ SUCCESS! Project Created...

💬 Enter your prompt: Build a chest X-ray detector
✅ SUCCESS! Project Created...
```

### 3️⃣ Batch Processing (Multiple at Once)

```bash
py batch_process.py
```

Processes 5 example prompts automatically. Edit the file to add your own.

## 🔄 The Automation Flow

```
YOU TYPE:
"Train a model to detect wheat rust disease"
         ↓
PLANNER AGENT (architecture1.md):
✓ Gemini LLM parses intent
✓ Creates structured plan
✓ Stores in Supabase: status='pending_dataset'
         ↓
DATASET AGENT (architecture2.md):
✓ Automatically picks up project
✓ Downloads dataset from Kaggle
✓ Uploads to GCP
✓ Updates status='pending_training'
         ↓
TRAINING AGENT (architecture3.md):
✓ Automatically picks up project
✓ Trains PyTorch model
✓ Uploads model to GCP
✓ Updates status='pending_evaluation'
         ↓
EVALUATION AGENT (architecture4.md):
✓ Automatically evaluates model
✓ Computes metrics
✓ Updates status='completed'
         ↓
DONE! ✨
```

## 📝 Example Prompts

Try these:

```bash
# Plant diseases
py quick_submit.py "Train a model to classify tomato leaf diseases"
py quick_submit.py "Detect wheat rust from leaf images"
py quick_submit.py "Build a corn disease classifier"

# Medical imaging
py quick_submit.py "Build a chest X-ray pneumonia detector"
py quick_submit.py "Classify skin cancer from dermoscopy images"
py quick_submit.py "Detect brain tumors from MRI scans"

# Animals
py quick_submit.py "Create a cat vs dog classifier"
py quick_submit.py "Detect different bird species"
py quick_submit.py "Classify dog breeds from photos"

# Agriculture
py quick_submit.py "Identify crop diseases from drone images"
py quick_submit.py "Detect fruit ripeness from photos"
py quick_submit.py "Classify weed species in fields"
```

## ✅ Verification

### Check in Supabase

After submitting, verify in Supabase:

```sql
-- View all projects
SELECT id, name, status, created_at 
FROM projects 
ORDER BY created_at DESC;

-- View pending projects (waiting for Dataset Agent)
SELECT id, name, status 
FROM projects 
WHERE status = 'pending_dataset';
```

### Check via API

```bash
# Get project details
curl http://localhost:8001/agents/planner/project/{project_id}
```

## 🎬 Complete Demo

```bash
# Terminal 1: Start Planner Agent
py main.py

# Terminal 2: Submit a prompt
py quick_submit.py "Train a model for plant disease detection"

# Result:
✅ SUCCESS!
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Project Name: Plant Disease Detector
Project ID: abc-123-def
Status: pending_dataset
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔄 Dataset Agent will pick this up automatically!
```

## 🔗 Integration with Your Teammates

### For Dataset Agent (Member 2)

Your teammate's Dataset Agent should poll Supabase:

```python
# In their agent code
while True:
    # Get projects with status='pending_dataset'
    projects = supabase.table("projects")\
        .select("*")\
        .eq("status", "pending_dataset")\
        .execute()
    
    for project in projects.data:
        # Process the project
        process_dataset(project)
        
        # Update status when done
        supabase.table("projects")\
            .update({"status": "pending_training"})\
            .eq("id", project["id"])\
            .execute()
    
    time.sleep(10)  # Check every 10 seconds
```

### Status Flow

```
pending_dataset  → Dataset Agent processes
pending_training → Training Agent processes
pending_evaluation → Evaluation Agent processes
completed → Done!
```

## 📊 What Gets Created

Each prompt creates a complete project plan:

```json
{
  "name": "Tomato Leaf Disease Classifier",
  "task_type": "image_classification",
  "framework": "pytorch",
  "dataset_source": "kaggle",
  "search_keywords": ["tomato leaf disease", "plantvillage"],
  "preferred_model": "resnet18",
  "target_metric": "accuracy",
  "target_value": 0.9,
  "max_dataset_size_gb": 50,
  "status": "pending_dataset"
}
```

## 🐛 Troubleshooting

### "Cannot connect to Planner Agent"

Start the agent:
```bash
py main.py
```

### "User ID not found"

Create test user:
```bash
py create_test_user.py
```

### Projects not picked up by Dataset Agent

1. Check projects exist in Supabase with `status='pending_dataset'`
2. Verify Dataset Agent is running and polling
3. Check Dataset Agent is looking at correct table

## 📚 Files Overview

- `main.py` - Main Planner Agent service (keep running)
- `quick_submit.py` - Submit single prompt (easiest)
- `auto_planner.py` - Interactive mode (for testing)
- `batch_process.py` - Process multiple prompts
- `test_manual.py` - Manual testing
- `create_test_user.py` - Create test user
- `AUTOMATION.md` - Detailed automation guide

## 🎯 Next Steps

1. ✅ **You're Done!** Planner Agent is complete
2. ⏭️ **Dataset Agent** (Member 2) should poll for `pending_dataset`
3. ⏭️ **Training Agent** (Member 3) should poll for `pending_training`
4. ⏭️ **Evaluation Agent** (Member 4) should poll for `pending_evaluation`

## 🎉 Success!

You can now:
- ✅ Submit prompts in plain English
- ✅ Gemini automatically parses intent
- ✅ Projects stored in Supabase
- ✅ Ready for Dataset Agent to pick up
- ✅ Full pipeline automation working

**Just type your prompt and watch the magic happen!** 🚀

---

**Quick Commands:**
```bash
# Single prompt
py quick_submit.py "Your prompt here"

# Interactive
py auto_planner.py

# Batch
py batch_process.py
```
