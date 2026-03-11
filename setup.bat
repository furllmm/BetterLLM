@echo off
setlocal

echo [INFO] Setting up BetterLLM for Windows...

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found. Install Python 3.10+ and add it to PATH.
    pause
    exit /b 1
)

if not exist .venv (
    echo [INFO] Creating virtual environment...
    python -m venv .venv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
)

call .venv\Scripts\activate

echo [INFO] Upgrading pip/setuptools/wheel...
python -m pip install --upgrade pip setuptools wheel

echo [INFO] Installing dependencies...
pip install -r requirements.txt --prefer-binary
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)

echo [INFO] Setup complete. Use run.bat to start the app.
pause
endlocal
