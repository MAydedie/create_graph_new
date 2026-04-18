#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Phase 1 / Task 1.1 - 路径覆盖率验证脚本

用途：
- 给定一个项目路径，运行一次功能层级分析（使用现有 analyze_function_hierarchy）
- 从分析结果里抽取每个分区的 path_analyses
- 用“已知功能路径”用例做覆盖率粗验（是否存在“包含这些方法片段”的路径）

说明：
- 这是一个“验证脚本”，不是严格单元测试；不会改变任何业务逻辑。
- 运行方式示例：
    python tests/test_path_coverage.py --project-path D:\\path\\to\\repo
"""

import argparse
import os
from typing import List, Dict, Any


def _normalize_sig(sig: str) -> str:
    return (sig or "").strip()


def _path_contains_subsequence(path: List[str], expected: List[str]) -> bool:
    """检查 path 是否按顺序包含 expected（可跳跃）。"""
    if not expected:
        return True
    i = 0
    for node in path:
        if _normalize_sig(node) == _normalize_sig(expected[i]):
            i += 1
            if i >= len(expected):
                return True
    return False


def _extract_all_paths(result: Dict[str, Any]) -> List[List[str]]:
    all_paths: List[List[str]] = []
    partition_analyses = result.get("partition_analyses", {}) if isinstance(result, dict) else {}
    for _, p in partition_analyses.items():
        for pa in p.get("path_analyses", []) or []:
            path = pa.get("path") or pa.get("function_chain") or []
            if isinstance(path, list) and path:
                all_paths.append(path)
    return all_paths


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-path", required=True, help="待分析项目路径")
    args = parser.parse_args()

    project_path = os.path.normpath(args.project_path)
    if not os.path.isdir(project_path):
        raise SystemExit(f"Invalid project path: {project_path}")

    # NOTE: 直接复用当前系统的分析函数
    from app.services.analysis_service import analyze_function_hierarchy, data_accessor

    analyze_function_hierarchy(project_path)
    cached = data_accessor.get_function_hierarchy(project_path)
    if not cached:
        raise SystemExit("No function hierarchy result found in cache after analysis.")

    all_paths = _extract_all_paths(cached)
    print(f"[test_path_coverage] total_paths={len(all_paths)}")

    # 你可以在这里补充“已知功能路径”的断言用例（例子：登录/鉴权/解析等）
    # 格式：按顺序出现即可（允许中间夹杂其它节点）
    known_cases = [
        # 示例（请按实际项目方法签名替换）：
        # {"name": "OAuth登录", "expected_subsequence": ["Auth.login", "OAuth.exchange_token", "User.load"]},
    ]

    if not known_cases:
        print("[test_path_coverage] No known_cases configured; script finished.")
        return

    hit = 0
    for case in known_cases:
        expected = case.get("expected_subsequence") or []
        ok = any(_path_contains_subsequence(p, expected) for p in all_paths)
        print(f"[test_path_coverage] {case.get('name','unknown')}: {'OK' if ok else 'MISS'}")
        hit += int(ok)

    print(f"[test_path_coverage] coverage={hit}/{len(known_cases)}")


if __name__ == "__main__":
    main()






