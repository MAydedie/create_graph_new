"""
my_cli_tool 核心业务逻辑模块

包含工具的主要功能函数和业务逻辑实现
"""

import os
import sys
import json
import logging
from typing import Dict, List, Optional, Any, Union
from pathlib import Path

# 配置日志
logger = logging.getLogger(__name__)


def initialize_project(project_name: str, template: str = "default") -> bool:
    """
    初始化新项目
    
    Args:
        project_name: 项目名称
        template: 项目模板类型
        
    Returns:
        bool: 初始化是否成功
    """
    try:
        logger.info(f"正在初始化项目: {project_name}，使用模板: {template}")
        
        # 创建项目目录
        project_path = Path(project_name)
        if project_path.exists():
            logger.error(f"项目目录已存在: {project_name}")
            return False
        
        project_path.mkdir(parents=True)
        
        # 根据模板创建项目结构
        if template == "default":
            _create_default_project_structure(project_path)
        elif template == "minimal":
            _create_minimal_project_structure(project_path)
        else:
            logger.warning(f"未知模板: {template}，使用默认模板")
            _create_default_project_structure(project_path)
        
        logger.info(f"项目初始化成功: {project_name}")
        return True
        
    except Exception as e:
        logger.error(f"项目初始化失败: {str(e)}")
        return False


def _create_default_project_structure(project_path: Path) -> None:
    """创建默认项目结构"""
    # 创建主要目录
    directories = [
        "src",
        "tests",
        "docs",
        "data",
        "config",
        "logs"
    ]
    
    for directory in directories:
        (project_path / directory).mkdir(exist_ok=True)
    
    # 创建基本文件
    files = {
        "README.md": "# 项目说明\n\n这是一个新项目。",
        "requirements.txt": "# 项目依赖\n",
        "setup.py": """from setuptools import setup, find_packages

setup(
    name='my_project',
    version='0.1.0',
    packages=find_packages(),
    install_requires=[],
)""",
        "src/__init__.py": "",
        ".gitignore": """# Python
__pycache__/
*.py[cod]
*$py.class

# Virtual Environment
venv/
env/

# IDE
.vscode/
.idea/
*.swp
*.swo
"""
    }
    
    for filename, content in files.items():
        file_path = project_path / filename
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")


def _create_minimal_project_structure(project_path: Path) -> None:
    """创建最小化项目结构"""
    # 创建主要目录
    directories = [
        "src",
        "tests"
    ]
    
    for directory in directories:
        (project_path / directory).mkdir(exist_ok=True)
    
    # 创建基本文件
    files = {
        "README.md": "# 项目说明\n\n这是一个最小化项目。",
        "src/__init__.py": "",
        "tests/__init__.py": ""
    }
    
    for filename, content in files.items():
        file_path = project_path / filename
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")


def process_data(input_file: str, output_file: str, config: Optional[Dict] = None) -> bool:
    """
    处理数据文件
    
    Args:
        input_file: 输入文件路径
        output_file: 输出文件路径
        config: 处理配置
        
    Returns:
        bool: 处理是否成功
    """
    try:
        logger.info(f"开始处理数据: {input_file} -> {output_file}")
        
        # 检查输入文件是否存在
        input_path = Path(input_file)
        if not input_path.exists():
            logger.error(f"输入文件不存在: {input_file}")
            return False
        
        # 读取输入文件
        if input_path.suffix == ".json":
            data = _read_json_file(input_path)
        elif input_path.suffix == ".txt":
            data = _read_text_file(input_path)
        else:
            logger.error(f"不支持的文件格式: {input_path.suffix}")
            return False
        
        if data is None:
            logger.error("读取文件失败")
            return False
        
        # 处理数据
        processed_data = _process_data_content(data, config)
        
        # 写入输出文件
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        if output_path.suffix == ".json":
            _write_json_file(output_path, processed_data)
        elif output_path.suffix == ".txt":
            _write_text_file(output_path, processed_data)
        else:
            logger.error(f"不支持的输出格式: {output_path.suffix}")
            return False
        
        logger.info(f"数据处理完成: {output_file}")
        return True
        
    except Exception as e:
        logger.error(f"数据处理失败: {str(e)}")
        return False


def _read_json_file(file_path: Path) -> Optional[Dict]:
    """读取JSON文件"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"读取JSON文件失败: {str(e)}")
        return None


def _read_text_file(file_path: Path) -> Optional[str]:
    """读取文本文件"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        logger.error(f"读取文本文件失败: {str(e)}")
        return None


def _process_data_content(data: Union[Dict, str], config: Optional[Dict]) -> Union[Dict, str]:
    """处理数据内容"""
    if config is None:
        config = {}
    
    # 根据配置处理数据
    if isinstance(data, dict):
        # 处理字典数据
        processed = data.copy()
        
        # 应用过滤规则
        if "filter_keys" in config:
            filter_keys = config["filter_keys"]
            if isinstance(filter_keys, list):
                processed = {k: v for k, v in processed.items() if k in filter_keys}
        
        # 应用转换规则
        if "transform_rules" in config:
            transform_rules = config["transform_rules"]
            if isinstance(transform_rules, dict):
                for key, rule in transform_rules.items():
                    if key in processed:
                        if rule == "uppercase" and isinstance(processed[key], str):
                            processed[key] = processed[key].upper()
                        elif rule == "lowercase" and isinstance(processed[key], str):
                            processed[key] = processed[key].lower()
        
        return processed
    
    elif isinstance(data, str):
        # 处理文本数据
        processed = data
        
        # 应用文本处理规则
        if "text_transform" in config:
            transform = config["text_transform"]
            if transform == "uppercase":
                processed = processed.upper()
            elif transform == "lowercase":
                processed = processed.lower()
            elif transform == "strip":
                processed = processed.strip()
        
        return processed
    
    return data


