import sys


PROJECT_ROOT = r"D:\代码仓库生图\create_graph"
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


from app import create_app
from app.services import analysis_service as svc
from analysis.code_model import ClassInfo, MethodInfo, Parameter, ProjectAnalysisReport, SourceLocation


def test_api_node_detail_uses_available_method_source_to_populate_cfg_dfg_io(tmp_path, monkeypatch):
    source_file = tmp_path / "demo_method.py"
    source_file.write_text(
        "def compute(value):\n"
        "    doubled = value * 2\n"
        "    return doubled\n",
        encoding="utf-8",
    )

    method = MethodInfo(
        name="compute",
        class_name="DemoService",
        signature="DemoService.compute(value)",
        return_type="int",
        parameters=[Parameter(name="value", param_type="int")],
        source_code=None,
        source_location=SourceLocation(
            file_path=str(source_file),
            line_start=1,
            line_end=3,
        ),
    )
    class_info = ClassInfo(name="DemoService", full_name="DemoService", methods={"compute": method})
    report = ProjectAnalysisReport(
        project_name="demo",
        project_path=str(tmp_path),
        analysis_timestamp="2026-04-24T00:00:00Z",
        classes={class_info.full_name: class_info},
    )

    monkeypatch.setattr(svc, "_resolve_runtime_project_path", lambda project_path: str(tmp_path))
    monkeypatch.setattr(svc, "_resolve_report_cached", lambda project_path: report)
    monkeypatch.setattr(
        svc,
        "_resolve_graph_node_data",
        lambda project_path, entity_id: {
            "type": "method",
            "label": "compute",
            "file": str(source_file),
            "line": 1,
        },
    )

    app = create_app()
    with app.test_request_context("/api/node_detail/DemoService.compute(value)", query_string={"project_path": str(tmp_path)}):
        response = svc.api_node_detail("DemoService.compute(value)")

    if isinstance(response, tuple):
        response = response[0]

    payload = response.get_json()

    assert payload["kind"] == "method"
    assert payload["display_name"] == "compute"
    assert payload["source"]["available"] is True
    assert "doubled = value * 2" in payload["source"]["snippet"]

    assert payload["cfg"], "expected non-empty cfg when a method source snippet is available"
    assert payload["cfg_json"]["nodes"], "expected cfg_json nodes for method with usable source"
    assert payload["dfg"], "expected non-empty dfg when a method source snippet is available"
    assert payload["dfg_json"]["nodes"], "expected dfg_json nodes for method with usable source"
    assert payload["io"]["inputs"], "expected non-empty io inputs when a method source snippet is available"
    assert payload["has_cfg"] is True
    assert payload["has_dfg"] is True
    assert payload["has_io"] is True


def test_api_node_detail_generates_cfg_dfg_io_from_graph_source_snippet_when_report_is_missing(tmp_path, monkeypatch):
    source_file = tmp_path / "graph_only_method.py"
    source_file.write_text(
        "class Entry:\n"
        "    def to_dict(self, value):\n"
        "        cleaned = value.strip()\n"
        "        return {\"value\": cleaned}\n"
        "\n"
        "    @classmethod\n"
        "    def from_dict(cls, payload):\n"
        "        return cls()\n"
        "\n"
        "class Ledger:\n"
        "    pass\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(svc, "_resolve_runtime_project_path", lambda project_path: str(tmp_path))
    monkeypatch.setattr(svc, "_resolve_report_cached", lambda project_path: None)
    monkeypatch.setattr(
        svc,
        "_resolve_graph_node_data",
        lambda project_path, entity_id: {
            "type": "method",
            "label": "to_dict",
            "file": str(source_file),
            "line": 2,
        },
    )

    app = create_app()
    with app.test_request_context("/api/node_detail/method_graph_only", query_string={"project_path": str(tmp_path)}):
        response = svc.api_node_detail("method_graph_only")

    if isinstance(response, tuple):
        response = response[0]

    payload = response.get_json()

    assert payload["kind"] == "method"
    assert payload["display_name"] == "to_dict"
    assert payload["source"]["available"] is True
    assert "cleaned = value.strip()" in payload["source"]["snippet"]
    assert "class Ledger" in payload["source"]["snippet"]

    assert payload["cfg"], "expected non-empty cfg from source snippet fallback when report is missing"
    assert payload["cfg_json"]["nodes"], "expected cfg_json nodes from source snippet fallback when report is missing"
    assert payload["dfg"], "expected non-empty dfg from source snippet fallback when report is missing"
    assert payload["dfg_json"]["nodes"], "expected dfg_json nodes from source snippet fallback when report is missing"
    assert payload["io"]["inputs"], "expected non-empty io inputs from indented source snippet fallback when report is missing"
    assert payload["io"]["outputs"], "expected non-empty io outputs from source snippet fallback when report is missing"
    assert payload["has_cfg"] is True
    assert payload["has_dfg"] is True
    assert payload["has_io"] is True
