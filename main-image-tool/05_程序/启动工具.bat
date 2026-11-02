@echo off
chcp 65001 >nul
cd /d "%~dp0"
"C:\Users\user\AppData\Local\Programs\Python\Python310\python.exe" start_app.py
if errorlevel 1 (
  echo.
  echo 程序异常退出，请把上面的错误信息反馈给开发。
  pause
)
