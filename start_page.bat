@echo off
cd /d "%~dp0"
rem The filings, rules and reports are UTF-8; see utf8_mode.py.
set PYTHONUTF8=1
if exist ".venv-desk\Scripts\python.exe" (
  ".venv-desk\Scripts\python.exe" page.py
) else (
  echo Create .venv-desk with Python 3.13 and install requirements-pipeline.txt first.
)
pause
