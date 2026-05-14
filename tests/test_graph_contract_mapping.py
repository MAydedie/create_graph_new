from app.services.analysis_service import _map_gn_node_label, _map_gn_relationship_type


def test_graph_node_mapping_covers_residual_entity_types():
    assert _map_gn_node_label('decorator') == 'Decorator'
    assert _map_gn_node_label('parameter') == 'Variable'
    assert _map_gn_node_label('return_value') == 'Variable'
    assert _map_gn_node_label('repository') == 'Project'
    assert _map_gn_node_label('import') == 'Import'


def test_graph_relationship_mapping_preserves_implements_aliases():
    assert _map_gn_relationship_type('implements') == 'IMPLEMENTS'
    assert _map_gn_relationship_type('class_implements_interface') == 'IMPLEMENTS'
