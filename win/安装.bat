@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title GPT-SoVITS Installer

echo ============================================================
echo   GPT-SoVITS Windows installer (lightweight package)
echo   Needs internet: downloads Python deps and models (~4GB)
echo ============================================================
echo.

set "PY="
call :find_python
if not defined PY call :install_python
if not defined PY (
  echo [X] Python is still not available. Please install Python 3.10 manually
  echo     from https://www.python.org/downloads/windows/
  echo     ^(remember to check "Add python.exe to PATH"^) and run this again.
  pause
  exit /b 1
)

echo Using Python: %PY%
echo.
%PY% "%~dp0install.py" %*
set RC=%ERRORLEVEL%
echo.
if not "%RC%"=="0" (
  echo [X] Installer exited with code %RC%.
  echo     Please copy ALL the output above and send it back for troubleshooting.
) else (
  echo [OK] Install finished.
)
pause
endlocal
exit /b 0

:find_python
if defined PY exit /b 0
py -3.11 -c "import sys" >nul 2>&1 && set "PY=py -3.11"
if defined PY exit /b 0
py -3.10 -c "import sys" >nul 2>&1 && set "PY=py -3.10"
if defined PY exit /b 0
py -3.12 -c "import sys" >nul 2>&1 && set "PY=py -3.12"
if defined PY exit /b 0
py -3.13 -c "import sys" >nul 2>&1 && set "PY=py -3.13"
if defined PY exit /b 0
py -3 -c "import sys" >nul 2>&1 && set "PY=py -3"
if defined PY exit /b 0
python -c "import sys" >nul 2>&1 && set "PY=python"
exit /b 0

:install_python
echo [!] Python not found. Downloading Python 3.10.11 (about 28MB) ...
echo     If a UAC / installer window appears, please follow it.
echo.
curl -L -o "%TEMP%\python-3.10.11-amd64.exe" https://www.python.org/ftp/python/3.10.11/python-3.10.11-amd64.exe
if errorlevel 1 (
  echo [X] Download failed.
  exit /b 0
)
"%TEMP%\python-3.10.11-amd64.exe" /passive InstallAllUsers=0 PrependPath=1 Include_test=0 Include_launcher=1
echo     Waiting for the Python installer to finish ...
timeout /t 25 >nul
set "PY=py -3.10"
py -3.10 -c "import sys" >nul 2>&1 || set "PY="
exit /b 0
