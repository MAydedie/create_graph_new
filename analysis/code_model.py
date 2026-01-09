"""
代码分析数据模型 - 定义所有核心数据结构
"""

from dataclasses import dataclass, field
from typing import List, Dict, Set, Optional, Any
from enum import Enum


class ElementType(Enum):
    """代码元素类型"""
    REPOSITORY = "repository"  # 仓库/项目
    PACKAGE = "package"        # 包
    MODULE = "module"          # 模块（Python特有）
    FILE = "file"              # 文件
    CLASS = "class"            # 类
    METHOD = "method"          # 方法
    FUNCTION = "function"      # 函数
    PARAMETER = "parameter"    # 参数（作为独立实体）
    RETURN_VALUE = "return_value"  # 返回值（作为独立实体）
    FIELD = "field"            # 字段/属性（作为独立实体）
    VARIABLE = "variable"      # 变量
    IMPORT = "import"          # 导入
    INTERFACE = "interface"    # 接口
    CFG = "cfg"                # 控制流图（作为独立实体）
    DFG = "dfg"                # 数据流图（作为独立实体）


class RelationType(Enum):
    """关系类型"""
    # 包含关系（明确化）
    REPOSITORY_CONTAINS_PACKAGE = "repository_contains_package"  # 仓库包含包
    PACKAGE_CONTAINS_FILE = "package_contains_file"              # 包包含文件
    PACKAGE_CONTAINS_CLASS = "package_contains_class"            # 包包含类
    FILE_CONTAINS_CLASS = "file_contains_class"                   # 文件包含类
    CLASS_CONTAINS_METHOD = "class_contains_method"               # 类包含方法
    CLASS_CONTAINS_FIELD = "class_contains_field"                 # 类包含字段
    FUNCTION_CONTAINS_PARAMETER = "function_contains_parameter"  # 函数包含参数
    METHOD_CONTAINS_PARAMETER = "method_contains_parameter"      # 方法包含参数
    METHOD_HAS_CFG = "method_has_cfg"                          # 方法拥有CFG
    FUNCTION_HAS_CFG = "function_has_cfg"                       # 函数拥有CFG
    METHOD_HAS_DFG = "method_has_dfg"                           # 方法拥有DFG
    FUNCTION_HAS_DFG = "function_has_dfg"                       # 函数拥有DFG
    METHOD_HAS_RETURN = "method_has_return"                      # 方法拥有返回值
    FUNCTION_HAS_RETURN = "function_has_return"                   # 函数拥有返回值
    
    # 调用关系
    CALLS = "calls"                    # 调用关系（通用）
    METHOD_CALLS_METHOD = "method_calls_method"    # 方法调用方法
    METHOD_CALLS_FUNCTION = "method_calls_function"  # 方法调用函数
    FUNCTION_CALLS_FUNCTION = "function_calls_function"  # 函数调用函数
    FUNCTION_CALLS_METHOD = "function_calls_method"  # 函数调用方法
    
    # 继承关系
    INHERITS = "inherits"              # 继承关系
    CLASS_INHERITS_CLASS = "class_inherits_class"  # 类继承类
    IMPLEMENTS = "implements"          # 实现接口
    CLASS_IMPLEMENTS_INTERFACE = "class_implements_interface"  # 类实现接口
    
    # 访问关系
    METHOD_ACCESSES_FIELD = "method_accesses_field"  # 方法访问字段
    METHOD_USES_VARIABLE = "method_uses_variable"     # 方法使用变量
    
    # 依赖关系
    DEPENDS_ON = "depends_on"          # 依赖关系（通用）
    CLASS_DEPENDS_ON_CLASS = "class_depends_on_class"  # 类依赖类
    PACKAGE_DEPENDS_ON_PACKAGE = "package_depends_on_package"  # 包依赖包
    FILE_DEPENDS_ON_FILE = "file_depends_on_file"  # 文件依赖文件
    
    # 引用关系
    REFERENCES = "references"          # 引用关系（通用）
    METHOD_REFERENCES_CLASS = "method_references_class"  # 方法引用类
    METHOD_REFERENCES_VARIABLE = "method_references_variable"  # 方法引用变量
    
    # 数据流关系
    PARAMETER_FLOW = "parameter_flow"  # 参数流动
    DATA_FLOW = "data_flow"            # 数据流


@dataclass
class RepositoryInfo:
    """仓库/项目信息"""
    name: str
    path: str
    language: str = "python"  # 主要编程语言
    description: Optional[str] = None
    total_packages: int = 0
    total_files: int = 0
    total_classes: int = 0
    total_functions: int = 0
    
    def __repr__(self):
        return f"Repository(name={self.name}, path={self.path})"


@dataclass
class SourceLocation:
    """源代码位置"""
    file_path: str
    line_start: int
    line_end: int
    column_start: int = 0
    column_end: int = 0
    
    def __str__(self):
        return f"{self.file_path}:{self.line_start}:{self.column_start}"


