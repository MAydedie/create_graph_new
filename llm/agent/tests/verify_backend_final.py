
import sys
import os
from pathlib import Path
from unittest.mock import MagicMock

# Setup paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Mock DeepSeekAPI
sys.modules["llm.rag_core.llm_api"] = MagicMock()
mock_api = MagicMock()
mock_api.chat.return_value = {"choices": [{"message": {"content": "Thinking..."}}]}
sys.modules["llm.rag_core.llm_api"].DeepSeekAPI.return_value = mock_api

from llm.agent.agents import orchestrator
from llm.agent.core.task_session import TaskSession

def verify_final():
    sandbox_root = PROJECT_ROOT / "test_sandbox"
    os.environ["WORKSPACE_ROOT"] = str(sandbox_root)
    print(f"Workspace Root: {os.environ['WORKSPACE_ROOT']}")
    
    # Mock Planner
    mock_planner = MagicMock()
    mock_planner.plan.return_value = {
        "plan_id": "p1", "goal": "g", 
        "steps": [
            {"step_id": 0, "type": "code_change", "action": "execute", "target": "t", "description": "d"}
        ]
    }
    
    orch = orchestrator.create_orchestrator(planner=mock_planner)
    
    print("Executing internal...")
    res = orch._execute_internal("Test Goal")
    print(f"Result success: {res.get('success')}")
    
    session = orch.current_session
    if session:
        print(f"Session ID: {session.task_id}")
        events = [e.event_type for e in session.event_log.events]
        print(f"Events: {events}")
        if "thought" in events:
            print("[PASS] Thought event found")
        else:
            print("[FAIL] Thought event missing")
            
        if "files_generated" in events:
            print("[PASS] Files generated event found")
        else:
            print("[FAIL] Files generated event missing")
            
    plans_dir = sandbox_root / ".agent" / "plans"
    if (plans_dir / "plan.md").exists():
        print("[PASS] plan.md created")
        print("Content preview:")
        print((plans_dir / "plan.md").read_text(encoding="utf-8")[:100])
    else:
        print("[FAIL] plan.md missing")

if __name__ == "__main__":
    verify_final()
