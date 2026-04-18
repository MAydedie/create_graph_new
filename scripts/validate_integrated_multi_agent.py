#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""验证 create_graph 内嵌三省六部接口是否可用。"""

import importlib.util
import json
import os
import sys
import time


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_FILE = os.path.join(PROJECT_ROOT, 'app.py')
TARGET_PROJECT = os.environ.get('INTEGRATED_TARGET_PROJECT', os.path.join(PROJECT_ROOT, 'demo_code_package'))


def _load_app():
    if PROJECT_ROOT not in sys.path:
        sys.path.insert(0, PROJECT_ROOT)
    spec = importlib.util.spec_from_file_location('create_graph_integrated_app', APP_FILE)
    if spec is None or spec.loader is None:
        raise RuntimeError('无法加载 create_graph app.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.create_app()


def main() -> int:
    app = _load_app()
    client = app.test_client()

    response = client.post('/api/multi_agent/session/start', json={
        'project_path': TARGET_PROJECT,
        'query': '请分析 create_graph 中 Graph RAG 与功能路径如何支撑代码修改建议',
        'task_mode': 'modify_existing',
    })
    payload = response.get_json() or {}
    print('START:', json.dumps(payload, ensure_ascii=False, indent=2))
    if response.status_code != 200 or not payload.get('sessionId'):
        return 1

    session_id = payload['sessionId']
    for index in range(180):
        status_resp = client.get(f'/api/multi_agent/session/{session_id}/status')
        status_payload = status_resp.get_json() or {}
        if index % 15 == 0:
            print('STATUS:', json.dumps(status_payload, ensure_ascii=False, indent=2))
        if status_payload.get('status') in {'completed', 'failed'}:
            result_resp = client.get(f'/api/multi_agent/session/{session_id}/result')
            result_payload = result_resp.get_json() or {}
            print('RESULT:', json.dumps(result_payload, ensure_ascii=False, indent=2))
            return 0 if status_payload.get('status') == 'completed' else 2
        time.sleep(1)

    print('TIMEOUT: integrated multi-agent session not finished in time')
    return 3


if __name__ == '__main__':
    raise SystemExit(main())
