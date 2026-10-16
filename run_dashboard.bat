@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
    set "PYTHON=py -3.11"
) else (
    where python >nul 2>nul
    if errorlevel 1 (
        echo ERROR: Python was not found. Install Python 3.11 from https://www.python.org/downloads/ and enable Add Python to PATH.
        pause
        exit /b 1
    )
    set "PYTHON=python"
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating project virtual environment...
    %PYTHON% -m venv .venv
    if errorlevel 1 goto :error
)

echo Installing or checking required packages...
.venv\Scripts\python.exe -m pip install --upgrade pip
if errorlevel 1 goto :error
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto :error

echo Building the C++ ASI engine...
call build_cpp.bat
if errorlevel 1 goto :error

echo Starting ASI Smart Power Grid dashboard...
.venv\Scripts\python.exe -m streamlit run dashboard\app.py
if errorlevel 1 goto :error
exit /b 0

:error
echo.
echo Setup or launch failed. Read the error above and check your Python installation and internet connection.
pause
exit /b 1
