#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
股票功能模块

提供股票价格查询功能，支持模拟数据和API占位符
"""

import random
import time
from typing import Dict, Optional, Tuple
from datetime import datetime


class StockAPI:
    """股票API接口类（占位符）"""
    
    def __init__(self, api_key: Optional[str] = None):
        """初始化API接口
        
        Args:
            api_key: API密钥，用于真实API调用（当前为模拟）
        """
        self.api_key = api_key
        self.last_request_time = 0
        self.request_interval = 1  # 模拟请求间隔（秒）
    
    def _check_rate_limit(self):
        """检查请求频率限制（模拟）"""
        current_time = time.time()
        if current_time - self.last_request_time < self.request_interval:
            time.sleep(self.request_interval - (current_time - self.last_request_time))
        self.last_request_time = time.time()
    
    def get_real_time_price(self, symbol: str) -> Optional[float]:
        """获取实时股价（API占位符）
        
        Args:
            symbol: 股票代码（如：AAPL, 000001.SZ）
            
        Returns:
            实时股价，如果获取失败返回None
        """
        # 这里可以替换为真实的API调用
        # 例如：使用yfinance、Alpha Vantage、腾讯财经等API
        self._check_rate_limit()
        
        # 模拟API响应
        if not symbol:
            return None
            
        # 模拟不同股票的基准价格
        base_prices = {
            'AAPL': 175.0,
            'GOOGL': 135.0,
            'MSFT': 330.0,
            'TSLA': 240.0,
            '000001.SZ': 12.5,  # 平安银行
            '600519.SH': 1600.0,  # 贵州茅台
        }
        
        base_price = base_prices.get(symbol.upper(), 100.0)
        
        # 添加随机波动（模拟市场波动）
        fluctuation = random.uniform(-0.02, 0.02)  # ±2%
        price = base_price * (1 + fluctuation)
        
        return round(price, 2)


class StockSimulator:
    """股票模拟器"""
    
    def __init__(self):
        """初始化模拟器"""
        self.stock_data = {
            'AAPL': {
                'name': '苹果公司',
                'base_price': 175.0,
                'volatility': 0.03,  # 波动率
            },
            'GOOGL': {
                'name': '谷歌',
                'base_price': 135.0,
                'volatility': 0.025,
            },
            'MSFT': {
                'name': '微软',
                'base_price': 330.0,
                'volatility': 0.02,
            },
            'TSLA': {
                'name': '特斯拉',
                'base_price': 240.0,
                'volatility': 0.05,
            },
            '000001.SZ': {
                'name': '平安银行',
                'base_price': 12.5,
                'volatility': 0.015,
            },
            '600519.SH': {
                'name': '贵州茅台',
                'base_price': 1600.0,
                'volatility': 0.01,
            },
        }
    
    def get_simulated_price(self, symbol: str) -> Optional[float]:
        """获取模拟股价
        
        Args:
            symbol: 股票代码
            
        Returns:
            模拟股价，如果股票不存在返回None
        """
        if not symbol:
            return None
            
        stock_info = self.stock_data.get(symbol.upper())
        if not stock_info:
            return None
        
        # 基于基准价格和波动率生成模拟价格
        base_price = stock_info['base_price']
        volatility = stock_info['volatility']
        
        # 使用当前时间作为随机种子的一部分，使价格随时间变化
        time_factor = datetime.now().timestamp() / 1000
        random.seed(int(time_factor) + hash(symbol))
        
        # 生成价格波动
        fluctuation = random.uniform(-volatility, volatility)
        price = base_price * (1 + fluctuation)
        
        return round(price, 2)
    
    def get_stock_info(self, symbol: str) -> Optional[Dict]:
        """获取股票信息
        
        Args:
            symbol: 股票代码
            
        Returns:
            股票信息字典，包含名称和当前价格
        """
        price = self.get_simulated_price(symbol)
        if price is None:
            return None
            
        stock_info = self.stock_data.get(symbol.upper(), {})
        return {
            'symbol': symbol.upper(),
            'name': stock_info.get('name', '未知'),
            'price': price,
            'currency': 'USD' if '.' not in symbol else 'CNY',
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }


def get_stock_price(symbol: str, use_api: bool = False, api_key: Optional[str] = None) -> Tuple[bool, Dict]:
    """获取股票价格（主函数）
    
    Args:
        symbol: 股票代码
        use_api: 是否使用API（True）或模拟数据（False）
        api_key: API密钥（如果需要）
        
    Returns:
        (success, result_dict)
        success: 是否成功获取
        result_dict: 包含股票信息的字典
    """
    if not symbol:
        return False, {'error': '股票代码不能为空'}
    
    symbol = symbol.strip().upper()
    
    try:
        if use_api:
            # 使用API获取真实数据（当前为模拟）
            api = StockAPI(api_key)
            price = api.get_real_time_price(symbol)
            source = 'api'
        else:
            # 使用模拟数据
            simulator = StockSimulator()
            price = simulator.get_simulated_price(symbol)
            source = 'simulation'
        
        if price is None:
            return False, {
                'error': f'未找到股票代码: {symbol}',
                'symbol': symbol,
                'source': source
            }
        
        # 获取股票名称（从模拟器中）
        simulator = StockSimulator()
        stock_info = simulator.stock_data.get(symbol, {})
        stock_name = stock_info.get('name', '未知')
        
        # 确定货币单位
        currency = 'USD' if '.' not in symbol else 'CNY'
        
        return True, {
            'symbol': symbol,
            'name': stock_name,
            'price': price,
            'currency': currency,
            'source': source,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }
        
    except Exception as e:
        return False, {
            'error': f'获取股票价格时出错: {str(e)}',
            'symbol': symbol,
            'source': 'api' if use_api else 'simulation'
        }


def get_multiple_stock_prices(symbols: list, use_api: bool = False) -> Dict:
    """批量获取多个股票价格
    
    Args:
        symbols: 股票代码列表
        use_api: 是否使用API
        
    Returns:
        包含所有股票价格的字典
    """
    results = {}
    
    for symbol in symbols:
        success, data = get_stock_price(symbol, use_api)
        results[symbol] = {
            'success': success,
            'data': data
        }
    
    return results


# 命令行测试函数
def main():
    """命令行测试"""
    print("股票功能模块测试")
    print("=" * 50)
    
    # 测试单个股票
    test_symbols = ['AAPL', 'GOOGL', '000001.SZ', 'INVALID']
    
    for symbol in test_symbols:
        print(f"\n查询股票: {symbol}")
        
        # 使用模拟数据
        success, result = get_stock_price(symbol, use_api=False)
        if success:
            print(f"  模拟数据: {result['name']} - ¥{result['price']} {result['currency']}")
        else:
            print(f"  错误: {result.get('error', '未知错误')}")
        
        # 使用API（模拟）
        success, result = get_stock_price(symbol, use_api=True)
        if success:
            print(f"  API数据: {result['name']} - ¥{result['price']} {result['currency']}")
        else:
            print(f"  API错误: {result.get('error', '未知错误')}")
    
    # 测试批量查询
    print("\n" + "=" * 50)
    print("批量查询测试:")
    batch_results = get_multiple_stock_prices(['AAPL', 'MSFT', '600519.SH'], use_api=False)
    
    for symbol, result in batch_results.items():
        if result['success']:
            data = result['data']
            print(f"  {symbol}: {data['name']} - ¥{data['price']} {data['currency']}")
        else:
            print(f"  {symbol}: 查询失败 - {result['data'].get('error')}")


if __name__ == '__main__':
    main()
