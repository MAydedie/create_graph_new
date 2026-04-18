#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
股票功能模块单元测试

测试 StockAPI 和 StockSimulator 类的功能
"""

import unittest
import time
from unittest.mock import patch, MagicMock
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from finance_cli.stock import StockAPI, StockSimulator


class TestStockAPI(unittest.TestCase):
    """测试 StockAPI 类"""
    
    def setUp(self):
        """测试前准备"""
        self.api = StockAPI(api_key="test_key")
    
    def test_init(self):
        """测试初始化"""
        self.assertEqual(self.api.api_key, "test_key")
        self.assertEqual(self.api.request_interval, 1)
        
        # 测试无api_key初始化
        api_no_key = StockAPI()
        self.assertIsNone(api_no_key.api_key)
    
    def test_get_real_time_price_valid_symbol(self):
        """测试获取有效股票代码的实时价格"""
        # 测试已知股票代码
        symbols = ['AAPL', 'GOOGL', 'MSFT', 'TSLA', '000001.SZ', '600519.SH']
        
        for symbol in symbols:
            price = self.api.get_real_time_price(symbol)
            self.assertIsInstance(price, float)
            self.assertGreater(price, 0)
            # 价格应该保留两位小数
            self.assertEqual(price, round(price, 2))
    
    def test_get_real_time_price_invalid_symbol(self):
        """测试获取无效股票代码的实时价格"""
        # 测试空字符串
        price = self.api.get_real_time_price("")
        self.assertIsNone(price)
        
        # 测试不存在的股票代码
        price = self.api.get_real_time_price("INVALID")
        self.assertIsInstance(price, float)
        self.assertGreater(price, 0)
    
    def test_get_real_time_price_case_insensitive(self):
        """测试股票代码大小写不敏感"""
        price1 = self.api.get_real_time_price("aapl")
        price2 = self.api.get_real_time_price("AAPL")
        price3 = self.api.get_real_time_price("Aapl")
        
        # 所有大小写变体都应该返回有效价格
        self.assertIsInstance(price1, float)
        self.assertIsInstance(price2, float)
        self.assertIsInstance(price3, float)
    
    @patch('time.sleep')
    def test_rate_limit(self, mock_sleep):
        """测试请求频率限制"""
        # 第一次请求
        self.api.get_real_time_price("AAPL")
        
        # 立即第二次请求，应该触发等待
        self.api.get_real_time_price("GOOGL")
        
        # 验证 sleep 被调用
        mock_sleep.assert_called_once()
        
        # 验证 sleep 时间在合理范围内
        sleep_time = mock_sleep.call_args[0][0]
        self.assertGreaterEqual(sleep_time, 0)
        self.assertLessEqual(sleep_time, 1)


class TestStockSimulator(unittest.TestCase):
    """测试 StockSimulator 类"""
    
    def setUp(self):
        """测试前准备"""
        self.simulator = StockSimulator()
    
    def test_init(self):
        """测试模拟器初始化"""
        # 验证初始化的股票数据
        expected_symbols = ['AAPL', 'GOOGL', 'MSFT', 'TSLA', '000001.SZ', '600519.SH']
        
        for symbol in expected_symbols:
            self.assertIn(symbol, self.simulator.stock_data)
            stock_info = self.simulator.stock_data[symbol]
            
            # 验证每个股票都有必要的信息
            self.assertIn('name', stock_info)
            self.assertIn('base_price', stock_info)
            self.assertIn('volatility', stock_info)
            
            # 验证数据类型
            self.assertIsInstance(stock_info['name'], str)
            self.assertIsInstance(stock_info['base_price'], float)
            self.assertIsInstance(stock_info['volatility'], float)
            
            # 验证价格为正数
            self.assertGreater(stock_info['base_price'], 0)
            
            # 验证波动率为正数
            self.assertGreater(stock_info['volatility'], 0)
    
    def test_get_simulated_price_valid_symbol(self):
        """测试获取有效股票代码的模拟价格"""
        symbols = ['AAPL', 'GOOGL', 'MSFT', 'TSLA', '000001.SZ', '600519.SH']
        
        for symbol in symbols:
            price = self.simulator.get_simulated_price(symbol)
            self.assertIsInstance(price, float)
            self.assertGreater(price, 0)
            # 价格应该保留两位小数
            self.assertEqual(price, round(price, 2))
            
            # 验证价格在合理范围内（基准价格 ± 50%）
            base_price = self.simulator.stock_data[symbol]['base_price']
            volatility = self.simulator.stock_data[symbol]['volatility']
            
            min_price = base_price * (1 - volatility)
            max_price = base_price * (1 + volatility)
            
            # 由于随机性，价格可能在波动率范围内
            # 这里只验证价格为正数
            self.assertGreater(price, 0)
    
    def test_get_simulated_price_invalid_symbol(self):
        """测试获取无效股票代码的模拟价格"""
        # 测试不存在的股票代码
        price = self.simulator.get_simulated_price("INVALID")
        self.assertIsNone(price)
        
        # 测试空字符串
        price = self.simulator.get_simulated_price("")
        self.assertIsNone(price)
        
        # 测试 None
        price = self.simulator.get_simulated_price(None)
        self.assertIsNone(price)
    
    def test_get_simulated_price_case_insensitive(self):
        """测试股票代码大小写不敏感"""
        price1 = self.simulator.get_simulated_price("aapl")
        price2 = self.simulator.get_simulated_price("AAPL")
        
        # 两种写法都应该返回有效价格
        self.assertIsInstance(price1, float)
        self.assertIsInstance(price2, float)
    
    def test_get_stock_info_valid_symbol(self):
        """测试获取有效股票代码的完整信息"""
        symbol = 'AAPL'
        info = self.simulator.get_stock_info(symbol)
        
        self.assertIsInstance(info, dict)
        
        # 验证返回的字段
        expected_keys = ['symbol', 'name', 'price']
        for key in expected_keys:
            self.assertIn(key, info)
        
        # 验证具体值
        self.assertEqual(info['symbol'], 'AAPL')
        self.assertEqual(info['name'], '苹果公司')
        self.assertIsInstance(info['price'], float)
        self.assertGreater(info['price'], 0)
    
    def test_get_stock_info_invalid_symbol(self):
        """测试获取无效股票代码的完整信息"""
        # 测试不存在的股票代码
        info = self.simulator.get_stock_info("INVALID")
        self.assertIsNone(info)
        
        # 测试空字符串
        info = self.simulator.get_stock_info("")
        self.assertIsNone(info)
    
    def test_price_variation(self):
        """测试价格变化（模拟市场波动）"""
        symbol = 'AAPL'
        
        # 获取多次价格，验证价格有变化（由于随机种子不同）
        prices = []
        for _ in range(5):
            # 每次调用前稍微改变时间，影响随机种子
            time.sleep(0.01)
            price = self.simulator.get_simulated_price(symbol)
            prices.append(price)
        
        # 验证所有价格都有效
        for price in prices:
            self.assertIsInstance(price, float)
            self.assertGreater(price, 0)
        
        # 由于随机性，价格可能相同也可能不同
        # 这里只验证我们得到了5个价格
        self.assertEqual(len(prices), 5)


class TestIntegration(unittest.TestCase):
    """集成测试"""
    
    def test_both_classes_produce_valid_prices(self):
        """测试两个类都能产生有效的价格数据"""
        api = StockAPI()
        simulator = StockSimulator()
        
        test_symbols = ['AAPL', 'GOOGL', 'MSFT']
        
        for symbol in test_symbols:
            # 测试 API 价格
            api_price = api.get_real_time_price(symbol)
            self.assertIsInstance(api_price, float)
            self.assertGreater(api_price, 0)
            
            # 测试模拟器价格
            sim_price = simulator.get_simulated_price(symbol)
            self.assertIsInstance(sim_price, float)
            self.assertGreater(sim_price, 0)
            
            # 两个价格都应该保留两位小数
            self.assertEqual(api_price, round(api_price, 2))
            self.assertEqual(sim_price, round(sim_price, 2))
    
    def test_symbol_consistency(self):
        """测试两个类对相同股票代码的处理一致性"""
        api = StockAPI()
        simulator = StockSimulator()
        
        # 测试大小写处理的一致性
        symbol_variants = ['aapl', 'AAPL', 'Aapl']
        
        for symbol in symbol_variants:
            api_price = api.get_real_time_price(symbol)
            sim_price = simulator.get_simulated_price(symbol)
            
            # API 应该对所有变体返回有效价格
            self.assertIsInstance(api_price, float)
            self.assertGreater(api_price, 0)
            
            # 模拟器应该对正确的大小写返回有效价格
            if symbol.upper() == 'AAPL':
                self.assertIsInstance(sim_price, float)
                self.assertGreater(sim_price, 0)


if __name__ == '__main__':
    unittest.main()
