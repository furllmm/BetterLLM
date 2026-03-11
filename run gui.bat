@echo off
setlocal

:: Check if virtual environment exists
if not exist .venv (
    echo [ERROR] Virtual environment not found. Please run 'setup.bat' first.
    pause
    exit /b 1
)

:: Activate virtual environment and run the app in GUI mode
echo [INFO] Starting BetterLLM GUI...
call .venv\Scripts\activate
python main.py %*

if %errorlevel% neq 0 (
    echo [ERROR] Application exited with error code %errorlevel%
    pause
)

endlocal
