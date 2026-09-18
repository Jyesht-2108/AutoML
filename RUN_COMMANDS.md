# Quick Run Commands - AutoML Platform

## 🚀 Start All Services (Run in Separate Terminals)

### Terminal 1: Backend (Node.js + Express)
```bash
cd backend
npm run dev
```
**Port:** `4000` | **URL:** `http://localhost:4000`

---

### Terminal 2: Frontend (React + Vite)
```bash
cd frontend
npm run dev
```
**Port:** `5173` | **URL:** `http://localhost:5173`

---

### Terminal 3: MCP Server (Python FastAPI)
```bash
cd mcp_server
source venv/bin/activate  # Windows: venv\Scripts\activate
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```
**Port:** `8000` | **URL:** `http://localhost:8000`

**Note:** If you get `command not found: uvicorn`, your venv needs dependencies:
```bash
cd mcp_server
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

---

### Terminal 4: Planner Agent (Gemini AI)
```bash
cd Planner-Agent/agent/planner
source myvenv2/bin/activate  # Windows: myvenv2\Scripts\activate
uvicorn main:app --reload --host 0.0.0.0 --port 8001
```
**Port:** `8001` | **URL:** `http://localhost:8001`

---

### Terminal 5: Dataset Agent (Kaggle + GCP)
```bash
cd Dataset_Agent/agents/dataset
source myvenv1/bin/activate  # Windows: myvenv1\Scripts\activate
python main.py
```
**Port:** `8002` | **URL:** `http://localhost:8002`
**Note:** Auto-polling enabled (checks every 10 seconds)

---

### Terminal 6: Training Agent (PyTorch)
```bash
cd Trainer-Agent/agent
source venv/bin/activate  # Windows: venv\Scripts\activate
python main.py
```
**Port:** `8003` | **URL:** `http://localhost:8003`
**Note:** Auto-polling enabled

---

### Terminal 7: Evaluation Agent (Optional)
```bash
cd Evaluation-Agent/agent
source venv/bin/activate  # Windows: venv\Scripts\activate
python main.py
```
**Port:** `8004` | **URL:** `http://localhost:8004`

---

## 🔍 Health Check Commands

Test if all services are running correctly:

```bash
# Backend
curl http://localhost:4000/health

# MCP Server
curl http://localhost:8000/health

# Planner Agent
curl http://localhost:8001/health

# Dataset Agent
curl http://localhost:8002/health

# Training Agent
curl http://localhost:8003/health

# Evaluation Agent
curl http://localhost:8004/health
```

---

## 🛠️ One-Line Commands (macOS/Linux)

### Start Backend
```bash
cd backend && npm run dev
```

### Start Frontend
```bash
cd frontend && npm run dev
```

### Start MCP Server
```bash
cd mcp_server && source venv/bin/activate && uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Start Planner Agent
```bash
cd Planner-Agent/agent/planner && source myvenv2/bin/activate && uvicorn main:app --reload --host 0.0.0.0 --port 8001
```

### Start Dataset Agent
```bash
cd Dataset_Agent/agents/dataset && source myvenv1/bin/activate && python main.py
```

### Start Training Agent
```bash
cd Trainer-Agent/agent && source venv/bin/activate && python main.py
```

---

## 🪟 Windows Batch Commands

### Start Backend
```cmd
cd backend && npm run dev
```

### Start Frontend
```cmd
cd frontend && npm run dev
```

### Start MCP Server
```cmd
cd mcp_server && venv\Scripts\activate && uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Start Planner Agent
```cmd
cd Planner-Agent\agent\planner && myvenv2\Scripts\activate && uvicorn main:app --reload --host 0.0.0.0 --port 8001
```

### Start Dataset Agent
```cmd
cd Dataset_Agent\agents\dataset && myvenv1\Scripts\activate && python main.py
```

### Start Training Agent
```cmd
cd Trainer-Agent\agent && venv\Scripts\activate && python main.py
```

---

## 🔥 Start All at Once (macOS/Linux)

Create a shell script `start-all.sh`:

```bash
#!/bin/bash

# Start all services in background
echo "Starting Backend..."
(cd backend && npm run dev) &

echo "Starting Frontend..."
(cd frontend && npm run dev) &

echo "Starting MCP Server..."
(cd mcp_server && source venv/bin/activate && uvicorn main:app --reload --host 0.0.0.0 --port 8000) &

echo "Starting Planner Agent..."
(cd Planner-Agent/agent/planner && source myvenv2/bin/activate && uvicorn main:app --reload --host 0.0.0.0 --port 8001) &

echo "Starting Dataset Agent..."
(cd Dataset_Agent/agents/dataset && source myvenv1/bin/activate && python main.py) &

echo "Starting Training Agent..."
(cd Trainer-Agent/agent && source venv/bin/activate && python main.py) &

echo "All services started!"
echo "Press Ctrl+C to stop all services"
wait
```

