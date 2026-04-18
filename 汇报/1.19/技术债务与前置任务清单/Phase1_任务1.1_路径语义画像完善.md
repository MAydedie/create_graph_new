# 【Phase 1】路径语义画像完善与存储

#### 任务1.1：路径语义画像完善
**优先级：** 🟡 高（0.1版本需要）  
**预计工作量：** 3-4天  
**前置依赖：** 任务0.1（DataAccessor）

##### 问题分析

**当前路径提取的局限性：**
1. **策略限制：** 当前从"叶子节点回溯到入口点"，可能遗漏：
   - 中间路径（既不从入口开始，也不在叶子结束）
   - 跨分区路径（功能涉及多个分区）
   - 长路径（被 `max_path_length=10` 截断）

2. **验证建议：**
   - 先用现有方法做验证测试（如测试"OAuth登录"是否能找到相关路径）
   - 如果覆盖率不足，再逐步改进

##### 实施方案

**步骤1：路径找全验证测试**
- 创建测试脚本 `tests/test_path_coverage.py`
- 设计测试用例：已知功能的完整路径（如"用户登录"）
- 验证现有路径提取能否找到这些路径
- 记录覆盖率

**步骤2：增强路径提取（如果覆盖率不足）**

**修改 `analysis/function_node_enhancer.py` 中的 `explore_paths_in_partition`：**

```python
def explore_paths_in_partition_enhanced(
    leaf_nodes: List[str],
    entry_points: List[str],  # 新增：入口点列表
    hypergraph: FunctionCallHypergraph,
    call_graph: Dict[str, Set[str]],
    partition_methods: Set[str],
    max_path_length: int = 15  # 增加到15
) -> Dict[str, List[List[str]]]:
    """
    增强版路径探索：
    1. 从叶子节点回溯（原有策略）
    2. 从入口点前向探索（新增策略）
    3. 合并中间路径（新增策略）
    """
    # 策略1：从叶子节点回溯
    paths_from_leafs = explore_paths_in_partition(
        leaf_nodes, hypergraph, call_graph, partition_methods, max_path_length
    )
    
    # 策略2：从入口点前向探索
    paths_from_entries = explore_paths_from_entries(
        entry_points, call_graph, partition_methods, max_path_length
    )
    
    # 策略3：合并中间路径（找到不在入口和叶子中的节点，探索其周围路径）
    intermediate_paths = explore_intermediate_paths(
        call_graph, partition_methods, entry_points, leaf_nodes, max_path_length
    )
    
    # 合并所有路径并去重
    all_paths = merge_paths(paths_from_leafs, paths_from_entries, intermediate_paths)
    
    return all_paths
```

**步骤3：为路径生成语义标签**

**修改 `analysis/path_semantic_analyzer.py`，添加路径级语义分析：**

```python
def analyze_path_semantics(
    path: List[str],
    analyzer_report: ProjectAnalysisReport,
    method_profiles: Dict[str, MethodFunctionProfile]
) -> Dict[str, Any]:
    """
    分析路径的语义信息
    
    Returns:
        {
            'semantic_label': str,        # 语义标签（如"用户登录流程"）
            'keywords': List[str],        # 关键词
            'input_types': List[str],     # 输入类型
            'output_types': List[str],    # 输出类型
            'functional_domain': str,     # 功能域
            'description': str            # 功能描述
        }
    """
    # 1. 从方法画像中提取关键词
    keywords = set()
    for method_sig in path:
        profile = method_profiles.get(method_sig)
        if profile:
            keywords.update(profile.code_clues.get('keywords', []))
    
    # 2. 使用LLM生成语义标签（可选）
    # 如果方法画像足够丰富，也可以直接用启发式规则
    
    # 3. 从路径的函数名推断功能域
    functional_domain = infer_functional_domain(path)
    
    return {
        'semantic_label': generate_semantic_label(path, keywords),
        'keywords': list(keywords),
        'functional_domain': functional_domain,
        'description': generate_path_description(path)
    }
```

**步骤4：集成到功能层级分析流程**

**修改 `app/services/analysis_service.py`：**

```python
def analyze_function_hierarchy(self, project_path: str):
    """功能层级分析（增强版：包含路径语义画像）"""
    # ... 现有分析逻辑 ...
    
    # 新增：为每个路径生成语义画像
    from analysis.method_function_profile_builder import MethodFunctionProfileBuilder
    from analysis.path_semantic_analyzer import analyze_path_semantics
    
    profile_builder = MethodFunctionProfileBuilder(project_path, analyzer.report)
    
    for partition_id, partition_data in partition_analyses.items():
        path_analyses = partition_data.get('path_analyses', [])
        for path_analysis in path_analyses:
            path = path_analysis.get('path', [])
            
            # 为路径中的每个方法构建画像
            method_profiles = {}
            for method_sig in path:
                profile = profile_builder.build_profile(method_sig)
                if profile:
                    method_profiles[method_sig] = profile
            
            # 分析路径语义
            path_semantics = analyze_path_semantics(path, analyzer.report, method_profiles)
            path_analysis['semantics'] = path_semantics
```

**验收标准：**
- ✅ 路径覆盖率测试通过（或覆盖率 > 80%）
- ✅ 每条路径都有语义标签
- ✅ 路径语义信息保存在分析结果中






