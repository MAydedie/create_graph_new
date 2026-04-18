#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
finance_cli/cli.py 的单元测试

测试 finance_cli 命令行接口的主要功能
"""

import unittest
import sys
import os
from unittest.mock import patch, MagicMock
from io import StringIO

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from finance_cli.cli import main, parse_arguments, process_command


class TestFinanceCLI(unittest.TestCase):
    """finance_cli 命令行接口测试类"""
    
    def setUp(self):
        """测试前准备"""
        self.original_argv = sys.argv
        self.original_stdout = sys.stdout
        self.original_stderr = sys.stderr
        
    def tearDown(self):
        """测试后清理"""
        sys.argv = self.original_argv
        sys.stdout = self.original_stdout
        sys.stderr = self.original_stderr
    
    def test_parse_arguments_help(self):
        """测试解析帮助参数"""
        # 测试 -h 参数
        sys.argv = ['finance_cli', '-h']
        with self.assertRaises(SystemExit) as cm:
            parse_arguments()
        self.assertEqual(cm.exception.code, 0)
        
        # 测试 --help 参数
        sys.argv = ['finance_cli', '--help']
        with self.assertRaises(SystemExit) as cm:
            parse_arguments()
        self.assertEqual(cm.exception.code, 0)
    
    def test_parse_arguments_version(self):
        """测试解析版本参数"""
        # 测试 -v 参数
        sys.argv = ['finance_cli', '-v']
        with self.assertRaises(SystemExit) as cm:
            parse_arguments()
        self.assertEqual(cm.exception.code, 0)
        
        # 测试 --version 参数
        sys.argv = ['finance_cli', '--version']
        with self.assertRaises(SystemExit) as cm:
            parse_arguments()
        self.assertEqual(cm.exception.code, 0)
    
    def test_parse_arguments_command(self):
        """测试解析命令参数"""
        # 测试带命令的参数解析
        sys.argv = ['finance_cli', 'analyze', '--input', 'data.csv']
        args = parse_arguments()
        self.assertEqual(args.command, 'analyze')
        self.assertEqual(args.input, 'data.csv')
        
        # 测试带输出文件的参数解析
        sys.argv = ['finance_cli', 'report', '--output', 'report.pdf']
        args = parse_arguments()
        self.assertEqual(args.command, 'report')
        self.assertEqual(args.output, 'report.pdf')
    
    @patch('finance_cli.cli.process_command')
    def test_main_success(self, mock_process_command):
        """测试主函数成功执行"""
        # 模拟 process_command 成功执行
        mock_process_command.return_value = 0
        
        # 测试正常命令
        sys.argv = ['finance_cli', 'test']
        result = main()
        self.assertEqual(result, 0)
        mock_process_command.assert_called_once()
    
    @patch('finance_cli.cli.process_command')
    def test_main_error(self, mock_process_command):
        """测试主函数错误处理"""
        # 模拟 process_command 抛出异常
        mock_process_command.side_effect = Exception("Test error")
        
        # 测试异常情况
        sys.argv = ['finance_cli', 'test']
        result = main()
        self.assertEqual(result, 1)
    
    def test_process_command_analyze(self):
        """测试处理 analyze 命令"""
        # 创建模拟参数
        args = MagicMock()
        args.command = 'analyze'
        args.input = 'test_data.csv'
        args.output = None
        args.verbose = False
        
        # 测试 analyze 命令处理
        with patch('finance_cli.cli.analyze_data') as mock_analyze:
            mock_analyze.return_value = {'status': 'success'}
            result = process_command(args)
            self.assertEqual(result, 0)
            mock_analyze.assert_called_once_with('test_data.csv', None, False)
    
    def test_process_command_report(self):
        """测试处理 report 命令"""
        # 创建模拟参数
        args = MagicMock()
        args.command = 'report'
        args.input = 'analysis.json'
        args.output = 'report.pdf'
        args.format = 'pdf'
        
        # 测试 report 命令处理
        with patch('finance_cli.cli.generate_report') as mock_report:
            mock_report.return_value = True
            result = process_command(args)
            self.assertEqual(result, 0)
            mock_report.assert_called_once_with('analysis.json', 'report.pdf', 'pdf')
    
    def test_process_command_unknown(self):
        """测试处理未知命令"""
        # 创建模拟参数
        args = MagicMock()
        args.command = 'unknown_command'
        
        # 测试未知命令处理
        result = process_command(args)
        self.assertEqual(result, 1)
    
    def test_process_command_exception(self):
        """测试命令处理异常"""
        # 创建模拟参数
        args = MagicMock()
        args.command = 'analyze'
        args.input = 'test_data.csv'
        
        # 模拟函数抛出异常
        with patch('finance_cli.cli.analyze_data') as mock_analyze:
            mock_analyze.side_effect = Exception("Analysis failed")
            result = process_command(args)
            self.assertEqual(result, 1)
    
    def test_cli_output_capture(self):
        """测试命令行输出捕获"""
        # 测试标准输出捕获
        sys.argv = ['finance_cli', '--help']
        
        # 捕获输出
        captured_output = StringIO()
        sys.stdout = captured_output
        
        try:
            with self.assertRaises(SystemExit):
                main()
        finally:
            sys.stdout = self.original_stdout
        
        # 验证输出包含帮助信息
        output = captured_output.getvalue()
        self.assertIn('usage:', output.lower())
        self.assertIn('finance_cli', output)
    
    def test_command_validation(self):
        """测试命令参数验证"""
        # 测试缺少必要参数
        sys.argv = ['finance_cli', 'analyze']
        
        # 应该显示错误信息
        captured_output = StringIO()
        sys.stderr = captured_output
        
        try:
            result = main()
            self.assertEqual(result, 1)
        finally:
            sys.stderr = self.original_stderr
        
        error_output = captured_output.getvalue()
        self.assertIn('error', error_output.lower())


class TestCLIIntegration(unittest.TestCase):
    """CLI 集成测试类"""
    
    @patch('finance_cli.cli.analyze_data')
    @patch('finance_cli.cli.generate_report')
    def test_full_workflow(self, mock_report, mock_analyze):
        """测试完整工作流程"""
        # 模拟分析函数返回结果
        mock_analyze.return_value = {
            'summary': {'total': 1000, 'average': 100},
            'data': [1, 2, 3]
        }
        
        # 模拟报告生成成功
        mock_report.return_value = True
        
        # 测试分析命令
        sys.argv = ['finance_cli', 'analyze', '--input', 'data.csv', '--verbose']
        result = main()
        self.assertEqual(result, 0)
        mock_analyze.assert_called_once_with('data.csv', None, True)
        
        # 测试报告命令
        sys.argv = ['finance_cli', 'report', '--input', 'result.json', '--output', 'report.pdf']
        result = main()
        self.assertEqual(result, 0)
        mock_report.assert_called_once_with('result.json', 'report.pdf', 'pdf')
    
    def test_error_handling(self):
        """测试错误处理流程"""
        # 测试文件不存在错误
        sys.argv = ['finance_cli', 'analyze', '--input', 'nonexistent.csv']
        
        with patch('finance_cli.cli.analyze_data') as mock_analyze:
            mock_analyze.side_effect = FileNotFoundError("File not found")
            result = main()
            self.assertEqual(result, 1)
        
        # 测试权限错误
        sys.argv = ['finance_cli', 'report', '--output', '/root/report.pdf']
        
        with patch('finance_cli.cli.generate_report') as mock_report:
            mock_report.side_effect = PermissionError("Permission denied")
            result = main()
            self.assertEqual(result, 1)


if __name__ == '__main__':
    unittest.main()
