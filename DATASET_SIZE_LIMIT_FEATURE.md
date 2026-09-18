# 📦 Dataset Size Limit Feature

## 🎯 Overview

Users can now specify dataset size limits in their prompts! The system will automatically extract the size limit and only select datasets within that limit.

## ✨ How It Works

### User Input Examples:

```
✅ "Train a plant disease classifier with dataset not more than 1GB"
✅ "Create a flower classifier, dataset under 500MB"
✅ "Build a cat vs dog model, max 2GB dataset"
✅ "Train a skin cancer detector with dataset less than 800MB"
```

### What Happens:

1. **Planner Agent** extracts size limit from user message
2. **Converts MB to GB** automatically (500MB → 0.5GB)
3. **Stores in project metadata** as `max_dataset_size_gb`
4. **Dataset Agent** filters Kaggle datasets by size
5. **Frontend displays** the size limit on project card

## 🔧 Implementation Details

### 1. Planner Agent (Gemini AI)

**Updated Prompt:**
- Extracts size mentions like "not more than 1GB", "under 500MB", "max 2GB"
- Converts MB to GB automatically
- Defaults to 50GB if no size mentioned

**Examples:**
```
Input: "Train a plant disease classifier with dataset not more than 1GB"
Output: { ..., "max_dataset_size_gb": 1 }

Input: "Create a flower classifier, dataset under 500MB"
Output: { ..., "max_dataset_size_gb": 0.5 }

Input: "Build a cat vs dog model" (no size mentioned)
Output: { ..., "max_dataset_size_gb": 50 }
```

### 2. Dataset Agent

**Filtering Logic:**
```python
# Gets max_size from project metadata
max_size = project.get("metadata", {}).get("max_dataset_size_gb", 50)

# Filters datasets during search
for dataset in datasets:
    size_gb = dataset.totalBytes / (1024**3)
    
    # Skip if too large
    if size_gb > max_size:
        continue
```

**Logs:**
- "Searching for dataset with keywords: [...], max size: 1GB"
- "🔍 Searching for datasets (max 1GB)..."

### 3. Frontend Display

**Project Card:**
- Shows size limit badge if < 50GB
- Yellow badge: "📦 Max 1GB"
- Only displays when user specified a limit

**Example:**
```
┌──────────────────────────┐
│ Plant Disease Classifier │
│ [Pending Dataset] [PyTorch]│
│ ████░░░░░░ 25%           │
│                          │
│ Keywords:                │
│ [plant] [disease]        │
│                          │
│ Dataset Size Limit:      │
│ 📦 Max 1GB               │
│                          │
│ [View Details]           │
└──────────────────────────┘
```

## 🧪 Testing

### Test 1: With Size Limit
```
User: "Train a plant disease classifier with dataset not more than 1GB"
```

**Expected:**
- ✅ Project created
- ✅ Metadata shows: `max_dataset_size_gb: 1`
- ✅ Dataset Agent searches with 1GB limit
- ✅ Only datasets ≤ 1GB are considered
- ✅ Frontend shows "📦 Max 1GB" badge

### Test 2: MB to GB Conversion
```
User: "Create a flower classifier, dataset under 500MB"
```

**Expected:**
- ✅ Metadata shows: `max_dataset_size_gb: 0.5`
- ✅ Dataset Agent searches with 0.5GB limit
- ✅ Frontend shows "📦 Max 0.5GB" badge

### Test 3: No Size Limit
```
User: "Train a cat vs dog classifier"
```

**Expected:**
- ✅ Metadata shows: `max_dataset_size_gb: 50` (default)
- ✅ Dataset Agent searches with 50GB limit
- ✅ Frontend does NOT show size badge (default)

## 📊 Size Conversion Table

| User Says | Extracted Value | In GB |
|-----------|----------------|-------|
| "500MB" | 500MB | 0.5GB |
| "1GB" | 1GB | 1GB |
| "2.5GB" | 2.5GB | 2.5GB |
| "800MB" | 800MB | 0.8GB |
| "100MB" | 100MB | 0.1GB |
| (no mention) | default | 50GB |

## 🎯 Benefits

1. **User Control** - Users can specify their storage/bandwidth limits
2. **Faster Downloads** - Smaller datasets download quicker
3. **Resource Management** - Prevents downloading huge datasets
4. **Flexibility** - Works with any size (MB or GB)
5. **Smart Defaults** - 50GB default if not specified

## 📝 Keywords That Work

The Planner Agent recognizes these phrases:
- "not more than X"
- "under X"
- "max X"
- "less than X"
- "maximum X"
- "up to X"
- "within X"

Where X can be:
- "500MB", "1GB", "2.5GB", etc.

## 🔍 How Dataset Agent Filters

```python
# Example: User wants max 1GB

datasets = api.dataset_list(search="plant disease")
# Returns: [5GB, 0.8GB, 2GB, 0.5GB, 10GB, 0.3GB]

filtered = []
for dataset in datasets:
    if dataset.size_gb <= 1:  # Only keep ≤ 1GB
        filtered.append(dataset)
# Result: [0.8GB, 0.5GB, 0.3GB]

# Then ranks by relevance and downloads best match
```

## ✅ Files Modified

### Planner Agent
- `Planner-Agent/agent/planner/main.py`
  - Updated `build_gemini_prompt()` with size extraction rules
  - Added examples for size limit extraction

### Dataset Agent
- `Dataset_Agent/agents/dataset/main.py`
  - Added size limit to log messages
  - Added user notification with size limit

### Frontend
- `frontend/src/components/ProjectCard.jsx`
  - Added size limit badge display
  - Shows only when limit < 50GB

## 🎉 Result

Users can now control dataset size by simply mentioning it in their prompt! The system intelligently extracts, converts, and applies the limit throughout the pipeline.

**Example Flow:**
```
User: "Train a plant disease classifier with dataset not more than 1GB"
    ↓
Planner Agent: Extracts "1GB" → max_dataset_size_gb: 1
    ↓
Dataset Agent: Searches Kaggle, filters to ≤ 1GB
    ↓
Downloads: Only datasets within 1GB limit
    ↓
Frontend: Shows "📦 Max 1GB" badge
```

---

**Status:** ✅ Feature Complete and Ready to Use!
