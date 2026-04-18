from __future__ import annotations

import difflib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR.parent) not in sys.path:
    sys.path.insert(0, str(BASE_DIR.parent))

from advisor_consultant_lab import common as c
from advisor_consultant_lab import config as cfg

try:
    from app.services.opencode_kernel_service import run_opencode_kernel as _run_opencode_kernel_service
except Exception:
    _run_opencode_kernel_service = None


as_str = c.as_str
as_str_list = c.as_str_list
append_jsonl = c.append_jsonl
ensure_runtime = c.ensure_runtime
read_json = c.read_json
utc_now = c.utc_now
write_json = c.write_json
write_text = c.write_text

RUNTIME_DIR = cfg.RUNTIME_DIR
STEP1_MATCH_RESULT_FILE = cfg.STEP1_MATCH_RESULT_FILE
STEP2_ANALYSIS_JSON_FILE = cfg.STEP2_ANALYSIS_JSON_FILE
STEP3_DESIGN_JSON_FILE = cfg.STEP3_DESIGN_JSON_FILE
STEP4_CODEGEN_JSON_FILE = cfg.STEP4_CODEGEN_JSON_FILE
STEP4_CODEGEN_MD_FILE = cfg.STEP4_CODEGEN_MD_FILE
STEP4_CODEGEN_PROCESS_FILE = cfg.STEP4_CODEGEN_PROCESS_FILE
STAGE_TRACE_FILE = cfg.STAGE_TRACE_FILE


def _select_advisors_for_codegen(match_payload: dict[str, Any], analysis_payload: dict[str, Any]) -> list[dict[str, Any]]:
    advisors = [item for item in (match_payload.get("matched_advisors") or []) if isinstance(item, dict)]
    if not advisors:
        return []

    analysis_result_raw = analysis_payload.get("analysis_result")
    analysis_result: dict[str, Any] = analysis_result_raw if isinstance(analysis_result_raw, dict) else {}
    followup_ids = as_str_list(analysis_result.get("selected_advisors_for_followup_ids"))

    selected: list[dict[str, Any]] = []
    if followup_ids:
        advisor_map = {as_str(item.get("advisor_id")): item for item in advisors if as_str(item.get("advisor_id"))}
        for advisor_id in followup_ids:
            advisor = advisor_map.get(advisor_id)
            if isinstance(advisor, dict):
                selected.append(advisor)

    if not selected:
        selected = advisors

    query_profile_raw = match_payload.get("query_profile")
    query_profile: dict[str, Any] = query_profile_raw if isinstance(query_profile_raw, dict) else {}
    scope = as_str(query_profile.get("scope")) or "mixed"
    if scope == "broad":
        max_count = 14
    elif scope == "specific":
        max_count = 6
    else:
        max_count = 10
    return selected[:max_count]


def _build_source_targets(match_payload: dict[str, Any], analysis_payload: dict[str, Any]) -> list[dict[str, Any]]:
    advisors = _select_advisors_for_codegen(match_payload, analysis_payload)
    targets: list[dict[str, Any]] = []

    for advisor in advisors:
        source_locations = advisor.get("source_locations") or []
        file_refs: list[str] = []
        for item in source_locations:
            if not isinstance(item, dict):
                continue
            file_path = as_str(item.get("file_path"))
            line = item.get("line")
            symbol = as_str(item.get("symbol"))
            if file_path and isinstance(line, int):
                file_refs.append(f"{file_path}:{line}")
            elif file_path:
                file_refs.append(file_path)
            elif symbol:
                file_refs.append(symbol)

        if not file_refs:
            file_refs = as_str_list(advisor.get("code_refs"))[:8]

        targets.append(
            {
                "advisor_id": as_str(advisor.get("advisor_id")),
                "advisor_name": as_str(advisor.get("advisor_name")),
                "project_name": as_str(advisor.get("project_name")),
                "project_path": as_str(advisor.get("project_path")),
                "source_targets": as_str_list(file_refs)[:12],
            }
        )

    if targets:
        return targets

    analysis_result_raw = analysis_payload.get("analysis_result")
    analysis_result: dict[str, Any] = analysis_result_raw if isinstance(analysis_result_raw, dict) else {}
    fallback_targets = as_str_list(analysis_result.get("key_code_refs"))
    fallback_targets.extend(as_str_list(analysis_result.get("key_call_chain")))
    fallback_targets = as_str_list(fallback_targets)[:12]
    if fallback_targets:
        return [
            {
                "advisor_id": "analysis_context",
                "advisor_name": "analysis_context",
                "project_name": as_str(match_payload.get("project_name")) or "unknown_project",
                "project_path": "",
                "source_targets": fallback_targets,
            }
        ]

    return []


def _flatten_source_targets(source_targets: list[dict[str, Any]]) -> list[str]:
    all_targets: list[str] = []
    for item in source_targets:
        if not isinstance(item, dict):
            continue
        all_targets.extend(as_str_list(item.get("source_targets")))
    return as_str_list(all_targets)


def _detect_codegen_profile(requirement: str) -> dict[str, Any]:
    text = as_str(requirement)

    def hit(words: list[str]) -> bool:
        return any(word in text for word in words)

    if hit(["不做代码改动", "只分析", "只说明"]):
        return {"mode": "design_only", "scenario": "analysis_only"}

    if hit(["字段", "写入失败", "更新失败", "事务", "rollback", "commit", "接口返回成功但没写入"]):
        return {"mode": "patch_level_code", "scenario": "data_write_bugfix"}

    if hit(["可解释", "中间特征", "可视化", "heatmap"]):
        return {"mode": "file_level_code", "scenario": "explainability_extension"}

    if hit(["多数据集", "统一训练", "公共评估", "输入格式"]):
        return {"mode": "file_level_code", "scenario": "multi_dataset_refactor"}

    if hit(["模块化配置", "约束校验", "CFG", "DFG", "校验机制"]):
        return {"mode": "file_level_code", "scenario": "config_validation"}

    if hit(["推理服务化", "批量推理", "错误回退", "日志追踪", "service"]):
        return {"mode": "file_level_code", "scenario": "inference_serviceization"}

    if hit(["创建", "新项目", "最小可运行架构"]):
        return {"mode": "file_level_code", "scenario": "new_project_bootstrap"}

    return {"mode": "file_level_code", "scenario": "generic_refactor"}


def _block(file_path: str, purpose: str, code: str, language: str = "") -> dict[str, Any]:
    normalized_path = as_str(file_path).lower()
    normalized_language = as_str(language)
    if not normalized_language:
        if normalized_path.endswith(".md"):
            normalized_language = "markdown"
        elif normalized_path.endswith(".txt"):
            normalized_language = "text"
        elif normalized_path.endswith(".json"):
            normalized_language = "json"
        elif normalized_path.endswith(".yml") or normalized_path.endswith(".yaml"):
            normalized_language = "yaml"
        else:
            normalized_language = "python"
    return {
        "file_path": file_path,
        "language": normalized_language,
        "purpose": purpose,
        "code": code.strip("\n") + "\n",
    }


def _normalize_patch_path(file_path: str) -> str:
    normalized = as_str(file_path).replace("\\", "/")
    return normalized.lstrip("/")


def _code_to_plus_lines(code: str) -> str:
    lines = as_str(code).splitlines()
    if not lines:
        return "+\n"
    return "\n".join([f"+{line}" for line in lines]) + "\n"


def _build_unified_diff_patch(file_path: str, code: str, *, mode: str) -> str:
    normalized_path = _normalize_patch_path(file_path)
    line_count = max(len(as_str(code).splitlines()), 1)
    header = f"--- a/{normalized_path}\n+++ b/{normalized_path}\n"
    if mode == "patch_level_code":
        hunk = "@@ -1,1 +1," + str(line_count) + " @@\n"
    else:
        hunk = "@@ -0,0 +1," + str(line_count) + " @@\n"
    return header + hunk + _code_to_plus_lines(code)


