"""
验证后端完整流程：
1. thought 事件（澄清与简洁思考）
2. files_generated 事件（plan.md, workflow.md）
3. final_summary 事件（最终总结）
"""
import sys
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Set workspace root BEFORE imports
sandbox_root = PROJECT_ROOT / "test_sandbox"
os.environ["WORKSPACE_ROOT"] = str(sandbox_root)

from llm.agent.agents import orchestrator, planner_agent

def verify():
    print("=" * 60)
    print("验证后端完整流程")
    print("=" * 60)
    print(f"工作区: {os.environ['WORKSPACE_ROOT']}")

    # Create Planner with real LLM
    planner = planner_agent.PlannerAgent()
    
    # Create Orchestrator
    orch = orchestrator.create_orchestrator(
        planner=planner,
        verbose=True
    )
    
    goal = "在 finance_cli 项目中添加一个新的函数 say_hello"
    print(f"\n用户目标: {goal}")
    print("-" * 60)
    
    try:
        result = orch._execute_internal(goal)
        print(f"\n执行结果: {result.get('success', 'N/A')}")
    except Exception as e:
        print(f"执行异常 (可忽略，主要看事件): {e}")
    
    session = orch.current_session
    if not session:
        print("\n[FAIL] 没有会话被创建！")
        return
    
    print("\n" + "=" * 60)
    print("事件日志分析")
    print("=" * 60)
    
    events = session.event_log.events
    print(f"总事件数: {len(events)}\n")
    
    has_thought = False
    has_files = False
    has_summary = False
    thought_content = ""
    files_info = []
    summary_content = ""
    
    for evt in events:
        print(f"[{evt.event_type}] {evt.summary[:50]}...")
        if evt.event_type == "thought":
            has_thought = True
            thought_content = evt.details.get("thought", "")
        if evt.event_type == "files_generated":
            has_files = True
            files_info = evt.details.get("files", [])
        if evt.event_type == "final_summary":
            has_summary = True
            summary_content = evt.details.get("summary", "")
    
    print("\n" + "=" * 60)
    print("验证结果")
    print("=" * 60)
    
    # 1. Thought
    if has_thought:
        print("[PASS] ✓ 思考澄清 (thought) 事件已生成")
        print(f"       内容: {thought_content[:100]}...")
    else:
        print("[FAIL] ✗ 没有找到 thought 事件")
    
    # 2. Files
    if has_files:
        print("[PASS] ✓ 文件生成 (files_generated) 事件已生成")
        for f in files_info:
            print(f"       - {f.get('name')}: {f.get('path')}")
    else:
        print("[FAIL] ✗ 没有找到 files_generated 事件")
    
    # 3. Summary
    if has_summary:
        print("[PASS] ✓ 最终总结 (final_summary) 事件已生成")
        print(f"       内容: {summary_content[:100]}...")
    else:
        print("[WARN] ⚠ 没有找到 final_summary 事件 (可能执行未完成)")
    
    # 4. Check files on disk
    print("\n" + "=" * 60)
    print("磁盘文件验证")
    print("=" * 60)
    plans_dir = sandbox_root / ".agent" / "plans"
    
    plan_path = plans_dir / "plan.md"
    workflow_path = plans_dir / "workflow.md"
    
    if plan_path.exists():
        print(f"[PASS] ✓ plan.md 已创建: {plan_path}")
        print(f"       大小: {plan_path.stat().st_size} bytes")
    else:
        print(f"[FAIL] ✗ plan.md 未找到")
        
    if workflow_path.exists():
        print(f"[PASS] ✓ workflow.md 已创建: {workflow_path}")
        print(f"       大小: {workflow_path.stat().st_size} bytes")
    else:
        print(f"[FAIL] ✗ workflow.md 未找到")

if __name__ == "__main__":
    verify()
