# 【Phase 1】路径语义画像完善与存储

#### 任务1.2：经验路径持久化存储
**优先级：** 🟡 高（0.1版本需要）  
**预计工作量：** 2-3天  
**前置依赖：** 任务1.1、任务0.1

##### 存储方案决策

**阶段划分：**
- **0.1版本：** JSON文件存储（简单、可读、易调试）
- **0.3-0.4版本：** 考虑轻量数据库（如果数据量大或需要复杂查询）
- **0.6+版本：** 统一知识库（如果需要跨项目复用）

**为什么0.1版本用JSON：**
1. 路径数据规模：一个项目通常几百到几千条路径，JSON完全够用
2. 查询需求：初期只需要简单匹配，不需要复杂SQL查询
3. 开发速度：JSON无需数据库配置，开发更快
4. 调试友好：可以直接查看和修改JSON文件

##### 实施方案

**步骤1：定义存储格式**

**创建 `data/experience_path_schema.json`（文档，不是实际数据）：**
```json
{
  "version": "0.1",
  "description": "经验路径库存储格式",
  "structure": {
    "project_path": "项目路径（作为键）",
    "analysis_timestamp": "分析时间戳",
    "partitions": [
      {
        "partition_id": "分区ID",
        "partition_name": "分区名称",
        "paths": [
          {
            "path_id": "路径ID",
            "function_chain": ["函数1", "函数2", ...],
            "semantics": {
              "semantic_label": "语义标签",
              "keywords": ["关键词1", ...],
              "functional_domain": "功能域",
              "description": "功能描述"
            },
            "io_summary": {
              "input": ["输入1", ...],
              "output": ["输出1", ...]
            },
            "cfg_data": {...},  // 可选
            "dfg_data": {...}   // 可选
          }
        ]
      }
    ]
  }
}
```

**步骤2：实现存储服务**

**创建 `data/experience_path_storage.py`：**
```python
"""
经验路径存储服务 - 负责经验路径的持久化和加载
"""
from typing import Dict, List, Optional, Any
from pathlib import Path
import json
import os
from datetime import datetime

class ExperiencePathStorage:
    """经验路径存储服务"""
    
    def __init__(self, storage_dir: str = "output_analysis/experience_paths"):
        """
        初始化存储服务
        
        Args:
            storage_dir: 存储目录
        """
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
    
    def save_experience_paths(
        self,
        project_path: str,
        experience_paths: List[Dict],
        partition_analyses: Dict[str, Dict]
    ):
        """
        保存经验路径到JSON文件
        
        Args:
            project_path: 项目路径
            experience_paths: 经验路径列表（从DataAccessor获取）
            partition_analyses: 分区分析结果
        """
        # 按项目路径生成文件名（使用路径的hash避免特殊字符）
        import hashlib
        project_hash = hashlib.md5(project_path.encode()).hexdigest()[:8]
        project_name = os.path.basename(project_path) or "unknown_project"
        filename = f"{project_name}_{project_hash}.json"
        filepath = self.storage_dir / filename
        
        # 组织数据
        data = {
            'version': '0.1',
            'project_path': project_path,
            'project_name': project_name,
            'analysis_timestamp': datetime.now().isoformat(),
            'total_paths': len(experience_paths),
            'partitions': []
        }
        
        # 按分区组织路径
        partition_paths_map = {}
        for path in experience_paths:
            partition_id = path['partition_id']
            if partition_id not in partition_paths_map:
                partition_paths_map[partition_id] = []
            partition_paths_map[partition_id].append(path)
        
        # 构建分区数据
        for partition_id, paths in partition_paths_map.items():
            partition_data = partition_analyses.get(partition_id, {})
            partition_entry = {
                'partition_id': partition_id,
                'partition_name': partition_data.get('partition_name', partition_id),
                'total_paths': len(paths),
                'paths': paths
            }
            data['partitions'].append(partition_entry)
        
        # 保存到JSON
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        print(f"[ExperiencePathStorage] ✅ 经验路径已保存到: {filepath}")
    
    def load_experience_paths(self, project_path: str) -> Optional[Dict]:
        """
        加载经验路径
        
        Args:
            project_path: 项目路径
        
        Returns:
            经验路径数据，如果不存在则返回None
        """
        # 查找匹配的JSON文件
        project_name = os.path.basename(project_path) or "unknown_project"
        
        for filepath in self.storage_dir.glob(f"{project_name}_*.json"):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # 验证项目路径是否匹配
                if data.get('project_path') == project_path or data.get('project_name') == project_name:
                    return data
            except Exception as e:
                print(f"[ExperiencePathStorage] ⚠️ 加载文件失败 {filepath}: {e}")
                continue
        
        return None
    
    def list_all_projects(self) -> List[Dict[str, str]]:
        """列出所有已存储的项目"""
        projects = []
        for filepath in self.storage_dir.glob("*.json"):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    projects.append({
                        'project_path': data.get('project_path', ''),
                        'project_name': data.get('project_name', ''),
                        'analysis_timestamp': data.get('analysis_timestamp', ''),
                        'total_paths': data.get('total_paths', 0)
                    })
            except Exception as e:
                print(f"[ExperiencePathStorage] ⚠️ 读取文件失败 {filepath}: {e}")
        return projects
```

**步骤3：集成到功能层级分析流程**

**修改 `app/services/analysis_service.py`：**

```python
def analyze_function_hierarchy(self, project_path: str):
    """功能层级分析（完成后自动保存经验路径）"""
    # ... 现有分析逻辑 ...
    
    # 保存分析结果
    self.data_accessor.save_function_hierarchy(project_path, result_data)
    
    # 新增：保存经验路径到JSON
    from data.experience_path_storage import ExperiencePathStorage
    from data.data_accessor import get_data_accessor
    
    storage = ExperiencePathStorage()
    experience_paths = self.data_accessor.get_experience_paths(project_path)
    storage.save_experience_paths(project_path, experience_paths, partition_analyses)
```

**步骤4：DataAccessor支持从JSON加载**

**修改 `data/data_accessor.py`：**

```python
def load_experience_paths_from_storage(self, project_path: str) -> Optional[List[Dict]]:
    """从持久化存储加载经验路径"""
    from data.experience_path_storage import ExperiencePathStorage
    storage = ExperiencePathStorage()
    data = storage.load_experience_paths(project_path)
    if not data:
        return None
    
    # 提取所有路径
    all_paths = []
    for partition in data.get('partitions', []):
        all_paths.extend(partition.get('paths', []))
    return all_paths
```

**验收标准：**
- ✅ 功能层级分析完成后，自动保存经验路径到JSON
- ✅ 可以通过存储服务加载经验路径
- ✅ JSON文件格式清晰，易于查看和调试