def _build_unified_diff_patch_from_baseline(file_path: str, before_code: str, after_code: str) -> str:
    normalized_path = _normalize_patch_path(file_path)
    before_lines = as_str(before_code).splitlines()
    after_lines = as_str(after_code).splitlines()
    diff_lines = list(
        difflib.unified_diff(
            before_lines,
            after_lines,
            fromfile=f"a/{normalized_path}",
            tofile=f"b/{normalized_path}",
            lineterm="",
        )
    )
    if not diff_lines:
        return _build_unified_diff_patch(file_path, after_code, mode="patch_level_code")
    return "\n".join(diff_lines) + "\n"


def _build_apply_patch_snippet(file_path: str, code: str) -> str:
    normalized_path = _normalize_patch_path(file_path)
    plus_lines = _code_to_plus_lines(code)
    return "*** Begin Patch\n" + f"*** Add File: {normalized_path}\n" + plus_lines + "*** End Patch\n"


def _build_apply_patch_snippet_for_update(file_path: str, code: str) -> str:
    normalized_path = _normalize_patch_path(file_path)
    plus_lines = _code_to_plus_lines(code)
    return (
        "*** Begin Patch\n"
        + f"*** Delete File: {normalized_path}\n"
        + f"*** Add File: {normalized_path}\n"
        + plus_lines
        + "*** End Patch\n"
    )


def _resolve_target_repo_root(source_targets: list[dict[str, Any]]) -> Path:
    for item in source_targets:
        if not isinstance(item, dict):
            continue
        project_path = as_str(item.get("project_path"))
        if not project_path:
            continue
        candidate = Path(project_path)
        if candidate.exists() and candidate.is_dir():
            return candidate
    return BASE_DIR.parent


def _build_patch_blocks(code_blocks: list[dict[str, Any]], *, mode: str, target_repo_root: Path) -> list[dict[str, Any]]:
    patch_blocks: list[dict[str, Any]] = []
    for block in code_blocks:
        file_path = as_str(block.get("file_path"))
        code = as_str(block.get("code"))
        if not file_path or not code:
            continue

        normalized_path = _normalize_patch_path(file_path)
        absolute_path = (target_repo_root / normalized_path).resolve()
        base_exists = absolute_path.exists() and absolute_path.is_file()

        patch_text = _build_unified_diff_patch(file_path, code, mode=mode)
        apply_patch_snippet = _build_apply_patch_snippet(file_path, code)
        operation = "add_candidate"
        apply_strategy = "apply_add_file"
        is_apply_ready = True

        if base_exists:
            operation = "modify_candidate"
            try:
                before_code = absolute_path.read_text(encoding="utf-8")
                patch_text = _build_unified_diff_patch_from_baseline(file_path, before_code, code)
                apply_patch_snippet = _build_apply_patch_snippet_for_update(file_path, code)
                apply_strategy = "apply_replace_file"
                is_apply_ready = True
            except Exception:
                apply_strategy = "proposal_only"
                is_apply_ready = False

        patch_blocks.append(
            {
                "artifact_id": f"patch::{normalized_path}",
                "file_path": file_path,
                "base_file_path": file_path,
                "base_file_resolved": str(absolute_path),
                "base_exists": base_exists,
                "patch_mode": mode,
                "patch_type": "unified_diff_proposal",
                "target_operation": operation,
                "diff_format": "unified_diff",
                "apply_strategy": apply_strategy,
                "is_apply_ready": is_apply_ready,
                "summary": f"{operation} for {file_path}",
                "hunk_count": patch_text.count("@@"),
                "patch_text": patch_text,
                "apply_patch_snippet": apply_patch_snippet,
            }
        )
    return patch_blocks


