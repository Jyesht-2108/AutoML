@echo off
echo Starting Deployment Agent (Phase 3 - Model Packaging)...
cd Deployment-Agent\agent

if not exist venv (
    echo Creating virtual environment...
    python -m venv venv
)

echo Activating virtual environment...
call venv\Scripts\activate.bat

echo Installing requirements...
pip install -r requirements.txt

echo.
echo Starting FastAPI server...
uvicorn main:app --host 0.0.0.0 --port 8007 --reload
