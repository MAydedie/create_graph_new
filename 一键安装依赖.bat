@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo [错误] 依赖安装失败
  pause
  exit /b 1
)
echo 依赖安装完成
pause
endlocal