def _generate_blocks_for_scenario(
    scenario: str,
    source_anchor_targets: list[str],
    constraint_types: list[str],
) -> list[dict[str, Any]]:
    anchors_literal = repr(source_anchor_targets[:8])
    constraints_literal = repr(constraint_types)

    if scenario == "new_project_bootstrap":
        return [
            _block(
                "tamper_det/__init__.py",
                "导出分割基线配置接口",
                """
from tamper_det.config import ExperimentConfig, get_default_config

__all__ = ["ExperimentConfig", "get_default_config"]
""",
            ),
            _block(
                "tamper_det/config.py",
                "统一项目配置与设备解析",
                """
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
import json

import torch


@dataclass
class DataConfig:
    root_dir: str = "data/CASIA"
    train_split: str = "train"
    val_split: str = "val"
    image_size: int = 256
    batch_size: int = 4
    num_workers: int = 0
    pin_memory: bool = False


@dataclass
class ModelConfig:
    in_channels: int = 3
    base_channels: int = 32
    dropout: float = 0.1


@dataclass
class TrainConfig:
    epochs: int = 20
    learning_rate: float = 3e-4
    weight_decay: float = 1e-4
    threshold: float = 0.5
    log_interval: int = 10
    seed: int = 42
    output_dir: str = "outputs"
    checkpoint_name: str = "best_model.pt"


@dataclass
class InferConfig:
    checkpoint_path: str = "outputs/best_model.pt"
    threshold: float = 0.5
    output_path: str = "prediction_mask.png"


@dataclass
class ExperimentConfig:
    data: DataConfig = field(default_factory=DataConfig)
    model: ModelConfig = field(default_factory=ModelConfig)
    train: TrainConfig = field(default_factory=TrainConfig)
    infer: InferConfig = field(default_factory=InferConfig)

    @property
    def checkpoint_path(self) -> Path:
        return Path(self.train.output_dir) / self.train.checkpoint_name


def get_default_config() -> ExperimentConfig:
    return ExperimentConfig()


def save_config(config: ExperimentConfig, path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(asdict(config), indent=2, ensure_ascii=False), encoding="utf-8")


def resolve_device() -> torch.device:
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")
""",
            ),
            _block(
                "tamper_det/data/__init__.py",
                "导出数据集接口",
                """
from tamper_det.data.base_dataset import BaseSegmentationDataset, SampleRecord
from tamper_det.data.casia_dataset import CASIADataset, build_casia_records

__all__ = [
    "BaseSegmentationDataset",
    "SampleRecord",
    "CASIADataset",
    "build_casia_records",
]
""",
            ),
            _block(
                "tamper_det/data/base_dataset.py",
                "定义图像与掩码分割数据基类",
                """
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch
from PIL import Image
from PIL.Image import Resampling
from torch.utils.data import Dataset


@dataclass(frozen=True)
class SampleRecord:
    image_path: Path
    mask_path: Path | None = None


class BaseSegmentationDataset(Dataset):
    def __init__(self, records: list[SampleRecord], image_size: int = 256) -> None:
        self.records = list(records)
        self.image_size = image_size

    def __len__(self) -> int:
        return len(self.records)

    def __getitem__(self, index: int) -> dict[str, torch.Tensor | str]:
        record = self.records[index]
        image = self._load_image(record.image_path)
        mask = self._load_mask(record.mask_path)
        return {
            "image": image,
            "mask": mask,
            "image_path": str(record.image_path),
            "mask_path": str(record.mask_path) if record.mask_path else "",
        }

    def _load_image(self, path: Path) -> torch.Tensor:
        if not path.exists():
            base = torch.linspace(0.0, 1.0, steps=self.image_size, dtype=torch.float32)
            grid_y, grid_x = torch.meshgrid(base, base, indexing="ij")
            synthetic = torch.stack([grid_x, grid_y, (grid_x + grid_y) * 0.5], dim=0)
            return synthetic
        image = Image.open(path).convert("RGB")
        image = image.resize((self.image_size, self.image_size), resample=Resampling.BILINEAR)
        image_array = np.asarray(image, dtype=np.float32) / 255.0
        tensor = torch.from_numpy(image_array).permute(2, 0, 1)
        return tensor

    def _load_mask(self, path: Path | None) -> torch.Tensor:
        if path is None or not path.exists():
            return torch.zeros((1, self.image_size, self.image_size), dtype=torch.float32)
        mask = Image.open(path).convert("L")
        mask = mask.resize((self.image_size, self.image_size), resample=Resampling.NEAREST)
        mask_array = (np.asarray(mask, dtype=np.float32) > 0).astype(np.float32)
        return torch.from_numpy(mask_array).unsqueeze(0)
""",
            ),
            _block(
                "tamper_det/data/casia_dataset.py",
                "实现 CASIA 风格图像与掩码配对逻辑",
                """
from __future__ import annotations

from pathlib import Path

from tamper_det.data.base_dataset import BaseSegmentationDataset, SampleRecord


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}


def _first_existing(paths: list[Path]) -> Path | None:
    for path in paths:
        if path.exists() and path.is_dir():
            return path
    return None


def _sample_key(path: Path) -> str:
    key = path.stem.lower()
    for suffix in ("_gt", "_mask", "-gt", "-mask"):
        if key.endswith(suffix):
            key = key[: -len(suffix)]
    return key


def build_casia_records(root_dir: str | Path, split: str) -> list[SampleRecord]:
    root = Path(root_dir)

    def _synthetic_records() -> list[SampleRecord]:
        return [
            SampleRecord(image_path=root / split / "synthetic" / f"sample_{index:03d}.png", mask_path=None)
            for index in range(16)
        ]

    image_dir = _first_existing(
        [
            root / split / "images",
            root / "images" / split,
            root / split / "Tp",
            root / "Tp" / split,
        ]
    )
    mask_dir = _first_existing(
        [
            root / split / "masks",
            root / "masks" / split,
            root / split / "Gt",
            root / "Gt" / split,
        ]
    )
    if image_dir is None:
        return _synthetic_records()

    mask_index: dict[str, Path] = {}
    if mask_dir is not None:
        for mask_path in sorted(mask_dir.iterdir()):
            if mask_path.suffix.lower() in IMAGE_SUFFIXES:
                mask_index[_sample_key(mask_path)] = mask_path

    records: list[SampleRecord] = []
    for image_path in sorted(image_dir.iterdir()):
        if image_path.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        records.append(SampleRecord(image_path=image_path, mask_path=mask_index.get(_sample_key(image_path))))
    if not records:
        return _synthetic_records()
    return records


class CASIADataset(BaseSegmentationDataset):
    def __init__(self, root_dir: str | Path, split: str, image_size: int = 256) -> None:
        records = build_casia_records(root_dir, split)
        super().__init__(records=records, image_size=image_size)
""",
            ),
            _block(
                "tamper_det/models/__init__.py",
                "导出编码器与分割模型接口",
                """
from tamper_det.models.backbone import Encoder
from tamper_det.models.model import TamperSegmentationModel
from tamper_det.models.seg_head import SegmentationHead

__all__ = ["Encoder", "SegmentationHead", "TamperSegmentationModel"]
""",
            ),
            _block(
                "tamper_det/models/backbone.py",
                "实现轻量级 U-Net 风格编码器",
                """
import torch
import torch.nn as nn


class ConvBlock(nn.Module):
    def __init__(self, in_channels: int, out_channels: int) -> None:
        super().__init__()
        self.layers = nn.Sequential(
            nn.Conv2d(in_channels, out_channels, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
            nn.Conv2d(out_channels, out_channels, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
        )

    def forward(self, inputs: torch.Tensor) -> torch.Tensor:
        return self.layers(inputs)


class Encoder(nn.Module):
    def __init__(self, in_channels: int = 3, base_channels: int = 32) -> None:
        super().__init__()
        self.stem = ConvBlock(in_channels, base_channels)
        self.pool1 = nn.MaxPool2d(kernel_size=2, stride=2)
        self.down1 = ConvBlock(base_channels, base_channels * 2)
        self.pool2 = nn.MaxPool2d(kernel_size=2, stride=2)
        self.down2 = ConvBlock(base_channels * 2, base_channels * 4)
        self.pool3 = nn.MaxPool2d(kernel_size=2, stride=2)
        self.bridge = ConvBlock(base_channels * 4, base_channels * 8)

    def forward(self, inputs: torch.Tensor) -> dict[str, torch.Tensor]:
        low_level = self.stem(inputs)
        mid_level = self.down1(self.pool1(low_level))
        high_level = self.down2(self.pool2(mid_level))
        bridge = self.bridge(self.pool3(high_level))
        return {
            "low_level": low_level,
            "mid_level": mid_level,
            "high_level": high_level,
            "bridge": bridge,
        }
""",
            ),
            _block(
                "tamper_det/models/seg_head.py",
                "实现带跳跃连接的分割解码头",
                """
import torch
import torch.nn as nn

from tamper_det.models.backbone import ConvBlock


class UpBlock(nn.Module):
    def __init__(self, in_channels: int, skip_channels: int, out_channels: int) -> None:
        super().__init__()
        self.upsample = nn.Upsample(scale_factor=2, mode="bilinear", align_corners=False)
        self.block = ConvBlock(in_channels + skip_channels, out_channels)

    def forward(self, inputs: torch.Tensor, skip: torch.Tensor) -> torch.Tensor:
        upsampled = self.upsample(inputs)
        merged = torch.cat([upsampled, skip], dim=1)
        return self.block(merged)


class SegmentationHead(nn.Module):
    def __init__(self, base_channels: int = 32, dropout: float = 0.1) -> None:
        super().__init__()
        self.up1 = UpBlock(base_channels * 8, base_channels * 4, base_channels * 4)
        self.up2 = UpBlock(base_channels * 4, base_channels * 2, base_channels * 2)
        self.up3 = UpBlock(base_channels * 2, base_channels, base_channels)
        self.dropout = nn.Dropout2d(p=dropout)
        self.classifier = nn.Conv2d(base_channels, 1, kernel_size=1)

    def forward(self, features: dict[str, torch.Tensor]) -> torch.Tensor:
        x = self.up1(features["bridge"], features["high_level"])
        x = self.up2(x, features["mid_level"])
        x = self.up3(x, features["low_level"])
        x = self.dropout(x)
        return self.classifier(x)
""",
            ),
            _block(
                "tamper_det/models/model.py",
                "组装完整图像篡改分割模型",
                """
import torch
import torch.nn as nn

from tamper_det.models.backbone import Encoder
from tamper_det.models.seg_head import SegmentationHead


class TamperSegmentationModel(nn.Module):
    def __init__(self, in_channels: int = 3, base_channels: int = 32, dropout: float = 0.1) -> None:
        super().__init__()
        self.encoder = Encoder(in_channels=in_channels, base_channels=base_channels)
        self.decoder = SegmentationHead(base_channels=base_channels, dropout=dropout)

    def forward(self, inputs: torch.Tensor) -> torch.Tensor:
        features = self.encoder(inputs)
        logits = self.decoder(features)
        return nn.functional.interpolate(logits, size=inputs.shape[-2:], mode="bilinear", align_corners=False)
""",
            ),
            _block(
                "tamper_det/engine/__init__.py",
                "导出训练器与指标接口",
                """
from tamper_det.engine.metrics import compute_segmentation_metrics
from tamper_det.engine.trainer import SegmentationTrainer, build_dataloaders, set_seed

__all__ = ["compute_segmentation_metrics", "SegmentationTrainer", "build_dataloaders", "set_seed"]
""",
            ),
            _block(
                "tamper_det/engine/metrics.py",
                "实现 Dice 与 IoU 等分割指标",
                """
import torch


def _flatten_masks(tensor: torch.Tensor) -> torch.Tensor:
    return tensor.reshape(tensor.shape[0], -1)


def dice_score(predictions: torch.Tensor, targets: torch.Tensor, eps: float = 1e-6) -> torch.Tensor:
    preds = _flatten_masks(predictions)
    refs = _flatten_masks(targets)
    intersection = (preds * refs).sum(dim=1)
    denominator = preds.sum(dim=1) + refs.sum(dim=1)
    return ((2.0 * intersection + eps) / (denominator + eps)).mean()


def iou_score(predictions: torch.Tensor, targets: torch.Tensor, eps: float = 1e-6) -> torch.Tensor:
    preds = _flatten_masks(predictions)
    refs = _flatten_masks(targets)
    intersection = (preds * refs).sum(dim=1)
    union = preds.sum(dim=1) + refs.sum(dim=1) - intersection
    return ((intersection + eps) / (union + eps)).mean()


def pixel_accuracy(predictions: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
    correct = (predictions == targets).float().mean(dim=(1, 2, 3))
    return correct.mean()


def compute_segmentation_metrics(logits: torch.Tensor, targets: torch.Tensor, threshold: float = 0.5) -> dict[str, float]:
    probabilities = torch.sigmoid(logits)
    predictions = (probabilities >= threshold).float()
    return {
        "dice": float(dice_score(predictions, targets).item()),
        "iou": float(iou_score(predictions, targets).item()),
        "pixel_acc": float(pixel_accuracy(predictions, targets).item()),
    }
""",
            ),
            _block(
                "tamper_det/engine/trainer.py",
                "实现训练循环、评估与最佳权重保存",
                """
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import random

import numpy as np
import torch
from torch.utils.data import DataLoader

from tamper_det.config import ExperimentConfig, save_config
from tamper_det.data.casia_dataset import CASIADataset
from tamper_det.engine.metrics import compute_segmentation_metrics


@dataclass
class EpochResult:
    loss: float
    dice: float
    iou: float
    pixel_acc: float


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def build_dataloaders(config: ExperimentConfig) -> tuple[DataLoader, DataLoader]:
    train_dataset = CASIADataset(config.data.root_dir, config.data.train_split, image_size=config.data.image_size)
    val_dataset = CASIADataset(config.data.root_dir, config.data.val_split, image_size=config.data.image_size)
    loader_kwargs = {
        "batch_size": config.data.batch_size,
        "num_workers": config.data.num_workers,
        "pin_memory": config.data.pin_memory,
    }
    train_loader = DataLoader(train_dataset, shuffle=True, **loader_kwargs)
    val_loader = DataLoader(val_dataset, shuffle=False, **loader_kwargs)
    return train_loader, val_loader


class SegmentationTrainer:
    def __init__(self, model: torch.nn.Module, config: ExperimentConfig, device: torch.device) -> None:
        self.model = model.to(device)
        self.config = config
        self.device = device
        self.criterion = torch.nn.BCEWithLogitsLoss()
        self.optimizer = torch.optim.AdamW(
            self.model.parameters(),
            lr=config.train.learning_rate,
            weight_decay=config.train.weight_decay,
        )

    def _move_batch(self, batch: dict[str, torch.Tensor]) -> tuple[torch.Tensor, torch.Tensor]:
        images = batch["image"].to(self.device)
        masks = batch["mask"].to(self.device)
        return images, masks

    def train_one_epoch(self, dataloader: DataLoader) -> EpochResult:
        self.model.train()
        total_loss = 0.0
        metric_sums = {"dice": 0.0, "iou": 0.0, "pixel_acc": 0.0}
        for step, batch in enumerate(dataloader, start=1):
            images, masks = self._move_batch(batch)
            self.optimizer.zero_grad()
            logits = self.model(images)
            loss = self.criterion(logits, masks)
            loss.backward()
            self.optimizer.step()

            total_loss += float(loss.item())
            metrics = compute_segmentation_metrics(logits.detach(), masks, threshold=self.config.train.threshold)
            for key in metric_sums:
                metric_sums[key] += metrics[key]

            if step % self.config.train.log_interval == 0:
                print(f"train step={step} loss={loss.item():.4f} dice={metrics['dice']:.4f} iou={metrics['iou']:.4f}")

        steps = max(len(dataloader), 1)
        return EpochResult(
            loss=total_loss / steps,
            dice=metric_sums["dice"] / steps,
            iou=metric_sums["iou"] / steps,
            pixel_acc=metric_sums["pixel_acc"] / steps,
        )

    @torch.no_grad()
    def evaluate(self, dataloader: DataLoader) -> EpochResult:
        self.model.eval()
        total_loss = 0.0
        metric_sums = {"dice": 0.0, "iou": 0.0, "pixel_acc": 0.0}
        for batch in dataloader:
            images, masks = self._move_batch(batch)
            logits = self.model(images)
            loss = self.criterion(logits, masks)
            total_loss += float(loss.item())
            metrics = compute_segmentation_metrics(logits, masks, threshold=self.config.train.threshold)
            for key in metric_sums:
                metric_sums[key] += metrics[key]

        steps = max(len(dataloader), 1)
        return EpochResult(
            loss=total_loss / steps,
            dice=metric_sums["dice"] / steps,
            iou=metric_sums["iou"] / steps,
            pixel_acc=metric_sums["pixel_acc"] / steps,
        )

    def fit(self, train_loader: DataLoader, val_loader: DataLoader) -> Path:
        output_dir = Path(self.config.train.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        save_config(self.config, output_dir / "config_snapshot.json")

        best_dice = -1.0
        checkpoint_path = self.config.checkpoint_path
        for epoch in range(1, self.config.train.epochs + 1):
            train_metrics = self.train_one_epoch(train_loader)
            val_metrics = self.evaluate(val_loader)
            print(
                f"epoch={epoch} train_loss={train_metrics.loss:.4f} val_loss={val_metrics.loss:.4f} "
                f"val_dice={val_metrics.dice:.4f} val_iou={val_metrics.iou:.4f} val_acc={val_metrics.pixel_acc:.4f}"
            )
            if val_metrics.dice >= best_dice:
                best_dice = val_metrics.dice
                torch.save(
                    {
                        "model_state_dict": self.model.state_dict(),
                        "best_dice": best_dice,
                    },
                    checkpoint_path,
                )
        return checkpoint_path
""",
            ),
            _block(
                "train.py",
                "训练入口脚本，装配数据、模型与训练器",
                """
from tamper_det.config import get_default_config, resolve_device
from tamper_det.engine.trainer import SegmentationTrainer, build_dataloaders, set_seed
from tamper_det.models.model import TamperSegmentationModel


def main() -> None:
    config = get_default_config()
    set_seed(config.train.seed)
    device = resolve_device()
    train_loader, val_loader = build_dataloaders(config)
    model = TamperSegmentationModel(
        in_channels=config.model.in_channels,
        base_channels=config.model.base_channels,
        dropout=config.model.dropout,
    )
    trainer = SegmentationTrainer(model=model, config=config, device=device)
    checkpoint_path = trainer.fit(train_loader, val_loader)
    print(f"training finished, best checkpoint saved to {checkpoint_path}")


if __name__ == "__main__":
    main()
""",
            ),
            _block(
                "infer.py",
                "单张图像推理并导出预测掩码",
                """
import argparse
from pathlib import Path

import numpy as np
from PIL import Image
from PIL.Image import Resampling
import torch

from tamper_det.config import get_default_config, resolve_device
from tamper_det.models.model import TamperSegmentationModel


def load_image(image_path: str, image_size: int) -> torch.Tensor:
    if not image_path or not Path(image_path).exists():
        base = torch.linspace(0.0, 1.0, steps=image_size, dtype=torch.float32)
        grid_y, grid_x = torch.meshgrid(base, base, indexing="ij")
        synthetic = torch.stack([grid_x, grid_y, (grid_x + grid_y) * 0.5], dim=0)
        return synthetic.unsqueeze(0)
    image = Image.open(image_path).convert("RGB")
    image = image.resize((image_size, image_size), resample=Resampling.BILINEAR)
    image_array = np.asarray(image, dtype=np.float32) / 255.0
    return torch.from_numpy(image_array).permute(2, 0, 1).unsqueeze(0)


def save_mask(mask: np.ndarray, output_path: str) -> None:
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(mask.astype(np.uint8)).save(target)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run tamper segmentation inference on one image.")
    parser.add_argument("image", nargs="?", default="", help="Path to the input RGB image.")
    parser.add_argument("--checkpoint", default="", help="Path to a trained checkpoint.")
    parser.add_argument("--output", default="", help="Path to save the predicted binary mask.")
    parser.add_argument("--threshold", type=float, default=None, help="Binarization threshold.")
    args = parser.parse_args()

    config = get_default_config()
    device = resolve_device()
    checkpoint_path = args.checkpoint or config.infer.checkpoint_path
    output_path = args.output or config.infer.output_path
    threshold = args.threshold if args.threshold is not None else config.infer.threshold

    model = TamperSegmentationModel(
        in_channels=config.model.in_channels,
        base_channels=config.model.base_channels,
        dropout=config.model.dropout,
    ).to(device)
    if Path(checkpoint_path).exists():
        checkpoint = torch.load(checkpoint_path, map_location=device)
        state_dict = checkpoint.get("model_state_dict", checkpoint)
        model.load_state_dict(state_dict)
    else:
        print(f"checkpoint not found at {checkpoint_path}, using randomly initialized weights")
    model.eval()

    image = load_image(args.image, config.data.image_size).to(device)
    with torch.no_grad():
        probabilities = torch.sigmoid(model(image))[0, 0].cpu().numpy()

    binary_mask = (probabilities >= threshold).astype(np.uint8) * 255
    save_mask(binary_mask, output_path)
    tampered_ratio = float((binary_mask > 0).mean())
    print(f"saved predicted mask to {output_path}")
    print(f"tampered_area_ratio={tampered_ratio:.4f}")


if __name__ == "__main__":
    main()
""",
            ),
            _block(
                "requirements.txt",
                "图像分割基线依赖清单",
                """
torch
torchvision
numpy
Pillow
""",
                language="text",
            ),
            _block(
                "README.md",
                "分割基线项目说明",
                """
# Tamper Detection Segmentation Scaffold

这是一个面向图像篡改定位任务的参考级最小工程，目标是提供可直接扩展的 image+mask 分割基线，而不是玩具二分类脚手架。

## Project Layout

```text
tamper_det/
├── config.py
├── data/
│   ├── base_dataset.py
│   └── casia_dataset.py
├── engine/
│   ├── metrics.py
│   └── trainer.py
└── models/
    ├── backbone.py
    ├── seg_head.py
    └── model.py
train.py
infer.py
```

## Expected Dataset Layout

推荐使用下列任一目录风格，训练与验证 split 都遵循同样结构：

```text
data/CASIA/
├── train/
│   ├── images/
│   └── masks/
└── val/
    ├── images/
    └── masks/
```

也兼容常见的 `Tp` / `Gt` 命名目录。图像与掩码默认通过文件 stem 对齐，掩码允许 `_gt`、`_mask` 等后缀。

## Install

```bash
pip install -r requirements.txt
```

## Train

```bash
python train.py
```

训练过程会：

- 构建 `CASIADataset` 读取 image/mask 对
- 训练轻量级 U-Net 风格分割模型
- 计算 `Dice`、`IoU`、`Pixel Accuracy`
- 在 `outputs/best_model.pt` 保存最佳权重

## Infer

```bash
python infer.py path/to/image.jpg --checkpoint outputs/best_model.pt --output outputs/pred_mask.png
```

推理脚本会输出二值掩码，并打印预测篡改区域占比，便于做快速质检和基线验收。
""",
                language="markdown",
            ),
        ]

    if scenario == "explainability_extension":
        return [
            _block(
                "app/visualization/feature_hooks.py",
                "注册中间层特征钩子并缓存输出",
                f"""
import torch


class FeatureHookManager:
    def __init__(self, model: torch.nn.Module):
        self.model = model
        self.features: dict[str, torch.Tensor] = {{}}
        self.handles: list = []

    def register(self, layer_names: list[str]) -> None:
        named_modules = dict(self.model.named_modules())
        for layer_name in layer_names:
            module = named_modules.get(layer_name)
            if module is None:
                continue
            handle = module.register_forward_hook(self._build_hook(layer_name))
            self.handles.append(handle)

    def _build_hook(self, layer_name: str):
        def hook(_module, _inputs, outputs):
            if isinstance(outputs, torch.Tensor):
                self.features[layer_name] = outputs.detach().cpu()
        return hook

    def clear(self) -> None:
        self.features.clear()

    def close(self) -> None:
        for handle in self.handles:
            handle.remove()
        self.handles.clear()
""",
            ),
            _block(
                "app/visualization/explain.py",
                "生成可解释热力图与中间特征摘要",
                f"""
import numpy as np


def build_heatmap(feature_map: np.ndarray) -> np.ndarray:
    reduced = feature_map.mean(axis=0)
    reduced = reduced - reduced.min()
    denom = reduced.max() if reduced.max() > 0 else 1.0
    return reduced / denom


def summarize_feature_statistics(feature_map: np.ndarray) -> dict:
    return {{
        "mean": float(feature_map.mean()),
        "std": float(feature_map.std()),
        "max": float(feature_map.max()),
        "min": float(feature_map.min()),
    }}
""",
            ),
        ]

    if scenario == "multi_dataset_refactor":
        return [
            _block(
                "app/data/unified_registry.py",
                "统一不同数据集输入格式为标准样本协议",
                f"""
from dataclasses import dataclass


@dataclass
class SampleRecord:
    image_path: str
    mask_path: str | None
    label: int
    source_dataset: str


def normalize_sample(raw_item: dict, dataset_name: str) -> SampleRecord:
    return SampleRecord(
        image_path=raw_item.get("image") or raw_item.get("image_path", ""),
        mask_path=raw_item.get("mask") or raw_item.get("mask_path"),
        label=int(raw_item.get("label", 0)),
        source_dataset=dataset_name,
    )


def merge_datasets(raw_datasets: dict[str, list[dict]]) -> list[SampleRecord]:
    merged: list[SampleRecord] = []
    for dataset_name, dataset_items in raw_datasets.items():
        for item in dataset_items:
            merged.append(normalize_sample(item, dataset_name))
    return merged
""",
            ),
            _block(
                "app/train/runner.py",
                "统一训练/评估入口，支持多数据集联合训练",
                f"""
from app.data.unified_registry import merge_datasets


def run_train_epoch(raw_datasets: dict[str, list[dict]]) -> dict:
    samples = merge_datasets(raw_datasets)
    return {{
        "sample_count": len(samples),
        "dataset_count": len(raw_datasets),
        "status": "trained",
    }}


def run_eval_epoch(raw_datasets: dict[str, list[dict]]) -> dict:
    samples = merge_datasets(raw_datasets)
    return {{
        "sample_count": len(samples),
        "status": "evaluated",
    }}
""",
            ),
        ]

    if scenario == "config_validation":
        return [
            _block(
                "app/config/schema.py",
                "定义配置与约束对象",
                f"""
from dataclasses import dataclass


@dataclass
class RuntimeConfig:
    batch_size: int
    learning_rate: float
    max_epoch: int


@dataclass
class ConstraintSpec:
    required_types: list[str]
    source_anchors: list[str]


DEFAULT_CONSTRAINT_SPEC = ConstraintSpec(
    required_types={constraints_literal},
    source_anchors={anchors_literal},
)
""",
            ),
            _block(
                "app/config/validator.py",
                "按CFG/DFG/IO类型做运行前约束校验",
                f"""
from app.config.schema import RuntimeConfig, ConstraintSpec


def validate_runtime_config(config: RuntimeConfig) -> list[str]:
    errors: list[str] = []
    if config.batch_size <= 0:
        errors.append("batch_size 必须大于 0")
    if config.learning_rate <= 0:
        errors.append("learning_rate 必须大于 0")
    if config.max_epoch <= 0:
        errors.append("max_epoch 必须大于 0")
    return errors


def validate_constraint_types(actual_types: list[str], spec: ConstraintSpec) -> list[str]:
    missing = [item for item in spec.required_types if item not in actual_types]
    return [f"缺少约束类型: {{item}}" for item in missing]
""",
            ),
        ]

    if scenario == "inference_serviceization":
        return [
            _block(
                "app/service/inference_service.py",
                "批量推理服务主逻辑",
                f"""
from dataclasses import dataclass


@dataclass
class InferenceRequest:
    request_id: str
    image_paths: list[str]


@dataclass
class InferenceResponse:
    request_id: str
    predictions: list[dict]
    status: str


class InferenceService:
    def __init__(self, model_gateway):
        self.model_gateway = model_gateway

    def batch_predict(self, request: InferenceRequest) -> InferenceResponse:
        predictions = self.model_gateway.predict(request.image_paths)
        return InferenceResponse(request_id=request.request_id, predictions=predictions, status="ok")
""",
            ),
            _block(
                "app/service/fallback.py",
                "错误回退策略与日志追踪",
                f"""
def run_with_fallback(primary_fn, fallback_fn, *, logger, context: dict):
    try:
        result = primary_fn()
        logger.info("primary_success", extra=context)
        return result
    except Exception as error:
        logger.error("primary_failed", extra={{**context, "error": str(error)}})
        fallback_result = fallback_fn()
        logger.info("fallback_success", extra=context)
        return fallback_result
""",
            ),
            _block(
                "app/service/api.py",
                "推理API入口",
                f"""
from fastapi import APIRouter

from app.service.inference_service import InferenceRequest, InferenceService


router = APIRouter(prefix="/inference", tags=["inference"])


@router.post("/batch")
def batch_inference(payload: dict, service: InferenceService):
    request = InferenceRequest(
        request_id=payload.get("request_id", ""),
        image_paths=payload.get("image_paths", []),
    )
    response = service.batch_predict(request)
    return {{"request_id": response.request_id, "status": response.status, "predictions": response.predictions}}
""",
            ),
        ]

    if scenario == "data_write_bugfix":
        return [
            _block(
                "app/repository/write_repository.py",
                "修复写入链路：显式事务提交与异常回滚",
                f"""
def update_record_with_transaction(session, model, record_id: str, patch: dict) -> bool:
    try:
        row = session.query(model).filter(model.id == record_id).first()
        if row is None:
            return False
        for key, value in patch.items():
            setattr(row, key, value)
        session.add(row)
        session.commit()
        return True
    except Exception:
        session.rollback()
        raise
""",
            ),
            _block(
                "app/service/update_service.py",
                "修复服务层：写入后强制回读校验",
                f"""
def safe_update(service_repo, record_id: str, patch: dict) -> dict:
    updated = service_repo.update(record_id, patch)
    if not updated:
        return {{"status": "not_found", "record_id": record_id}}
    fresh = service_repo.get(record_id)
    return {{"status": "ok", "record_id": record_id, "fresh": fresh}}
""",
            ),
        ]

    return [
        _block(
            "app/refactor/plan.py",
            "通用改造入口（默认场景）",
            f"""
def build_refactor_plan(requirement: str, source_targets: list[str], constraint_types: list[str]) -> dict:
    return {{
        "requirement": requirement,
        "source_targets": source_targets,
        "constraint_types": constraint_types,
        "next_actions": ["extract modules", "define interfaces", "implement tests"],
    }}
""",
        )
    ]


