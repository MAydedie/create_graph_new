#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import copy
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services import multi_agent_service as mas


@dataclass
class Scenario:
    name: str
    query: str
    task_mode: str
    expected: str


SCENARIOS = [
    Scenario('business_locator_endpoint', 'conversation session status result 接口在哪里', 'modify_existing', 'unchanged'),
    Scenario('business_codegen_architecture', '我要重构 multi_agent_service 的 advisor 调用策略，并保持 opencode 主流程稳定，给出可执行修改方案与验证命令', 'modify_existing', 'improved'),
]


def _now_text() -> str:
    return datetime.now().strftime('%Y%m%d_%H%M%S')


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _norm(value: Any) -> str:
    return str(value or '').strip()


def _simulate_old_chain_node_details(project_path: str, selected_path: dict[str, Any], fallback_details: list[dict[str, Any]]) -> list[dict[str, Any]]:
    details: list[dict[str, Any]] = []
    seen: set[str] = set()
    chain = _as_list(selected_path.get('function_chain')) or _as_list(selected_path.get('path'))
    for symbol in chain[:5]:
        if not isinstance(symbol, str) or not symbol.strip() or symbol in seen:
            continue
        seen.add(symbol)
        detail = mas._build_node_detail_payload(project_path, symbol)
        if isinstance(detail, dict):
            details.append(detail)
    return details if details else [item for item in fallback_details if isinstance(item, dict)]


def _build_control_bundle(project_path: str, retrieval_bundle: dict[str, Any]) -> dict[str, Any]:
    control = copy.deepcopy(retrieval_bundle)
    selected_path = _as_dict(control.get('selected_path'))
    fallback_details = [item for item in _as_list(control.get('node_details')) if isinstance(item, dict)]
    old_chain = _simulate_old_chain_node_details(project_path, selected_path, fallback_details)
    control['chain_node_details'] = old_chain
    control['node_details'] = old_chain
    control['advisor_packet'] = mas._build_disabled_advisor_packet()
    return control


def _build_treatment_advisor(project_path: str, query: str, retrieval_bundle: dict[str, Any], task_mode: str) -> dict[str, Any]:
    invoke, reason, signals = mas._should_invoke_advisor(query, task_mode, retrieval_bundle)
    if not invoke:
        packet = mas._build_skipped_advisor_packet(reason, signals)
        packet['invocation'] = {'decision': 'skipped', 'reason': reason, 'signals': signals}
        return packet

    runtime_payloads = mas._read_advisor_runtime_payloads()
    if isinstance(runtime_payloads.get('step2'), dict) and runtime_payloads.get('step2'):
        packet = mas._build_advisor_packet_from_runtime(runtime_payloads, query, project_path, mode='cached_runtime')
    else:
        packet = mas._run_advisor_sidecar(project_path, query, retrieval_bundle)
    packet = dict(packet) if isinstance(packet, dict) else {}
    packet['invocation'] = {'decision': 'invoked', 'reason': reason, 'signals': signals}
    return packet