Make it executable and run:
```bash
chmod +x start-all.sh
./start-all.sh
```

---

## 🪟 Start All at Once (Windows)

Create a batch script `start-all.bat`:

```batch
@echo off
echo Starting all services...

start "Backend" cmd /k "cd backend && npm run dev"
start "Frontend" cmd /k "cd frontend && npm run dev"
start "MCP Server" cmd /k "cd mcp_server && venv\Scripts\activate && uvicorn main:app --reload --host 0.0.0.0 --port 8000"
start "Planner Agent" cmd /k "cd Planner-Agent\agent\planner && myvenv2\Scripts\activate && uvicorn main:app --reload --host 0.0.0.0 --port 8001"
start "Dataset Agent" cmd /k "cd Dataset_Agent\agents\dataset && myvenv1\Scripts\activate && python main.py"
start "Training Agent" cmd /k "cd Trainer-Agent\agent && venv\Scripts\activate && python main.py"

echo All services started in separate windows!
```

Run:
```cmd
start-all.bat
```

---

## 🧪 Testing Commands

### Test Planner Agent
```bash
cd Planner-Agent/agent/planner
source myvenv2/bin/activate  # Windows: myvenv2\Scripts\activate
python test_agent.py
```

### Test Dataset Agent
```bash
cd Dataset_Agent/agents/dataset
source myvenv1/bin/activate  # Windows: myvenv1\Scripts\activate
python test_agent.py
```

### Test Full Workflow
```bash
cd Dataset_Agent/agents/dataset
source myvenv1/bin/activate
python test_full_workflow.py
```

### Check Database Status
```bash
cd Dataset_Agent/agents/dataset
source myvenv1/bin/activate
python verify_status_updates.py
```

---

## 🛑 Stop All Services

### macOS/Linux
```bash
# Find and kill all services
pkill -f "npm run dev"
pkill -f "uvicorn"
pkill -f "python main.py"
```

### Windows
```cmd
# Close all CMD windows or use Task Manager
# Or specifically:
taskkill /F /IM node.exe
taskkill /F /IM python.exe
```

---

## 📊 Port Summary

| Service | Port | URL |
|---------|------|-----|
| Frontend | 5173 | http://localhost:5173 |
| Backend | 4000 | http://localhost:4000 |
| MCP Server | 8000 | http://localhost:8000 |
| Planner Agent | 8001 | http://localhost:8001 |
| Dataset Agent | 8002 | http://localhost:8002 |
| Training Agent | 8003 | http://localhost:8003 |
| Evaluation Agent | 8004 | http://localhost:8004 |

---

## ✅ Startup Checklist

Before running services, ensure:

- [ ] All `.env` files are configured
- [ ] Virtual environments are created
- [ ] Dependencies are installed (`npm install` / `pip install -r requirements.txt`)
- [ ] Firebase credentials are in place (`backend/serviceAccount.json`)
- [ ] GCP credentials are configured
- [ ] Kaggle credentials are set (Dataset Agent)
- [ ] Supabase database schema is created
- [ ] PyTorch is installed (Training Agent)

---

## 🔄 Service Dependencies

**Startup Order Recommendation:**

1. **Backend** (Port 4000) - Core API server
2. **MCP Server** (Port 8000) - Orchestrator
3. **Planner Agent** (Port 8001) - Project planning
4. **Dataset Agent** (Port 8002) - Dataset acquisition
5. **Training Agent** (Port 8003) - Model training
6. **Frontend** (Port 5173) - User interface

This order ensures each service's dependencies are available when it starts.

---

## 🐛 Troubleshooting

### Port Already in Use
```bash
# macOS/Linux - Find process using port
lsof -i :4000
lsof -i :5173
lsof -i :8000

# Kill process
kill -9 <PID>

# Windows - Find and kill
netstat -ano | findstr :4000
taskkill /PID <PID> /F
```

### Virtual Environment Issues
```bash
# Recreate virtual environment
cd <service-directory>
rm -rf venv  # or myvenv1, myvenv2
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Module Not Found Errors
```bash
# Reinstall dependencies
pip install -r requirements.txt
# or
npm install
```

---

## 📝 Quick Notes

- **Auto-polling:** Dataset and Training Agents poll automatically every 10 seconds
- **Hot Reload:** All services support hot reload (changes apply automatically)
- **Logs:** Check console output in each terminal for errors
- **Database:** Monitor `agent_logs` table in Supabase for agent activities
- **Frontend:** Access at `http://localhost:5173` after all services are running

---

**Happy Coding! 🚀**