def _build_code_generation_output(
    requirement: str,
    source_targets: list[dict[str, Any]],
    analysis_payload: dict[str, Any],
    design_payload: dict[str, Any],
) -> dict[str, Any]:
    profile = _detect_codegen_profile(requirement)
    mode = as_str(profile.get("mode")) or "file_level_code"
    scenario = as_str(profile.get("scenario")) or "generic_refactor"

    structured_summary_raw = analysis_payload.get("constraints_structured_summary")
    structured_summary = structured_summary_raw if isinstance(structured_summary_raw, dict) else {}
    constraint_types = as_str_list(structured_summary.get("types"))
    flattened_targets = _flatten_source_targets(source_targets)
    target_repo_root = _resolve_target_repo_root(source_targets)

    def _flag(name: str, default: bool) -> bool:
        raw = as_str(os.getenv(name))
        if not raw:
            return default
        return raw.lower() in {"1", "true", "yes", "on", "enabled"}

    use_opencode = _flag("ADVISOR_OPENCODE_FIRST", True)
    provider = "template_fallback"
    fallback_used = True
    opencode_result: dict[str, Any] = {"status": "disabled", "reason": "opencode_not_used"}
    code_blocks: list[dict[str, Any]] = []

    if use_opencode and callable(_run_opencode_kernel_service):
        impacted_files: list[str] = []
        for item in source_targets:
            if not isinstance(item, dict):
                continue
            for raw_target in as_str_list(item.get("source_targets")):
                normalized = as_str(raw_target)
                if ":" in normalized:
                    left, right = normalized.rsplit(":", 1)
                    if right.isdigit():
                        normalized = left
                normalized = normalized.replace("\\", "/")
                if normalized and normalized not in impacted_files:
                    impacted_files.append(normalized)

        retrieval_bundle = {
            "selected_path": {
                "path_id": "advisor_primary",
                "path_name": as_str((analysis_payload.get("analysis_result") or {}).get("recommended_advisor")) or "advisor_primary",
                "path_description": as_str(design_payload.get("design_goal")) or requirement,
                "function_chain": as_str_list((analysis_payload.get("analysis_result") or {}).get("key_call_chain"))[:16],
            },
            "candidate_paths": [
                {
                    "path_name": as_str(item.get("advisor_name")) or as_str(item.get("advisor_id")),
                    "path_description": f"advisor_context::{as_str(item.get('advisor_name'))}",
                    "function_chain": as_str_list(item.get("source_targets"))[:8],
                    "source": "advisor_context",
                }
                for item in source_targets[:12]
                if isinstance(item, dict)
            ],
            "impacted_files": impacted_files[:24],
        }
        advisor_packet = {
            "status": "ready",
            "recommended": {
                "advisor_name": as_str((analysis_payload.get("analysis_result") or {}).get("recommended_advisor")),
                "partition": as_str((analysis_payload.get("analysis_result") or {}).get("recommended_partition")),
            },
            "analysis": {
                "what": as_str(analysis_payload.get("what")) or as_str((analysis_payload.get("analysis_result") or {}).get("what")),
                "how": as_str(analysis_payload.get("how")) or as_str((analysis_payload.get("analysis_result") or {}).get("how")),
                "next_step": as_str((analysis_payload.get("analysis_result") or {}).get("next_step")),
            },
            "constraints": {
                "types": as_str_list((analysis_payload.get("constraints_structured_summary") or {}).get("types")),
                "plain": as_str_list(analysis_payload.get("constraints")),
                "structured_summary": analysis_payload.get("constraints_structured_summary")
                if isinstance(analysis_payload.get("constraints_structured_summary"), dict)
                else {},
            },
            "source_targets": source_targets,
        }

        required_files: list[str] = []
        if scenario == "new_project_bootstrap":
            required_files = [
                "tamper_det/__init__.py",
                "tamper_det/config.py",
                "tamper_det/data/__init__.py",
                "tamper_det/data/base_dataset.py",
                "tamper_det/data/casia_dataset.py",
                "tamper_det/models/__init__.py",
                "tamper_det/models/backbone.py",
                "tamper_det/models/seg_head.py",
                "tamper_det/models/model.py",
                "tamper_det/engine/__init__.py",
                "tamper_det/engine/metrics.py",
                "tamper_det/engine/trainer.py",
                "train.py",
                "infer.py",
                "requirements.txt",
                "README.md",
            ]
        output_protocol = {
            "opencode": {
                "system_context": {
                    "authority": "OpenCode is the primary code generation authority. Advisor context is auxiliary only.",
                    "design_goal": as_str(design_payload.get("design_goal")) or requirement,
                    "scenario": scenario,
                    "required_files": required_files,
                    "must_follow": [
                        "Generate runnable, coherent project code rather than toy snippets.",
                        "Prefer full-file outputs for create_file and replace actions.",
                        "Keep outputs inside target repository.",
                    ],
                }
            }
        }

        timeout_raw = as_str(os.getenv("ADVISOR_OPENCODE_TIMEOUT_SECONDS"))
        try:
            timeout_seconds = int(timeout_raw or "180")
        except Exception:
            timeout_seconds = 180
        timeout_seconds = max(30, min(timeout_seconds, 600))

        project_path = as_str(os.getenv("ADVISOR_OPENCODE_PROJECT_PATH")) or str(target_repo_root)
        opencode_result = _run_opencode_kernel_service(
            project_path=project_path,
            user_query=requirement,
            task_mode="write_new_code",
            retrieval_bundle=retrieval_bundle,
            advisor_packet=advisor_packet,
            output_protocol=output_protocol,
            enabled=True,
            model=as_str(os.getenv("ADVISOR_OPENCODE_MODEL")),
            agent=as_str(os.getenv("ADVISOR_OPENCODE_AGENT")),
            timeout_seconds=timeout_seconds,
        )

        snippet_blocks = opencode_result.get("snippet_blocks") if isinstance(opencode_result, dict) else []
        if isinstance(snippet_blocks, list):
            for item in snippet_blocks:
                if not isinstance(item, dict):
                    continue
                file_path = as_str(item.get("file_path"))
                code = as_str(item.get("code"))
                if not file_path or not code:
                    continue
                code_blocks.append(
                    {
                        "file_path": file_path,
                        "language": as_str(item.get("language")),
                        "purpose": as_str(item.get("reason")) or as_str(item.get("action")) or "OpenCode snippet",
                        "code": code if code.endswith("\n") else code + "\n",
                    }
                )

        if not code_blocks:
            raw_text = as_str(opencode_result.get("text")) if isinstance(opencode_result, dict) else ""
            current_file = ""
            current_lang = "python"
            in_code = False
            code_lines: list[str] = []

            for line in raw_text.splitlines():
                stripped = line.strip()
                if stripped.startswith("**`") and stripped.endswith("`**"):
                    current_file = stripped[3:-3].strip()
                    continue
                if stripped.startswith("###"):
                    candidate = stripped[3:].strip().strip("`")
                    if candidate:
                        current_file = candidate
                    continue
                if stripped.startswith("```"):
                    fence_lang = stripped[3:].strip()
                    if not in_code:
                        in_code = True
                        current_lang = fence_lang or "python"
                        code_lines = []
                    else:
                        in_code = False
                        code = "\n".join(code_lines).rstrip()
                        if current_file and code:
                            code_blocks.append(
                                {
                                    "file_path": current_file,
                                    "language": current_lang,
                                    "purpose": "OpenCode parsed output",
                                    "code": code if code.endswith("\n") else code + "\n",
                                }
                            )
                        code_lines = []
                    continue
                if in_code:
                    code_lines.append(line)

        required_count = 12 if scenario == "new_project_bootstrap" else 1
        unique_files = {as_str(item.get("file_path")) for item in code_blocks if isinstance(item, dict) and as_str(item.get("file_path"))}
        if len(unique_files) >= required_count:
            provider = "opencode" if as_str(opencode_result.get("status")) == "ready" else "opencode_text_parse"
            fallback_used = False
        if not code_blocks and as_str(opencode_result.get("status")) == "ready":
            provider = "opencode_guided_template"
            fallback_used = False

    if fallback_used:
        code_blocks = _generate_blocks_for_scenario(scenario, flattened_targets, constraint_types)
    elif not code_blocks:
        code_blocks = _generate_blocks_for_scenario(scenario, flattened_targets, constraint_types)

    patch_blocks_raw = []
    if isinstance(opencode_result, dict):
        for key in ("generated_patch_blocks", "patch_blocks"):
            candidate = opencode_result.get(key)
            if isinstance(candidate, list) and candidate:
                patch_blocks_raw = [item for item in candidate if isinstance(item, dict)]
                if patch_blocks_raw:
                    break
    patch_blocks = patch_blocks_raw or _build_patch_blocks(code_blocks, mode=mode, target_repo_root=target_repo_root)

    implementation_targets_raw = opencode_result.get("implementation_targets") if isinstance(opencode_result, dict) else []
    implementation_targets = [item for item in implementation_targets_raw if isinstance(item, dict)] if isinstance(implementation_targets_raw, list) else []
    if not implementation_targets:
        implementation_targets = [
            {
                "file_path": as_str(item.get("file_path")),
                "purpose": as_str(item.get("purpose")),
                "language": as_str(item.get("language")) or "python",
                "anchor_targets": flattened_targets[:8],
            }
            for item in code_blocks
            if isinstance(item, dict)
        ]

    generated_preview = "\n\n".join(
        [
            f"# {as_str(item.get('file_path'))}\n{as_str(item.get('code'))}"
            for item in code_blocks
            if isinstance(item, dict)
        ]
    )

    return {
        "profile": {
            "mode": mode,
            "scenario": scenario,
            "target_repo_root": str(target_repo_root),
            "provider": provider,
            "fallback_used": fallback_used,
        },
        "opencode": {
            "status": as_str(opencode_result.get("status")) if isinstance(opencode_result, dict) else "",
            "reason": as_str(opencode_result.get("reason")) if isinstance(opencode_result, dict) else "",
            "session_id": as_str(opencode_result.get("session_id")) if isinstance(opencode_result, dict) else "",
            "validation_commands": as_str_list(opencode_result.get("validation_commands")) if isinstance(opencode_result, dict) else [],
            "stderr_tail": as_str(opencode_result.get("stderr_tail"))[-1200:] if isinstance(opencode_result, dict) else "",
            "stdout_tail": as_str(opencode_result.get("stdout_tail"))[-1200:] if isinstance(opencode_result, dict) else "",
        },
        "implementation_targets": implementation_targets,
        "generated_code_blocks": code_blocks,
        "generated_patch_blocks": patch_blocks,
        "generated_code_skeleton": generated_preview,
    }


