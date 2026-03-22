from typing import Dict, Any, Type, List
from llm.agent.tools.read_tool import ReadTool
from llm.agent.tools.edit_tool import EditTool
from llm.agent.tools.write_tool import WriteTool
from llm.agent.tools.bash_tool import BashTool
from llm.agent.tools.grep_tool import GrepTool
from llm.agent.tools.ls_tool import LsTool
from llm.agent.tools.glob_tool import GlobTool
from llm.agent.tools.task_tool import TaskTool

class ToolRegistry:
    """
    Central registry for all available tools.
    
    支持两种使用方式：
    1. 类方法（向后兼容）
    2. 实例方法（支持 filter 等高级功能）
    """
    
    _TOOLS = {
        "Read": ReadTool,
        "Edit": EditTool,
        "Write": WriteTool,
        "Bash": BashTool,
        "Grep": GrepTool,
        "Ls": LsTool,  # Phase 6.1 新增
        "Glob": GlobTool,  # Phase 6.1 新增
        "Task": TaskTool  # Phase 3.1 新增
    }
    
    def __init__(self, tools: Dict[str, Type] = None):
        """
        初始化工具注册表
        
        Args:
            tools: 工具字典，如果为 None 则使用全部工具
        """
        if tools is None:
            self._instance_tools = self._TOOLS.copy()
        else:
            self._instance_tools = tools
    
    # ==================== 类方法（向后兼容）====================
    
    @classmethod
    def get_tool(cls, name: str) -> Type:
        """Get tool class by name"""
        return cls._TOOLS.get(name)
    
    @classmethod
    def get_all_tools(cls) -> Dict[str, Type]:
        """Get all registered tools"""
        return cls._TOOLS
    
    @classmethod
    def get_tool_schemas(cls) -> list[Dict[str, Any]]:
        """Get JSON schemas for all tools"""
        return [tool.get_schema() for tool in cls._TOOLS.values()]
    
    @classmethod
    def execute_tool(cls, name: str, **kwargs) -> Dict[str, Any]:
        """Execute a tool by name"""
        tool = cls.get_tool(name)
        if not tool:
            return {"error": f"Tool '{name}' not found."}
        return tool.execute(**kwargs)
    
    # ==================== 实例方法（新增）====================
    
    def get(self, name: str) -> Type:
        """获取工具类（实例方法）"""
        return self._instance_tools.get(name)
    
    def register(self, tool: Type):
        """
        注册工具
        
        Args:
            tool: 工具类
        """
        if hasattr(tool, 'name'):
            self._instance_tools[tool.name] = tool
        else:
            raise ValueError(f"工具类必须有 'name' 属性")
    
    def get_all_tools(self) -> List[Type]:
        """获取所有工具（实例方法）"""
        return list(self._instance_tools.values())
    
    def filter(self, allowed_tools: List[str]) -> 'ToolRegistry':
        """
        创建只包含指定工具的子注册表
        
        Args:
            allowed_tools: 允许的工具名称列表
            
        Returns:
            新的 ToolRegistry 实例
        """
        filtered_tools = {
            name: tool
            for name, tool in self._instance_tools.items()
            if name in allowed_tools
        }
        return ToolRegistry(tools=filtered_tools)
    
    def has_tool(self, name: str) -> bool:
        """检查是否有指定工具"""
        return name in self._instance_tools
    
    def list_tool_names(self) -> List[str]:
        """列出所有工具名称"""
        return list(self._instance_tools.keys())
