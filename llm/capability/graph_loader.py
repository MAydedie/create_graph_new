import json
import os
from typing import List, Dict, Any
from pathlib import Path

class GraphKnowledgeLoader:
    """
    负责加载 create_graph 生成的代码图谱数据 (JSON)，
    并将其转换为 RAG 系统可用的文本块格式。
    """
    
    def __init__(self, output_dir: str = "output"):
        self.output_dir = output_dir
        
    def load_graph_data(self, graph_data_path: str = None) -> List[Dict[str, Any]]:
        """
        加载详细的图谱数据 (graph_data.json) 并提取关键信息
        """
        if not graph_data_path:
             graph_data_path = os.path.join(self.output_dir, "graph_data.json")
             
        if not os.path.exists(graph_data_path):
            print(f"Warning: Graph data not found at {graph_data_path}")
            return []
            
        with open(graph_data_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        chunks = []
        nodes = data.get("nodes", [])
        
        # 建立 ID 到节点的映射，方便后续扩展（如查找父子关系）
        node_map = {n['data']['id']: n['data'] for n in nodes}
        
        for node in nodes:
            node_data = node['data']
            node_type = node_data.get('type')
            
            if node_type == 'class':
                # 处理类节点
                # 格式化为 LLM 易读的描述
                class_name = node_data['label']
                docstring = node_data.get('docstring', 'No description').strip()
                if docstring == "No documentation":
                    docstring = "No description provided."
                    
                text = f"## Class: {class_name}\n"
                text += f"- **File**: {node_data.get('file', 'Unknown')}:{node_data.get('line', 0)}\n"
                text += f"- **Description**: {docstring}\n"
                text += f"- **Methods Count**: {node_data.get('methods_count', 0)}\n"
                
                chunks.append({
                    "content": text,
                    "metadata": {
                        "source": "graph_analysis",
                        "type": "class",
                        "name": class_name,
                        "file": node_data.get('file', 'Unknown')
                    }
                })
                
            elif node_type in ['method', 'function']:
                # 处理方法/函数节点
                method_name = node_data['label']
                parent_class = node_data.get('class_name', 'Global')
                signature = node_data.get('signature', method_name)
                docstring = node_data.get('docstring', 'No description').strip()
                if docstring == "No documentation":
                    docstring = "No description provided."
                
                text = f"## Method: {signature}\n"
                text += f"- **Type**: {node_type.capitalize()}\n"
                text += f"- **Parent Class**: {parent_class}\n"
                text += f"- **File**: {node_data.get('file', 'Unknown')}:{node_data.get('line', 0)}\n"
                text += f"- **Description**: {docstring}\n"
                text += f"- **Return Type**: {node_data.get('return_type', 'Any')}\n"
                
                # 添加参数信息
                params = node_data.get('parameters', [])
                if params:
                    param_str = ", ".join([f"{p['name']}: {p['type']}" for p in params])
                    text += f"- **Parameters**: {param_str}\n"
                
                chunks.append({
                    "content": text,
                    "metadata": {
                        "source": "graph_analysis",
                        "type": node_type,
                        "name": method_name,
                        "parent": parent_class,
                        "signature": signature,
                        "file": node_data.get('file', 'Unknown')
                    }
                })
        
        return chunks
    
    def load_experience_paths(self, experience_paths_dir: str = None) -> List[Dict[str, Any]]:
        """
        加载经验路径数据（功能路径/Desk）并转换为知识块格式
        
        采用层级结构组织知识：
        1. 功能分区层
        2. 功能路径层（包含路径序列、调用链类型、语义描述）
        3. 详细分析层（CFG、DFG、输入输出）
        
        Args:
            experience_paths_dir: 经验路径JSON文件目录
            
        Returns:
            知识块列表
        """
        if not experience_paths_dir:
            experience_paths_dir = os.path.join(self.output_dir, "experience_paths")
        
        if not os.path.exists(experience_paths_dir):
            print(f"Warning: Experience paths directory not found at {experience_paths_dir}")
            return []
        
        chunks = []
        
        # 遍历目录下的所有JSON文件
        for filename in os.listdir(experience_paths_dir):
            if not filename.endswith('.json'):
                continue
            
            filepath = os.path.join(experience_paths_dir, filename)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except Exception as e:
                print(f"Warning: Failed to load {filepath}: {e}")
                continue
            
            project_name = data.get('project_name', 'Unknown')
            
            # 遍历所有分区中的路径
            for partition in data.get('partitions', []):
                partition_id = partition.get('partition_id', 'unknown')
                partition_name = partition.get('partition_name', partition_id)
                
                for path_info in partition.get('paths', []):
                    # 提取路径信息
                    path_id = path_info.get('path_id', f"{partition_id}_{path_info.get('path_index', 0)}")
                    function_chain = path_info.get('function_chain') or path_info.get('path', [])
                    leaf_node = path_info.get('leaf_node', '')
                    
                    # 命名提取优先级：
                    # 1. path_name (LLM生成的中文短语)
                    # 2. semantics.semantic_label (同上)
                    # 3. semantics.description (取前20字)
                    # 4. 自动生成 "功能路径 [叶子节点]"
                    semantics = path_info.get('semantics') or {}
                    path_name = path_info.get('path_name')
                    
                    if not path_name:
                        path_name = semantics.get('semantic_label')
                    
                    if not path_name:
                        desc = semantics.get('description')
                        if desc:
                            path_name = desc[:20] + "..." if len(desc) > 20 else desc
                    
                    
                    # 如果仍然没有名字，或者是英文的技术ID，尝试用叶子节点名生成更友好的名字
                    # 增强判断：如果包含 "general:" 或 "partition_" 或纯英文/数字，则强制使用中文描述
                    is_generic_name = (
                        not path_name or 
                        path_name == path_id or 
                        "general:" in path_name or
                        "partition_" in path_name or
                        path_name.isascii()  # 简单粗暴：如果是纯ASCII（英文），也尝试优化
                    )

                    if is_generic_name:
                         # 尝试提取叶子节点的中文别名（如果有的话），这里先用简单处理
                         leaf_short = leaf_node.split('.')[-1] if '.' in leaf_node else leaf_node
                         # TODO: 如果能从 graph_data 获取到 leaf_short 的 docstring 或 label 会更好
                         # 这里暂时用 "功能路径: [函数名]"
                         path_name = f"功能路径: {leaf_short}"

                    path_description = path_info.get('path_description', '')
                    if not path_description:
                        path_description = semantics.get('description', '')

                    
                    # ========== 层级1：功能路径概述 ==========
                    path_overview = f"# 【功能路径】{path_name}\n\n"
                    path_overview += f"## 基本信息\n"
                    path_overview += f"- **所属分区**: {partition_name}\n"
                    path_overview += f"- **功能域**: {semantics.get('functional_domain', partition_name)}\n"
                    path_overview += f"- **路径ID**: {path_id}\n\n"
                    
                    path_overview += f"## 路径序列（调用链）\n"
                    path_overview += f"```\n{' → '.join(function_chain)}\n```\n\n"
                    
                    if path_description:
                        path_overview += f"## 调用链解释\n{path_description}\n\n"
                    
                    # 调用链类型分析
                    call_chain_analysis = path_info.get('call_chain_analysis')
                    if call_chain_analysis:
                        chain_type = call_chain_analysis.get('call_chain_type', '')
                        main_method = call_chain_analysis.get('main_method', '')
                        if chain_type:
                            path_overview += f"## 调用链类型\n"
                            path_overview += f"- **类型**: {chain_type}\n"
                            if main_method:
                                path_overview += f"- **总方法**: {main_method}\n"
                            path_overview += "\n"
                    
                    # ========== 层级2：输入输出信息 (优先使用 IO Graph 节点) ==========
                    io_section = ""
                    io_graph = path_info.get('io_graph')
                    input_info = path_info.get('input_info') or {}
                    output_info = path_info.get('output_info') or {}
                    
                    # 尝试从 io_graph 解析更友好的 IO 信息（这与前端展示一致）
                    io_graph_text = ""
                    if io_graph and isinstance(io_graph, dict):
                        io_nodes = io_graph.get('nodes', [])
                        inputs = []
                        outputs = []
                        intermediates = []
                        
                        for node in io_nodes:
                            n_type = node.get('type', '')
                            n_label = node.get('label', '')
                            # 过滤掉纯ID展示，尝试提取更有意义的内容
                            if n_type == 'input':
                                inputs.append(n_label)
                            elif n_type == 'output':
                                outputs.append(n_label)
                            elif n_type == 'process':
                                intermediates.append(n_label)
                        
                        if inputs:
                            io_graph_text += f"### 核心输入\n" + "\n".join([f"- {i}" for i in inputs]) + "\n"
                        if outputs:
                            io_graph_text += f"\n### 核心输出\n" + "\n".join([f"- {o}" for o in outputs]) + "\n"
                    
                    # 如果 io_graph 解析出了内容，优先使用它
                    if io_graph_text:
                         io_section += f"## 输入输出视点 (IO View)\n{io_graph_text}\n"
                    
                    # 补充详细参数信息（如果有且不重复）
                    # ... (旧的详细参数提取逻辑可以作为补充，或者在没有 io_graph 时使用)
                    if not io_graph_text: # 只有当可视化图缺失时，才回退到代码级参数列表
                        cfg = path_info.get('cfg') or {}
                        if not input_info and cfg.get('input_info'):
                            input_info = cfg.get('input_info')
                        if not output_info and cfg.get('output_info'):
                            output_info = cfg.get('output_info')
                        
                        if input_info or output_info:
                            io_section += f"## 代码级输入输出\n"
                            if input_info and isinstance(input_info, dict):
                                io_section += f"### 参数列表\n"
                                for method_sig, params in input_info.items():
                                    if params:
                                        param_strs = [f"`{p.get('name', '?')}: {p.get('type', 'Any')}`" for p in params if isinstance(p, dict)]
                                        if param_strs:
                                            method_short = method_sig.split('.')[-1] if '.' in method_sig else method_sig
                                            io_section += f"- **{method_short}**: {', '.join(param_strs)}\n"
                                            
                            if output_info and isinstance(output_info, dict):
                                io_section += f"### 返回类型\n"
                                for method_sig, return_type in output_info.items():
                                    method_short = method_sig.split('.')[-1] if '.' in method_sig else method_sig
                                    io_section += f"- **{method_short}**: `{return_type}`\n"
                        io_section += "\n"
                    
                    # ========== 层级3：控制流图（CFG） ==========
                    cfg_section = ""
                    if cfg and isinstance(cfg, dict):
                        cfg_nodes = cfg.get('nodes', {})
                        cfg_edges = cfg.get('edges', [])
                        if cfg_nodes:
                            cfg_section += f"## 控制流图（CFG）\n"
                            cfg_section += f"- **节点数**: {len(cfg_nodes)}\n"
                            cfg_section += f"- **边数**: {len(cfg_edges)}\n"
                            # 摘要前3个关键节点
                            key_nodes = []
                            for nid, ndata in list(cfg_nodes.items())[:5]:
                                if isinstance(ndata, dict):
                                    label = ndata.get('label', nid)
                                    key_nodes.append(label[:80])
                            if key_nodes:
                                cfg_section += f"- **关键节点**: {'; '.join(key_nodes)}\n"
                            cfg_section += "\n"
                    
                    # ========== 层级4：数据流图（DFG） ==========
                    dfg_section = ""
                    dfg = path_info.get('dfg') or {}
                    if dfg and isinstance(dfg, dict):
                        dfg_nodes = dfg.get('nodes', {})
                        dfg_edges = dfg.get('edges', [])
                        if dfg_nodes:
                            dfg_section += f"## 数据流图（DFG）\n"
                            dfg_section += f"- **节点数**: {len(dfg_nodes)}\n"
                            dfg_section += f"- **边数**: {len(dfg_edges)}\n"
                            # 摘要变量定义
                            var_defs = []
                            for nid, ndata in list(dfg_nodes.items())[:5]:
                                if isinstance(ndata, dict) and ndata.get('type') == 'variable':
                                    var_defs.append(ndata.get('name', nid))
                            if var_defs:
                                dfg_section += f"- **关键变量**: {', '.join(var_defs)}\n"
                            dfg_section += "\n"
                    
                    # ========== 层级5：数据流Mermaid图 ==========
                    dataflow_section = ""
                    dataflow_mermaid = path_info.get('dataflow_mermaid')
                    if dataflow_mermaid:
                        dataflow_section += f"## 数据流视图\n"
                        dataflow_section += f"```mermaid\n{dataflow_mermaid}\n```\n\n"
                    
                    # ========== 层级6：CFG/DFG LLM解释 ==========
                    explain_section = ""
                    cfg_dfg_explain = path_info.get('cfg_dfg_explain_md')
                    if cfg_dfg_explain:
                        explain_section += f"## 分析解释\n{cfg_dfg_explain}\n\n"
                    
                    # ========== 组合完整知识块 ==========
                    full_text = path_overview + io_section + cfg_section + dfg_section + dataflow_section + explain_section
                    
                    # Fix: Ensure has_io is defined
                    has_io = bool(io_section)
                    
                    chunks.append({
                        "content": full_text.strip(),
                        "metadata": {
                            "source": "experience_path",
                            "type": "functional_path",
                            "path_id": path_id,
                            "path_name": path_name,
                            "partition_id": partition_id,
                            "partition_name": partition_name,
                            "function_chain": function_chain,
                            "functional_domain": semantics.get('functional_domain', partition_name),
                            "keywords": semantics.get('keywords', []),
                            "has_cfg": bool(cfg_section),
                            "has_dfg": bool(dfg_section),
                            "has_io": has_io
                        }
                    })
        
        return chunks
    
    def load_all(self, graph_data_path: str = None, experience_paths_dir: str = None) -> List[Dict[str, Any]]:
        """
        加载所有知识数据（图谱 + 功能路径）
        
        Args:
            graph_data_path: graph_data.json 路径
            experience_paths_dir: 经验路径目录
            
        Returns:
            合并后的知识块列表
        """
        all_chunks = []
        
        # 加载图谱数据
        graph_chunks = self.load_graph_data(graph_data_path)
        all_chunks.extend(graph_chunks)
        print(f"Loaded {len(graph_chunks)} chunks from graph data")
        
        # 加载经验路径
        path_chunks = self.load_experience_paths(experience_paths_dir)
        all_chunks.extend(path_chunks)
        print(f"Loaded {len(path_chunks)} chunks from experience paths")
        
        print(f"Total: {len(all_chunks)} knowledge chunks")
        return all_chunks

if __name__ == "__main__":
    # Test
    loader = GraphKnowledgeLoader(output_dir="output_self_analysis")
    print("Graph Loader Initialized")
    
    # 尝试加载所有数据
    chunks = loader.load_all(
        experience_paths_dir="output_analysis/experience_paths"
    )
    print(f"Loaded {len(chunks)} total knowledge chunks")
    
    # 显示样例
    path_chunks = [c for c in chunks if c['metadata'].get('type') == 'functional_path']
    if path_chunks:
        print("\nSample Functional Path Chunk:")
        print(path_chunks[0]['content'])

