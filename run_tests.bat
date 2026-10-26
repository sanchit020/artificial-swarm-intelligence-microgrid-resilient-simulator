@echo off
setlocal
cd /d "%~dp0"

echo ========================================================
echo Running C++ Unit Tests (asi_tests)
echo ========================================================
set "CPP_EXE="
if exist "build\Release\asi_tests.exe" set "CPP_EXE=build\Release\asi_tests.exe"
if exist "build\asi_tests.exe" set "CPP_EXE=build\asi_tests.exe"

if defined CPP_EXE (
    "%CPP_EXE%"
    if errorlevel 1 (
        echo ERROR: C++ unit tests failed.
        pause
        exit /b 1
    )
) else (
    echo WARNING: asi_tests executable not found. Run build_cpp.bat first.
)

echo.
echo ========================================================
echo Running Python Test Suite (pytest)
echo ========================================================
if not exist ".venv\Scripts\python.exe" (
    echo Project environment not found. Run run_dashboard.bat first to install dependencies.
    pause
    exit /b 1
)

.venv\Scripts\python.exe -m pytest -v tests
set "TEST_RESULT=%ERRORLEVEL%"
echo.
if "%TEST_RESULT%"=="0" (
    echo All C++ and Python tests passed successfully.
) else (
    echo Some Python tests failed. Review the output above.
)
exit /b %TEST_RESULT%
