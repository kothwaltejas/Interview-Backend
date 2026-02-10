@echo off
echo 🚀 Starting Intervu AI Backend...

REM Create virtual environment if it doesn't exist
if not exist "venv" (
    echo 📦 Creating virtual environment...
    python -m venv venv
)

REM Activate virtual environment
echo 🔧 Activating virtual environment...
call venv\Scripts\activate

REM Install dependencies
echo 📚 Installing dependencies...
pip install -r requirements.txt

REM Check if .env file exists
if not exist ".env" (
    echo ⚠️  .env file not found. Please copy .env.example to .env and configure your API keys.
    pause
    exit /b 1
)

REM Start the server
echo 🌟 Starting FastAPI server...
cd src
python main.py

pause