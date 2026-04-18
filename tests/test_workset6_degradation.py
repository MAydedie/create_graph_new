import os
import sys


PROJECT_ROOT = r"D:\代码仓库生图\create_graph"
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


from app.services.analysis_service import _record_layer_degradation


def test_record_layer_degradation_deduplicates_identical_events():
    layer_states = {}
    degradation_summary = []
    skipped_or_deferred_work = []

    kwargs = {
        'layer': 'advanced_visible',
        'stage': 'path_cfg_dfg_io_total',
        'reason_code': 'path_deep_analysis_timeout',
        'status_after_degrade': 'available_on_demand',
        'timeout_seconds': 0.5,
        'user_message': 'timeout happened',
        'retry_mode': 'on_demand',
        'deferred_section': 'path_analysis',
    }

    _record_layer_degradation(layer_states, degradation_summary, skipped_or_deferred_work, **kwargs)
    _record_layer_degradation(layer_states, degradation_summary, skipped_or_deferred_work, **kwargs)

    assert layer_states['advanced_visible']['degraded'] is True
    assert layer_states['advanced_visible']['degradation_codes'] == ['path_deep_analysis_timeout']
    assert layer_states['advanced_visible']['deferred_sections'] == ['path_analysis']
    assert len(degradation_summary) == 1
    assert len(skipped_or_deferred_work) == 1
