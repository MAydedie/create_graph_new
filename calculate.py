#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
计算脚本
计算12345 * 6789并打印结果
"""


def main():
    """主函数：执行计算并打印结果"""
    # 定义两个乘数
    num1 = 12345
    num2 = 6789
    
    # 执行乘法运算
    result = num1 * num2
    
    # 打印计算结果
    print(f"{num1} * {num2} = {result}")
    
    return result


if __name__ == "__main__":
    main()
