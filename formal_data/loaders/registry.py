from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from formal_data.loaders.codesearchnet import inspect_codesearchnet
from formal_data.loaders.crosscodeeval import inspect_crosscodeeval
from formal_data.loaders.fea_bench import inspect_fea_bench
from formal_data.loaders.repobench_r import inspect_repobench_r
from formal_data.loaders.repobench_v11 import inspect_repobench_v11
from formal_data.loaders.repoeval import inspect_repoeval
from formal_data.loaders.repoqa import inspect_repoqa
from formal_data.loaders.swe_bench_verified import inspect_swe_bench_verified


INSPECTORS: dict[str, Callable[..., dict[str, Any]]] = {
    "repoqa": inspect_repoqa,
    "codesearchnet": inspect_codesearchnet,
    "repobench_r": inspect_repobench_r,
    "repobench_v11": inspect_repobench_v11,
    "crosscodeeval": inspect_crosscodeeval,
    "repoeval": inspect_repoeval,
    "fea_bench": inspect_fea_bench,
    "swe_bench_verified": inspect_swe_bench_verified,
}


def infer_dataset(path: str | Path) -> str:
    path_obj = Path(path)
    name = path_obj.name.lower()
    full = str(path_obj).replace("\\", "/").lower()
    if "repoqa" in full:
        return "repoqa"
    if "codesearchnet" in full or name.endswith(".zip") and "python" in name:
        return "codesearchnet"
    if "repobench-r" in full or "repobench_r" in full:
        return "repobench_r"
    if "repobench" in full and name.endswith(".parquet"):
        return "repobench_v11"
    if "crosscodeeval" in full:
        return "crosscodeeval"
    if name == "datasets.zip" or "repoeval" in full:
        return "repoeval"
    if "fea" in full:
        return "fea_bench"
    if "swe" in full and "verified" in full:
        return "swe_bench_verified"
    from formal_data.loaders.core import UnsupportedDataError

    raise UnsupportedDataError("cannot infer formal dataset loader", evidence={"path": str(path_obj)})


def inspect_path(path: str | Path, dataset: str | None = None, **kwargs: Any) -> dict[str, Any]:
    dataset_key = dataset or infer_dataset(path)
    inspector = INSPECTORS.get(dataset_key)
    if inspector is None:
        from formal_data.loaders.core import UnsupportedDataError

        raise UnsupportedDataError("unsupported formal dataset loader", evidence={"dataset": dataset_key})
    return inspector(path, **kwargs)
