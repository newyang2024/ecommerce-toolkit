@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

set "APP_PYTHONW="
if exist "%~dp0.venv\Scripts\pythonw.exe" set "APP_PYTHONW=%~dp0.venv\Scripts\pythonw.exe"
for /f "delims=" %%I in ('where pythonw.exe 2^>nul') do if not defined APP_PYTHONW set "APP_PYTHONW=%%I"

if defined APP_PYTHONW (
    start "Marketing Calendar" /D "%~dp0" "%APP_PYTHONW%" -m marketing_calendar.gui_entry
    exit /b 0
)

python main.py gui
if errorlevel 1 (
    echo.
    echo The application could not start. See logs\gui_startup_error.log or README.md.
    pause
)
