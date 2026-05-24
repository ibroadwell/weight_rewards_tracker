@echo off
REM Build a Windows executable for the Weight Rewards Tracker.
REM The executable will be placed in the dist\main folder.

set PYTHON=%~dp0app_env\Scripts\python.exe
if not exist "%PYTHON%" (
  echo Python interpreter not found at %PYTHON%
  exit /b 1
)

echo Installing PyInstaller in the virtual environment...
"%PYTHON%" -m pip install pyinstaller
if errorlevel 1 (
  echo Failed to install PyInstaller.
  exit /b 1
)

set SPEC_FILE=%~dp0main.spec
set DB_FILE=%~dp0weight_rewards.db
set ADD_DATA=
if exist "%DB_FILE%" (
  set ADD_DATA=--add-data "%DB_FILE%;."
)

echo Packaging application...
"%PYTHON%" -m PyInstaller --noconfirm --onedir --windowed %ADD_DATA% "%~dp0main.py"
if errorlevel 1 (
  echo PyInstaller failed.
  exit /b 1
)

echo Build complete. See dist\main\main.exe
pause
