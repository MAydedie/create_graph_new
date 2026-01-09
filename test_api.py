#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试Web API和分析流程
"""

import requests
import time
import json
import os

BASE_URL = "http://127.0.0.1:5000"

def test_analysis():
    """测试分析API"""
    print("\n=== 开始测试代码分析API ===\n")
    
    # 获取当前项目路径
    project_path = os.path.dirname(os.path.abspath(__file__))
    print(f"📁 分析项目路径: {project_path}\n")
    
    # 1. 发起分析请求
    print("1️⃣  发起分析请求...")
    response = requests.post(
        f"{BASE_URL}/api/analyze",
        json={"project_path": project_path}
    )
    
    if response.status_code != 200:
        print(f"❌ 分析请求失败: {response.status_code}")
        print(f"错误信息: {response.text}")
        return False
    
    print(f"✅ 分析请求成功\n")
    
    # 2. 实时监控分析进度
    print("2️⃣  监控分析进度...")
    max_wait = 60  # 最多等待60秒
    elapsed = 0
    check_interval = 0.5  # 每0.5秒检查一次
    
    while elapsed < max_wait:
        response = requests.get(f"{BASE_URL}/api/status")
        
        if response.status_code != 200:
            print(f"❌ 获取状态失败: {response.status_code}")
            return False
        
        status = response.json()
        progress = status.get('progress', 0)
        status_msg = status.get('status', '未知')
        is_analyzing = status.get('is_analyzing', False)
        
        # 打印进度条
        bar_length = 40
        filled = int(bar_length * progress / 100)
        bar = '█' * filled + '░' * (bar_length - filled)
        print(f"\r📊 进度: [{bar}] {progress}% - {status_msg}", end='', flush=True)
        
        # 检查是否完成
        if not is_analyzing and progress == 100:
            print("\n✅ 分析完成！\n")
            break
        
        time.sleep(check_interval)
        elapsed += check_interval
    else:
        print(f"\n⏱️  等待超时（{max_wait}秒）")
        return False
    
    # 3. 获取分析结果
    print("3️⃣  获取分析结果...")
    response = requests.get(f"{BASE_URL}/api/result")
    
    if response.status_code != 200:
        print(f"❌ 获取结果失败: {response.status_code}")
        return False
    
    result = response.json()
    nodes_count = len(result.get('nodes', []))
    edges_count = len(result.get('edges', []))
    metadata = result.get('metadata', {})
    
    print(f"✅ 结果获取成功")
    print(f"\n📊 分析统计:")
    print(f"  - 节点数量: {nodes_count}")
    print(f"  - 边数量: {edges_count}")
    print(f"  - 类数: {metadata.get('total_classes', 0)}")
    print(f"  - 方法数: {metadata.get('total_methods', 0)}")
    print(f"  - 函数数: {metadata.get('total_functions', 0)}")
    print(f"  - 文件数: {metadata.get('total_files', 0)}")
    print(f"  - 总代码行数: {metadata.get('total_lines_of_code', 0)}")
    
    return True

if __name__ == '__main__':
    try:
        success = test_analysis()
        if success:
            print("\n✅ 所有测试通过！Web应用运行正常。")
            print("📍 访问地址: http://127.0.0.1:5000")
        else:
            print("\n❌ 测试失败，请检查Flask服务器是否运行。")
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        print("请确保Flask服务器运行在 http://127.0.0.1:5000")
