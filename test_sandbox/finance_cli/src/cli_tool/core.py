"""
核心业务逻辑模块

将工具的主要功能实现放在这里，与CLI代码分离，保持代码结构清晰。
"""

import os
import sys
import json
import logging
from typing import Dict, List, Optional, Any, Union
from pathlib import Path


class CoreTool:
    """核心工具类，封装所有业务逻辑"""
    
    def __init__(self, config_path: Optional[str] = None):
        """初始化核心工具
        
        Args:
            config_path: 配置文件路径，如果为None则使用默认配置
        """
        self.logger = self._setup_logger()
        self.config = self._load_config(config_path)
        
    def _setup_logger(self) -> logging.Logger:
        """设置日志记录器
        
        Returns:
            配置好的日志记录器
        """
        logger = logging.getLogger(__name__)
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
        return logger
    
    def _load_config(self, config_path: Optional[str]) -> Dict[str, Any]:
        """加载配置文件
        
        Args:
            config_path: 配置文件路径
            
        Returns:
            配置字典
        """
        default_config = {
            "debug": False,
            "output_dir": "output",
            "max_retries": 3,
            "timeout": 30
        }
        
        if config_path and os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    user_config = json.load(f)
                default_config.update(user_config)
                self.logger.info(f"已加载配置文件: {config_path}")
            except Exception as e:
                self.logger.warning(f"加载配置文件失败: {e}，使用默认配置")
        
        return default_config
    
    def process_data(self, input_data: Union[str, List, Dict], **kwargs) -> Dict[str, Any]:
        """处理数据的主要业务逻辑
        
        Args:
            input_data: 输入数据，可以是字符串、列表或字典
            **kwargs: 其他参数
            
        Returns:
            处理结果字典
        """
        self.logger.info("开始处理数据")
        
        try:
            # 数据预处理
            processed_data = self._preprocess_data(input_data)
            
            # 执行核心业务逻辑
            result = self._execute_core_logic(processed_data, **kwargs)
            
            # 后处理
            final_result = self._postprocess_result(result)
            
            self.logger.info("数据处理完成")
            return {
                "success": True,
                "data": final_result,
                "message": "处理成功"
            }
            
        except Exception as e:
            self.logger.error(f"数据处理失败: {e}")
            return {
                "success": False,
                "data": None,
                "message": f"处理失败: {str(e)}"
            }
    
    def _preprocess_data(self, data: Any) -> Any:
        """数据预处理
        
        Args:
            data: 原始数据
            
        Returns:
            预处理后的数据
        """
        # 根据数据类型进行不同的预处理
        if isinstance(data, str):
            # 字符串数据：去除首尾空格
            return data.strip()
        elif isinstance(data, list):
            # 列表数据：过滤空值
            return [item for item in data if item is not None]
        elif isinstance(data, dict):
            # 字典数据：确保所有键都是字符串
            return {str(k): v for k, v in data.items()}
        else:
            return data
    
    def _execute_core_logic(self, data: Any, **kwargs) -> Any:
        """执行核心业务逻辑
        
        Args:
            data: 预处理后的数据
            **kwargs: 其他参数
            
        Returns:
            处理结果
        """
        # 这里实现具体的业务逻辑
        # 示例：如果是字符串，返回其长度和内容
        if isinstance(data, str):
            return {
                "length": len(data),
                "content": data,
                "processed": True
            }
        # 示例：如果是列表，返回统计信息
        elif isinstance(data, list):
            return {
                "count": len(data),
                "items": data,
                "has_items": len(data) > 0
            }
        # 示例：如果是字典，返回键信息
        elif isinstance(data, dict):
            return {
                "keys": list(data.keys()),
                "values": list(data.values()),
                "size": len(data)
            }
        else:
            return {"original_data": data}
    
    def _postprocess_result(self, result: Any) -> Any:
        """结果后处理
        
        Args:
            result: 原始处理结果
            
        Returns:
            后处理后的结果
        """
        # 根据配置决定是否添加额外信息
        if self.config.get("debug", False):
            if isinstance(result, dict):
                result["_debug"] = {
                    "config": self.config,
                    "timestamp": "2024-01-01T00:00:00Z"  # 这里应该使用实际时间戳
                }
        return result
    
    def save_result(self, result: Dict[str, Any], output_path: Optional[str] = None) -> bool:
        """保存处理结果到文件
        
        Args:
            result: 处理结果
            output_path: 输出文件路径，如果为None则使用配置中的路径
            
        Returns:
            是否保存成功
        """
        try:
            if output_path is None:
                output_dir = self.config.get("output_dir", "output")
                os.makedirs(output_dir, exist_ok=True)
                output_path = os.path.join(output_dir, "result.json")
            
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            
            self.logger.info(f"结果已保存到: {output_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"保存结果失败: {e}")
            return False
    
    def validate_input(self, input_data: Any) -> bool:
        """验证输入数据
        
        Args:
            input_data: 输入数据
            
        Returns:
            数据是否有效
        """
        if input_data is None:
            self.logger.warning("输入数据不能为None")
            return False
            
        # 检查数据类型是否支持
        supported_types = (str, list, dict, int, float, bool)
        if not isinstance(input_data, supported_types):
            self.logger.warning(f"不支持的数据类型: {type(input_data)}")
            return False
            
        return True
    
    def get_status(self) -> Dict[str, Any]:
        """获取工具状态信息
        
        Returns:
            状态信息字典
        """
        return {
            "config": self.config,
            "logger_level": self.logger.level,
            "python_version": sys.version,
            "working_directory": os.getcwd()
        }


# 工具函数

def format_output(data: Any, format_type: str = "json") -> str:
    """格式化输出数据
    
    Args:
        data: 要格式化的数据
        format_type: 格式类型，支持 'json', 'yaml', 'text'
        
    Returns:
        格式化后的字符串
    """
    if format_type == "json":
        return json.dumps(data, ensure_ascii=False, indent=2)
    elif format_type == "text":
        if isinstance(data, dict):
            lines = []
            for key, value in data.items():
                lines.append(f"{key}: {value}")
            return "\n".join(lines)
        else:
            return str(data)
    else:
        # 默认返回JSON格式
        return json.dumps(data, ensure_ascii=False, indent=2)


def read_input_file(file_path: str) -> Any:
    """读取输入文件
    
    Args:
        file_path: 文件路径
        
    Returns:
        文件内容
        
    Raises:
        FileNotFoundError: 文件不存在
        ValueError: 文件格式不支持
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"文件不存在: {file_path}")
    
    # 根据文件扩展名决定读取方式
    ext = os.path.splitext(file_path)[1].lower()
    
    if ext == '.json':
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    elif ext in ['.txt', '.md', '.py', '.js', '.html', '.css']:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    else:
        raise ValueError(f"不支持的文件格式: {ext}")
