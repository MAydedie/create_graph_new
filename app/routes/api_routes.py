"""
API routes blueprint (Phase 0 / Task 0.3 Option B/C)
将原 app.py 中的所有 /api 路由注册为 Blueprint，行为保持不变。
"""

from flask import Blueprint

from app.services import analysis_service as svc
from app.services import conversation_service as cs
from app.services import experience_library_service as els
from app.services import multi_agent_service as mas

api_bp = Blueprint("api", __name__, url_prefix="/api")


# 主分析与状态
api_bp.add_url_rule("/analyze", view_func=svc.api_analyze, methods=["POST"])
api_bp.add_url_rule("/status", view_func=svc.api_status, methods=["GET"])
api_bp.add_url_rule("/result", view_func=svc.api_result, methods=["GET"])
api_bp.add_url_rule("/result/check", view_func=svc.api_check_main_result, methods=["GET"])
api_bp.add_url_rule("/repos", view_func=svc.api_gn_repos, methods=["GET"])
api_bp.add_url_rule("/repo", view_func=svc.api_gn_repo, methods=["GET"])
api_bp.add_url_rule("/graph", view_func=svc.api_gn_graph, methods=["GET"])
api_bp.add_url_rule("/file", view_func=svc.api_gn_file, methods=["GET"])
api_bp.add_url_rule("/workbench/session/start", view_func=svc.api_workbench_session_start, methods=["POST"])
api_bp.add_url_rule("/workbench/session/<session_id>/status", view_func=svc.api_workbench_session_status, methods=["GET"])
api_bp.add_url_rule("/workbench/session/<session_id>/bootstrap", view_func=svc.api_workbench_session_bootstrap, methods=["GET"])
api_bp.add_url_rule("/workbench/project_status", view_func=svc.api_workbench_project_status, methods=["GET"])
api_bp.add_url_rule("/benchmark/fixed_scenario/start", view_func=svc.api_fixed_scenario_benchmark_start, methods=["POST"])
api_bp.add_url_rule("/benchmark/fixed_scenario/<session_id>/status", view_func=svc.api_fixed_scenario_benchmark_status, methods=["GET"])
api_bp.add_url_rule("/benchmark/fixed_scenario/<session_id>/result", view_func=svc.api_fixed_scenario_benchmark_result, methods=["GET"])
api_bp.add_url_rule("/front_door/route", view_func=mas.api_front_door_route, methods=["POST"])
api_bp.add_url_rule("/multi_agent/session/start", view_func=mas.api_multi_agent_session_start, methods=["POST"])
api_bp.add_url_rule("/multi_agent/session/<session_id>/status", view_func=mas.api_multi_agent_session_status, methods=["GET"])
api_bp.add_url_rule("/multi_agent/session/<session_id>/result", view_func=mas.api_multi_agent_session_result, methods=["GET"])
api_bp.add_url_rule("/conversations/session/start", view_func=cs.api_conversation_session_start, methods=["POST"])
api_bp.add_url_rule("/conversations/turn", view_func=cs.api_conversation_turn, methods=["POST"])
api_bp.add_url_rule("/conversations/session/<session_id>/status", view_func=cs.api_conversation_session_status, methods=["GET"])
api_bp.add_url_rule("/conversations/session/<session_id>/result", view_func=cs.api_conversation_session_result, methods=["GET"])
api_bp.add_url_rule("/conversations", view_func=cs.api_conversation_list, methods=["GET"])
api_bp.add_url_rule("/conversations/<conversation_id>", view_func=cs.api_conversation_get, methods=["GET"])
api_bp.add_url_rule("/conversations/<conversation_id>/messages", view_func=cs.api_conversation_messages, methods=["GET"])
api_bp.add_url_rule("/conversations/<conversation_id>/summary", view_func=cs.api_conversation_summary, methods=["GET"])
api_bp.add_url_rule("/conversations/<conversation_id>/compactions", view_func=cs.api_conversation_compactions, methods=["GET"])
api_bp.add_url_rule("/conversations/<conversation_id>/events", view_func=cs.api_conversation_events, methods=["GET"])
api_bp.add_url_rule("/conversations/<conversation_id>/reply", view_func=cs.api_conversation_reply, methods=["POST"])
api_bp.add_url_rule("/conversations/<conversation_id>/export_runbook", view_func=cs.api_conversation_export_runbook, methods=["POST"])

# 层级分析
api_bp.add_url_rule("/analyze_hierarchy", view_func=svc.api_analyze_hierarchy, methods=["POST"])
api_bp.add_url_rule("/analyze_function_hierarchy", view_func=svc.api_analyze_function_hierarchy, methods=["POST"])
api_bp.add_url_rule("/function_hierarchy/check", view_func=svc.api_check_function_hierarchy, methods=["GET"])
api_bp.add_url_rule("/function_hierarchy/result", view_func=svc.api_get_function_hierarchy_result, methods=["GET"])
api_bp.add_url_rule("/phase6/read_contract", view_func=svc.api_get_phase6_read_contract, methods=["GET"])
api_bp.add_url_rule("/entry_points_shadow", view_func=svc.api_get_entry_points_shadow, methods=["GET"])
api_bp.add_url_rule("/community_shadow", view_func=svc.api_get_community_shadow, methods=["GET"])
api_bp.add_url_rule("/process_shadow", view_func=svc.api_get_process_shadow, methods=["GET"])
api_bp.add_url_rule("/processes", view_func=svc.api_get_processes_compat, methods=["GET"])
api_bp.add_url_rule("/process", view_func=svc.api_get_process_compat, methods=["GET"])

# 知识图谱与图形数据
api_bp.add_url_rule("/knowledge_graph", view_func=svc.api_knowledge_graph, methods=["GET"])
api_bp.add_url_rule("/cfg_dfg/<entity_id>", view_func=svc.api_cfg_dfg, methods=["GET"])
api_bp.add_url_rule("/node_detail/<entity_id>", view_func=svc.api_node_detail, methods=["GET"])
api_bp.add_url_rule("/rag/ask", view_func=svc.api_rag_ask, methods=["POST"])
api_bp.add_url_rule("/search_hybrid_shadow", view_func=svc.api_search_hybrid_shadow, methods=["POST"])
api_bp.add_url_rule("/fs/open", view_func=svc.api_open_file_system_path, methods=["POST"])
api_bp.add_url_rule("/experience/library", view_func=els.api_experience_library_overview, methods=["GET"])
api_bp.add_url_rule("/experience/library/file", view_func=els.api_experience_library_file, methods=["GET"])
api_bp.add_url_rule("/experience/library/file/save", view_func=els.api_experience_library_file_save, methods=["POST"])
api_bp.add_url_rule("/experience/library/import", view_func=els.api_experience_library_import, methods=["POST"])

# 功能分区相关接口
api_bp.add_url_rule("/partition/<partition_id>/analysis", view_func=svc.api_partition_analysis, methods=["GET"])
api_bp.add_url_rule("/partition/<partition_id>/call_graph", view_func=svc.api_partition_call_graph, methods=["GET"])
api_bp.add_url_rule("/partition/<partition_id>/hypergraph", view_func=svc.api_partition_hypergraph, methods=["GET"])
api_bp.add_url_rule("/partition/<partition_id>/entry_points", view_func=svc.api_partition_entry_points, methods=["GET"])
api_bp.add_url_rule("/partition/<partition_id>/dataflow", view_func=svc.api_partition_dataflow, methods=["GET"])
api_bp.add_url_rule("/partition/<partition_id>/controlflow", view_func=svc.api_partition_controlflow, methods=["GET"])





