@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  echo Create the Python environment using the README first.
  pause
  exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" -m forge_pdf %*
