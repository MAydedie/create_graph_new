# 调试路径截断逻辑
from pathlib import Path

candidate = r"D:\代码仓库生图\create_graph\test_sandbox下的所有函数生成测试文件"

print(f"原始候选: {candidate}")
print()

normalized = candidate.replace("/", "\\")
parts = normalized.split("\\")

print(f"分解后的部分 ({len(parts)}):")
for i, part in enumerate(parts):
    print(f"  {i}: {part}")

print()
print("逐步截断测试:")
for i in range(len(parts), 1, -1):
    test_path_str = "\\".join(parts[:i])
    test_path = Path(test_path_str)
    exists = test_path.exists()
    is_dir = test_path.is_dir() if exists else False
    print(f"  试 {i}: {test_path_str}")
    print(f"       存在: {exists}, 是目录: {is_dir}")
    if exists and is_dir:
        print(f"       ✓ 找到有效路径!")
        break
