#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
命令行接口核心模块

使用argparse库定义命令、参数和主逻辑入口
"""

import argparse
import sys
import os
from typing import Optional, List

# 添加项目根目录到路径，确保可以导入其他模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main() -> None:
    """
    命令行主函数
    """
    parser = create_parser()
    args = parser.parse_args()
    
    # 如果没有提供子命令，显示帮助信息
    if not hasattr(args, 'func'):
        parser.print_help()
        sys.exit(1)
    
    # 执行对应的子命令函数
    try:
        args.func(args)
    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)


def create_parser() -> argparse.ArgumentParser:
    """
    创建命令行参数解析器
    
    Returns:
        argparse.ArgumentParser: 配置好的参数解析器
    """
    parser = argparse.ArgumentParser(
        description="命令行工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s init --name myproject
  %(prog)s process --input data.txt --output result.txt
  %(prog)s --version
        """
    )
    
    # 添加全局参数
    parser.add_argument(
        '--version',
        action='version',
        version='%(prog)s 1.0.0'
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='显示详细输出'
    )
    
    # 创建子命令解析器
    subparsers = parser.add_subparsers(
        title='可用命令',
        description='有效的子命令',
        dest='command',
        help='子命令帮助信息'
    )
    
    # 初始化命令
    init_parser = subparsers.add_parser(
        'init',
        help='初始化项目或配置'
    )
    init_parser.add_argument(
        '--name',
        required=True,
        help='项目名称'
    )
    init_parser.add_argument(
        '--path',
        default='.',
        help='项目路径（默认当前目录）'
    )
    init_parser.set_defaults(func=handle_init)
    
    # 处理命令
    process_parser = subparsers.add_parser(
        'process',
        help='处理数据或文件'
    )
    process_parser.add_argument(
        '-i', '--input',
        required=True,
        help='输入文件路径'
    )
    process_parser.add_argument(
        '-o', '--output',
        help='输出文件路径（可选）'
    )
    process_parser.add_argument(
        '--format',
        choices=['json', 'csv', 'txt'],
        default='json',
        help='输出格式（默认: json）'
    )
    process_parser.set_defaults(func=handle_process)
    
    # 配置命令
    config_parser = subparsers.add_parser(
        'config',
        help='管理配置'
    )
    config_parser.add_argument(
        '--set',
        nargs=2,
        metavar=('KEY', 'VALUE'),
        help='设置配置项'
    )
    config_parser.add_argument(
        '--get',
        help='获取配置项'
    )
    config_parser.add_argument(
        '--list',
        action='store_true',
        help='列出所有配置'
    )
    config_parser.set_defaults(func=handle_config)
    
    return parser


def handle_init(args: argparse.Namespace) -> None:
    """
    处理初始化命令
    
    Args:
        args: 命令行参数
    """
    if args.verbose:
        print(f"正在初始化项目: {args.name}")
        print(f"项目路径: {args.path}")
    
    # 这里实现实际的初始化逻辑
    print(f"项目 '{args.name}' 初始化完成")


def handle_process(args: argparse.Namespace) -> None:
    """
    处理处理命令
    
    Args:
        args: 命令行参数
    """
    if args.verbose:
        print(f"正在处理文件: {args.input}")
        if args.output:
            print(f"输出文件: {args.output}")
        print(f"输出格式: {args.format}")
    
    # 检查输入文件是否存在
    if not os.path.exists(args.input):
        raise FileNotFoundError(f"输入文件不存在: {args.input}")
    
    # 这里实现实际的处理逻辑
    print(f"文件处理完成: {args.input}")
    if args.output:
        print(f"结果已保存到: {args.output}")


def handle_config(args: argparse.Namespace) -> None:
    """
    处理配置命令
    
    Args:
        args: 命令行参数
    """
    if args.set:
        key, value = args.set
        if args.verbose:
            print(f"设置配置项: {key} = {value}")
        # 这里实现实际的配置设置逻辑
        print(f"配置项 '{key}' 已设置为 '{value}'")
    elif args.get:
        if args.verbose:
            print(f"获取配置项: {args.get}")
        # 这里实现实际的配置获取逻辑
        print(f"配置项 '{args.get}' 的值是: example_value")
    elif args.list:
        if args.verbose:
            print("列出所有配置项")
        # 这里实现实际的配置列表逻辑
        print("配置列表:")
        print("  key1: value1")
        print("  key2: value2")
        print("  key3: value3")
    else:
        print("请指定配置操作: --set, --get 或 --list")


if __name__ == '__main__':
    main()
