
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from llm.agent.core.execution_state import EventLog

def test_event_log_signature():
    print("Testing EventLog.log signature...")
    log = EventLog()
    
    # CASE 1: Full arguments
    try:
        log.log(
            event_type="test",
            agent="tester",
            step_id=1,
            summary="Full args"
        )
        print("PASS: Full args")
    except TypeError as e:
        print(f"FAIL: Full args raised {e}")

    # CASE 2: Missing 'details' (should pass if default=None)
    try:
        log.log("test", "tester", 1, "No details")
        print("PASS: No details")
    except TypeError as e:
        print(f"FAIL: No details raised {e}")

    # CASE 3: Missing required arguments (Simulate the user error)
    try:
        log.log("Just one arg")
        print("FAIL: 'Just one arg' should have raised TypeError")
    except TypeError as e:
        print(f"PASS: 'Just one arg' raised {e}")
        if "missing 3 required positional arguments" in str(e):
            print("MATCH: Error message matches user report!")
        else:
            print(f"MISMATCH: Error message was '{e}'")

if __name__ == "__main__":
    try:
        test_event_log_signature()
    except Exception as e:
        print(f"CRITICAL FAIL: {e}")
