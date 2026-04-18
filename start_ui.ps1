
# 启动前端和后端的自动化脚本
Write-Host "正在启动 AI Agent 系统..." -ForegroundColor Green

# 1. 启动后端 (新建窗口)
Write-Host "1. 启动后端服务器..."
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd 'D:\代码仓库生图\create_graph'; python ui/server.py"

# 2. 启动前端 (新建窗口)
Write-Host "2. 启动前端界面..."
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd 'D:\代码仓库生图\create_graph\ui\frontend'; npm run dev"

Write-Host "✅ 启动命令已发送！请等待两个新窗口出现。" -ForegroundColor Cyan
Write-Host "如果浏览器没有自动打开，请访问: http://localhost:5173" -ForegroundColor Yellow
