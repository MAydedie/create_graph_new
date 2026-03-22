
import sys
import os
from pathlib import Path
from unittest.mock import MagicMock

# Setup paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Mock DeepSeekAPI to avoid key errors
sys.modules["llm.rag_core.llm_api"] = MagicMock()
sys.modules["llm.rag_core.llm_api"].DeepSeekAPI.return_value.chat.return_value = {
    "choices": [{"message": {"content": "Mocked Thought\nMocked Clarification"}}]
}

from llm.agent.agents import orchestrator
from llm.agent.core.task_session import TaskSession

def verify_backend_flow():
    sandbox_root = PROJECT_ROOT / "test_sandbox"
    os.environ["WORKSPACE_ROOT"] = str(sandbox_root)
    print(f"Workspace Root: {os.environ['WORKSPACE_ROOT']}")
    
    # Mock Planner
    mock_planner = MagicMock()
    mock_planner.plan.return_value = {
        "plan_id": "mock_plan",
        "goal": "mock_goal",
        "steps": [
            {"step_id": 0, "type": "code_change", "action": "execute", "target": "test", "description": "mock step"}
        ]
    }
    
    orch = orchestrator.create_orchestrator(
        planner=mock_planner,
        verbose=True
    )
    
    goal = "Test Goal"
    print(f"Executing goal: {goal}")
    
    try:
        result = orch.execute_with_retry(goal, max_retries=0)
        print("Execution Result:", result)
    except Exception as e:
        print(f"Execution failed with error: {e}")
        import traceback
        traceback.print_exc()

    session = orch.get_current_session()
    if not session:
        print("ERROR: No session created. content of orchestrator:", orch.__dict__)
        return

    # Verify Events
    events = session.event_log.events
    print(f"\nTotal Events: {len(events)}")
    
    has_thought = False
    has_files = False
    
    for evt in events:
        print(f"[{evt.event_type}] {evt.summary}")
        if evt.event_type == "thought":
            has_thought = True
        if evt.event_type == "files_generated":
            has_files = True

    if has_thought:
        print("\n[PASS] Thought generation verified.")
    else:
        print("\n[FAIL] No 'thought' event found.")

    if has_files:
        print("[PASS] File generation verified.")
    else:
        print("[FAIL] No 'files_generated' event found.")
        
    # Verify Files on Disk
    plans_dir = sandbox_root / ".agent" / "plans"
    print(f"Checking plans dir: {plans_dir}")
    if (plans_dir / "plan.md").exists():
        print("[PASS] plan.md exists.")
    else:
        print("[FAIL] plan.md not found.")
        
    if (plans_dir / "workflow.md").exists():
        print("[PASS] workflow.md exists.")
    else:
        print("[FAIL] workflow.md not found.")

if __name__ == "__main__":
    verify_backend_flow()
