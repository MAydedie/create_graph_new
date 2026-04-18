#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
最小化调试脚本 - 测试单个 Agent 的执行
针对：为小目录生成测试文件
"""

import sys
import os
import json
import logging
from pathlib import Path

# 设置环境变量来确保正确的输出编码
os.environ['PYTHONIOENCODING'] = 'utf-8'

# 确保项目路径
PROJECT_ROOT = Path(r"D:\代码仓库生图\create_graph")
sys.path.insert(0, str(PROJECT_ROOT))

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s'
)

def safe_print(*args, **kwargs):
    """安全打印函数，处理 Windows 编码问题"""
    try:
        print(*args, **kwargs)
    except UnicodeEncodeError:
        # 将对象转换为字符串，替换非 ASCII 字符
        safe_args = []
        for arg in args:
            if isinstance(arg, str):
                safe_args.append(arg.encode('gbk', errors='replace').decode('gbk'))
            else:
                safe_args.append(str(arg).encode('gbk', errors='replace').decode('gbk'))
        print(*safe_args, **kwargs)

def test_coder_create_file():
    """测试 CoderAgent 创建文件"""
    safe_print("=" * 60)
    safe_print("测试：CoderAgent 创建测试文件")
    safe_print("=" * 60)
    
    from llm.agent.agents.coder_agent import CoderAgent
    
    coder = CoderAgent(verbose=True)
    
    # 测试步骤：创建一个简单的测试文件
    step = {
        "step_id": 0,
        "type": "code_change",
        "action": "create_file",
        "target": r"D:\代码仓库生图\create_graph\test_sandbox\finance_cli\tests\test_stock_commands.py",
        "description": "为 finance_cli/commands/stock.py 创建单元测试文件，测试 get_stock_price 和 format_stock_price 函数"
    }
    
    # 构建上下文 - 包含源文件信息（不使用特殊字符）
    context = {
        "workspace_root": str(PROJECT_ROOT / "test_sandbox" / "finance_cli"),
        "rag_knowledge": {
            "context_summary": """
源文件: finance_cli/commands/stock.py
包含的函数:
- stock_command(symbol, source, verbose): Click 命令，查询股票价格
- get_stock_price(symbol, source="demo"): 获取股票价格信息
- _get_demo_stock_data(symbol): 获取演示股票数据
- format_stock_price(price, currency="USD"): 格式化股票价格显示，支持 USD 和 CNY
"""
        }
    }
    
    safe_print(f"\n执行步骤: {step}")
    safe_print(f"\n上下文: (rag_knowledge summary)")
    
    result = coder.execute_step(step, context)
    
    safe_print(f"\n执行结果:")
    # 使用 safe_print 输出结果
    result_str = json.dumps(result, ensure_ascii=False, indent=2)
    safe_print(result_str)
    
    return result


def test_reviewer_check():
    """测试 ReviewerAgent 审查"""
    safe_print("\n" + "=" * 60)
    safe_print("测试：ReviewerAgent 审查代码")
    safe_print("=" * 60)
    
    from llm.agent.agents.reviewer_agent import ReviewerAgent
    
    reviewer = ReviewerAgent(verbose=True)
    
    # 模拟 Coder 的输出 - 避免使用特殊字符
    changes = {
        "success": True,
        "action": "create_file",
        "target": r"D:\代码仓库生图\create_graph\test_sandbox\finance_cli\tests\test_stock_commands.py",
        "summary": "创建测试文件",
        "code_content": '''#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
股票命令模块 (stock.py) 的单元测试
"""

import pytest
from finance_cli.commands.stock import (
    get_stock_price, 
    format_stock_price, 
    _get_demo_stock_data
)


class TestGetStockPrice:
    """测试 get_stock_price 函数"""
    
    def test_demo_source_returns_data(self):
        """测试使用 demo 数据源返回数据"""
        result = get_stock_price("AAPL", "demo")
        assert result is not None
        assert "symbol" in result
        assert "price" in result
    
    def test_unknown_source_fallback_to_demo(self):
        """测试未知数据源回退到 demo"""
        result = get_stock_price("AAPL", "unknown")
        assert result is not None


class TestFormatStockPrice:
    """测试 format_stock_price 函数"""
    
    def test_format_usd(self):
        """测试 USD 格式化"""
        result = format_stock_price(123.45, "USD")
        assert result == "$123.45"
    
    def test_format_cny(self):
        """测试 CNY 格式化"""
        result = format_stock_price(100.00, "CNY")
        assert "100.00" in result
    
    def test_format_other_currency(self):
        """测试其他货币格式化"""
        result = format_stock_price(50.00, "EUR")
        assert result == "50.00 EUR"


class TestGetDemoStockData:
    """测试 _get_demo_stock_data 函数"""
    
    def test_known_symbol(self):
        """测试已知股票代码"""
        result = _get_demo_stock_data("AAPL")
        assert result["symbol"] == "AAPL"
    
    def test_unknown_symbol_returns_default(self):
        """测试未知股票代码返回默认数据"""
        result = _get_demo_stock_data("UNKNOWN")
        assert result["symbol"] == "UNKNOWN"
'''
    }
    
    context = {}
    
    result = reviewer.review(changes, context)
    
    safe_print(f"\n审查结果:")
    safe_print(json.dumps(result, ensure_ascii=False, indent=2))
    
    return result


if __name__ == "__main__":
    # 设置 stdout 编码
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    
    safe_print("=" * 60)
    safe_print("最小化调试测试 - 诊断测试文件生成问题")
    safe_print("=" * 60)
    
    # 1. 测试 CoderAgent
    coder_result = test_coder_create_file()
    
    # 2. 如果成功，测试 ReviewerAgent
    if coder_result.get("success"):
        reviewer_result = test_reviewer_check()
    else:
        safe_print(f"\nCoderAgent 执行失败，跳过 ReviewerAgent 测试")
        safe_print(f"错误: {coder_result.get('error')}")
    
    safe_print("\n" + "=" * 60)
    safe_print("调试测试完成")
    safe_print("=" * 60)
