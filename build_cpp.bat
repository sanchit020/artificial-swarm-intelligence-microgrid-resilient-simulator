@echo off
setlocal
cd /d "%~dp0"
where cmake >nul 2>nul
if errorlevel 1 (
  echo ERROR: CMake was not found. Install CMake and the Visual Studio C++ build tools.
  pause
  exit /b 1
)
cmake -S . -B build
if errorlevel 1 goto :error
cmake --build build --config Release --parallel
if errorlevel 1 goto :error
echo C++ ASI engine built successfully.
exit /b 0
:error
echo C++ build failed. Check the compiler/CMake output above.
pause
exit /b 1
