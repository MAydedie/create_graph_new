#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量运行Python文件脚本

该脚本用于遍历指定目录，查找所有.py文件，并使用subprocess运行每个文件，
捕获stdout、stderr和返回码，最后生成运行报告。
"""

import os
import sys
import subprocess
import argparse
import time
from pathlib import Path
from typing import List, Dict, Tuple
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


def find_python_files(directory: str, exclude_dirs: List[str] = None) -> List[str]:
    """
    查找目录中的所有Python文件
    
    Args:
        directory: 要搜索的目录路径
        exclude_dirs: 要排除的目录列表
        
    Returns:
        Python文件路径列表
    """
    if exclude_dirs is None:
        exclude_dirs = ['__pycache__', '.git', '.venv', 'venv', 'env']
    
    python_files = []
    
    for root, dirs, files in os.walk(directory):
        # 排除不需要的目录
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        
        for file in files:
            if file.endswith('.py'):
                full_path = os.path.join(root, file)
                python_files.append(full_path)
    
    return sorted(python_files)


def run_python_file(file_path: str, timeout: int = 30) -> RunResult:
    """
    运行单个Python文件
    
    Args:
        file_path: Python文件路径
        timeout: 运行超时时间（秒）
        
    Returns:
        RunResult对象，包含运行结果信息
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
            cwd=os.path.dirname(file_path) if os.path.dirname(file_path) else '.'
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
            stdout='',
            stderr=f'运行超时（{timeout}秒）',
            execution_time=execution_time,
            timestamp=timestamp
        )
    except Exception as e:
        execution_time = time.time() - start_time
        return RunResult(
            file_path=file_path,
            success=False,
            return_code=-1,
            stdout='',
            stderr=f'运行异常: {str(e)}',
            execution_time=execution_time,
            timestamp=timestamp
        )


def print_results_summary(results: List[RunResult]):
    """打印运行结果摘要"""
    print("\n" + "="*60)
    print("运行结果摘要")
    print("="*60)
    
    total_files = len(results)
    successful_files = sum(1 for r in results if r.success)
    failed_files = total_files - successful_files
    total_time = sum(r.execution_time for r in results)
    
    print(f"总文件数: {total_files}")
    print(f"成功运行: {successful_files}")
    print(f"运行失败: {failed_files}")
    print(f"总运行时间: {total_time:.2f}秒")
    print(f"平均运行时间: {total_time/max(total_files, 1):.2f}秒/文件")
    
    if failed_files > 0:
        print("\n失败文件列表:")
        for result in results:
            if not result.success:
                print(f"  - {result.file_path}")
                if result.stderr:
                    print(f"    错误: {result.stderr[:100]}..." if len(result.stderr) > 100 else f"    错误: {result.stderr}")
    
    print("="*60)


def save_detailed_report(results: List[RunResult], report_file: str = "run_report.txt"):
    """保存详细运行报告到文件"""
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write("Python文件批量运行详细报告\n")
        f.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("="*80 + "\n\n")
        
        for i, result in enumerate(results, 1):
            f.write(f"文件 {i}: {result.file_path}\n")
            f.write(f"运行时间: {result.timestamp.strftime('%H:%M:%S')}\n")
            f.write(f"执行耗时: {result.execution_time:.2f}秒\n")
            f.write(f"运行状态: {'成功' if result.success else '失败'}\n")
            f.write(f"返回码: {result.return_code}\n")
            
            if result.stdout:
                f.write(f"标准输出:\n{result.stdout}\n")
            
            if result.stderr:
                f.write(f"错误输出:\n{result.stderr}\n")
            
            f.write("-"*80 + "\n\n")
        
        # 添加统计信息
        total_files = len(results)
        successful_files = sum(1 for r in results if r.success)
        failed_files = total_files - successful_files
        total_time = sum(r.execution_time for r in results)
        
        f.write("统计信息:\n")
        f.write(f"总文件数: {total_files}\n")
        f.write(f"成功运行: {successful_files}\n")
        f.write(f"运行失败: {failed_files}\n")
        f.write(f"总运行时间: {total_time:.2f}秒\n")
        f.write(f"平均运行时间: {total_time/max(total_files, 1):.2f}秒/文件\n")
        
    print(f"详细报告已保存到: {report_file}")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='批量运行Python文件')
    parser.add_argument('directory', nargs='?', default='.', 
                       help='要扫描的目录（默认为当前目录）')
    parser.add_argument('--exclude', nargs='+', default=['__pycache__', '.git', '.venv'],
                       help='要排除的目录列表')
    parser.add_argument('--timeout', type=int, default=30,
                       help='每个文件运行超时时间（秒，默认30）')
    parser.add_argument('--report', action='store_true',
                       help='生成详细运行报告文件')
    parser.add_argument('--report-file', default='run_report.txt',
                       help='报告文件名（默认run_report.txt）')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='显示详细输出')
    
    args = parser.parse_args()
    
    # 检查目录是否存在
    if not os.path.isdir(args.directory):
        print(f"错误: 目录 '{args.directory}' 不存在")
        sys.exit(1)
    
    print(f"正在扫描目录: {os.path.abspath(args.directory)}")
    print(f"排除目录: {', '.join(args.exclude)}")
    
    # 查找Python文件
    python_files = find_python_files(args.directory, args.exclude)
    
    if not python_files:
        print("未找到任何Python文件")
        return
    
    print(f"找到 {len(python_files)} 个Python文件")
    
    # 运行所有Python文件
    results = []
    for i, file_path in enumerate(python_files, 1):
        print(f"运行文件 {i}/{len(python_files)}: {file_path}")
        
        result = run_python_file(file_path, args.timeout)
        results.append(result)
        
        if args.verbose:
            if result.success:
                print(f"  状态: 成功 (耗时: {result.execution_time:.2f}秒)")
                if result.stdout:
                    print(f"  输出: {result.stdout[:100]}..." if len(result.stdout) > 100 else f"  输出: {result.stdout}")
            else:
                print(f"  状态: 失败 (返回码: {result.return_code})")
                if result.stderr:
                    print(f"  错误: {result.stderr[:100]}..." if len(result.stderr) > 100 else f"  错误: {result.stderr}")
        else:
            status = "成功" if result.success else "失败"
            print(f"  状态: {status} (耗时: {result.execution_time:.2f}秒)")
    
    # 打印摘要
    print_results_summary(results)
    
    # 生成详细报告
    if args.report:
        save_detailed_report(results, args.report_file)
    
    # 如果有失败的文件，返回非零退出码
    if any(not r.success for r in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