def _build_report(
    match_payload: dict[str, Any],
    analysis_payload: dict[str, Any],
    design_payload: dict[str, Any],
    *,
    run_id: str,
    question_id: str,
) -> dict[str, Any]:
    requirement = as_str(analysis_payload.get("requirement"))
    source_targets = _build_source_targets(match_payload, analysis_payload)
    codegen_output = _build_code_generation_output(requirement, source_targets, analysis_payload, design_payload)

    codegen_profile_raw = codegen_output.get("profile")
    codegen_profile: dict[str, Any] = codegen_profile_raw if isinstance(codegen_profile_raw, dict) else {}
    code_blocks = [item for item in (codegen_output.get("generated_code_blocks") or []) if isinstance(item, dict)]
    patch_blocks = [item for item in (codegen_output.get("generated_patch_blocks") or []) if isinstance(item, dict)]
    implementation_targets = [item for item in (codegen_output.get("implementation_targets") or []) if isinstance(item, dict)]

    return {
        "version": "advisor.lab.v2",
        "step": "generate_code",
        "generated_at": utc_now(),
        "run_id": run_id,
        "question_id": question_id,
        "input_files": {
            "step1_match": str(STEP1_MATCH_RESULT_FILE),
            "step2_analysis": str(STEP2_ANALYSIS_JSON_FILE),
            "step3_design": str(STEP3_DESIGN_JSON_FILE),
        },
        "codegen_profile": {
            "mode": as_str(codegen_profile.get("mode")) or "file_level_code",
            "scenario": as_str(codegen_profile.get("scenario")) or "generic_refactor",
            "target_repo_root": as_str(codegen_profile.get("target_repo_root")),
            "provider": as_str(codegen_profile.get("provider")) or "template_fallback",
            "fallback_used": bool(codegen_profile.get("fallback_used", True)),
        },
        "opencode": codegen_output.get("opencode") if isinstance(codegen_output.get("opencode"), dict) else {},
        "codegen_basis": {
            "analysis_summary": as_str((analysis_payload.get("analysis_result") or {}).get("next_step")),
            "design_goal": as_str(design_payload.get("design_goal")),
            "constraint_types": as_str_list((analysis_payload.get("constraints_structured_summary") or {}).get("types")),
            "constraints_structured_summary": analysis_payload.get("constraints_structured_summary")
            if isinstance(analysis_payload.get("constraints_structured_summary"), dict)
            else {},
        },
        "source_targets": source_targets,
        "source_advisor_count": len(source_targets),
        "implementation_targets": implementation_targets,
        "generated_code_blocks": code_blocks,
        "generated_patch_blocks": patch_blocks,
        "generated_code_skeleton": as_str(codegen_output.get("generated_code_skeleton")),
    }


