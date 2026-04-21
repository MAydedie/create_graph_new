"""
基础解析器 - 所有语言解析器的基类
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Dict, Optional
from analysis.code_model import ProjectAnalysisReport, ClassInfo, MethodInfo
from analysis.symbol_table import SymbolTable


class BaseParser(ABC):
    """基础解析器抽象类"""
    
    def __init__(self, project_path: str):
        self.project_path = Path(project_path)
        self.symbol_table = SymbolTable()
        self.report = None
        
    @abstractmethod
    def get_supported_extensions(self) -> List[str]:
        """返回支持的文件扩展名列表"""
        pass
    
    @abstractmethod
    def parse_file(self, file_path: Path) -> None:
        """解析单个文件"""
        pass
    
    def parse_project(self) -> ProjectAnalysisReport:
        """解析整个项目"""
        from datetime import datetime
        
        # 初始化报告
        self.report = ProjectAnalysisReport(
            project_name=self.project_path.name,
            project_path=str(self.project_path),
            analysis_timestamp=datetime.now().isoformat()
        )
        
        # 获取所有源文件
        source_files = self._get_source_files()
        
        if not source_files:
            print(f"警告：在 {self.project_path} 中没有找到源文件")
            return self.report
        
        print(f"找到 {len(source_files)} 个源文件，开始解析...")
        
        # 逐个解析文件
        for i, file_path in enumerate(source_files, 1):
            try:
                print(f"[{i}/{len(source_files)}] Parsing: {file_path.relative_to(self.project_path)}")
                self.parse_file(file_path, self.report)
            except Exception as e:
                print(f"  ⚠️  解析失败: {e}")
                continue
        
        # 生成报告数据
        self._populate_report()
        
        return self.report
    
    def _get_source_files(self) -> List[Path]:
        """获取项目中的所有源文件"""
        extensions = self.get_supported_extensions()
        files = []
        
        for ext in extensions:
            files.extend(self.project_path.rglob(f"*.{ext}"))
        
        return sorted(files)
    
    def _populate_report(self) -> None:
        """从符号表填充报告数据"""
        # 将符号表中的类添加到报告
        for class_name, class_info in self.symbol_table.classes.items():
            self.report.add_class(class_info)
        
        # 添加函数
        for func_name, func_info in self.symbol_table.functions.items():
            self.report.functions.append(func_info)
        
        # 统计信息
        self.report.total_files = len(self._get_source_files())
        self.report.total_lines_of_code = self._calculate_total_loc()
    
    def _calculate_total_loc(self) -> int:
        """计算项目总行数"""
        total_loc = 0
        
        for file_path in self._get_source_files():
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    total_loc += len(f.readlines())
            except Exception:
                continue
        
        return total_loc
