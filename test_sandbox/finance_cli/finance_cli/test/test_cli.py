#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CLI模块单元测试

测试finance_cli.cli模块中的所有命令和功能
"""

import unittest
import sys
import os
from unittest.mock import patch, MagicMock
from click.testing import CliRunner

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from finance_cli import cli as cli_module


class TestCLI(unittest.TestCase):
    """CLI基础功能测试类"""
    
    def setUp(self):
        """测试前准备"""
        self.runner = CliRunner()
        
    def test_cli_version_option(self):
        """测试版本选项"""
        result = self.runner.invoke(cli_module.cli, ['--version'])
        self.assertEqual(result.exit_code, 0)
        self.assertIn('finance-cli', result.output)
        self.assertIn('1.0.0', result.output)
    
    def test_cli_verbose_option(self):
        """测试详细模式选项"""
        result = self.runner.invoke(cli_module.cli, ['--verbose', 'version'])
        self.assertEqual(result.exit_code, 0)
        self.assertIn('详细模式已启用', result.output)
        self.assertIn('finance-cli v1.0.0', result.output)
    
    def test_version_command(self):
        """测试version命令"""
        result = self.runner.invoke(cli_module.cli, ['version'])
        self.assertEqual(result.exit_code, 0)
        self.assertIn('finance-cli v1.0.0', result.output)
        self.assertIn('金融数据命令行工具', result.output)


class TestStockCommands(unittest.TestCase):
    """股票命令测试类"""
    
    def setUp(self):
        """测试前准备"""
        self.runner = CliRunner()
    
    def test_stock_quote_basic(self):
        """测试股票报价基础命令"""
        result = self.runner.invoke(cli_module.cli, ['stock', 'quote', 'AAPL'])
        self.assertEqual(result.exit_code, 0)
        self.assertIn('股票 AAPL 的报价数据（模拟）', result.output)
        self.assertIn('当前价格: $150.25', result.output)
    
    def test_stock_quote_with_options(self):
        """测试带选项的股票报价命令"""
        result = self.runner.invoke(cli_module.cli, [
            'stock', 'quote', '000001.SZ',
            '--period', '1y',
            '--interval', '1d'
        ])
        self.assertEqual(result.exit_code, 0)
        self.assertIn('股票 000001.SZ 的报价数据（模拟）', result.output)
    
    def test_stock_quote_verbose(self):
        """测试详细模式下的股票报价"""
        result = self.runner.invoke(cli_module.cli, [
            '--verbose', 'stock', 'quote', 'MSFT',
            '--period', '6mo', '--interval', '1h'
        ])
        self.assertEqual(result.exit_code, 0)
        self.assertIn('详细模式已启用', result.output)
        self.assertIn('获取股票 MSFT 的报价数据', result.output)
        self.assertIn('周期: 6mo', result.output)
    
    def test_stock_info_basic(self):
        """测试股票基本信息命令"""
        result = self.runner.invoke(cli_module.cli, ['stock', 'info', 'GOOGL'])
        self.assertEqual(result.exit_code, 0)
        self.assertIn('股票 GOOGL 的基本信息（模拟）', result.output)
        self.assertIn('公司名称: 示例公司', result.output)
        self.assertIn('市盈率: 25.3', result.output)
    
    def test_stock_info_with_output_format(self):
        """测试带输出格式选项的股票信息命令"""
        result = self.runner.invoke(cli_module.cli, [
            'stock', 'info', 'TSLA', '--output', 'json'
        ])
        self.assertEqual(result.exit_code, 0)
        self.assertIn('股票 TSLA 的基本信息（模拟）', result.output)
    
    def test_stock_info_verbose(self):
        """测试详细模式下的股票信息"""
        result = self.runner.invoke(cli_module.cli, [
            '--verbose', 'stock', 'info', 'AMZN', '--output', 'csv'
        ])
        self.assertEqual(result.exit_code, 0)
        self.assertIn('详细模式已启用', result.output)
        self.assertIn('获取股票 AMZN 的基本信息', result.output)


class TestPortfolioCommands(unittest.TestCase):
    """投资组合命令测试类"""
    
    def setUp(self):
        """测试前准备"""
        self.runner = CliRunner()
    
    def test_portfolio_list_all(self):
        """测试列出所有投资组合"""
        result = self.runner.invoke(cli_module.cli, ['portfolio', 'list'])
        self.assertEqual(result.exit_code, 0)
        self.assertIn('所有投资组合（模拟）:', result.output)
        self.assertIn('默认组合', result.output)
        self.assertIn('科技组合', result.output)
    
    def test_portfolio_list_specific(self):
        """测试列出特定投资组合"""
        result = self.runner.invoke(cli_module.cli, ['portfolio', 'list', '默认组合'])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("投资组合 '默认组合' 的详细信息（模拟）", result.output)
        self.assertIn('AAPL: 100股', result.output)
        self.assertIn('总价值: $25,000', result.output)
    
    def test_portfolio_list_verbose(self):
        """测试详细模式下列出投资组合"""
        result = self.runner.invoke(cli_module.cli, ['--verbose', 'portfolio', 'list'])
        self.assertEqual(result.exit_code, 0)
        self.assertIn('详细模式已启用', result.output)
        self.assertIn('列出投资组合', result.output)
    
    def test_portfolio_create_basic(self):
        """测试创建投资组合基础命令"""
        result = self.runner.invoke(cli_module.cli, ['portfolio', 'create', '我的组合'])
        self.assertEqual(result.exit_code, 0)
        self.assertIn('已创建投资组合: 我的组合', result.output)
    
    def test_portfolio_create_with_description(self):
        """测试带描述的投资组合创建"""
        result = self.runner.invoke(cli_module.cli, [
            'portfolio', 'create', '科技投资',
            '--description', '专注于科技股的投资组合'
        ])
        self.assertEqual(result.exit_code, 0)
        self.assertIn('已创建投资组合: 科技投资', result.output)
        self.assertIn('描述: 专注于科技股的投资组合', result.output)
    
    def test_portfolio_create_verbose(self):
        """测试详细模式下创建投资组合"""
        result = self.runner.invoke(cli_module.cli, [
            '--verbose', 'portfolio', 'create', '保守组合',
            '-d', '低风险投资组合'
        ])
        self.assertEqual(result.exit_code, 0)
        self.assertIn('详细模式已启用', result.output)
        self.assertIn("创建投资组合 '保守组合'", result.output)
        self.assertIn('描述: 低风险投资组合', result.output)


class TestConfigCommand(unittest.TestCase):
    """配置命令测试类"""
    
    def setUp(self):
        """测试前准备"""
        self.runner = CliRunner()
    
    def test_config_basic(self):
        """测试配置命令基础功能"""
        result = self.runner.invoke(cli_module.cli, ['config'])
        self.assertEqual(result.exit_code, 0)
        self.assertIn('当前配置（模拟）:', result.output)
        self.assertIn('API密钥: 已设置', result.output)
        self.assertIn('数据源: yfinance', result.output)
    
    def test_config_with_file(self):
        """测试带配置文件的配置命令"""
        # 使用临时文件
        import tempfile
        with tempfile.NamedTemporaryFile(suffix='.yaml', delete=False) as f:
            f.write(b"config: test\n")
            config_path = f.name
        
        try:
            result = self.runner.invoke(cli_module.cli, ['config', '--config', config_path])
            self.assertEqual(result.exit_code, 0)
            self.assertIn('当前配置（模拟）:', result.output)
        finally:
            if os.path.exists(config_path):
                try:
                    os.unlink(config_path)
                except:
                    pass
    
    def test_config_verbose(self):
        """测试详细模式下的配置命令"""
        result = self.runner.invoke(cli_module.cli, ['--verbose', 'config'])
        self.assertEqual(result.exit_code, 0)
        self.assertIn('详细模式已启用', result.output)
        self.assertIn('配置管理', result.output)


class TestErrorCases(unittest.TestCase):
    """错误情况测试类"""
    
    def setUp(self):
        """测试前准备"""
        self.runner = CliRunner()
    
    def test_invalid_command(self):
        """测试无效命令"""
        result = self.runner.invoke(cli_module.cli, ['invalid-command'])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn('Error:', result.output)
    
    def test_stock_quote_missing_symbol(self):
        """测试缺少股票代码的报价命令"""
        result = self.runner.invoke(cli_module.cli, ['stock', 'quote'])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn('Error:', result.output)
    
    def test_portfolio_create_missing_name(self):
        """测试缺少名称的投资组合创建"""
        result = self.runner.invoke(cli_module.cli, ['portfolio', 'create'])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn('Error:', result.output)


if __name__ == '__main__':
    unittest.main()