@dataclass
class PackageInfo:
    """包/模块信息"""
    name: str
    path: str  # 包路径
    parent_repository: Optional[str] = None  # 所属仓库名称
    description: Optional[str] = None
    total_files: int = 0
    total_classes: int = 0
    total_functions: int = 0
    source_location: Optional[SourceLocation] = None
    
    def __repr__(self):
        return f"Package(name={self.name}, path={self.path})"


@dataclass
class Parameter:
    """方法参数（作为独立实体）"""
    name: str
    param_type: str
    default_value: Optional[str] = None
    entity_id: Optional[str] = None  # 作为KG实体的唯一ID
    owner_method: Optional[str] = None  # 所属方法/函数的ID
    position: int = 0  # 参数位置（第几个参数）
    
    def __repr__(self):
        if self.default_value:
            return f"{self.name}: {self.param_type} = {self.default_value}"
        return f"{self.name}: {self.param_type}"


@dataclass
class ReturnValue:
    """返回值（作为独立实体）"""
    entity_id: str  # 唯一ID，如 "return_method_ClassName_methodName"
    return_type: str
    owner_method: Optional[str] = None  # 所属方法/函数的ID
    description: Optional[str] = None
    source_location: Optional[SourceLocation] = None
    
    def __repr__(self):
        return f"ReturnValue(type={self.return_type}, owner={self.owner_method})"


@dataclass
class CFGEntity:
    """控制流图实体（作为独立实体）"""
    entity_id: str  # 唯一ID，如 "cfg_method_ClassName_methodName"
    method_id: str  # 所属方法/函数的ID
    method_name: str
    dot_format: Optional[str] = None  # DOT格式的CFG
    json_format: Optional[Dict] = None  # JSON格式的CFG
    node_count: int = 0
    edge_count: int = 0
    
    def __repr__(self):
        return f"CFGEntity(method={self.method_name}, nodes={self.node_count}, edges={self.edge_count})"


@dataclass
class DFGEntity:
    """数据流图实体（作为独立实体）"""
    entity_id: str  # 唯一ID，如 "dfg_method_ClassName_methodName"
    method_id: str  # 所属方法/函数的ID
    method_name: str
    dot_format: Optional[str] = None  # DOT格式的DFG
    json_format: Optional[Dict] = None  # JSON格式的DFG
    node_count: int = 0
    edge_count: int = 0
    
    def __repr__(self):
        return f"DFGEntity(method={self.method_name}, nodes={self.node_count}, edges={self.edge_count})"


@dataclass
class MethodInfo:
    """方法信息"""
    name: str
    class_name: str  # 所属类
    signature: str  # 完整签名
    return_type: str
    parameters: List[Parameter] = field(default_factory=list)
    modifiers: List[str] = field(default_factory=list)  # public, static, etc.
    docstring: Optional[str] = None
    source_code: Optional[str] = None  # 完整的方法源代码 - Phase 2分析器关键
    source_location: Optional[SourceLocation] = None
    
    # 关系信息
    calls: Set[str] = field(default_factory=set)  # 调用的方法签名
    called_by: Set[str] = field(default_factory=set)  # 被调用的方法签名
    references: Set[str] = field(default_factory=set)  # 引用的其他符号
    
    # 代码复杂度指标
    cyclomatic_complexity: int = 1
    lines_of_code: int = 0
    
    def get_full_name(self) -> str:
        """获取完整方法名 (ClassName.methodName)"""
        return f"{self.class_name}.{self.name}"
    
    def __repr__(self):
        params_str = ", ".join(str(p) for p in self.parameters)
        return f"{self.return_type} {self.class_name}.{self.name}({params_str})"


@dataclass
class FieldInfo:
    """字段/属性信息"""
    name: str
    field_type: str
    modifiers: List[str] = field(default_factory=list)
    default_value: Optional[str] = None
    docstring: Optional[str] = None
    source_location: Optional[SourceLocation] = None


@dataclass
class ClassInfo:
    """类信息"""
    name: str
    full_name: str  # 包含包名的完整名称
    parent_class: Optional[str] = None  # 超类名称
    interfaces: List[str] = field(default_factory=list)  # 实现的接口
    methods: Dict[str, MethodInfo] = field(default_factory=dict)  # {method_name: MethodInfo}
    fields: Dict[str, FieldInfo] = field(default_factory=dict)  # {field_name: FieldInfo}
    modifiers: List[str] = field(default_factory=list)  # public, abstract, final, etc.
    docstring: Optional[str] = None
    source_location: Optional[SourceLocation] = None
    
    # 关系
    dependencies: Set[str] = field(default_factory=set)  # 依赖的其他类
    direct_references: Set[str] = field(default_factory=set)  # 直接引用的类
    
    def add_method(self, method: MethodInfo) -> None:
        """添加方法"""
        self.methods[method.name] = method
    
    def add_field(self, field: FieldInfo) -> None:
        """添加字段"""
        self.fields[field.name] = field
    
    def get_all_method_signatures(self) -> Set[str]:
        """获取所有方法签名"""
        return set(m.signature for m in self.methods.values())
    
    def __repr__(self):
        parent_str = f" extends {self.parent_class}" if self.parent_class else ""
        interfaces_str = f" implements {', '.join(self.interfaces)}" if self.interfaces else ""
        return f"class {self.name}{parent_str}{interfaces_str}"


