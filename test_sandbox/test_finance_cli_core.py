#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
finance_cli/core.py 单元测试

测试 finance_cli 核心功能模块
"""

import unittest
import sys
import os
from unittest.mock import patch, MagicMock

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from finance_cli.core import (
    FinanceCLI,
    calculate_compound_interest,
    calculate_present_value,
    calculate_future_value,
    calculate_loan_payment,
    calculate_investment_return,
    format_currency
)


class TestFinanceCLI(unittest.TestCase):
    """测试 FinanceCLI 类"""
    
    def setUp(self):
        """测试前准备"""
        self.cli = FinanceCLI()
    
    def test_init(self):
        """测试初始化"""
        self.assertIsNotNone(self.cli)
        self.assertTrue(hasattr(self.cli, 'commands'))
        self.assertIsInstance(self.cli.commands, dict)
    
    def test_register_command(self):
        """测试注册命令"""
        # 定义测试函数
        def test_func():
            return "test"
        
        # 注册命令
        self.cli.register_command("test", test_func, "测试命令")
        
        # 验证命令已注册
        self.assertIn("test", self.cli.commands)
        self.assertEqual(self.cli.commands["test"]["func"], test_func)
        self.assertEqual(self.cli.commands["test"]["description"], "测试命令")
    
    def test_execute_command_valid(self):
        """测试执行有效命令"""
        # 注册测试命令
        def test_func():
            return "success"
        
        self.cli.register_command("test", test_func, "测试命令")
        
        # 执行命令
        result = self.cli.execute_command("test")
        
        # 验证结果
        self.assertEqual(result, "success")
    
    def test_execute_command_invalid(self):
        """测试执行无效命令"""
        # 执行不存在的命令
        result = self.cli.execute_command("nonexistent")
        
        # 验证返回错误信息
        self.assertIn("未知命令", result)
    
    def test_get_help(self):
        """测试获取帮助信息"""
        # 注册几个测试命令
        self.cli.register_command("cmd1", lambda: None, "命令1描述")
        self.cli.register_command("cmd2", lambda: None, "命令2描述")
        
        # 获取帮助信息
        help_text = self.cli.get_help()
        
        # 验证帮助信息包含命令描述
        self.assertIn("cmd1", help_text)
        self.assertIn("命令1描述", help_text)
        self.assertIn("cmd2", help_text)
        self.assertIn("命令2描述", help_text)


class TestFinancialCalculations(unittest.TestCase):
    """测试金融计算函数"""
    
    def test_calculate_compound_interest(self):
        """测试复利计算"""
        # 测试用例1: 基本复利计算
        result = calculate_compound_interest(1000, 0.05, 10)
        # 1000 * (1 + 0.05)^10 ≈ 1628.89
        self.assertAlmostEqual(result, 1628.89, delta=0.01)
        
        # 测试用例2: 零利率
        result = calculate_compound_interest(1000, 0, 10)
        self.assertEqual(result, 1000)
        
        # 测试用例3: 负利率（如果有处理）
        result = calculate_compound_interest(1000, -0.05, 10)
        # 1000 * (1 - 0.05)^10 ≈ 598.74
        self.assertAlmostEqual(result, 598.74, delta=0.01)
    
    def test_calculate_present_value(self):
        """测试现值计算"""
        # 测试用例1: 基本现值计算
        result = calculate_present_value(1000, 0.05, 10)
        # 1000 / (1 + 0.05)^10 ≈ 613.91
        self.assertAlmostEqual(result, 613.91, delta=0.01)
        
        # 测试用例2: 零折现率
        result = calculate_present_value(1000, 0, 10)
        self.assertEqual(result, 1000)
    
    def test_calculate_future_value(self):
        """测试终值计算"""
        # 测试用例1: 基本终值计算
        result = calculate_future_value(1000, 0.05, 10)
        # 与复利计算相同
        self.assertAlmostEqual(result, 1628.89, delta=0.01)
        
        # 测试用例2: 零利率
        result = calculate_future_value(1000, 0, 10)
        self.assertEqual(result, 1000)
    
    def test_calculate_loan_payment(self):
        """测试贷款还款计算"""
        # 测试用例1: 基本贷款计算
        result = calculate_loan_payment(100000, 0.05, 20)
        # 月还款额应该是一个正数
        self.assertGreater(result, 0)
        
        # 测试用例2: 零利率贷款
        result = calculate_loan_payment(100000, 0, 20)
        # 100000 / (20 * 12) ≈ 416.67
        self.assertAlmostEqual(result, 416.67, delta=0.01)
        
        # 测试用例3: 短期贷款
        result = calculate_loan_payment(1000, 0.12, 1)
        self.assertGreater(result, 0)
    
    def test_calculate_investment_return(self):
        """测试投资回报计算"""
        # 测试用例1: 正回报
        result = calculate_investment_return(1000, 1500)
        # (1500 - 1000) / 1000 = 0.5 = 50%
        self.assertEqual(result, 0.5)
        
        # 测试用例2: 负回报
        result = calculate_investment_return(1000, 800)
        # (800 - 1000) / 1000 = -0.2 = -20%
        self.assertEqual(result, -0.2)
        
        # 测试用例3: 零投资（应该处理除零错误）
        with self.assertRaises(ValueError):
            calculate_investment_return(0, 1000)
    
    def test_format_currency(self):
        """测试货币格式化"""
        # 测试用例1: 正数
        result = format_currency(1234.56)
        self.assertIn("1,234.56", result)
        
        # 测试用例2: 负数
        result = format_currency(-1234.56)
        self.assertIn("-1,234.56", result)
        
        # 测试用例3: 零
        result = format_currency(0)
        self.assertIn("0.00", result)
        
        # 测试用例4: 大数
        result = format_currency(1234567.89)
        self.assertIn("1,234,567.89", result)


class TestIntegration(unittest.TestCase):
    """测试集成功能"""
    
    def test_cli_with_calculations(self):
        """测试CLI与计算功能的集成"""
        cli = FinanceCLI()
        
        # 模拟用户输入
        test_cases = [
            ("compound", [1000, 0.05, 10], 1628.89),
            ("present", [1000, 0.05, 10], 613.91),
        ]
        
        for command, args, expected in test_cases:
            # 这里假设命令可以通过某种方式调用
            # 实际测试中可能需要更复杂的模拟
            pass
    
    @patch('builtins.print')
    def test_cli_output_formatting(self, mock_print):
        """测试CLI输出格式化"""
        cli = FinanceCLI()
        
        # 注册一个返回格式化货币的命令
        def format_money_command(amount):
            return format_currency(amount)
        
        cli.register_command("format", format_money_command, "格式化货币")
        
        # 执行命令并验证输出格式
        result = cli.execute_command("format", 1234.56)
        self.assertIsInstance(result, str)
        self.assertIn("1,234.56", result)


class TestErrorHandling(unittest.TestCase):
    """测试错误处理"""
    
    def test_invalid_inputs(self):
        """测试无效输入"""
        # 测试负时间周期
        with self.assertRaises(ValueError):
            calculate_compound_interest(1000, 0.05, -1)
        
        # 测试负本金
        with self.assertRaises(ValueError):
            calculate_compound_interest(-1000, 0.05, 10)
        
        # 测试无效利率（如果有限制）
        # 这里假设利率可以是任意值，所以不测试
    
    def test_edge_cases(self):
        """测试边界情况"""
        # 测试极大值
        result = calculate_compound_interest(1e6, 0.01, 100)
        self.assertGreater(result, 1e6)
        
        # 测试极小值
        result = calculate_compound_interest(0.01, 0.05, 10)
        self.assertGreater(result, 0)
        
        # 测试零时间周期
        result = calculate_compound_interest(1000, 0.05, 0)
        self.assertEqual(result, 1000)


def run_tests():
    """运行所有测试"""
    # 创建测试套件
    suite = unittest.TestSuite()
    
    # 添加测试类
    suite.addTest(unittest.makeSuite(TestFinanceCLI))
    suite.addTest(unittest.makeSuite(TestFinancialCalculations))
    suite.addTest(unittest.makeSuite(TestIntegration))
    suite.addTest(unittest.makeSuite(TestErrorHandling))
    
    # 运行测试
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result


if __name__ == '__main__':
    # 运行测试
    print("开始运行 finance_cli/core.py 单元测试...")
    print("=" * 60)
    
    result = run_tests()
    
    print("=" * 60)
    print(f"测试完成: 通过 {result.testsRun - len(result.failures) - len(result.errors)} / {result.testsRun}")
    
    if result.failures:
        print(f"失败: {len(result.failures)}")
        for test, traceback in result.failures:
            print(f"  {test}: {traceback.split('\n')[0]}")
    
    if result.errors:
        print(f"错误: {len(result.errors)}")
        for test, traceback in result.errors:
            print(f"  {test}: {traceback.split('\n')[0]}")
    
    # 返回适当的退出码
    sys.exit(0 if result.wasSuccessful() else 1)
