# 直接测试 Orchestrator 扫描器
import sys
from pathlib import Path

PROJECT_ROOT = Path(r"D:\代码仓库生图\create_graph")
sys.path.insert(0, str(PROJECT_ROOT))

from llm.agent.agents.orchestrator import Orchestrator

orch = Orchestrator(verbose=True)

user_goal = r"只为D:\代码仓库生图\create_graph\test_sandbox下的所有函数生成测试文件"

print(f"用户目标: {user_goal}")
print(f"用户目标 repr: {repr(user_goal)}")
print()

result = orch._scan_files_from_goal(user_goal)

print(f"\n结果:")
print(f"  scanned: {result.get('scanned')}")
print(f"  paths: {result.get('paths')}")
print(f"  source_files 数量: {len(result.get('source_files', []))}")
print(f"  source_files: {result.get('source_files', [])[:5]}...")