def _build_codegen_process(
    match_payload: dict[str, Any],
    analysis_payload: dict[str, Any],
    design_payload: dict[str, Any],
    report: dict[str, Any],
    *,
    run_id: str,
    question_id: str,
) -> dict[str, Any]:
    source_targets = [item for item in (report.get("source_targets") or []) if isinstance(item, dict)]
    code_blocks = [item for item in (report.get("generated_code_blocks") or []) if isinstance(item, dict)]
    patch_blocks = [item for item in (report.get("generated_patch_blocks") or []) if isinstance(item, dict)]
    implementation_targets = [item for item in (report.get("implementation_targets") or []) if isinstance(item, dict)]
    codegen_profile_raw = report.get("codegen_profile")
    codegen_profile: dict[str, Any] = codegen_profile_raw if isinstance(codegen_profile_raw, dict) else {}
    apply_ready_patch_count = len([item for item in patch_blocks if bool(item.get("is_apply_ready"))])

    return {
        "version": "advisor.lab.v2",
        "step": "generate_code_process",
        "generated_at": utc_now(),
        "run_id": run_id,
        "question_id": question_id,
        "requirement": as_str(analysis_payload.get("requirement")),
        "phase_traces": [
            {
                "phase": "input_documents",
                "details": {
                    "step1_match_file": str(STEP1_MATCH_RESULT_FILE),
                    "step2_analysis_file": str(STEP2_ANALYSIS_JSON_FILE),
                    "step3_design_file": str(STEP3_DESIGN_JSON_FILE),
                    "matched_advisor_count": len([item for item in (match_payload.get("matched_advisors") or []) if isinstance(item, dict)]),
                },
            },
            {
                "phase": "source_target_resolution",
                "details": {
                    "source_target_count": len(source_targets),
                    "source_advisor_count": len(source_targets),
                    "source_targets": source_targets,
                },
            },
            {
                "phase": "code_solution_synthesis",
                "details": {
                    "codegen_mode": as_str(codegen_profile.get("mode")) or "file_level_code",
                    "codegen_scenario": as_str(codegen_profile.get("scenario")) or "generic_refactor",
                    "codegen_provider": as_str(codegen_profile.get("provider")) or "template_fallback",
                    "fallback_used": bool(codegen_profile.get("fallback_used", True)),
                    "opencode_status": as_str((report.get("opencode") or {}).get("status")),
                    "constraint_types": as_str_list((report.get("codegen_basis") or {}).get("constraint_types")),
                    "implementation_target_count": len(implementation_targets),
                    "code_block_count": len(code_blocks),
                    "patch_block_count": len(patch_blocks),
                    "apply_ready_patch_count": apply_ready_patch_count,
                    "code_block_files": [as_str(item.get("file_path")) for item in code_blocks],
                },
            },
        ],
    }


