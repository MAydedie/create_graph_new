import sys


PROJECT_ROOT = r"D:\代码仓库生图\create_graph"
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


from app.services import analysis_service as svc


def test_build_pipeline_structure_reflects_effective_steps():
    pipeline_builder = getattr(svc, '_build_pipeline_structure')

    execution_profile = {
        'effective_steps': {
            'partition_llm_semantics': True,
            'path_cfg_dfg_io': False,
            'index_rebuild_immediate': False,
            'index_rebuild_deferred': True,
        },
        'step_visibility': {
            'index_rebuild': {'status': 'available_on_demand'},
        },
    }

    pipeline = pipeline_builder(execution_profile)

    heavy_steps = {item['id']: item['enabled'] for item in pipeline['heavy_chain']['steps']}
    assert pipeline['schema_version'] == 'workset7.v1'
    assert pipeline['light_chain']['publish_points'] == [55, 80]
    assert pipeline['heavy_chain']['publish_points'] == [90, 96]
    assert heavy_steps['partition_llm_semantics'] is True
    assert heavy_steps['path_cfg_dfg_io_total'] is False
    assert heavy_steps['index_rebuild'] is True
    assert pipeline['boundary_state']['advanced_visible_default_status'] == 'available_on_demand'


def test_run_partition_llm_semantics_pass_keeps_behavior_without_timeout_degrade(monkeypatch):
    run_partition_pass = getattr(svc, '_run_partition_llm_semantics_pass')
    status_updates = []

    class FakeTiming:
        def __init__(self):
            self.started = []
            self.ended = []

        def start_phase(self, phase_id, **kwargs):
            self.started.append((phase_id, kwargs))

        def end_phase(self, phase_id):
            self.ended.append(phase_id)

    class FakeAgent:
        def enhance_partition_with_llm(self, partition, analyzer_report, project_path):
            partition['name'] = f"{partition.get('name', 'unknown')}_enhanced"
            return partition

    monkeypatch.setattr(svc, 'update_analysis_status', lambda **kwargs: status_updates.append(kwargs))
    monkeypatch.setattr(svc, '_safe_traceback_print', lambda: None)

    timing = FakeTiming()
    layer_states = {}
    degradation_summary = []
    skipped_or_deferred_work = []
    partitions = [{'partition_id': 'p1', 'name': 'partition_one', 'methods': ['a.b']}]

    run_partition_pass(
        timing=timing,
        phase_id='partition_llm_semantics_pass_2',
        update_status_text='步骤6.5.6/7: 对所有分区进行LLM语义分析...',
        pass_title='步骤6.5.6: 对所有分区进行LLM语义分析',
        use_limit=2,
        enable_partition_llm_semantics=True,
        llm_agent_for_partition=FakeAgent(),
        partitions=partitions,
        analyzer_report=None,
        project_path='demo',
        layer_states=layer_states,
        degradation_summary=degradation_summary,
        skipped_or_deferred_work=skipped_or_deferred_work,
        timeout_degrade_stage=None,
        timeout_reason_code=None,
        timeout_user_message_template=None,
        timeout_deferred_section=None,
        disabled_message='disabled',
    )

    assert partitions[0]['name'] == 'partition_one_enhanced'
    assert timing.started and timing.started[0][0] == 'partition_llm_semantics_pass_2'
    assert timing.ended == ['partition_llm_semantics_pass_2']
    assert degradation_summary == []
    assert skipped_or_deferred_work == []
    assert status_updates[0]['status'] == '步骤6.5.6/7: 对所有分区进行LLM语义分析...'
