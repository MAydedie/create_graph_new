#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
金融数据CLI工具 - 主入口点

使用Click框架构建命令行界面，提供股票数据、投资组合管理等功能
"""

import click
from typing import Optional


@click.group()
@click.version_option(version="1.0.0", prog_name="finance-cli")
@click.option('--verbose', '-v', is_flag=True, help='启用详细输出模式')
@click.pass_context
def cli(ctx: click.Context, verbose: bool) -> None:
    """
    金融数据命令行工具
    
    提供股票数据查询、投资组合管理等功能
    """
    # 确保ctx.obj存在且为字典
    ctx.ensure_object(dict)
    
    # 设置全局配置
    ctx.obj['verbose'] = verbose
    
    if verbose:
        click.echo("详细模式已启用")


@cli.group()
def stock() -> None:
    """股票数据相关命令"""
    pass


@stock.command()
@click.argument('symbol', type=str)
@click.option('--period', '-p', type=click.Choice(['1d', '5d', '1mo', '3mo', '6mo', '1y', '2y', '5y', '10y', 'ytd', 'max']),
              default='1mo', help='数据时间周期')
@click.option('--interval', '-i', type=click.Choice(['1m', '2m', '5m', '15m', '30m', '60m', '90m', '1h', '1d', '5d', '1wk', '1mo', '3mo']),
              default='1d', help='数据时间间隔')
@click.pass_context
def quote(ctx: click.Context, symbol: str, period: str, interval: str) -> None:
    """
    获取股票报价数据
    
    SYMBOL: 股票代码（例如：AAPL, 000001.SZ）
    """
    if ctx.obj.get('verbose'):
        click.echo(f"获取股票 {symbol} 的报价数据...")
        click.echo(f"周期: {period}, 间隔: {interval}")
    
    # 这里将调用实际的股票数据获取逻辑
    click.echo(f"股票 {symbol} 的报价数据（模拟）")
    click.echo(f"当前价格: $150.25")
    click.echo(f"涨跌幅: +2.5%")
    click.echo(f"成交量: 10,234,567")


@stock.command()
@click.argument('symbol', type=str)
@click.option('--output', '-o', type=click.Choice(['table', 'json', 'csv']),
              default='table', help='输出格式')
@click.pass_context
def info(ctx: click.Context, symbol: str, output: str) -> None:
    """
    获取股票基本信息
    
    SYMBOL: 股票代码
    """
    if ctx.obj.get('verbose'):
        click.echo(f"获取股票 {symbol} 的基本信息...")
    
    click.echo(f"股票 {symbol} 的基本信息（模拟）")
    click.echo(f"公司名称: 示例公司")
    click.echo(f"行业: 科技")
    click.echo(f"市值: $2.5T")
    click.echo(f"市盈率: 25.3")


@cli.group()
def portfolio() -> None:
    """投资组合管理相关命令"""
    pass


@portfolio.command()
@click.argument('name', type=str, required=False)
@click.pass_context
def list(ctx: click.Context, name: Optional[str]) -> None:
    """
    列出投资组合
    
    NAME: 可选的投资组合名称
    """
    if ctx.obj.get('verbose'):
        click.echo("列出投资组合...")
    
    if name:
        click.echo(f"投资组合 '{name}' 的详细信息（模拟）")
        click.echo("持仓:")
        click.echo("  AAPL: 100股")
        click.echo("  MSFT: 50股")
        click.echo("总价值: $25,000")
    else:
        click.echo("所有投资组合（模拟）:")
        click.echo("  1. 默认组合")
        click.echo("  2. 科技组合")
        click.echo("  3. 保守组合")


@portfolio.command()
@click.argument('name', type=str)
@click.option('--description', '-d', type=str, help='投资组合描述')
@click.pass_context
def create(ctx: click.Context, name: str, description: Optional[str]) -> None:
    """
    创建新的投资组合
    
    NAME: 投资组合名称
    """
    if ctx.obj.get('verbose'):
        click.echo(f"创建投资组合 '{name}'...")
        if description:
            click.echo(f"描述: {description}")
    
    click.echo(f"已创建投资组合: {name}")
    if description:
        click.echo(f"描述: {description}")


@cli.command()
@click.option('--config', '-c', type=click.Path(exists=True),
              help='配置文件路径')
@click.pass_context
def config(ctx: click.Context, config: Optional[str]) -> None:
    """
    管理配置
    """
    if ctx.obj.get('verbose'):
        click.echo("配置管理...")
        if config:
            click.echo(f"使用配置文件: {config}")
    
    click.echo("当前配置（模拟）:")
    click.echo("  API密钥: 已设置")
    click.echo("  数据源: yfinance")
    click.echo("  默认输出格式: table")


@cli.command()
@click.pass_context
def version(ctx: click.Context) -> None:
    """显示版本信息"""
    click.echo("finance-cli v1.0.0")
    click.echo("金融数据命令行工具")


if __name__ == '__main__':
    cli(obj={})
