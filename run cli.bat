@echo off
setlocal

:: Check if virtual environment exists
if not exist .venv (
    echo [ERROR] Virtual environment not found. Please run 'setup.bat' first.
    pause
    exit /b 1
)

:: Activate virtual environment and run the app in CLI mode
echo [INFO] Starting BetterLLM CLI...
call .venv\Scripts\activate
python main.py --cli %*

if %errorlevel% neq 0 (
    echo [ERROR] Application exited with error code %errorlevel%
    pause
)

endlocal
