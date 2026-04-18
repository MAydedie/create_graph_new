
import unittest
from unittest.mock import MagicMock, patch
import sys
from pathlib import Path
import json

# Add project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from llm.agent.agents.orchestrator import Orchestrator
from llm.agent.core.task_session import TaskSession
from llm.agent.core.execution_state import StepStatus

class TestSmartLoop(unittest.TestCase):
    
    def setUp(self):
        # Mock dependencies
        self.mock_planner = MagicMock()
        self.mock_error_solver = MagicMock()
        self.mock_api = MagicMock()
        
        # Setup Orchestrator
        self.orch = Orchestrator(
            planner=self.mock_planner,
            error_solver=self.mock_error_solver,
            verbose=True
        )
        
        # Mock _generate_clarification to avoid real LLM call
        self.orch._run_clarification = MagicMock()
        self.orch._prepare_session_environment = MagicMock()
        self.orch._save_plan_files = MagicMock()
        self.orch._generate_final_summary = MagicMock()
        self.orch.force_summary_generation = MagicMock()

    def test_smart_loop_retry_success(self):
        """测试：步骤失败后，修复成功，然后步骤重试成功"""
        print("\n=== Test: Retry Success ===")
        
        # 1. Setup Plan
        self.mock_planner.plan.return_value = {
            "plan_id": "test_plan",
            "steps": [{"step_id": 0, "type": "test", "description": "Step 0"}]
        }
        
        # 2. Mock Execution: Fail first, then Success
        # side_effect for _execute_step: [Fail, Success]
        # 注意：第一次失败触发修复，修复后会再次调用 _execute_step
        self.orch._execute_step = MagicMock(side_effect=[False, True])
        
        # Mock Session to return error details on first call
        def get_last_error_side_effect():
            return {"error": "Mock Error"}
        
        # Mock ErrorSolver to return a valid plan
        self.mock_error_solver.solve_error.return_value = {
            "micro_plan": {"goal": "Fix it"},
            "give_up": False
        }
        self.orch._execute_fix_plan = MagicMock(return_value=True)

        # 3. Run
        result = self.orch.execute_with_resolution_loop("Test Goal")
        
        # 4. Verify
        if not result["success"]:
            print(f"FAILED RESULT: {result}")
        self.assertTrue(result["success"])
        self.assertEqual(self.orch._execute_step.call_count, 2)
        self.assertEqual(self.orch._execute_fix_plan.call_count, 1)
        print("Test Passed: Step retried and succeeded.")

    def test_smart_loop_give_up(self):
        """测试：ErrorSolver 判定无法解决，放弃步骤"""
        print("\n=== Test: Give Up ===")
        
        # 1. Setup Plan
        self.mock_planner.plan.return_value = {
            "plan_id": "test_plan",
            "steps": [{"step_id": 0, "type": "test", "description": "Step 0"}]
        }
        
        # 2. Mock Execution: Always Fail
        self.orch._execute_step = MagicMock(return_value=False)
        
        # Mock ErrorSolver to Give Up
        self.mock_error_solver.solve_error.return_value = {
            "give_up": True,
            "give_up_reason": "Too hard"
        }
        
        # 3. Run
        result = self.orch.execute_with_resolution_loop("Test Goal")
        
        # 4. Verify
        # If skipped, the task overall might be marked success (all steps processed)
        # But let's check the logic. Step 0 failed -> give up -> continue.
        # Since it's the only step, loop ends.
        
        if not result["success"]:
            print(f"FAILED RESULT: {result}")
        self.assertTrue(result["success"]) # Task completes (even if step skipped)
        
        # Verify events
        skipped_events = [e for e in self.orch.current_session.event_log.events if e.event_type == "step_skipped"]
        self.assertEqual(len(skipped_events), 1)
        self.assertEqual(skipped_events[0].details["reason"], "Too hard")
        print("Test Passed: Step skipped as requested.")

if __name__ == '__main__':
    unittest.main()
