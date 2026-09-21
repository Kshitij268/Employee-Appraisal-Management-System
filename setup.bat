@echo off
setlocal enabledelayedexpansion

echo ============================================================
echo   Employee Appraisal Management System (EAMS) Setup
echo ============================================================
echo.

:: 1. Find Python executable
set "PY_CMD="
where python >nul 2>&1
if %ERRORLEVEL% equ 0 (
    set "PY_CMD=python"
) else (
    where py >nul 2>&1
    if !ERRORLEVEL! equ 0 (
        set "PY_CMD=py"
    ) else (
        if exist "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" (
            set "PY_CMD=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
        ) else (
            echo [ERROR] Python was not found in standard PATH or %LOCALAPPDATA%\Programs\Python\Python313.
            echo Please install Python 3.9+ from python.org and check "Add python.exe to PATH".
            pause
            exit /b 1
        )
    )
)

echo [1/4] Using Python: !PY_CMD!
!PY_CMD! --version

:: 2. Create virtual environment if missing
if not exist "venv\Scripts\activate.bat" (
    echo [2/4] Creating virtual environment (venv)...
    !PY_CMD! -m venv venv
    if %ERRORLEVEL% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo Virtual environment created successfully.
) else (
    echo [2/4] Virtual environment (venv) already exists.
)

:: 3. Install dependencies
echo [3/4] Installing dependencies from requirements.txt...
call venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Failed to install packages.
    pause
    exit /b 1
)

:: 4. Initialize Database
echo [4/4] Initializing MySQL database and seeding initial accounts...
python -c "import database as db; db.init_db(); db.seed_db()"
if %ERRORLEVEL% neq 0 (
    echo [NOTE] Database initialization notice. If MySQL was not running, start MySQL and run:
    echo        python -c "import database as db; db.init_db(); db.seed_db()"
)

echo.
echo ============================================================
echo   EAMS Setup Complete!
echo   To start the application, run: run.bat
echo   Or run: .\venv\Scripts\activate  then  python app.py
echo ============================================================
echo.
pause
