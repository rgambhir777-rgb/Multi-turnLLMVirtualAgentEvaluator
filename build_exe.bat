@echo off
REM Build a single-file Windows executable: dist\AgentProof.exe
REM Requires the virtual environment created by start.bat (run start.bat once first).
REM Node.js is NOT needed: the built frontend (frontend\dist) is already in the repository.
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo  Run start.bat once first to create the virtual environment.
  pause
  exit /b 1
)
if not exist "frontend\dist\index.html" (
  echo  frontend\dist is missing. Build it with: cd frontend ^&^& npm install ^&^& npm run build
  pause
  exit /b 1
)

echo  Installing PyInstaller ...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q pyinstaller==6.16.0 || goto :fail

echo  Building dist\AgentProof.exe (takes a few minutes) ...
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean agentproof.spec || goto :fail

echo.
echo  Done: dist\AgentProof.exe
echo  Copy it anywhere and double-click it. It creates data\ and .env next to itself.
exit /b 0

:fail
echo.
echo  Build failed. See the messages above.
pause
exit /b 1