def _build_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Step4 代码草案",
        "",
        "## 代码生成依据",
        f"- 分析结论：{as_str((payload.get('codegen_basis') or {}).get('analysis_summary'))}",
        f"- 设计目标：{as_str((payload.get('codegen_basis') or {}).get('design_goal'))}",
        f"- 结构化约束类型：{', '.join(as_str_list((payload.get('codegen_basis') or {}).get('constraint_types')))}",
        f"- 生成模式：{as_str((payload.get('codegen_profile') or {}).get('mode'))}",
        f"- 场景识别：{as_str((payload.get('codegen_profile') or {}).get('scenario'))}",
        f"- 代码生成主导：{as_str((payload.get('codegen_profile') or {}).get('provider'))}",
        f"- 是否回退模板：{bool((payload.get('codegen_profile') or {}).get('fallback_used'))}",
        f"- OpenCode状态：{as_str((payload.get('opencode') or {}).get('status'))}",
        f"- 目标仓库根：{as_str((payload.get('codegen_profile') or {}).get('target_repo_root'))}",
        "",
        "## 源码落点",
    ]

    for item in payload.get("source_targets") or []:
        if not isinstance(item, dict):
            continue
        lines.append(f"- 顾问 {as_str(item.get('advisor_name'))} ({as_str(item.get('advisor_id'))})")
        for target in as_str_list(item.get("source_targets")):
            lines.append(f"  - {target}")

    lines.extend(["", "## 文件级代码实现建议"])
    for block in payload.get("generated_code_blocks") or []:
        if not isinstance(block, dict):
            continue
        lines.extend(
            [
                f"### {as_str(block.get('file_path'))}",
                f"- 目的：{as_str(block.get('purpose'))}",
                f"```{as_str(block.get('language')) or 'python'}",
                as_str(block.get("code")),
                "```",
                "",
            ]
        )

    lines.extend(["", "## 补丁级输出（Diff Proposal）"])
    for patch_block in payload.get("generated_patch_blocks") or []:
        if not isinstance(patch_block, dict):
            continue
        lines.extend(
            [
                f"### {as_str(patch_block.get('file_path'))}",
                f"- operation: {as_str(patch_block.get('target_operation'))}",
                f"- apply_strategy: {as_str(patch_block.get('apply_strategy'))}",
                f"- is_apply_ready: {bool(patch_block.get('is_apply_ready'))}",
                "```diff",
                as_str(patch_block.get("patch_text")),
                "```",
                "",
            ]
        )

    return "\n".join(lines)


