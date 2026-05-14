import json
import subprocess

from app.services.opencode_kernel_service import run_opencode_kernel


def test_run_opencode_kernel_rejects_non_actionable_structured_output(monkeypatch, tmp_path):
    def _fake_run(command, **kwargs):
        payload = {"analysis_summary": "only summary"}
        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout=json.dumps({"sessionID": "kernel-1", "type": "text", "part": {"text": json.dumps(payload)}}) + "\n",
            stderr="",
        )

    monkeypatch.setenv("FH_OPENCODE_BIN", "opencode")
    monkeypatch.setattr(subprocess, "run", _fake_run)

    result = run_opencode_kernel(
        project_path=str(tmp_path),
        user_query="生成一个 CAT-Net demo 项目",
        task_mode="write_new_code",
        retrieval_bundle={"impacted_files": []},
        advisor_packet={},
        output_protocol={"opencode": {"system_context": {"required_files": ["README.md", "main.py"]}}},
        enabled=True,
    )

    assert result["status"] == "no_actionable_output"
    assert result["accepted"] is False
    assert result["actionable"] is False


def test_run_opencode_kernel_rejects_irrelevant_paths_when_required_files_missing(monkeypatch, tmp_path):
    def _fake_run(command, **kwargs):
        payload = {
            "snippet_blocks": [{"file_path": "app/refactor/plan.py", "language": "python", "reason": "generic", "action": "create_file", "code": "print(1)"}],
            "implementation_targets": [{"file_path": "app/refactor/plan.py", "purpose": "generic", "language": "python", "anchor_targets": []}],
        }
        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout=json.dumps({"sessionID": "kernel-2", "type": "text", "part": {"text": json.dumps(payload)}}) + "\n",
            stderr="",
        )

    monkeypatch.setenv("FH_OPENCODE_BIN", "opencode")
    monkeypatch.setattr(subprocess, "run", _fake_run)

    result = run_opencode_kernel(
        project_path=str(tmp_path),
        user_query="生成一个 CAT-Net demo 项目",
        task_mode="write_new_code",
        retrieval_bundle={"impacted_files": []},
        advisor_packet={},
        output_protocol={"opencode": {"system_context": {"required_files": ["README.md", "infer.py", "tamper_det/config.py"]}}},
        enabled=True,
    )

    assert result["status"] == "rejected_irrelevant_output"
    assert result["accepted"] is False
    assert result["actionable"] is True
    assert result["matched_required_files"] == []


def test_run_opencode_kernel_accepts_actionable_required_files(monkeypatch, tmp_path):
    def _fake_run(command, **kwargs):
        payload = {
            "snippet_blocks": [
                {"file_path": "README.md", "language": "markdown", "reason": "required", "action": "create_file", "code": "# demo"},
                {"file_path": "main.py", "language": "python", "reason": "required", "action": "create_file", "code": "print('demo')"},
            ],
            "implementation_targets": [
                {"file_path": "README.md", "purpose": "required", "language": "markdown", "anchor_targets": []},
                {"file_path": "main.py", "purpose": "required", "language": "python", "anchor_targets": []},
            ],
        }
        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout=json.dumps({"sessionID": "kernel-3", "type": "text", "part": {"text": json.dumps(payload)}}) + "\n",
            stderr="",
        )

    monkeypatch.setenv("FH_OPENCODE_BIN", "opencode")
    monkeypatch.setattr(subprocess, "run", _fake_run)

    result = run_opencode_kernel(
        project_path=str(tmp_path),
        user_query="生成一个 CAT-Net demo 项目",
        task_mode="write_new_code",
        retrieval_bundle={"impacted_files": []},
        advisor_packet={},
        output_protocol={"opencode": {"system_context": {"required_files": ["README.md", "main.py"]}}},
        enabled=True,
    )

    assert result["status"] == "ready"
    assert result["accepted"] is True
    assert result["matched_required_files"] == ["README.md", "main.py"]
