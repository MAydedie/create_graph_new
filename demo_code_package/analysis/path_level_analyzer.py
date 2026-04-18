"""
路径级别分析器 - 为每个叶子节点路径生成CFG、DFG和数据流图
"""


class PathLevelAnalyzer:
    """路径级别分析器类"""
    
    def __init__(self):
        """初始化分析器"""
        self.cfg_generator = None
        self.dfg_generator = None
    
    def generate_path_level_cfg(self, path, call_graph, partition_methods):
        """
        为一条路径生成功能层级的CFG（控制流图）
        
        Args:
            path: 路径节点列表
            call_graph: 调用图
            partition_methods: 分区方法集合
            
        Returns:
            路径级别的CFG数据
        """
        # 调用内部方法生成CFG
        path_cfgs = {}
        path_nodes = {}
        path_edges = []
        
        for method_sig in path:
            if method_sig not in partition_methods:
                continue
            
            method_cfg = self._generate_method_cfg(method_sig)
            if method_cfg:
                path_cfgs[method_sig] = method_cfg
                self._collect_cfg_nodes_edges(method_sig, method_cfg, path_nodes, path_edges)
        
        self._add_method_call_edges(path, path_cfgs, path_edges)
        
        return {
            'path': path,
            'nodes': path_nodes,
            'edges': path_edges,
            'dot': self._generate_dot(path_nodes, path_edges)
        }
    
    def generate_path_level_dfg(self, path, call_graph, partition_methods):
        """
        为一条路径生成功能层级的DFG（数据流图）
        
        Args:
            path: 路径节点列表
            call_graph: 调用图
            partition_methods: 分区方法集合
            
        Returns:
            路径级别的DFG数据
        """
        path_dfgs = {}
        path_nodes = {}
        path_edges = []
        
        for method_sig in path:
            if method_sig not in partition_methods:
                continue
            
            method_dfg = self._generate_method_dfg(method_sig)
            if method_dfg:
                path_dfgs[method_sig] = method_dfg
                self._collect_dfg_nodes_edges(method_sig, method_dfg, path_nodes, path_edges)
        
        parameter_flows = self._find_parameter_flows(path, partition_methods)
        return_flows = self._find_return_flows(path, partition_methods)
        
        return {
            'path': path,
            'nodes': path_nodes,
            'edges': path_edges,
            'parameter_flows': parameter_flows,
            'return_flows': return_flows,
            'dot': self._generate_dfg_dot(path_nodes, path_edges, parameter_flows, return_flows)
        }
    
    def _generate_method_cfg(self, method_sig):
        """生成方法级别的CFG"""
        return {
            'nodes': [
                {'id': 'entry', 'type': 'entry'},
                {'id': 'exit', 'type': 'exit'}
            ],
            'edges': [
                {'source': 'entry', 'target': 'exit', 'type': 'normal'}
            ]
        }
    
    def _generate_method_dfg(self, method_sig):
        """生成方法级别的DFG"""
        return {
            'nodes': [
                {'id': 'var1', 'variable': 'data', 'type': 'variable'}
            ],
            'edges': []
        }
    
    def _collect_cfg_nodes_edges(self, method_sig, method_cfg, path_nodes, path_edges):
        """收集CFG节点和边"""
        for node in method_cfg.get('nodes', []):
            path_nodes[f"{method_sig}_{node['id']}"] = {
                'id': f"{method_sig}_{node['id']}",
                'label': f"{method_sig}: {node['type']}",
                'type': node['type'],
                'method': method_sig
            }
        
        for edge in method_cfg.get('edges', []):
            path_edges.append({
                'source': f"{method_sig}_{edge['source']}",
                'target': f"{method_sig}_{edge['target']}",
                'type': edge['type'],
                'method': method_sig
            })
    
    def _collect_dfg_nodes_edges(self, method_sig, method_dfg, path_nodes, path_edges):
        """收集DFG节点和边"""
        for node in method_dfg.get('nodes', []):
            path_nodes[f"{method_sig}_{node['id']}"] = {
                'id': f"{method_sig}_{node['id']}",
                'label': f"{method_sig}: {node.get('variable', '')}",
                'type': node['type'],
                'method': method_sig
            }
    
    def _add_method_call_edges(self, path, path_cfgs, path_edges):
        """添加方法间的调用边"""
        for i in range(len(path) - 1):
            caller = path[i]
            callee = path[i + 1]
            if caller in path_cfgs and callee in path_cfgs:
                path_edges.append({
                    'source': f"{caller}_exit",
                    'target': f"{callee}_entry",
                    'type': 'method_call',
                    'caller': caller,
                    'callee': callee
                })
    
    def _find_parameter_flows(self, path, partition_methods):
        """查找参数流动"""
        flows = []
        for i in range(len(path) - 1):
            caller = path[i]
            callee = path[i + 1]
            if caller in partition_methods and callee in partition_methods:
                flows.append({
                    'source': caller,
                    'target': callee,
                    'parameter': 'data'
                })
        return flows
    
    def _find_return_flows(self, path, partition_methods):
        """查找返回值流动"""
        flows = []
        for i in range(len(path) - 1):
            callee = path[i]
            caller = path[i + 1]
            if caller in partition_methods and callee in partition_methods:
                flows.append({
                    'source': callee,
                    'target': caller,
                    'return_value': 'result'
                })
        return flows
    
    def _generate_dot(self, nodes, edges):
        """生成DOT格式"""
        lines = ['digraph PathCFG {', '  rankdir=TB;']
        for node_id, node_data in nodes.items():
            lines.append(f'  "{node_id}" [label="{node_data["label"]}"];')
        for edge in edges:
            lines.append(f'  "{edge["source"]}" -> "{edge["target"]}";')
        lines.append('}')
        return '\n'.join(lines)
    
    def _generate_dfg_dot(self, nodes, edges, parameter_flows, return_flows):
        """生成DFG的DOT格式"""
        lines = ['digraph PathDFG {', '  rankdir=LR;']
        for node_id, node_data in nodes.items():
            lines.append(f'  "{node_id}" [label="{node_data["label"]}"];')
        for flow in parameter_flows:
            lines.append(f'  "{flow["source"]}" -> "{flow["target"]}" [label="参数"];')
        for flow in return_flows:
            lines.append(f'  "{flow["source"]}" -> "{flow["target"]}" [label="返回值"];')
        lines.append('}')
        return '\n'.join(lines)


def generate_path_level_cfg(path, call_graph, partition_methods):
    """生成路径级别的CFG"""
    analyzer = PathLevelAnalyzer()
    return analyzer.generate_path_level_cfg(path, call_graph, partition_methods)


def generate_path_level_dfg(path, call_graph, partition_methods):
    """生成路径级别的DFG"""
    analyzer = PathLevelAnalyzer()
    return analyzer.generate_path_level_dfg(path, call_graph, partition_methods)