def _parse_system_context_lines(system_context: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in str(system_context or '').splitlines():
        if '=' not in line:
            continue
        key, value = line.split('=', 1)
        result[key.strip()] = value.strip()
    return result


def _quality_metrics(solution_packet: dict[str, Any], retrieval_bundle: dict[str, Any]) -> dict[str, Any]:
    output_protocol = _as_dict(solution_packet.get('output_protocol'))
    opencode_payload = _as_dict(output_protocol.get('opencode'))
    advisor_payload = _as_dict(output_protocol.get('advisor'))

    system_context = _norm(opencode_payload.get('system_context'))
    ctx_map = _parse_system_context_lines(system_context)

    preferred_files = [item for item in _as_list(opencode_payload.get('preferred_files')) if _norm(item)]
    preferred_symbols = [item for item in _as_list(opencode_payload.get('preferred_symbols')) if _norm(item)]

    chain_refs = [item.strip() for item in _norm(ctx_map.get('chain_source_refs')).split('|') if item.strip()]
    chain_expls = [item.strip() for item in _norm(ctx_map.get('chain_explanations')).split('|') if item.strip()]
    advisor_how = _norm(ctx_map.get('advisor_how'))
    constraint_types = [item.strip() for item in _norm(ctx_map.get('advisor_constraint_types')).split(',') if item.strip()]

    snippet_blocks = [item for item in _as_list(solution_packet.get('snippet_blocks')) if isinstance(item, dict)]
    anchored_snippets = 0
    for item in snippet_blocks:
        if _norm(item.get('file_path')) and _norm(item.get('file_path')) != '待定位' and _norm(item.get('anchor')):
            anchored_snippets += 1

    anchor_ratio = round(anchored_snippets / float(len(snippet_blocks)), 4) if snippet_blocks else 0.0

    chain_node_details = [item for item in _as_list(retrieval_bundle.get('chain_node_details')) if isinstance(item, dict)]
    structured_chain_nodes = sum(
        1
        for item in chain_node_details
        if isinstance(item.get('step_index'), int) and _norm(item.get('chain_role')) and _norm(item.get('call_explanation'))
    )
    structured_chain_ratio = round(structured_chain_nodes / float(len(chain_node_details)), 4) if chain_node_details else 0.0

    context_score = (
        len(preferred_files)
        + len(preferred_symbols)
        + 2 * len(chain_refs)
        + 1 * len(chain_expls)
        + (3 if advisor_how else 0)
        + 2 * len(constraint_types)
        + 2 * structured_chain_ratio
        + 1 * anchor_ratio
    )

    return {
        'opencode_status': _norm(_as_dict(solution_packet.get('opencode_kernel')).get('status')),
        'advisor_status': _norm(advisor_payload.get('status')),
        'system_context_len': len(system_context),
        'preferred_files_count': len(preferred_files),
        'preferred_symbols_count': len(preferred_symbols),
        'chain_source_refs_count': len(chain_refs),
        'chain_explanations_count': len(chain_expls),
        'advisor_how_present': bool(advisor_how),
        'constraint_types_count': len(constraint_types),
        'snippet_block_count': len(snippet_blocks),
        'anchored_snippet_ratio': anchor_ratio,
        'structured_chain_ratio': structured_chain_ratio,
        'generation_context_score': round(float(context_score), 4),
    }


def _scenario_verdict(control_score: float, treatment_score: float) -> str:
    delta = treatment_score - control_score
    if delta > 0.5:
        return 'improved'
    if delta < -0.5:
        return 'worse'
    return 'unchanged'


def run_compare(project_path: str, report_dir: str) -> dict[str, Any]:
    project = str(Path(project_path).resolve())
    root = Path(report_dir)
    root.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    improved = unchanged = worse = 0

    for scenario in SCENARIOS:
        treatment_bundle = mas._build_retrieval_bundle(project, scenario.query)
        treatment_bundle = copy.deepcopy(treatment_bundle)
        treatment_bundle['advisor_packet'] = _build_treatment_advisor(project, scenario.query, treatment_bundle, scenario.task_mode)

        control_bundle = _build_control_bundle(project, treatment_bundle)

        control_solution = mas._build_solution_packet(
            project_path=project,
            user_query=scenario.query,
            task_mode=scenario.task_mode,
            retrieval_bundle=control_bundle,
            intent_packet=None,
            evidence_verdict={'approved': True, 'reasons': ['benchmark_force_approve']},
            opencode_enabled=False,
        )
        treatment_solution = mas._build_solution_packet(
            project_path=project,
            user_query=scenario.query,
            task_mode=scenario.task_mode,
            retrieval_bundle=treatment_bundle,
            intent_packet=None,
            evidence_verdict={'approved': True, 'reasons': ['benchmark_force_approve']},
            opencode_enabled=False,
        )

        control_metrics = _quality_metrics(control_solution, control_bundle)
        treatment_metrics = _quality_metrics(treatment_solution, treatment_bundle)
        verdict = _scenario_verdict(control_metrics['generation_context_score'], treatment_metrics['generation_context_score'])

        if verdict == 'improved':
            improved += 1
        elif verdict == 'worse':
            worse += 1
        else:
            unchanged += 1

        rows.append({
            'name': scenario.name,
            'query': scenario.query,
            'expected': scenario.expected,
            'verdict': verdict,
            'score_delta': round(treatment_metrics['generation_context_score'] - control_metrics['generation_context_score'], 4),
            'control': control_metrics,
            'treatment': treatment_metrics,
        })


    summary = {
        'scenario_count': len(rows),
        'improved_count': improved,
        'unchanged_count': unchanged,
        'worse_count': worse,
        'rows': [{'name': item['name'], 'expected': item['expected'], 'verdict': item['verdict'], 'score_delta': item['score_delta']} for item in rows],
    }

    payload = {
        'generated_at': datetime.utcnow().isoformat() + 'Z',
        'project_path': project,
        'summary': summary,
        'scenarios': rows,
    }

    stamp = _now_text()
    json_path = root / f'two_task_opencode_compare_{stamp}.json'
    md_path = root / f'two_task_opencode_compare_{stamp}.md'
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')

    lines = [
        '# 两题业务对比（之前 opencode vs 嵌入后）',
        '',
        f"- 生成时间: {payload['generated_at']}",
        f"- 项目路径: `{project}`",
        f"- 题目数: {summary['scenario_count']}",
        f"- improved: {summary['improved_count']}, unchanged: {summary['unchanged_count']}, worse: {summary['worse_count']}",
        '',
        '| 题目 | 期望 | 结果 | 分数变化 |',
        '|---|---|---|---:|',
    ]
    for item in rows:
        lines.append(f"| {item['name']} | {item['expected']} | {item['verdict']} | {item['score_delta']:+.4f} |")
    md_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    artifacts = {'json_path': str(json_path), 'markdown_path': str(md_path)}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps(artifacts, ensure_ascii=False, indent=2))
    return {'payload': payload, 'artifacts': artifacts}


def main() -> None:
    parser = argparse.ArgumentParser(description='Compare two business tasks between baseline and advisor-embedded flow')
    parser.add_argument('--project-path', default=r'D:\代码仓库生图\create_graph')
    parser.add_argument('--report-dir', default=r'D:\代码仓库生图\create_graph\benchmark_reports\two_task_compare')
    args = parser.parse_args()
    run_compare(args.project_path, args.report_dir)


if __name__ == '__main__':
    main()
