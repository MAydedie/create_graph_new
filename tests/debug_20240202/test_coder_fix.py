#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
验证 CoderAgent 增强修复 - 确保测试文件基于实际源代码生成
"""

import sys
import os
import json
import io
from pathlib import Path

# 设置 stdout 编码
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# 确保项目路径
PROJECT_ROOT = Path(r"D:\代码仓库生图\create_graph")
sys.path.insert(0, str(PROJECT_ROOT))

def safe_print(msg):
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode('gbk', errors='replace').decode('gbk'))

def test_coder_create_test_file():
    """测试增强后的 CoderAgent 能否正确生成测试文件"""
    safe_print("=" * 60)
    safe_print("测试：增强后的 CoderAgent 创建测试文件")
    safe_print("=" * 60)
    
    from llm.agent.agents.coder_agent import CoderAgent
    
    coder = CoderAgent(verbose=True)
    
    # 测试步骤：创建测试文件
    step = {
        "step_id": 1,
        "type": "code_change",
        "action": "create_file",
        "target": r"D:\代码仓库生图\create_graph\test_sandbox\finance_cli\tests\test_stock.py",
        "description": "为 stock.py 创建单元测试文件，测试主要函数"
    }
    
    # 构建上下文 - 包含文件结构信息
    context = {
        "workspace_root": str(PROJECT_ROOT / "test_sandbox" / "finance_cli"),
        "file_structure": {
            "scanned": True,
            "paths": [
                str(PROJECT_ROOT / "test_sandbox" / "finance_cli" / "finance_cli" / "commands"),
                str(PROJECT_ROOT / "test_sandbox" / "finance_cli" / "finance_cli"),
            ],
            "source_files": [
                "commands/stock.py",
                "stock.py",
            ],
            "test_files": []
        }
    }
    
    safe_print(f"\n执行步骤: 创建 test_stock.py")
    safe_print(f"目标文件: {step['target']}")
    
    result = coder.execute_step(step, context)
    
    safe_print(f"\n执行结果:")
    safe_print(f"  成功: {result.get('success')}")
    safe_print(f"  摘要: {result.get('summary', '')[:100]}")
    
    if result.get('code_content'):
        content = result['code_content']
        safe_print(f"\n生成的代码长度: {len(content)} 字符")
        
        # 检查关键点
        checks = {
            "导入 get_stock_price": "get_stock_price" in content,
            "导入 format_stock_price": "format_stock_price" in content,
            "不包含 class Stock": "class Stock" not in content,  # 不应该有这个类
            "包含 def test_": "def test_" in content,
        }
        
        safe_print("\n代码质量检查:")
        all_passed = True
        for check_name, passed in checks.items():
            status = "✓" if passed else "✗"
            safe_print(f"  {status} {check_name}")
            if not passed:
                all_passed = False
        
        if all_passed:
            safe_print("\n✓ 所有检查通过！测试代码是基于实际源代码生成的。")
        else:
            safe_print("\n✗ 部分检查失败，请查看生成的代码。")
            # 显示生成代码的前 1000 字符
            safe_print(f"\n生成代码预览:\n{content[:1000]}")
    
    return result


if __name__ == "__main__":
    safe_print("=" * 60)
    safe_print("验证 CoderAgent 增强修复")
    safe_print("=" * 60)
    
    try:
        result = test_coder_create_test_file()
        
        if result.get('success'):
            safe_print("\n测试完成！")
            exit(0)
        else:
            safe_print(f"\n执行失败: {result.get('error')}")
            exit(1)
    except Exception as e:
        safe_print(f"\n异常: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
