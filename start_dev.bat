@echo off
REM ---------------------------------------------------------------------------
REM rdgen local development launcher.
REM
REM This script contains NO secrets. Configuration (including the GitHub PAT)
REM lives in the .env file next to this script, which is never committed.
REM Run setup_dev.bat once to create it.
REM ---------------------------------------------------------------------------
setlocal enabledelayedexpansion
cd /d "%~dp0"

REM ---- read RDGEN_PORT / RDGEN_HOST from .env (fall back to defaults) ----
set "RDGEN_PORT=8000"
set "RDGEN_HOST=127.0.0.1"
if exist ".env" (
  for /f "usebackq tokens=1,* delims==" %%a in (".env") do (
    set "KEY=%%a"
    set "VAL=%%b"
    set "VAL=!VAL:"=!"
    if /i "!KEY!"=="RDGEN_PORT" set "RDGEN_PORT=!VAL!"
    if /i "!KEY!"=="RDGEN_HOST" set "RDGEN_HOST=!VAL!"
  )
)

echo [rdgen] host=!RDGEN_HOST! port=!RDGEN_PORT!

REM ---- warn when the GitHub credentials are missing ----
if not exist ".env" (
  echo.
  echo [rdgen] WARNING: .env not found - GitHub builds will fail.
  echo [rdgen] Run setup_dev.bat to create it.
  echo.
) else (
  findstr /b /c:"GHBEARER=github_pat_" ".env" >nul 2>&1
  if errorlevel 1 (
    echo [rdgen] WARNING: GHBEARER looks empty in .env - GitHub builds will fail.
  )
)

REM ---- free the port ----
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :!RDGEN_PORT! ^| findstr LISTENING') do (
  echo [rdgen] stopping PID %%a on port !RDGEN_PORT!
  taskkill /F /PID %%a >nul 2>&1
)

if exist ".venv\Scripts\activate.bat" call .venv\Scripts\activate.bat

echo [rdgen] starting server on http://!RDGEN_HOST!:!RDGEN_PORT!/ ...
python manage.py runserver !RDGEN_HOST!:!RDGEN_PORT!

pause
