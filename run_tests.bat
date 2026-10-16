@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Project environment not found. Run run_dashboard.bat first to install dependencies.
    pause
    exit /b 1
)

.venv\Scripts\python.exe -m pytest -v tests
set "TEST_RESULT=%ERRORLEVEL%"
echo.
if "%TEST_RESULT%"=="0" (
    echo All tests passed.
) else (
    echo Some tests failed. Review the output above.
)
pause
exit /b %TEST_RESULT%
