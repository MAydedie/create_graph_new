#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量运行Python文件的主脚本

功能：
1. 遍历指定目录，识别所有.py文件
2. 使用subprocess运行每个.py文件
3. 捕获stdout、stderr和返回码
4. 汇总运行结果
"""

import os
import sys
import subprocess
import argparse
import time
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime


@dataclass
class RunResult:
    """运行结果数据类"""
    file_path: str
    success: bool
    return_code: int
    stdout: str
    stderr: str
    execution_time: float
    timestamp: datetime


def find_python_files(directory: str, recursive: bool = True) -> List[str]:
    """
    查找目录中的所有Python文件
    
    Args:
        directory: 要搜索的目录路径
        recursive: 是否递归搜索子目录
        
    Returns:
        Python文件路径列表
    """
    python_files = []
    
    if recursive:
        # 递归搜索所有子目录
        for root, _, files in os.walk(directory):
            for file in files:
                if file.endswith('.py'):
                    python_files.append(os.path.join(root, file))
    else:
        # 仅搜索当前目录
        for item in os.listdir(directory):
            item_path = os.path.join(directory, item)
            if os.path.isfile(item_path) and item.endswith('.py'):
                python_files.append(item_path)
    
    return sorted(python_files)


def run_python_file(file_path: str, timeout: Optional[int] = None) -> RunResult:
    """
    运行单个Python文件并捕获结果
    
    Args:
        file_path: Python文件路径
        timeout: 超时时间（秒），None表示无超时
        
    Returns:
        RunResult对象包含运行结果
    """
    start_time = time.time()
    timestamp = datetime.now()
    
    try:
        # 使用subprocess运行Python文件
        result = subprocess.run(
            [sys.executable, file_path],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=os.path.dirname(file_path)  # 在文件所在目录运行
        )
        
        execution_time = time.time() - start_time
        
        return RunResult(
            file_path=file_path,
            success=result.returncode == 0,
            return_code=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            execution_time=execution_time,
            timestamp=timestamp
        )
        
    except subprocess.TimeoutExpired:
        execution_time = time.time() - start_time
        return RunResult(
            file_path=file_path,
            success=False,
            return_code=-1,
            stdout="",
            stderr=f"执行超时（{timeout}秒）",
            execution_time=execution_time,
            timestamp=timestamp
        )
    except Exception as e:
        execution_time = time.time() - start_time
        return RunResult(
            file_path=file_path,
            success=False,
            return_code=-1,
            stdout="",
            stderr=f"执行错误: {str(e)}",
            execution_time=execution_time,
            timestamp=timestamp
        )


def print_result_summary(results: List[RunResult]) -> None:
    """
    打印运行结果摘要
    
    Args:
        results: 运行结果列表
    """
    if not results:
        print("未找到任何Python文件")
        return
    
    successful = sum(1 for r in results if r.success)
    failed = len(results) - successful
    total_time = sum(r.execution_time for r in results)
    
    print("\n" + "="*60)
    print("运行结果摘要")
    print("="*60)
    print(f"总文件数: {len(results)}")
    print(f"成功: {successful}")
    print(f"失败: {failed}")
    print(f"总执行时间: {total_time:.2f}秒")
    print("="*60)
    
    # 打印详细结果
    for i, result in enumerate(results, 1):
        status = "✓" if result.success else "✗"
        print(f"\n{i}. {status} {result.file_path}")
        print(f"   状态: {'成功' if result.success else '失败'}")
        print(f"   返回码: {result.return_code}")
        print(f"   执行时间: {result.execution_time:.2f}秒")
        
        if result.stderr:
            print(f"   错误输出: {result.stderr[:200]}{'...' if len(result.stderr) > 200 else ''}")
        
        if result.stdout and len(result.stdout.strip()) > 0:
            output_preview = result.stdout.strip().split('\n')[0]
            print(f"   输出预览: {output_preview[:100]}{'...' if len(output_preview) > 100 else ''}")


def save_results_to_file(results: List[RunResult], output_file: str) -> None:
    """
    将运行结果保存到文件
    
    Args:
        results: 运行结果列表
        output_file: 输出文件路径
    """
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("Python文件批量运行结果\n")
            f.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("="*60 + "\n\n")
            
            for result in results:
                f.write(f"文件: {result.file_path}\n")
                f.write(f"状态: {'成功' if result.success else '失败'}\n")
                f.write(f"返回码: {result.return_code}\n")
                f.write(f"执行时间: {result.execution_time:.2f}秒\n")
                f.write(f"时间戳: {result.timestamp.strftime('%Y-%m-%d %H:%M:%S')}\n")
                
                if result.stdout:
                    f.write(f"标准输出:\n{result.stdout}\n")
                
                if result.stderr:
                    f.write(f"错误输出:\n{result.stderr}\n")
                
                f.write("-"*60 + "\n\n")
        
        print(f"结果已保存到: {output_file}")
        
    except Exception as e:
        print(f"保存结果到文件失败: {str(e)}")


def main() -> None:
    """主函数"""
    parser = argparse.ArgumentParser(
        description='批量运行Python文件并捕获输出',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s .                     # 运行当前目录及其子目录中的所有.py文件
  %(prog)s /path/to/dir -r false # 仅运行指定目录（不含子目录）中的.py文件
  %(prog)s . -t 30 -o results.txt # 设置30秒超时并保存结果到文件
        """
    )
    
    parser.add_argument(
        'directory',
        nargs='?',
        default='.',
        help='要搜索Python文件的目录（默认: 当前目录）'
    )
    
    parser.add_argument(
        '-r', '--recursive',
        type=str,
        default='true',
        choices=['true', 'false'],
        help='是否递归搜索子目录（默认: true）'
    )
    
    parser.add_argument(
        '-t', '--timeout',
        type=int,
        default=None,
        help='每个文件的执行超时时间（秒），默认无超时'
    )
    
    parser.add_argument(
        '-o', '--output',
        type=str,
        default=None,
        help='将结果保存到指定文件'
    )
    
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='显示详细输出'
    )
    
    args = parser.parse_args()
    
    # 检查目录是否存在
    if not os.path.isdir(args.directory):
        print(f"错误: 目录 '{args.directory}' 不存在")
        sys.exit(1)
    
    # 转换递归参数
    recursive = args.recursive.lower() == 'true'
    
    print(f"搜索目录: {os.path.abspath(args.directory)}")
    print(f"递归搜索: {'是' if recursive else '否'}")
    print(f"超时设置: {args.timeout if args.timeout else '无'}")
    
    # 查找Python文件
    python_files = find_python_files(args.directory, recursive)
    
    if not python_files:
        print("未找到任何Python文件")
        sys.exit(0)
    
    print(f"\n找到 {len(python_files)} 个Python文件:")
    for file in python_files:
        print(f"  - {file}")
    
    # 运行所有Python文件
    print(f"\n开始运行Python文件...")
    results = []
    
    for i, file_path in enumerate(python_files, 1):
        if args.verbose:
            print(f"\n[{i}/{len(python_files)}] 运行: {file_path}")
        
        result = run_python_file(file_path, args.timeout)
        results.append(result)
        
        if args.verbose:
            status = "成功" if result.success else "失败"
            print(f"    状态: {status}, 时间: {result.execution_time:.2f}秒")
            if result.stderr:
                print(f"    错误: {result.stderr[:100]}")
        else:
            print(f"  {i:3d}/{len(python_files)}: {'✓' if result.success else '✗'} {os.path.basename(file_path)}")
    
    # 打印摘要
    print_result_summary(results)
    
    # 保存结果到文件
    if args.output:
        save_results_to_file(results, args.output)
    
    # 如果有失败的文件，返回非零退出码
    if any(not r.success for r in results):
        sys.exit(1)


if __name__ == '__main__':
    main()
