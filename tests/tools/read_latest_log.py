#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
读取最新的功能层级分析日志文件
"""

import os
import glob
from pathlib import Path

def get_latest_log_file():
    """获取最新的日志文件"""
    logs_dir = Path(__file__).parent / 'logs'
    
    if not logs_dir.exists():
        print(f"日志文件夹不存在: {logs_dir}")
        return None
    
    # 查找所有日志文件
    log_files = list(logs_dir.glob('function_hierarchy_*.log'))
    
    if not log_files:
        print(f"日志文件夹中没有找到日志文件")
        return None
    
    # 按修改时间排序，返回最新的
    latest_log = max(log_files, key=lambda p: p.stat().st_mtime)
    
    return latest_log

def read_log_file(log_file_path):
    """读取日志文件内容"""
    try:
        with open(log_file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        print(f"读取日志文件失败: {e}")
        return None

if __name__ == '__main__':
    log_file = get_latest_log_file()
    
    if log_file:
        print(f"找到最新日志文件: {log_file}")
        print(f"文件大小: {log_file.stat().st_size} 字节")
        print(f"修改时间: {log_file.stat().st_mtime}")
        print("=" * 80)
        
        content = read_log_file(log_file)
        if content:
            # 显示最后1000行（如果文件很大）
            lines = content.split('\n')
            if len(lines) > 1000:
                print("文件较大，显示最后1000行：")
                print("\n".join(lines[-1000:]))
            else:
                print(content)
    else:
        print("未找到日志文件")
