def main() -> None:
    ensure_runtime(RUNTIME_DIR)
    run_id = as_str(os.environ.get("ADVISOR_RUN_ID")) or "single_run"
    question_id = as_str(os.environ.get("ADVISOR_QUESTION_ID")) or "q00"

    match_payload = read_json(STEP1_MATCH_RESULT_FILE)
    analysis_payload = read_json(STEP2_ANALYSIS_JSON_FILE)
    design_payload = read_json(STEP3_DESIGN_JSON_FILE)

    report = _build_report(match_payload, analysis_payload, design_payload, run_id=run_id, question_id=question_id)
    process = _build_codegen_process(
        match_payload,
        analysis_payload,
        design_payload,
        report,
        run_id=run_id,
        question_id=question_id,
    )

    write_json(STEP4_CODEGEN_JSON_FILE, report)
    write_text(STEP4_CODEGEN_MD_FILE, _build_markdown(report))
    write_json(STEP4_CODEGEN_PROCESS_FILE, process)

    append_jsonl(
        STAGE_TRACE_FILE,
        {
            "version": "advisor.lab.v2",
            "run_id": run_id,
            "question_id": question_id,
            "step": "step4",
            "stage": "codegen",
            "generated_at": report.get("generated_at"),
            "status": "completed",
            "final_artifacts": [str(STEP4_CODEGEN_JSON_FILE), str(STEP4_CODEGEN_MD_FILE)],
            "process_artifact": str(STEP4_CODEGEN_PROCESS_FILE),
            "summary": {
                "source_target_count": len([item for item in (report.get("source_targets") or []) if isinstance(item, dict)]),
                "code_block_count": len([item for item in (report.get("generated_code_blocks") or []) if isinstance(item, dict)]),
                "patch_block_count": len([item for item in (report.get("generated_patch_blocks") or []) if isinstance(item, dict)]),
                "apply_ready_patch_count": len(
                    [
                        item
                        for item in (report.get("generated_patch_blocks") or [])
                        if isinstance(item, dict) and bool(item.get("is_apply_ready"))
                    ]
                ),
                "codegen_mode": as_str((report.get("codegen_profile") or {}).get("mode")),
            },
        },
    )
    print(f"[advisor-lab] step4 done: {STEP4_CODEGEN_MD_FILE}")


if __name__ == "__main__":
    main()
