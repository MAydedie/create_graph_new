#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
异常测试脚本

该脚本用于测试主脚本的异常处理路径，包含多种异常场景。
"""

import sys
import traceback
from typing import Any, Dict, Optional


def divide_by_zero() -> float:
    """
    除以零异常示例
    
    Returns:
        float: 永远不会返回，会抛出ZeroDivisionError
    
    Raises:
        ZeroDivisionError: 除以零异常
    """
    numerator = 10
    denominator = 0
    return numerator / denominator


def access_none_attribute() -> str:
    """
    访问None对象属性异常示例
    
    Returns:
        str: 永远不会返回，会抛出AttributeError
    
    Raises:
        AttributeError: 属性访问异常
    """
    obj = None
    return obj.non_existent_attribute


def index_out_of_range() -> str:
    """
    索引越界异常示例
    
    Returns:
        str: 永远不会返回，会抛出IndexError
    
    Raises:
        IndexError: 索引越界异常
    """
    my_list = ["a", "b", "c"]
    return my_list[10]


def key_error_example() -> Any:
    """
    字典键不存在异常示例
    
    Returns:
        Any: 永远不会返回，会抛出KeyError
    
    Raises:
        KeyError: 键不存在异常
    """
    my_dict = {"name": "test", "value": 123}
    return my_dict["non_existent_key"]


def type_error_example() -> int:
    """
    类型错误异常示例
    
    Returns:
        int: 永远不会返回，会抛出TypeError
    
    Raises:
        TypeError: 类型错误异常
    """
    return "string" + 123


def custom_exception(message: str = "自定义异常发生") -> None:
    """
    抛出自定义异常示例
    
    Args:
        message: 异常消息
    
    Raises:
        ValueError: 自定义值错误异常
    """
    raise ValueError(f"自定义异常: {message}")


def nested_exception() -> None:
    """
    嵌套异常示例，模拟复杂场景中的异常
    """
    try:
        # 第一层异常
        result = 10 / 0
    except ZeroDivisionError as e:
        try:
            # 第二层异常
            data = {"key": "value"}
            print(data["nonexistent"])
        except KeyError as ke:
            # 抛出新的异常，包含原始异常信息
            raise RuntimeError("嵌套异常发生") from e


def generate_exception(exception_type: str = "zero_division") -> None:
    """
    根据指定类型生成异常
    
    Args:
        exception_type: 异常类型，可选值:
            - "zero_division": 除以零异常
            - "attribute": 属性访问异常
            - "index": 索引越界异常
            - "key": 键不存在异常
            - "type": 类型错误异常
            - "custom": 自定义异常
            - "nested": 嵌套异常
    
    Raises:
        各种类型的异常
    """
    exception_handlers = {
        "zero_division": divide_by_zero,
        "attribute": access_none_attribute,
        "index": index_out_of_range,
        "key": key_error_example,
        "type": type_error_example,
        "custom": lambda: custom_exception("测试自定义异常"),
        "nested": nested_exception
    }
    
    if exception_type not in exception_handlers:
        raise ValueError(f"不支持的异常类型: {exception_type}")
    
    exception_handlers[exception_type]()


def main() -> Dict[str, Any]:
    """
    主函数，执行异常测试
    
    Returns:
        Dict[str, Any]: 包含测试结果的字典
    """
    results = {
        "total_tests": 0,
        "passed_tests": 0,
        "failed_tests": 0,
        "exceptions": []
    }
    
    # 测试所有异常类型
    exception_types = [
        "zero_division",
        "attribute",
        "index",
        "key",
        "type",
        "custom",
        "nested"
    ]
    
    for exc_type in exception_types:
        results["total_tests"] += 1
        try:
            generate_exception(exc_type)
            # 如果执行到这里，说明没有抛出异常
            print(f"测试失败: {exc_type} 没有抛出异常")
            results["failed_tests"] += 1
        except Exception as e:
            # 成功捕获异常
            exception_info = {
                "type": exc_type,
                "exception_class": e.__class__.__name__,
                "message": str(e),
                "traceback": traceback.format_exc()
            }
            results["exceptions"].append(exception_info)
            results["passed_tests"] += 1
            print(f"测试通过: {exc_type} 成功抛出 {e.__class__.__name__}")
    
    return results


if __name__ == "__main__":
    """
    直接运行时的入口点
    """
    print("开始异常处理测试...")
    print("=" * 50)
    
    try:
        test_results = main()
        
        print("=" * 50)
        print(f"测试完成!")
        print(f"总测试数: {test_results['total_tests']}")
        print(f"通过测试: {test_results['passed_tests']}")
        print(f"失败测试: {test_results['failed_tests']}")
        
        # 输出异常摘要
        if test_results["exceptions"]:
            print("\n捕获的异常摘要:")
            for i, exc in enumerate(test_results["exceptions"], 1):
                print(f"  {i}. {exc['type']}: {exc['exception_class']} - {exc['message']}")
        
        # 如果有失败测试，返回非零退出码
        if test_results["failed_tests"] > 0:
            sys.exit(1)
        else:
            sys.exit(0)
            
    except KeyboardInterrupt:
        print("\n测试被用户中断")
        sys.exit(130)
    except Exception as e:
        print(f"测试框架发生未预期错误: {e}")
        traceback.print_exc()
        sys.exit(2)