@dataclass
class CallRelation:
    """调用关系"""
    caller_signature: str
    callee_signature: str
    line_number: int
    call_type: str = "method_call"  # method_call, function_call, constructor_call


@dataclass
class DependencyRelation:
    """类之间的依赖关系"""
    source_class: str
    target_class: str
    relation_type: RelationType
    description: Optional[str] = None


@dataclass
class ExecutionEntry:
    """执行入口点"""
    method: MethodInfo
    entry_type: str  # "main", "constructor", "init", "entry_point"
    description: str
    parameters_required: List[str] = field(default_factory=list)


@dataclass
class ExecutionStep:
    """执行步骤"""
    method: MethodInfo
    depth: int
    description: str
    input_data: List[str] = field(default_factory=list)
    output_data: List[str] = field(default_factory=list)
    estimated_runtime: Optional[str] = None


@dataclass
class ExecutionPath:
    """执行路径"""
    entry_method: MethodInfo
    steps: List[ExecutionStep] = field(default_factory=list)
    total_depth: int = 0
    
    def add_step(self, step: ExecutionStep) -> None:
        """添加执行步骤"""
        self.steps.append(step)
        self.total_depth = max(self.total_depth, step.depth)


@dataclass
class ConfigRequirement:
    """配置需求"""
    name: str
    required: bool
    description: str
    example: Optional[str] = None


@dataclass
class ConfigRequirements:
    """配置需求集合"""
    environment_variables: List[ConfigRequirement] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    framework_setups: List[ClassInfo] = field(default_factory=list)
    database_configs: List[ConfigRequirement] = field(default_factory=list)


@dataclass
class DataFlowInfo:
    """数据流信息"""
    source_method: str
    target_method: str
    data_type: str
    description: str
    line_number: int


@dataclass
class ProjectAnalysisReport:
    """完整的项目分析报告"""
    project_name: str
    project_path: str
    analysis_timestamp: str
    
    # 代码元素
    repository: Optional[RepositoryInfo] = None  # 仓库信息
    packages: Dict[str, PackageInfo] = field(default_factory=dict)  # 包/模块信息
    classes: Dict[str, ClassInfo] = field(default_factory=dict)
    functions: List[MethodInfo] = field(default_factory=list)  # 不属于类的函数
    
    # 关系
    call_graph: List[CallRelation] = field(default_factory=list)
    dependency_graph: List[DependencyRelation] = field(default_factory=list)
    
    # 执行流
    entry_points: List[ExecutionEntry] = field(default_factory=list)
    execution_paths: Dict[str, ExecutionPath] = field(default_factory=dict)
    critical_path: Optional[ExecutionPath] = None
    
    # 配置
    config_requirements: ConfigRequirements = field(default_factory=ConfigRequirements)
    
    # 数据流
    data_flows: List[DataFlowInfo] = field(default_factory=list)
    
    # 统计信息
    total_files: int = 0
    total_lines_of_code: int = 0
    
    def add_class(self, class_info: ClassInfo) -> None:
        """添加类"""
        self.classes[class_info.full_name] = class_info
    
    def add_call_relation(self, relation: CallRelation) -> None:
        """添加调用关系"""
        self.call_graph.append(relation)
    
    def get_class_count(self) -> int:
        """获取类数量"""
        return len(self.classes)
    
    def get_method_count(self) -> int:
        """获取方法总数"""
        return sum(len(c.methods) for c in self.classes.values()) + len(self.functions)
    
    def get_total_methods_called(self, method_sig: str) -> Set[str]:
        """获取某个方法调用的所有方法"""
        called = set()
        for relation in self.call_graph:
            if relation.caller_signature == method_sig:
                called.add(relation.callee_signature)
        return called
    
    def get_all_callers_of(self, method_sig: str) -> Set[str]:
        """获取调用某个方法的所有方法"""
        callers = set()
        for relation in self.call_graph:
            if relation.callee_signature == method_sig:
                callers.add(relation.caller_signature)
        return callers


@dataclass
class AnalysisStatistics:
    """分析统计信息"""
    total_classes: int = 0
    total_methods: int = 0
    total_functions: int = 0
    total_lines_of_code: int = 0
    max_inheritance_depth: int = 0
    max_call_chain_depth: int = 0
    average_method_complexity: float = 0.0
    files_analyzed: int = 0
