#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
命令行界面主模块

使用click库实现命令行参数解析和子命令管理
"""

import click
import sys
import os
from pathlib import Path
from typing import Optional

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent

# 版本信息
__version__ = "0.1.0"


def print_version(ctx, param, value):
    """显示版本信息"""
    if not value or ctx.resilient_parsing:
        return
    click.echo(f"my-cli-tool v{__version__}")
    ctx.exit()


@click.group()
@click.option(
    "--version",
    is_flag=True,
    callback=print_version,
    expose_value=False,
    is_eager=True,
    help="显示版本信息"
)
@click.option(
    "-v", "--verbose",
    is_flag=True,
    help="启用详细输出模式"
)
@click.pass_context
def cli(ctx, verbose):
    """
    My CLI Tool - 一个多功能命令行工具
    
    提供配置管理、数据处理等功能
    """
    # 确保ctx.obj存在
    ctx.ensure_object(dict)
    
    # 设置verbose标志
    ctx.obj["verbose"] = verbose
    
    if verbose:
        click.echo("详细模式已启用")


@cli.command()
@click.option(
    "--config",
    type=click.Path(dir_okay=False, writable=True),
    default=str(PROJECT_ROOT / "config.yaml"),
    help="配置文件路径"
)
@click.option(
    "--init",
    is_flag=True,
    help="初始化配置文件"
)
@click.pass_context
def config(ctx, config, init):
    """配置管理命令"""
    if ctx.obj.get("verbose"):
        click.echo(f"配置文件路径: {config}")
    
    if init:
        # 初始化配置文件
        config_path = Path(config)
        if config_path.exists():
            click.confirm("配置文件已存在，是否覆盖？", abort=True)
        
        default_config = """# My CLI Tool 配置文件

# 数据库配置
database:
  host: localhost
  port: 5432
  username: admin
  password: secret

# 日志配置
logging:
  level: INFO
  file: logs/app.log

# 其他设置
settings:
  timeout: 30
  retry_count: 3
"""
        
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(default_config, encoding="utf-8")
        click.echo(f"配置文件已创建: {config}")
    else:
        # 显示配置信息
        config_path = Path(config)
        if config_path.exists():
            click.echo(f"配置文件内容 ({config}):")
            click.echo(config_path.read_text(encoding="utf-8"))
        else:
            click.echo(f"配置文件不存在: {config}")
            click.echo("使用 --init 选项初始化配置文件")


@cli.command()
@click.argument("input_file", type=click.Path(exists=True))
@click.option(
    "-o", "--output",
    type=click.Path(writable=True),
    help="输出文件路径"
)
@click.option(
    "--format",
    type=click.Choice(["json", "csv", "yaml"], case_sensitive=False),
    default="json",
    help="输出格式"
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="试运行，不实际写入文件"
)
@click.pass_context
def process(ctx, input_file, output, format, dry_run):
    """数据处理命令"""
    verbose = ctx.obj.get("verbose")
    
    if verbose:
        click.echo(f"处理文件: {input_file}")
        click.echo(f"输出格式: {format}")
        if dry_run:
            click.echo("试运行模式")
    
    # 检查输入文件
    input_path = Path(input_file)
    if not input_path.is_file():
        click.echo(f"错误: 输入文件不存在或不是文件: {input_file}", err=True)
        sys.exit(1)
    
    # 确定输出文件路径
    if output:
        output_path = Path(output)
    else:
        # 默认输出文件名
        stem = input_path.stem
        output_path = input_path.parent / f"{stem}_processed.{format}"
    
    if verbose:
        click.echo(f"输出文件: {output_path}")
    
    # 模拟数据处理
    try:
        # 读取输入文件
        content = input_path.read_text(encoding="utf-8")
        lines = content.splitlines()
        
        if verbose:
            click.echo(f"读取到 {len(lines)} 行数据")
        
        # 根据格式处理数据
        if format == "json":
            processed = f"{{\"data\": {len(lines)}, \"filename\": \"{input_path.name}\"}}"
        elif format == "csv":
            processed = "id,content\n" + "\n".join([f"{i+1},{line}" for i, line in enumerate(lines[:5])])
            if len(lines) > 5:
                processed += f"\n... 还有 {len(lines)-5} 行数据"
        else:  # yaml
            processed = f"data:\n  count: {len(lines)}\n  filename: {input_path.name}"
        
        if dry_run:
            click.echo("试运行结果:")
            click.echo(processed)
            click.echo(f"将写入到: {output_path}")
        else:
            # 写入输出文件
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(processed, encoding="utf-8")
            click.echo(f"数据处理完成，结果已保存到: {output_path}")
            
    except Exception as e:
        click.echo(f"处理文件时出错: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option(
    "--name",
    prompt="请输入您的姓名",
    help="用户姓名"
)
@click.option(
    "--age",
    type=int,
    prompt="请输入您的年龄",
    help="用户年龄"
)
@click.option(
    "--email",
    prompt="请输入您的邮箱",
    help="用户邮箱"
)
@click.pass_context
def hello(ctx, name, age, email):
    """打招呼命令"""
    verbose = ctx.obj.get("verbose")
    
    if verbose:
        click.echo(f"收到参数: name={name}, age={age}, email={email}")
    
    click.echo(f"你好 {name}！")
    click.echo(f"年龄: {age}")
    click.echo(f"邮箱: {email}")
    
    if age >= 18:
        click.echo("您已成年")
    else:
        click.echo("您未成年")


def main():
    """主函数入口"""
    try:
        cli(obj={})
    except click.exceptions.Abort:
        click.echo("操作已取消")
        sys.exit(1)
    except Exception as e:
        click.echo(f"程序出错: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
