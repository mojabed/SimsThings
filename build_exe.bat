@echo off
setlocal
cd /d "%~dp0"
set PYTHON_EXE=%~dp0.venv310\Scripts\python.exe
if not exist "%PYTHON_EXE%" (
    set PYTHON_EXE=%~dp0.venv\Scripts\python.exe
)
if not exist "%PYTHON_EXE%" (
    echo Python interpreter not found. Expected .venv310 or .venv.
    exit /b 1
)
"%PYTHON_EXE%" -m PyInstaller --noconfirm --clean build_exe.spec
if errorlevel 1 (
    echo Build failed.
    exit /b 1
)
echo Build complete. Output is in dist\SimsThings.exe
