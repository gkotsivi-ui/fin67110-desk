@echo off
rem Starts the desk's page and opens it in your browser. Keep this window open; close it to stop the page.
rem It uses the virtual environment from the README's setup when there is one.
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" page.py
) else (
  where python >nul 2>nul
  if errorlevel 1 (py page.py) else (python page.py)
)
pause
