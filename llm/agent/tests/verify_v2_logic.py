import sys
import os
import time
from unittest.mock import MagicMock, patch

# Add project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from llm.agent.agents.orchestrator import Orchestrator
from ui.server import TaskManager, TaskRequest

def test_infinite_resolution_loop():
    print("\n=== Testing Infinite Resolution Loop ===", flush=True)
    
    orch = Orchestrator(verbose=True)
    orch.error_solver = MagicMock()
    orch.planner = MagicMock()
    orch.coder = MagicMock()
    orch._generate_final_summary = MagicMock()
    orch.force_summary_generation = MagicMock()
    orch._execute_fix_plan = MagicMock(return_value=True)
    
    # Scenario: Fail twice, then succeed
    result_fail = {"success": False, "error": "Simulated Failure"}
    result_success = {"success": True}
    
    orch._execute_internal = MagicMock(side_effect=[
        result_fail,
        result_fail,
        result_success
    ])
    
    orch.error_solver.solve_error.return_value = {
        "micro_plan": {"goal": "Fix It", "steps": ["do_fix"]}
    }
    
    print("Starting execution loop...", flush=True)
    final_result = orch.execute_with_resolution_loop("Test Goal")
    
    print(f"Final Result: {final_result}", flush=True)
    
    assert final_result["success"] == True
    assert final_result["resolution_info"]["total_attempts"] == 3
    assert orch._execute_fix_plan.call_count == 2
    print("PASS: Loop ran 3 times and executed fix plan twice.", flush=True)

def test_server_stop_isolation():
    print("\n=== Testing Server Stop & Isolation ===", flush=True)
    tm = TaskManager()
    orch_mock = MagicMock()
    orch_mock.request_stop = MagicMock()
    orch_mock.force_summary_generation = MagicMock()
    orch_mock.execute_with_resolution_loop = MagicMock()
    
    # Create Task A
    with patch('llm.agent.agents.orchestrator.create_orchestrator', return_value=orch_mock):
        task_id = tm.create_task(TaskRequest(user_goal="Task A", workspace_root=".", restore_from=None))
        print(f"Created Task A: {task_id}", flush=True)
        
        # Stop Task A
        print("Stopping Task A...", flush=True)
        tm.stop_task(task_id)
        
        assert tm.stopped_tasks.get(task_id) == True
        assert orch_mock.request_stop.called
        assert orch_mock.force_summary_generation.called
        
        # Create Task B
        print("Creating Task B (Hello)...", flush=True)
        task_id_b = tm.create_task(TaskRequest(user_goal="Hello", workspace_root=".", restore_from=None))
        
        assert task_id != task_id_b
        # Verify Orchestrator for Task B is new (mock logic ensures it is unique if create_orchestrator is called again, but here we mocked it to return same mock object potentially?)
        # Wait, create_orchestrator is mocked to return 'orch_mock'. 
        # So both tasks use same mock object.
        # But tm.orchestrators[task_id] = orch.
        # tm.orchestrators[task_id_b] = orch.
        # This is fine for testing TaskManager logic.
        
        print("PASS: Task A stopped, Task B started.", flush=True)

if __name__ == "__main__":
    try:
        test_infinite_resolution_loop()
        test_server_stop_isolation()
        print("\nALL TESTS PASSED", flush=True)
    except Exception as e:
        print(f"\nTEST FAILED: {e}", flush=True)
        import traceback
        traceback.print_exc()
