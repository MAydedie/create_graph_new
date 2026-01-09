"""
调用图生成和分析 - 用于追踪方法调用关系和执行流
"""

from typing import Dict, List, Set, Optional, Tuple
from collections import defaultdict, deque
from .code_model import (
    MethodInfo, ClassInfo, CallRelation, ProjectAnalysisReport,
    ExecutionEntry, ExecutionPath, ExecutionStep
)
from .symbol_table import SymbolTable


class CallGraph:
    """方法调用图"""
    
    def __init__(self, report: ProjectAnalysisReport):
        self.report = report
        # 邻接表: {caller_sig -> [callee_sig]}
        self.call_edges: Dict[str, Set[str]] = defaultdict(set)
        # 反向边: {callee_sig -> [caller_sig]}
        self.reverse_edges: Dict[str, Set[str]] = defaultdict(set)
        # 调用位置: {(caller_sig, callee_sig) -> line_number}
        self.call_locations: Dict[Tuple[str, str], int] = {}
        
        # 构建图
        self._build_graph()
    
    def _build_graph(self) -> None:
        """从 report 中构建调用图"""
        for call_relation in self.report.call_graph:
            self.call_edges[call_relation.caller_signature].add(call_relation.callee_signature)
            self.reverse_edges[call_relation.callee_signature].add(call_relation.caller_signature)
            self.call_locations[(call_relation.caller_signature, call_relation.callee_signature)] = call_relation.line_number
    
    def get_called_methods(self, method_sig: str) -> Set[str]:
        """获取方法调用的所有方法"""
        return self.call_edges.get(method_sig, set())
    
    def get_calling_methods(self, method_sig: str) -> Set[str]:
        """获取调用方法的所有方法"""
        return self.reverse_edges.get(method_sig, set())
    
    def find_call_chain(self, from_method: str, to_method: str, max_depth: int = 10) -> Optional[List[str]]:
        """寻找从 from_method 到 to_method 的调用链"""
        if from_method == to_method:
            return [from_method]
        
        # BFS 寻找最短路径
        queue = deque([(from_method, [from_method])])
        visited = {from_method}
        depth = 0
        
        while queue and depth < max_depth:
            current, path = queue.popleft()
            
            for next_method in self.get_called_methods(current):
                if next_method == to_method:
                    return path + [next_method]
                
                if next_method not in visited:
                    visited.add(next_method)
                    queue.append((next_method, path + [next_method]))
            
            depth += 1
        
        return None
    
    def find_all_call_chains(self, from_method: str, max_depth: int = 5) -> Dict[str, List[str]]:
        """找到从 from_method 开始的所有调用链"""
        chains = {}
        
        def dfs(current: str, path: List[str], depth: int) -> None:
            if depth > max_depth:
                return
            
            for next_method in self.get_called_methods(current):
                new_path = path + [next_method]
                
                # 避免循环调用
                if next_method not in path:
                    chains[next_method] = new_path
                    dfs(next_method, new_path, depth + 1)
        
        dfs(from_method, [from_method], 0)
        return chains
    
    def trace_execution_path(self, entry_method: str, max_depth: int = 8) -> ExecutionPath:
        """追踪执行路径"""
        from .code_model import SourceLocation, Parameter
        
        # 创建基础方法信息
        entry_method_info = MethodInfo(
            name=entry_method.split('.')[-1],
            class_name=entry_method.split('.')[0] if '.' in entry_method else '<module>',
            signature=entry_method,
            return_type="None"
        )
        
        execution_path = ExecutionPath(entry_method=entry_method_info)
        visited = set()
        
        def traverse(method_sig: str, depth: int = 0) -> None:
            if depth > max_depth or method_sig in visited:
                return
            
            visited.add(method_sig)
            
            # 获取方法信息
            method_info = self._get_method_info(method_sig)
            
            if method_info:
                step = ExecutionStep(
                    method=method_info,
                    depth=depth,
                    description=self._infer_method_purpose(method_info),
                    input_data=[],
                    output_data=[]
                )
                execution_path.add_step(step)
                
                # 递归追踪调用的方法
                for called_method in self.get_called_methods(method_sig):
                    traverse(called_method, depth + 1)
        
        traverse(entry_method)
        return execution_path
    
    def _get_method_info(self, method_sig: str) -> Optional[MethodInfo]:
        """从报告中获取方法信息"""
        # 尝试从类中查找
        for class_info in self.report.classes.values():
            for method in class_info.methods.values():
                if method.signature == method_sig:
                    return method
        
        # 从全局函数中查找
        for method in self.report.functions:
            if method.signature == method_sig:
                return method
        
        return None
    
    def _infer_method_purpose(self, method: MethodInfo) -> str:
        """推断方法的目的"""
        # 如果有文档字符串，使用它
        if method.docstring:
            # 取第一行
            first_line = method.docstring.split('\n')[0].strip()
            return first_line[:100]  # 限制长度
        
        # 根据方法名推断
        name = method.name.lower()
        if 'init' in name or 'construct' in name:
            return "初始化"
        elif 'get' in name or 'fetch' in name or 'retrieve' in name:
            return "获取数据"
        elif 'set' in name or 'update' in name or 'modify' in name:
            return "更新数据"
        elif 'process' in name or 'handle' in name or 'execute' in name:
            return "处理逻辑"
        elif 'validate' in name or 'check' in name:
            return "数据验证"
        elif 'format' in name or 'convert' in name:
            return "数据转换"
        elif 'run' in name or 'start' in name:
            return "主执行方法"
        else:
            return "执行特定操作"
    
    def find_cycles(self) -> List[List[str]]:
        """查找调用图中的循环"""
        cycles = []
        visited = set()
        rec_stack = set()
        
        def dfs(node: str, path: List[str]) -> None:
            visited.add(node)
            rec_stack.add(node)
            path.append(node)
            
            for neighbor in self.get_called_methods(node):
                if neighbor not in visited:
                    dfs(neighbor, path[:])
                elif neighbor in rec_stack:
                    # 找到了一个循环
                    cycle_start = path.index(neighbor)
                    cycle = path[cycle_start:] + [neighbor]
                    if cycle not in cycles:
                        cycles.append(cycle)
            
            rec_stack.remove(node)
        
        for node in self.call_edges.keys():
            if node not in visited:
                dfs(node, [])
        
        return cycles
    
    def get_call_depth(self, method_sig: str) -> Dict[int, List[str]]:
        """获取方法的调用深度层级"""
        depth_dict = {}
        visited = set()
        queue = deque([(method_sig, 0)])
        
        while queue:
            current, depth = queue.popleft()
            
            if current not in visited:
                visited.add(current)
                if depth not in depth_dict:
                    depth_dict[depth] = []
                depth_dict[depth].append(current)
                
                for next_method in self.get_called_methods(current):
                    if next_method not in visited:
                        queue.append((next_method, depth + 1))
        
        return depth_dict
    
    def get_most_called_methods(self, top_n: int = 10) -> List[Tuple[str, int]]:
        """获取被调用最频繁的方法"""
        call_counts = {}
        
        for callers in self.reverse_edges.values():
            for method_sig in self.reverse_edges:
                call_counts[method_sig] = len(self.reverse_edges[method_sig])
        
        sorted_methods = sorted(call_counts.items(), key=lambda x: x[1], reverse=True)
        return sorted_methods[:top_n]
    
    def get_statistics(self) -> Dict:
        """获取调用图的统计信息"""
        return {
            'total_methods': len(self.call_edges) + len(self.reverse_edges),
            'total_call_relations': len(self.report.call_graph),
            'cyclic_calls': len(self.find_cycles()),
            'most_called_methods': self.get_most_called_methods(5),
            'entry_points': self._find_entry_points()
        }
    
    def _find_entry_points(self) -> List[str]:
        """找到调用图的入口点（没有调用者的方法）"""
        all_methods = set(self.call_edges.keys()) | set(self.reverse_edges.keys())
        called_methods = set()
        
        for callers in self.reverse_edges.values():
            called_methods.update(callers)
        
        return list(all_methods - called_methods)


class ExecutionFlowAnalyzer:
    """执行流分析"""
    
    def __init__(self, call_graph: CallGraph, report: ProjectAnalysisReport):
        self.call_graph = call_graph
        self.report = report
    
    def analyze_execution_flow(self) -> List[ExecutionPath]:
        """分析项目的执行流"""
        execution_paths = []
        
        # 找到所有入口点
        for entry in self.report.entry_points:
            path = self.call_graph.trace_execution_path(entry.method.signature)
            execution_paths.append(path)
        
        return execution_paths
    
    def find_critical_path(self, execution_paths: List[ExecutionPath]) -> Optional[ExecutionPath]:
        """找到最关键的执行路径（最深的）"""
        if not execution_paths:
            return None
        
        return max(execution_paths, key=lambda p: p.total_depth)
    
    def estimate_execution_time(self, path: ExecutionPath) -> str:
        """估计执行时间（简单估计）"""
        # 这是一个简单的启发式估计
        depth = path.total_depth
        
        if depth < 3:
            return "快速"
        elif depth < 6:
            return "中等"
        elif depth < 10:
            return "较长"
        else:
            return "很长"
