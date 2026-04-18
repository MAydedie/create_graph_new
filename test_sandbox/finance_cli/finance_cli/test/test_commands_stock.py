
import unittest
from unittest.mock import patch, MagicMock
import sys
import os
from click.testing import CliRunner

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

from finance_cli.commands.stock import get_stock_price, stock_command, format_stock_price

class TestStockFunctions(unittest.TestCase):
    """测试 stock.py 中的独立函数"""

    @patch('finance_cli.commands.stock._get_demo_stock_data')
    def test_get_stock_price_demo(self, mock_get_demo):
        """测试获取演示数据"""
        mock_data = {'symbol': 'AAPL', 'price': 150.0}
        mock_get_demo.return_value = mock_data
        
        result = get_stock_price('AAPL', source='demo')
        self.assertEqual(result, mock_data)
        mock_get_demo.assert_called_with('AAPL')

    def test_format_stock_price(self):
        """测试价格格式化"""
        self.assertEqual(format_stock_price(1234.56, 'USD'), '$1,234.56')
        self.assertEqual(format_stock_price(1234.56, 'CNY'), '¥1,234.56')
        self.assertEqual(format_stock_price(1234.56, 'EUR'), '$1,234.56') # Fallback

class TestStockCommandCLI(unittest.TestCase):
    """测试 stock 命令 CLI"""

    def setUp(self):
        self.runner = CliRunner()

    @patch('finance_cli.commands.stock.get_stock_price')
    def test_stock_command_success(self, mock_get_price):
        """测试 stock 命令成功"""
        mock_get_price.return_value = {
            'symbol': 'AAPL',
            'name': 'Apple Inc.',
            'price': 150.00,
            'change': 1.5,
            'change_percent': 1.0,
            'volume': '100M',
            'timestamp': '2023-01-01'
        }
        
        result = self.runner.invoke(stock_command, ['AAPL'])
        
        self.assertEqual(result.exit_code, 0)
        self.assertIn('股票代码: AAPL', result.output)
        self.assertIn('当前价格: 150.0', result.output)
        # self.assertIn('涨跌幅: +1.5 (+1.0%)', result.output) # Verbose only

    @patch('finance_cli.commands.stock.get_stock_price')
    def test_stock_command_verbose(self, mock_get_price):
        """测试 stock 命令详细模式"""
        mock_get_price.return_value = {
            'symbol': 'AAPL',
            'source': 'demo',
            'timestamp': '2023'
        }
        
        result = self.runner.invoke(stock_command, ['AAPL', '--verbose'])
        
        self.assertEqual(result.exit_code, 0)
        self.assertIn('数据来源: demo', result.output)

    @patch('finance_cli.commands.stock.get_stock_price')
    def test_stock_command_not_found(self, mock_get_price):
        """测试股票未找到"""
        mock_get_price.return_value = None
        
        result = self.runner.invoke(stock_command, ['INVALID'])
        
        self.assertEqual(result.exit_code, 0)
        self.assertIn('未找到股票代码: INVALID', result.output)

if __name__ == '__main__':
    unittest.main()
