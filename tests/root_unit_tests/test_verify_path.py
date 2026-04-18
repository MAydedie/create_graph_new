# 验证扫描的正确路径
import sys
from pathlib import Path

PROJECT_ROOT = Path(r"D:\代码仓库生图\create_graph")
sys.path.insert(0, str(PROJECT_ROOT))

from llm.agent.agents.orchestrator import Orchestrator

orch = Orchestrator(verbose=True)

user_goal = r"只为D:\代码仓库生图\create_graph\test_sandbox下的所有函数生成测试文件"

result = orch._scan_files_from_goal(user_goal)

print(f"\n扫描的路径: {result.get('paths')}")
print(f"源文件数量: {len(result.get('source_files', []))}")
print(f"测试文件数量: {len(result.get('test_files', []))}")

print(f"\n前20个源文件:")
for f in result.get('source_files', [])[:20]:
    print(f"  - {f}")

print(f"\nfile_structure 内容预览:")
fs = result.get("file_structure", "")
print(fs[:2000] if len(fs) > 2000 else fs)
