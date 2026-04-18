# 最小化测试问题 - 节省 Token
#
# 原问题: "为D:\代码仓库生图\create_graph\test_sandbox\finance_cli下这个文件夹生成测试文件"
# 太大了！包含 19+ 个 Python 文件，导致 31 个步骤
#
# 推荐的最小化问题:

问题1（推荐 - 只有 2 个文件）:
"为D:\代码仓库生图\create_graph\test_sandbox\finance_cli\finance_cli\commands目录下的所有.py文件生成测试"

预计步骤数: ~5 步
文件列表:
  - __init__.py (跳过，无需测试)
  - stock.py → test_stock.py

---

问题2（3 个核心文件）:
"为D:\代码仓库生图\create_graph\test_sandbox\finance_cli\finance_cli目录下的calculations.py和stock.py生成单元测试"

预计步骤数: ~6 步

---

问题3（最简 - 1 个文件）:
"为D:\代码仓库生图\create_graph\test_sandbox\finance_cli\finance_cli\commands\stock.py生成单元测试文件"

预计步骤数: ~3 步

---

备注:
1. 目标目录越小，步骤越少，Token 消耗越低
2. 明确指定文件名比使用"所有函数"更精确
3. 每个源文件（非 __init__.py）通常需要:
   - 1 步读取分析
   - 1 步创建测试文件
   - 1 步验证（最后总的验证）
