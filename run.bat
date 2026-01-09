@echo off
chcp 65001 >nul
echo.
echo ========================================
echo  代码结构分析工具 - Web应用启动
echo ========================================
echo.
echo 正在启动Flask应用...
echo.
echo 浏览器访问地址: http://127.0.0.1:5000
echo.
echo 按 Ctrl+C 停止应用
echo ========================================
echo.

python app.py
pause
