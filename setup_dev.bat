@echo off
REM ---------------------------------------------------------------------------
REM rdgen first-run configuration wizard.
REM
REM Creates the local ".env" file that holds the GitHub PAT and the other
REM settings. The .env file is git-ignored and is never committed.
REM Run start_dev.bat afterwards to launch the server.
REM
REM The prompts are implemented in setup_env.py because cmd's "set /p"
REM swallows the whole stdin buffer, which breaks piped input.
REM ---------------------------------------------------------------------------
setlocal enabledelayedexpansion
cd /d "%~dp0"

if exist ".env" (
  echo.
  echo [rdgen] .env already exists.
  set /p OVERWRITE="Overwrite it with fresh values? [y/N]: "
  if /i not "!OVERWRITE!"=="y" (
    echo [rdgen] keeping the existing .env - nothing changed.
    goto :done
  )
)

set "PY="
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

"%PY%" "%~dp0setup_env.py"
if errorlevel 1 (
  echo [rdgen] setup failed.
  goto :done
)

REM ---- restrict access to the current user only ----
icacls ".env" /inheritance:r /grant:r "%USERNAME%:F" >nul 2>&1

:done
pause
