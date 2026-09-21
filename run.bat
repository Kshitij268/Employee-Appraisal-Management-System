@echo off
echo ============================================================
echo   Starting Employee Appraisal Management System (EAMS)...
echo ============================================================

if not exist "venv\Scripts\activate.bat" (
    echo [ERROR] Virtual environment not found. Please run setup.bat first.
    pause
    exit /b 1
)

call venv\Scripts\activate.bat
python app.py
pause
