#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试快速问答功能
"""
import requests
import json
import time
import websocket
import threading

def test_quick_qa():
    """测试快速问答"""
    
    # 1. 发送问题
    print("=" * 60)
    print("测试问题: 你好,你是谁,你能给我干什么")
    print("=" * 60)
    
    url = "http://localhost:8000/api/chat"
    payload = {
        "user_goal": "你好,你是谁,你能给我干什么",
        "workspace_root": r"D:\代码仓库生图\create_graph"
    }
    
    print(f"\n[1] 发送 POST 请求到 {url}")
    print(f"    Payload: {json.dumps(payload, ensure_ascii=False)}")
    
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        result = response.json()
        
        print(f"\n[2] 收到响应:")
        print(f"    Status Code: {response.status_code}")
        print(f"    Response: {json.dumps(result, ensure_ascii=False, indent=2)}")
        
        task_id = result.get("task_id")
        if not task_id:
            print("\n❌ 错误: 未获取到 task_id")
            return
        
        print(f"\n[3] Task ID: {task_id}")
        
        # 2. 连接 WebSocket 获取结果
        ws_url = f"ws://localhost:8000/ws/{task_id}"
        print(f"\n[4] 连接 WebSocket: {ws_url}")
        
        messages = []
        
        def on_message(ws, message):
            data = json.loads(message)
            messages.append(data)
            print(f"\n[WS] 收到消息:")
            print(f"     Type: {data.get('type')}")
            if data.get('type') == 'log':
                event_data = data.get('data', {})
                print(f"     Event: {event_data.get('event_type')}")
                print(f"     Agent: {event_data.get('agent')}")
                print(f"     Summary: {event_data.get('summary', '')[:100]}...")
            elif data.get('type') == 'result':
                result_data = data.get('data', {})
                print(f"     Success: {result_data.get('success')}")
                print(f"     Summary: {result_data.get('summary', '')}")
        
        def on_error(ws, error):
            print(f"\n❌ WebSocket 错误: {error}")
        
        def on_close(ws, close_status_code, close_msg):
            print(f"\n[WS] 连接关闭")
        
        def on_open(ws):
            print(f"\n[WS] 连接已建立")
        
        # 创建 WebSocket 连接
        ws = websocket.WebSocketApp(
            ws_url,
            on_open=on_open,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close
        )
        
        # 在后台线程运行
        ws_thread = threading.Thread(target=ws.run_forever)
        ws_thread.daemon = True
        ws_thread.start()
        
        # 等待最多 30 秒
        print("\n[5] 等待响应 (最多 30 秒)...")
        for i in range(30):
            time.sleep(1)
            # 检查是否收到 result 类型的消息
            if any(msg.get('type') == 'result' for msg in messages):
                print(f"\n✅ 收到完整响应!")
                break
            if i % 5 == 0:
                print(f"    等待中... ({i}s)")
        
        ws.close()
        
        # 3. 显示最终结果
        print("\n" + "=" * 60)
        print("测试结果汇总")
        print("=" * 60)
        
        result_msg = next((msg for msg in messages if msg.get('type') == 'result'), None)
        if result_msg:
            result_data = result_msg.get('data', {})
            print(f"\n✅ 任务完成!")
            print(f"   Success: {result_data.get('success')}")
            print(f"\n📝 回答内容:")
            print(f"   {result_data.get('summary', result_data.get('message', ''))}")
        else:
            print(f"\n⚠️  未收到最终结果")
            print(f"   收到的消息数: {len(messages)}")
            for i, msg in enumerate(messages):
                print(f"   消息 {i+1}: type={msg.get('type')}")
        
        print("\n" + "=" * 60)
        
    except requests.exceptions.RequestException as e:
        print(f"\n❌ HTTP 请求错误: {e}")
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_quick_qa()
