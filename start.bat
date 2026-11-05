@echo off
REM AgentProof - one-command start for Windows.
REM Creates a virtual environment on first run, installs dependencies, starts the
REM server and opens http://localhost:8000 in your browser.
setlocal
cd /d "%~dp0"
title AgentProof

set "PY="
for %%V in (3.12 3.13 3.11) do (
  if not defined PY (
    py -%%V -c "import sys" >nul 2>&1 && set "PY=py -%%V"
  )
)
if not defined PY (
  python -c "import sys; sys.exit(0 if (3,11) <= sys.version_info[:2] < (3,14) else 1)" >nul 2>&1 && set "PY=python"
)
if not defined PY (
  echo.
  echo  Python 3.11, 3.12 or 3.13 is required but was not found.
  echo  Install it from https://www.python.org/downloads/ ^(tick "Add python.exe to PATH"^) and run start.bat again.
  echo.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo  Creating virtual environment with %PY% ...
  %PY% -m venv .venv || goto :fail
)

fc /b requirements.txt .venv\requirements.installed >nul 2>&1
if errorlevel 1 (
  echo  Installing dependencies ^(first run takes a minute or two^) ...
  ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q --upgrade pip || goto :fail
  ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt || goto :fail
  copy /y requirements.txt .venv\requirements.installed >nul
)

if not exist ".env" if exist ".env.example" copy /y ".env.example" ".env" >nul

".venv\Scripts\python.exe" run.py
if errorlevel 1 goto :fail
exit /b 0

:fail
echo.
echo  AgentProof could not start. See the messages above.
pause
exit /b 1
