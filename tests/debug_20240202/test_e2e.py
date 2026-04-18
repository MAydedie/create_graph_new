"""
端到端测试脚本：测试 Multi-Agent 任务执行
"""
import requests
import json
import time
import threading
import websocket

BASE_URL = "http://localhost:8000"
WORKSPACE = r"D:\代码仓库生图\create_graph\test_sandbox\finance_cli"
USER_GOAL = """请帮我开发一个 CLI 个人财务记账本。需要支持记录收入支出、查看余额，数据存放在 ledger.json 中。请设计一个可扩展的架构，将存储逻辑和交互逻辑分离"""

events_received = []
ws_closed = threading.Event()

def on_message(ws, message):
    try:
        data = json.loads(message)
        events_received.append(data)
        if data.get("type") == "event":
            evt = data.get("data", {})
            print(f"[{evt.get('agent', '?')}] {evt.get('type', '?')}: {evt.get('summary', '')[:100]}")
        elif data.get("type") == "status":
            print(f"[STATUS] {data.get('data')}")
            if data.get("data") in ["completed", "failed"]:
                ws_closed.set()
    except Exception as e:
        print(f"WS Parse Error: {e}")

def on_error(ws, error):
    print(f"WS Error: {error}")

def on_close(ws, close_status_code, close_msg):
    print(f"WS Closed: {close_status_code} {close_msg}")
    ws_closed.set()

def on_open(ws):
    print("WS Connected!")

def run_test():
    print("="*60)
    print("Multi-Agent E2E Test")
    print("="*60)
    print(f"Workspace: {WORKSPACE}")
    print(f"Goal: {USER_GOAL[:50]}...")
    print()

    # 1. Start task via REST API
    print("[1] Starting task via /api/chat...")
    try:
        resp = requests.post(
            f"{BASE_URL}/api/chat",
            json={"user_goal": USER_GOAL, "workspace_root": WORKSPACE},
            timeout=10
        )
        resp.raise_for_status()
        result = resp.json()
        task_id = result.get("task_id")
        print(f"    Task ID: {task_id}")
    except Exception as e:
        print(f"    ERROR: {e}")
        return

    # 2. Connect to WebSocket for events
    print(f"\n[2] Connecting to WebSocket ws://localhost:8000/ws/{task_id}...")
    ws_url = f"ws://localhost:8000/ws/{task_id}"
    
    ws = websocket.WebSocketApp(
        ws_url,
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close
    )
    
    # Run WebSocket in background thread
    wst = threading.Thread(target=ws.run_forever)
    wst.daemon = True
    wst.start()
    
    # 3. Wait for task completion (max 120s)
    print("\n[3] Waiting for task completion (max 120s)...")
    ws_closed.wait(timeout=120)
    
    if not ws_closed.is_set():
        print("    TIMEOUT: Task did not complete in 120s")
    
    ws.close()
    
    # 4. Summary
    print("\n" + "="*60)
    print("Test Summary")
    print("="*60)
    print(f"Total events received: {len(events_received)}")
    
    # Check for errors
    errors = [e for e in events_received if e.get("type") == "event" and "fail" in e.get("data", {}).get("type", "")]
    if errors:
        print(f"\nErrors encountered: {len(errors)}")
        for err in errors:
            evt = err.get("data", {})
            print(f"  - [{evt.get('agent')}] {evt.get('summary', '')[:100]}")
    else:
        print("\nNo errors! ✓")
    
    # Check final status
    statuses = [e for e in events_received if e.get("type") == "status"]
    if statuses:
        print(f"\nFinal status: {statuses[-1].get('data')}")

if __name__ == "__main__":
    run_test()
