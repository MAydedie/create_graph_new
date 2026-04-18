#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试脚本：hello.py

这是一个简单的测试文件，用于验证主脚本的正常执行路径。
打印 'Hello, World!' 作为基本功能验证。
"""

import sys
from unittest.mock import Mock, patch


def main():
    """
    主函数：打印欢迎信息
    
    这是一个简单的示例函数，用于演示正常执行路径。
    在实际测试中，可以替换为更复杂的逻辑。
    """
    print("Hello, World!")
    return 0


def test_main_with_mock():
    """
    使用Mock测试主函数
    
    示例：模拟print函数以验证其被正确调用
    """
    # 创建一个Mock对象来模拟print函数
    mock_print = Mock()
    
    # 使用patch临时替换print函数
    with patch('builtins.print', mock_print):
        result = main()
        
        # 验证print被调用了一次
        mock_print.assert_called_once()
        # 验证print被调用的参数是'Hello, World!'
        mock_print.assert_called_with("Hello, World!")
        # 验证返回值是0
        assert result == 0
        
    print("测试通过: print函数被正确调用")
    return True


def test_main_output(capsys):
    """
    测试主函数的实际输出
    
    使用pytest的capsys fixture捕获输出
    """
    result = main()
    
    # 捕获标准输出
    captured = capsys.readouterr()
    
    # 验证输出内容
    assert captured.out == "Hello, World!\n"
    # 验证返回值
    assert result == 0
    
    print("测试通过: 输出内容正确")
    return True


if __name__ == "__main__":
    """
    直接运行时的入口点
    
    当直接运行此脚本时，执行主函数并退出。
    """
    # 执行主函数
    exit_code = main()
    
    # 打印执行结果
    print(f"脚本执行完成，退出码: {exit_code}")
    
    # 退出程序
    sys.exit(exit_code)
