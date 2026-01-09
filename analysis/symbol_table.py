"""
符号表实现 - 用于追踪代码中的定义和引用
"""

from typing import Dict, List, Set, Optional, Tuple
from .code_model import MethodInfo, ClassInfo, FieldInfo, SourceLocation


class SymbolTable:
    """符号表，用于管理代码中的所有符号（类、方法、变量等）"""
    
    def __init__(self):
        # 类符号表: {full_class_name -> ClassInfo}
        self.classes: Dict[str, ClassInfo] = {}
        
        # 方法符号表: {method_signature -> MethodInfo}
        self.methods: Dict[str, MethodInfo] = {}
        
        # 函数符号表（不属于类）: {function_name -> MethodInfo}
        self.functions: Dict[str, MethodInfo] = {}
        
        # 别名映射: {简短名称 -> 完整名称}
        self.name_aliases: Dict[str, Set[str]] = {}
        
        # 当前作用域栈
        self.scope_stack: List[str] = []
        
        # 作用域内的本地变量: {scope -> {variable_name -> type}}
        self.local_variables: Dict[str, Dict[str, str]] = {}
    
    def register_class(self, class_info: ClassInfo) -> None:
        """注册类"""
        full_name = class_info.full_name
        self.classes[full_name] = class_info
        
        # 注册别名
        self._register_alias(class_info.name, full_name)
    
    def register_method(self, method_info: MethodInfo) -> None:
        """注册方法"""
        self.methods[method_info.signature] = method_info
        
        # 同时在类中注册
        if method_info.class_name in self.classes:
            self.classes[method_info.class_name].add_method(method_info)
    
    def register_function(self, function_info: MethodInfo) -> None:
        """注册函数（不属于类）"""
        self.functions[function_info.name] = function_info
    
    def _register_alias(self, short_name: str, full_name: str) -> None:
        """注册名称别名"""
        if short_name not in self.name_aliases:
            self.name_aliases[short_name] = set()
        self.name_aliases[short_name].add(full_name)
    
    def resolve_class(self, name: str) -> Optional[ClassInfo]:
        """解析类名，返回对应的 ClassInfo"""
        # 首先尝试直接查找
        if name in self.classes:
            return self.classes[name]
        
        # 然后尝试通过别名查找
        if name in self.name_aliases:
            candidates = self.name_aliases[name]
            if len(candidates) == 1:
                return self.classes[candidates.pop()]
            # 如果有多个候选，返回第一个（理想情况不应该出现）
            if candidates:
                return self.classes[list(candidates)[0]]
        
        return None
    
    def resolve_method(self, method_name: str, class_name: Optional[str] = None) -> Optional[MethodInfo]:
        """
        解析方法，返回对应的 MethodInfo
        如果提供了 class_name，则先在该类中查找
        """
        # 如果提供了类名，先在该类的方法中查找
        if class_name:
            class_info = self.resolve_class(class_name)
            if class_info and method_name in class_info.methods:
                return class_info.methods[method_name]
        
        # 然后在全局方法中查找
        for sig, method in self.methods.items():
            if method.name == method_name:
                return method
        
        # 最后在函数中查找
        if method_name in self.functions:
            return self.functions[method_name]
        
        return None
    
    def get_method_by_signature(self, signature: str) -> Optional[MethodInfo]:
        """通过完整签名获取方法"""
        return self.methods.get(signature)
    
    def get_class_by_name(self, name: str) -> Optional[ClassInfo]:
        """通过名称获取类"""
        return self.resolve_class(name)
    
    def push_scope(self, scope_name: str) -> None:
        """进入新的作用域"""
        self.scope_stack.append(scope_name)
        if scope_name not in self.local_variables:
            self.local_variables[scope_name] = {}
    
    def pop_scope(self) -> None:
        """离开当前作用域"""
        if self.scope_stack:
            self.scope_stack.pop()
    
    def get_current_scope(self) -> str:
        """获取当前作用域"""
        return self.scope_stack[-1] if self.scope_stack else "global"
    
    def add_local_variable(self, var_name: str, var_type: str) -> None:
        """添加本地变量到当前作用域"""
        scope = self.get_current_scope()
        if scope not in self.local_variables:
            self.local_variables[scope] = {}
        self.local_variables[scope][var_name] = var_type
    
    def get_local_variable_type(self, var_name: str) -> Optional[str]:
        """获取本地变量的类型"""
        scope = self.get_current_scope()
        if scope in self.local_variables:
            return self.local_variables[scope].get(var_name)
        return None
    
    def find_all_references_to_class(self, class_name: str) -> List[Tuple[str, int]]:
        """找到对某个类的所有引用"""
        references = []
        class_info = self.resolve_class(class_name)
        if not class_info:
            return references
        
        # 检查其他类中的引用
        for other_class in self.classes.values():
            if class_name in other_class.direct_references:
                # 这里应该记录源代码位置，暂时只记录类名和行号
                if other_class.source_location:
                    references.append((other_class.full_name, other_class.source_location.line_start))
        
        return references
    
    def find_all_references_to_method(self, method_signature: str) -> List[Tuple[str, int]]:
        """找到对某个方法的所有引用"""
        references = []
        
        # 在所有方法的调用关系中查找
        for caller_sig, caller_method in self.methods.items():
            if method_signature in caller_method.calls:
                if caller_method.source_location:
                    references.append((caller_sig, caller_method.source_location.line_start))
        
        return references
    
    def build_inheritance_chain(self, class_name: str) -> List[str]:
        """构建继承链"""
        chain = []
        current_class = self.resolve_class(class_name)
        
        while current_class:
            chain.append(current_class.full_name)
            if current_class.parent_class:
                current_class = self.resolve_class(current_class.parent_class)
            else:
                break
        
        return chain
    
    def get_all_methods_of_class(self, class_name: str, include_inherited: bool = True) -> Dict[str, MethodInfo]:
        """获取类的所有方法，可选择包括继承的方法"""
        class_info = self.resolve_class(class_name)
        if not class_info:
            return {}
        
        methods = dict(class_info.methods)
        
        if include_inherited and class_info.parent_class:
            parent_methods = self.get_all_methods_of_class(
                class_info.parent_class, 
                include_inherited=True
            )
            # 子类方法覆盖父类方法
            for method_name, method_info in parent_methods.items():
                if method_name not in methods:
                    methods[method_name] = method_info
        
        return methods
    
    def get_statistics(self) -> Dict:
        """获取符号表统计信息"""
        return {
            "total_classes": len(self.classes),
            "total_methods": len(self.methods),
            "total_functions": len(self.functions),
            "total_aliases": len(self.name_aliases),
        }
    
    def __repr__(self):
        return (
            f"SymbolTable("
            f"classes={len(self.classes)}, "
            f"methods={len(self.methods)}, "
            f"functions={len(self.functions)})"
        )
