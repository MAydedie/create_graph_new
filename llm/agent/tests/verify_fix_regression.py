import sys
import os
from unittest.mock import MagicMock, patch

# Add project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from llm.agent.core.task_session import TaskSession
from llm.agent.core.execution_state import EventLog

def test_retry_log_crash_fix():
    print("\n=== Testing Retry Log Crash Fix (Regression Test) ===", flush=True)
    
    # 1. Create a real TaskSession (not mocked)
    session = TaskSession.create(user_goal="Test Goal")
    
    # 2. Mock execution state where needed, but we rely on real event_log
    session.execution_state.total_steps = 1
    session.plan = {"steps": [{"description": "test step"}]}
    
    # 3. Trigger 'retry_step'
    print("Triggering 'retry_step' action...", flush=True)
    try:
        session.update_state(
            agent="orchestrator", 
            action="retry_step", 
            result={"reason": "Simulated Failure"}
        )
        print("PASS: update_state('retry_step') executed without exception.", flush=True)
        
        # Verify log entry
        assert session.execution_state.retry_count == 1
        print("PASS: retry_count updated.", flush=True)
        
    except TypeError as e:
        print(f"FAIL: Crashed with TypeError: {e}", flush=True)
        if "missing 3 required positional arguments" in str(e):
            print("CRITICAL FAIL: The bug is still present!", flush=True)
        raise
    except Exception as e:
        print(f"FAIL: Crashed with {type(e).__name__}: {e}", flush=True)
        raise

if __name__ == "__main__":
    try:
        test_retry_log_crash_fix()
        print("\nALL REGRESSION TESTS PASSED", flush=True)
    except Exception:
        sys.exit(1)
