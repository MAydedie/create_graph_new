#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CLI工具主程序入口

允许通过以下方式运行：
1. python -m cli_tool
2. python src/cli_tool/__main__.py
"""

import sys
import argparse
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from cli_tool.core import main as cli_main


def main():
    """主函数入口"""
    parser = argparse.ArgumentParser(
        description="CLI工具 - 多功能命令行工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python -m cli_tool --help
  python -m cli_tool <command> [options]
        """
    )
    
    # 添加通用参数
    parser.add_argument(
        '-v', '--version',
        action='store_true',
        help='显示版本信息'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='显示详细输出'
    )
    
    # 如果提供了参数，则解析并处理
    if len(sys.argv) > 1:
        args = parser.parse_args()
        
        if args.version:
            from cli_tool import __version__
            print(f"CLI工具版本: {__version__}")
            return 0
        
        # 设置详细模式
        if args.verbose:
            print("详细模式已启用")
    
    # 调用核心主函数
    try:
        return cli_main()
    except KeyboardInterrupt:
        print("\n操作已取消")
        return 130
    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