def _write_json_file(file_path: Path, data: Dict) -> None:
    """写入JSON文件"""
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _write_text_file(file_path: Path, data: str) -> None:
    """写入文本文件"""
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(data)


def validate_config(config_file: str) -> Dict[str, Any]:
    """
    验证配置文件
    
    Args:
        config_file: 配置文件路径
        
    Returns:
        Dict: 验证结果，包含状态和详细信息
    """
    result = {
        "valid": False,
        "errors": [],
        "warnings": [],
        "config": None
    }
    
    try:
        config_path = Path(config_file)
        if not config_path.exists():
            result["errors"].append(f"配置文件不存在: {config_file}")
            return result
        
        # 读取配置文件
        if config_path.suffix == ".json":
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
        else:
            result["errors"].append(f"不支持的配置文件格式: {config_path.suffix}")
            return result
        
        # 验证配置结构
        if not isinstance(config, dict):
            result["errors"].append("配置文件必须是JSON对象")
            return result
        
        # 检查必需字段
        required_fields = ["version", "name"]
        for field in required_fields:
            if field not in config:
                result["errors"].append(f"缺少必需字段: {field}")
        
        # 检查版本格式
        if "version" in config:
            version = config["version"]
            if not isinstance(version, str):
                result["errors"].append("version字段必须是字符串")
            elif not version.count(".") == 2:
                result["warnings"].append("version格式可能不正确，建议使用语义化版本号")
        
        # 检查名称格式
        if "name" in config:
            name = config["name"]
            if not isinstance(name, str):
                result["errors"].append("name字段必须是字符串")
            elif len(name.strip()) == 0:
                result["errors"].append("name不能为空")
        
        # 如果没有错误，标记为有效
        if len(result["errors"]) == 0:
            result["valid"] = True
            result["config"] = config
        
        return result
        
    except json.JSONDecodeError as e:
        result["errors"].append(f"JSON解析错误: {str(e)}")
        return result
    except Exception as e:
        result["errors"].append(f"验证配置文件失败: {str(e)}")
        return result


def generate_report(data: List[Dict], output_format: str = "text") -> Optional[str]:
    """
    生成报告
    
    Args:
        data: 报告数据
        output_format: 输出格式（text, json, markdown）
        
    Returns:
        Optional[str]: 生成的报告内容，失败时返回None
    """
    try:
        if not data:
            logger.warning("没有数据可生成报告")
            return "没有数据"
        
        if output_format == "text":
            return _generate_text_report(data)
        elif output_format == "json":
            return _generate_json_report(data)
        elif output_format == "markdown":
            return _generate_markdown_report(data)
        else:
            logger.error(f"不支持的输出格式: {output_format}")
            return None
            
    except Exception as e:
        logger.error(f"生成报告失败: {str(e)}")
        return None


def _generate_text_report(data: List[Dict]) -> str:
    """生成文本格式报告"""
    report_lines = ["报告摘要", "=" * 20]
    
    for i, item in enumerate(data, 1):
        report_lines.append(f"\n项目 {i}:")
        for key, value in item.items():
            report_lines.append(f"  {key}: {value}")
    
    report_lines.append(f"\n总计: {len(data)} 个项目")
    return "\n".join(report_lines)


def _generate_json_report(data: List[Dict]) -> str:
    """生成JSON格式报告"""
    report = {
        "summary": {
            "total_items": len(data),
            "generated_at": "2024-01-01T00:00:00Z"  # 实际使用时应该用当前时间
        },
        "data": data
    }
    return json.dumps(report, ensure_ascii=False, indent=2)


def _generate_markdown_report(data: List[Dict]) -> str:
    """生成Markdown格式报告"""
    report_lines = ["# 项目报告", "", "## 摘要", ""]
    
    # 生成表格头
    if data:
        headers = list(data[0].keys())
        report_lines.append("| " + " | ".join(headers) + " |")
        report_lines.append("|" + "---|" * len(headers))
        
        # 生成表格行
        for item in data:
            row = [str(item.get(header, "")) for header in headers]
            report_lines.append("| " + " | ".join(row) + " |")
    
    report_lines.append(f"\n**总计项目数:** {len(data)}")
    return "\n".join(report_lines)


def cleanup_temp_files(directory: str, patterns: List[str] = None) -> int:
    """
    清理临时文件
    
    Args:
        directory: 目录路径
        patterns: 文件模式列表
        
    Returns:
        int: 清理的文件数量
    """
    if patterns is None:
        patterns = ["*.tmp", "*.temp", "*.log", "*.bak"]
    
    try:
        dir_path = Path(directory)
        if not dir_path.exists():
            logger.warning(f"目录不存在: {directory}")
            return 0
        
        cleaned_count = 0
        
        for pattern in patterns:
            for file_path in dir_path.rglob(pattern):
                try:
                    file_path.unlink()
                    cleaned_count += 1
                    logger.debug(f"已清理文件: {file_path}")
                except Exception as e:
                    logger.warning(f"清理文件失败 {file_path}: {str(e)}")
        
        logger.info(f"清理完成，共清理 {cleaned_count} 个文件")
        return cleaned_count
        
    except Exception as e:
        logger.error(f"清理临时文件失败: {str(e)}")
        return 0


if __name__ == "__main__":
    # 模块测试代码
    print("my_cli_tool core module loaded successfully")
