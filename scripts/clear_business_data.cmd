@echo off
setlocal EnableExtensions
chcp 65001 >nul
set "ROOT=%~dp0.."
set "PYTHON=%ROOT%\.venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
call "%PYTHON%" "%~dp0clear_business_data.py" --yes %*
set "EXIT_CODE=%ERRORLEVEL%"
echo.
if "%EXIT_CODE%"=="0" (
  echo Done.
) else (
  echo Failed with code %EXIT_CODE%.
)
if not defined CMD_CLEAR_DATA_NOPAUSE pause
exit /b %EXIT_CODE%
