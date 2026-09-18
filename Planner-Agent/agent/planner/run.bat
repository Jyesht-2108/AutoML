@echo off
REM Quick start script for Planner Agent (Windows)

echo 🧠 Starting Planner Agent...

REM Check if .env exists
if not exist .env (
    echo ⚠️  .env file not found. Copying from .env.example...
    copy .env.example .env
    echo 📝 Please edit .env with your credentials before running again.
    exit /b 1
)

REM Check if venv exists
if not exist venv (
    echo 📦 Creating virtual environment...
    python -m venv venv
)

REM Activate venv
call venv\Scripts\activate.bat

REM Install dependencies
echo 📥 Installing dependencies...
pip install -r requirements.txt

REM Run the agent
echo 🚀 Starting Planner Agent on port 8001...
python main.py
