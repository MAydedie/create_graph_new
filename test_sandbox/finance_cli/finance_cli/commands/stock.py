#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
股票查询命令模块

提供股票价格查询功能，后续可集成各种股票数据API
"""

import click
from typing import Optional, Dict, Any


@click.command(name="stock")
@click.argument("symbol", required=True)
@click.option("--source", "-s", default="demo", help="数据源: demo(演示数据), yahoo(雅虎财经), sina(新浪财经)等")
@click.option("--verbose", "-v", is_flag=True, help="显示详细信息")
def stock_command(symbol: str, source: str, verbose: bool) -> None:
    """
    查询股票价格
    
    SYMBOL: 股票代码，如 AAPL, 000001.SZ, 600000.SH
    """
    try:
        # 获取股票数据
        stock_data = get_stock_price(symbol, source)
        
        if stock_data:
            # 显示基本信息
            click.echo(f"股票代码: {stock_data.get('symbol', symbol)}")
            click.echo(f"股票名称: {stock_data.get('name', '未知')}")
            click.echo(f"当前价格: {stock_data.get('price', 'N/A')}")
            
            # 如果启用了详细模式，显示更多信息
            if verbose:
                click.echo(f"数据来源: {stock_data.get('source', source)}")
                click.echo(f"更新时间: {stock_data.get('timestamp', 'N/A')}")
                
                # 显示涨跌幅信息
                change = stock_data.get('change')
                change_percent = stock_data.get('change_percent')
                if change is not None and change_percent is not None:
                    change_sign = "+" if change >= 0 else ""
                    click.echo(f"涨跌幅: {change_sign}{change} ({change_sign}{change_percent}%)")
                
                # 显示交易量信息
                volume = stock_data.get('volume')
                if volume:
                    click.echo(f"成交量: {volume}")
        else:
            click.echo(f"未找到股票代码: {symbol}", err=True)
            
    except Exception as e:
        click.echo(f"查询股票时发生错误: {str(e)}", err=True)


def get_stock_price(symbol: str, source: str = "demo") -> Optional[Dict[str, Any]]:
    """
    获取股票价格信息
    
    Args:
        symbol: 股票代码
        source: 数据源类型
        
    Returns:
        包含股票信息的字典，如果获取失败则返回None
    """
    # Normalize symbol: strip whitespace and convert to uppercase
    if symbol:
        symbol = symbol.strip().upper()
    
    # 根据数据源选择不同的获取方式
    if source == "demo":
        return _get_demo_stock_data(symbol)
    else:
        # 为后续集成真实API预留接口
        # 这里可以添加其他数据源的实现
        click.echo(f"暂不支持数据源: {source}，使用演示数据", err=True)
        return _get_demo_stock_data(symbol)


def _get_demo_stock_data(symbol: str) -> Dict[str, Any]:
    """
    获取演示股票数据（用于测试和演示）
    
    Args:
        symbol: 股票代码
        
    Returns:
        演示股票数据
    """
    # 演示数据映射
    demo_stocks = {
        "AAPL": {
            "symbol": "AAPL",
            "name": "苹果公司",
            "price": 175.25,
            "change": 2.15,
            "change_percent": 1.24,
            "volume": "45.2M",
            "source": "demo",
            "timestamp": "2024-01-15 15:30:00"
        },
        "GOOGL": {
            "symbol": "GOOGL",
            "name": "谷歌",
            "price": 142.80,
            "change": -0.75,
            "change_percent": -0.52,
            "volume": "28.7M",
            "source": "demo",
            "timestamp": "2024-01-15 15:30:00"
        },
        "000001.SZ": {
            "symbol": "000001.SZ",
            "name": "平安银行",
            "price": 10.25,
            "change": 0.12,
            "change_percent": 1.18,
            "volume": "125.3M",
            "source": "demo",
            "timestamp": "2024-01-15 15:00:00"
        },
        "600000.SH": {
            "symbol": "600000.SH",
            "name": "浦发银行",
            "price": 7.38,
            "change": -0.05,
            "change_percent": -0.67,
            "volume": "89.6M",
            "source": "demo",
            "timestamp": "2024-01-15 15:00:00"
        }
    }
    
    # 返回对应的演示数据，如果不存在则返回默认数据
    if symbol.upper() in demo_stocks:
        return demo_stocks[symbol.upper()]
    else:
        # 对于不存在的股票代码，返回一个默认的演示数据
        return {
            "symbol": symbol,
            "name": "演示股票",
            "price": 100.00,
            "change": 0.00,
            "change_percent": 0.00,
            "volume": "1.0M",
            "source": "demo",
            "timestamp": "2024-01-15 00:00:00"
        }


def format_stock_price(price: float, currency: str = "USD") -> str:
    """
    格式化股票价格显示
    
    Args:
        price: 股票价格
        currency: 货币类型
        
    Returns:
        格式化后的价格字符串
    """
    if currency == "USD":
        return f"${price:,.2f}"
    elif currency == "CNY":
        return f"¥{price:,.2f}"
    else:
        # Fallback to USD for unknown currencies
        return f"${price:,.2f}"


if __name__ == "__main__":
    # 直接运行时的测试代码
    stock_command(["AAPL", "--verbose"])
