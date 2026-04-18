#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
命令行工具入口点

此文件作为my_cli_tool的入口点，负责解析命令行参数并调用主逻辑。
"""

import sys
import argparse
from typing import Optional, List

# 导入主逻辑模块
from my_cli_tool.core import main_logic
from my_cli_tool.utils import logger


def parse_args(args: Optional[List[str]] = None) -> argparse.Namespace:
    """
    解析命令行参数
    
    Args:
        args: 命令行参数列表，默认为sys.argv[1:]
        
    Returns:
        解析后的参数命名空间
    """
    parser = argparse.ArgumentParser(
        description="我的CLI工具 - 一个实用的命令行工具",
        epilog="示例: python -m my_cli_tool --input data.txt --output result.txt"
    )
    
    # 添加命令行参数
    parser.add_argument(
        "--input",
        "-i",
        type=str,
        help="输入文件路径",
        required=True
    )
    
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        help="输出文件路径",
        required=True
    )
    
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="启用详细输出模式"
    )
    
    parser.add_argument(
        "--config",
        "-c",
        type=str,
        help="配置文件路径",
        default="config.yaml"
    )
    
    # 解析参数
    return parser.parse_args(args)


def main() -> int:
    """
    主函数 - 命令行工具入口点
    
    Returns:
        退出码: 0表示成功，非0表示失败
    """
    try:
        # 解析命令行参数
        args = parse_args()
        
        # 配置日志级别
        if args.verbose:
            logger.set_level("DEBUG")
        else:
            logger.set_level("INFO")
        
        logger.info(f"开始处理: 输入={args.input}, 输出={args.output}")
        
        # 调用主逻辑
        result = main_logic.process(
            input_path=args.input,
            output_path=args.output,
            config_path=args.config
        )
        
        if result:
            logger.info("处理完成")
            return 0
        else:
            logger.error("处理失败")
            return 1
            
    except KeyboardInterrupt:
        logger.warning("用户中断操作")
        return 130
        
    except FileNotFoundError as e:
        logger.error(f"文件未找到: {e}")
        return 2
        
    except PermissionError as e:
        logger.error(f"权限错误: {e}")
        return 3
        
    except Exception as e:
        logger.error(f"未预期的错误: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    # 当直接运行此模块时，执行main函数并退出
    sys.exit(main())
