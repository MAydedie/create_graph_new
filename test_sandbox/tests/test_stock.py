#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
股票功能模块单元测试

测试 stock.py 中的 StockAPI 和 StockSimulator 类
"""

import unittest
import time
from unittest.mock import patch, MagicMock
from finance_cli.stock import StockAPI, StockSimulator


class TestStockAPI(unittest.TestCase):
    """测试 StockAPI 类"""
    
    def setUp(self):
        """测试前准备"""
        self.api = StockAPI(api_key="test_key")
    
    def test_init(self):
        """测试初始化"""
        # 测试带 API key 初始化
        api_with_key = StockAPI(api_key="test_key_123")
        self.assertEqual(api_with_key.api_key, "test_key_123")
        self.assertEqual(api_with_key.request_interval, 1)
        
        # 测试不带 API key 初始化
        api_without_key = StockAPI()
        self.assertIsNone(api_without_key.api_key)
    
    def test_check_rate_limit(self):
        """测试请求频率限制检查"""
        # 记录初始时间
        start_time = time.time()
        
        # 第一次调用应该立即返回
        self.api._check_rate_limit()
        first_call_time = time.time() - start_time
        self.assertLess(first_call_time, 0.1)  # 应该很快
        
        # 立即第二次调用应该会等待
        start_time = time.time()
        self.api._check_rate_limit()
        second_call_time = time.time() - start_time
        self.assertGreaterEqual(second_call_time, 0.9)  # 应该等待约1秒
    
    def test_get_real_time_price_valid_symbols(self):
        """测试获取有效股票代码的实时价格"""
        # 测试已知股票代码
        test_cases = [
            ("AAPL", 175.0),
            ("GOOGL", 135.0),
            ("MSFT", 330.0),
            ("TSLA", 240.0),
            ("000001.SZ", 12.5),
            ("600519.SH", 1600.0),
        ]
        
        for symbol, expected_base in test_cases:
            with self.subTest(symbol=symbol):
                price = self.api.get_real_time_price(symbol)
                self.assertIsInstance(price, float)
                self.assertGreater(price, 0)
                # 价格应该在基准价格的 ±2% 范围内
                lower_bound = expected_base * 0.98
                upper_bound = expected_base * 1.02
                self.assertGreaterEqual(price, lower_bound)
                self.assertLessEqual(price, upper_bound)
    
    def test_get_real_time_price_invalid_symbol(self):
        """测试获取无效股票代码的价格"""
        # 测试未知股票代码
        price = self.api.get_real_time_price("INVALID")
        self.assertIsInstance(price, float)
        self.assertGreater(price, 0)
        # 默认基准价格是100.0，应该在 ±2% 范围内
        self.assertGreaterEqual(price, 98.0)
        self.assertLessEqual(price, 102.0)
    
    def test_get_real_time_price_empty_symbol(self):
        """测试空股票代码"""
        price = self.api.get_real_time_price("")
        self.assertIsNone(price)
        
        price = self.api.get_real_time_price(None)
        self.assertIsNone(price)
    
    def test_get_real_time_price_case_insensitive(self):
        """测试股票代码大小写不敏感"""
        # 测试小写代码
        price_lower = self.api.get_real_time_price("aapl")
        price_upper = self.api.get_real_time_price("AAPL")
        
        self.assertIsInstance(price_lower, float)
        self.assertIsInstance(price_upper, float)
        # 由于随机性，价格可能不同，但都应该是有效价格
        self.assertGreater(price_lower, 0)
        self.assertGreater(price_upper, 0)


class TestStockSimulator(unittest.TestCase):
    """测试 StockSimulator 类"""
    
    def setUp(self):
        """测试前准备"""
        self.simulator = StockSimulator()
    
    def test_init(self):
        """测试模拟器初始化"""
        self.assertIsInstance(self.simulator.stock_data, dict)
        self.assertGreater(len(self.simulator.stock_data), 0)
        
        # 检查包含的股票
        expected_symbols = ['AAPL', 'GOOGL', 'MSFT', 'TSLA', '000001.SZ', '600519.SH']
        for symbol in expected_symbols:
            self.assertIn(symbol, self.simulator.stock_data)
            
            stock_info = self.simulator.stock_data[symbol]
            self.assertIn('name', stock_info)
            self.assertIn('base_price', stock_info)
            self.assertIn('volatility', stock_info)
    
    def test_get_simulated_price_valid_symbols(self):
        """测试获取有效股票代码的模拟价格"""
        # 测试已知股票代码
        test_cases = [
            ("AAPL", 175.0, 0.03),
            ("GOOGL", 135.0, 0.025),
            ("MSFT", 330.0, 0.02),
            ("TSLA", 240.0, 0.05),
            ("000001.SZ", 12.5, 0.015),
            ("600519.SH", 1600.0, 0.01),
        ]
        
        for symbol, base_price, volatility in test_cases:
            with self.subTest(symbol=symbol):
                price = self.simulator.get_simulated_price(symbol)
                self.assertIsInstance(price, float)
                self.assertGreater(price, 0)
                
                # 价格应该在基准价格的波动范围内
                lower_bound = base_price * (1 - volatility)
                upper_bound = base_price * (1 + volatility)
                self.assertGreaterEqual(price, lower_bound)
                self.assertLessEqual(price, upper_bound)
    
    def test_get_simulated_price_invalid_symbol(self):
        """测试获取无效股票代码的模拟价格"""
        price = self.simulator.get_simulated_price("INVALID")
        self.assertIsNone(price)
        
        price = self.simulator.get_simulated_price("")
        self.assertIsNone(price)
    
    def test_get_simulated_price_case_insensitive(self):
        """测试股票代码大小写不敏感"""
        # 测试小写代码
        price_lower = self.simulator.get_simulated_price("aapl")
        price_upper = self.simulator.get_simulated_price("AAPL")
        
        self.assertIsInstance(price_lower, float)
        self.assertIsInstance(price_upper, float)
        
        # 由于使用时间作为随机种子，不同时间调用价格可能不同
        # 但都应该是有效价格
        self.assertGreater(price_lower, 0)
        self.assertGreater(price_upper, 0)
    
    def test_get_stock_info_valid_symbol(self):
        """测试获取有效股票信息"""
        # 测试已知股票
        info = self.simulator.get_stock_info("AAPL")
        
        self.assertIsInstance(info, dict)
        self.assertEqual(info['symbol'], "AAPL")
        self.assertEqual(info['name'], "苹果公司")
        self.assertIn('price', info)
        self.assertIsInstance(info['price'], float)
        self.assertGreater(info['price'], 0)
        
        # 检查价格在合理范围内
        base_price = 175.0
        volatility = 0.03
        lower_bound = base_price * (1 - volatility)
        upper_bound = base_price * (1 + volatility)
        self.assertGreaterEqual(info['price'], lower_bound)
        self.assertLessEqual(info['price'], upper_bound)
    
    def test_get_stock_info_invalid_symbol(self):
        """测试获取无效股票信息"""
        info = self.simulator.get_stock_info("INVALID")
        self.assertIsNone(info)
        
        info = self.simulator.get_stock_info("")
        self.assertIsNone(info)
    
    def test_get_stock_info_case_insensitive(self):
        """测试股票信息获取大小写不敏感"""
        info_lower = self.simulator.get_stock_info("aapl")
        info_upper = self.simulator.get_stock_info("AAPL")
        
        self.assertIsInstance(info_lower, dict)
        self.assertIsInstance(info_upper, dict)
        
        self.assertEqual(info_lower['symbol'], "AAPL")
        self.assertEqual(info_upper['symbol'], "AAPL")
    
    @patch('random.uniform')
    def test_get_simulated_price_with_mock_random(self, mock_uniform):
        """使用模拟的随机数测试价格计算"""
        # 设置模拟的随机数返回值
        mock_uniform.return_value = 0.01  # 1% 的波动
        
        # 测试 AAPL
        price = self.simulator.get_simulated_price("AAPL")
        
        # 验证 random.uniform 被调用
        mock_uniform.assert_called_once()
        
        # 验证价格计算：175.0 * (1 + 0.01) = 176.75
        expected_price = 175.0 * (1 + 0.01)
        self.assertEqual(price, round(expected_price, 2))


class TestStockModuleIntegration(unittest.TestCase):
    """股票模块集成测试"""
    
    def test_both_classes_independent(self):
        """测试两个类独立工作"""
        api = StockAPI()
        simulator = StockSimulator()
        
        # 两个类应该都能获取价格
        api_price = api.get_real_time_price("AAPL")
        sim_price = simulator.get_simulated_price("AAPL")
        
        self.assertIsInstance(api_price, float)
        self.assertIsInstance(sim_price, float)
        
        # 由于使用不同的算法，价格可能不同，但都应该是正数
        self.assertGreater(api_price, 0)
        self.assertGreater(sim_price, 0)
    
    def test_multiple_instances(self):
        """测试多个实例独立工作"""
        api1 = StockAPI()
        api2 = StockAPI()
        
        # 两个实例应该独立
        self.assertNotEqual(id(api1), id(api2))
        
        # 分别获取价格
        price1 = api1.get_real_time_price("AAPL")
        price2 = api2.get_real_time_price("AAPL")
        
        # 由于随机性，价格可能不同
        self.assertIsInstance(price1, float)
        self.assertIsInstance(price2, float)


def run_tests():
    """运行所有测试"""
    # 创建测试套件
    suite = unittest.TestSuite()
    
    # 添加测试类
    suite.addTest(unittest.makeSuite(TestStockAPI))
    suite.addTest(unittest.makeSuite(TestStockSimulator))
    suite.addTest(unittest.makeSuite(TestStockModuleIntegration))
    
    # 运行测试
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result


if __name__ == '__main__':
    # 直接运行测试
    unittest.main(verbosity=2)
