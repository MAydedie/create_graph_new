from app import create_app


def test_process_contract_endpoints_expose_steps():
    client = create_app().test_client()

    processes_response = client.get('/api/processes')
    assert processes_response.status_code == 200
    processes_payload = processes_response.get_json()
    processes = processes_payload.get('processes') or []
    assert processes, 'expected process list from /api/processes'

    process_with_steps = next((item for item in processes if (item.get('stepCount') or 0) > 0 and len(item.get('steps') or []) > 0), None)
    assert process_with_steps is not None, 'expected at least one process with non-empty steps'

    process_name = process_with_steps.get('process_id') or process_with_steps.get('entry') or process_with_steps.get('entry_node_id')
    detail_response = client.get(f'/api/process?name={process_name}')
    assert detail_response.status_code == 200
    detail_payload = detail_response.get_json()
    assert detail_payload.get('stepCount', 0) > 0
    assert len(detail_payload.get('steps') or []) > 0


def test_graph_step_relationships_have_connectivity_fields():
    client = create_app().test_client()

    graph_response = client.get('/api/graph')
    assert graph_response.status_code == 200
    graph_payload = graph_response.get_json()
    relationships = graph_payload.get('relationships') or []
    step_relationship = next((item for item in relationships if item.get('type') == 'STEP_IN_PROCESS'), None)

    assert step_relationship is not None, 'expected STEP_IN_PROCESS relationship in graph payload'
    assert step_relationship.get('sourceId')
    assert step_relationship.get('targetId')


def test_process_contract_falls_back_to_graph_when_shadow_missing(monkeypatch):
    from app.services import analysis_service as svc

    graph_data = {
        'nodes': [
            {'data': {'id': 'process-cold', 'type': 'process', 'label': 'Cold Start Process', 'processType': 'intra_community', 'stepCount': 0}},
            {'data': {'id': 'step-a', 'type': 'method', 'label': 'alpha', 'file': 'src/a.py'}},
            {'data': {'id': 'step-b', 'type': 'method', 'label': 'beta', 'file': 'src/b.py'}},
        ],
        'edges': [
            {'data': {'id': 'edge-a', 'source': 'step-a', 'target': 'process-cold', 'relation': 'step_in_process', 'step': 1}},
            {'data': {'id': 'edge-b', 'source': 'step-b', 'target': 'process-cold', 'relation': 'step_in_process', 'step': 2}},
        ],
    }

    monkeypatch.setattr(svc, '_resolve_process_shadow_payload', lambda project_path: None)
    monkeypatch.setattr(svc, '_resolve_graph_data_for_project', lambda project_path, allow_global_fallback=True: graph_data)

    client = create_app().test_client()
    response = client.get('/api/processes')
    assert response.status_code == 200
    payload = response.get_json()
    process = payload['processes'][0]
    assert process['stepCount'] == 2
    assert len(process['steps']) == 2
    assert process['steps'][0]['id'] == 'step-a'
