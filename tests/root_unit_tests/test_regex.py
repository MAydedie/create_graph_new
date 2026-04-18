# 测试正则表达式
import re

user_goal = r"只为D:\代码仓库生图\create_graph\test_sandbox下的所有函数生成测试文件"

print(f"用户目标: {user_goal}")
print(f"目标字符串长度: {len(user_goal)}")

# 当前使用的模式
patterns = [
    (r'([A-Za-z]:\\[^\s"<>|*?]+)', "Windows backslash pattern"),
    (r'([A-Za-z]:/[^\s"<>|*?]+)', "Windows forward slash pattern"),
]

for pattern, name in patterns:
    matches = re.findall(pattern, user_goal)
    print(f"\n{name}:")
    print(f"  Pattern: {pattern}")
    print(f"  Matches: {matches}")

# 检查路径中的实际字符
print("\n\n检查字符串中的路径字符:")
for i, char in enumerate(user_goal):
    if char == '\\' or char == ':':
        print(f"  位置 {i}: '{char}' (ord={ord(char)})")
