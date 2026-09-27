@echo off
echo Starting Privacy Agent (Phase 2 - PII Masking)...
cd Privacy-Agent\agent

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
uvicorn main:app --host 0.0.0.0 --port 8005 --reload
