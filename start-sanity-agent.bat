@echo off
echo ============================================
echo  Starting Data Sanity Auditor Agent (Port 8004)
echo ============================================

cd /d "%~dp0Sanity-Agent\agent"

if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate
) else (
    echo [WARNING] No virtual environment found.
    echo Creating one now...
    python -m venv venv
    call venv\Scripts\activate
    pip install -r requirements.txt
)

echo Starting Data Sanity Auditor on port 8004...
python main.py
