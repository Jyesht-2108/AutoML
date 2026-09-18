# AutoML Multi-Agent System - Agent Implementations

This folder contains the implementation of all AI agents for the AutoML pipeline.

## 📁 Structure

```
agent/
├── planner/          # Member 1 - Intent parsing & project planning
├── dataset/          # Member 2 - Dataset discovery & upload (TODO)
├── training/         # Member 3 - Model training (TODO)
└── evaluation/       # Member 4 - Model evaluation (TODO)
```

## 🧠 Planner Agent (✅ Implemented)

**Owner:** Member 1  
**Status:** Complete  
**Port:** 8001

### Features
- Natural language intent parsing using Gemini LLM
- Structured project plan generation
- Supabase integration for persistence
- Automatic user guidance for next steps
- Comprehensive error handling and logging

### Quick Start
```bash
cd planner
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your credentials
python main.py
```

See `planner/README.md` for detailed documentation.

## 🔄 Agent Communication Flow

```
User Message
    ↓
Planner Agent (creates project, status='pending_dataset')
    ↓
Dataset Agent (downloads data, status='pending_training')
    ↓
Training Agent (trains model, status='pending_evaluation')
    ↓
Evaluation Agent (evaluates model, status='completed')
```

All communication happens through Supabase tables - no direct API calls between agents.

## 🗄️ Shared Resources

### Environment Variables
All agents share the same environment variables:
- `SUPABASE_URL` - Supabase project URL
- `SUPABASE_KEY` - Supabase service key
- `GCP_BUCKET_NAME` - Google Cloud Storage bucket
- `GOOGLE_APPLICATION_CREDENTIALS` - GCP service account JSON path
- `GEMINI_API_KEY` - Google Gemini API key (Planner only)
- `LOG_LEVEL` - Logging level (INFO, DEBUG, ERROR)

### Database Tables
- `projects` - Project metadata and status
- `datasets` - Dataset information and GCS URLs
- `models` - Trained model metadata
- `agent_logs` - Agent activity logs
- `messages` - Chat messages
- `users` - User information

## 🚀 Running All Agents

Each agent runs independently on its own port:
- Planner: 8001
- Dataset: 8002 (TODO)
- Training: 8003 (TODO)
- Evaluation: 8004 (TODO)

## 📝 Development Guidelines

1. Each agent is self-contained with its own dependencies
2. Use Pydantic for data validation
3. Log all operations to `agent_logs` table
4. Follow the status-based workflow pattern
5. Handle errors gracefully with user-friendly messages
6. Write unit tests for core functionality

## 🧪 Testing

Each agent includes:
- Unit tests (`test_*.py`)
- Manual testing scripts
- Health check endpoints
- Example requests in README

## 📚 Documentation

Each agent folder contains:
- `README.md` - Setup and usage guide
- `architecture.md` - Detailed design document
- `.env.example` - Environment template
- `requirements.txt` - Python dependencies

## 🔗 Related Documentation

- Main project README: `../docs/README.md`
- Architecture documents: `../docs/architecture*.md`
- Database schema: See `docs/README.md`
