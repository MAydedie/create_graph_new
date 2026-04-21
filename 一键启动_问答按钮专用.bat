@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

python --version >nul 2>&1
if errorlevel 1 (
  echo [错误] 未检测到 Python
  pause
  exit /b 1
)

if not exist "config\user_runtime_config.json" (
  copy /Y "config\user_runtime_config.example.json" "config\user_runtime_config.json" >nul
  echo 已生成配置文件：config\user_runtime_config.json
  start "" notepad "config\user_runtime_config.json"
  pause
  exit /b 0
)

python "scripts\apply_user_config.py"
if errorlevel 1 (
  echo [错误] 生成 .env 失败
  pause
  exit /b 1
)

set PORT=5123
start "" "http://127.0.0.1:5123/"
python qa_button_app.py

endlocal
