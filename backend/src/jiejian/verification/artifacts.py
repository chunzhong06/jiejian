# =============================================================================
# Verification staging 工件
#
# 定位
#   Verification Runner 内的结果序列化边界，产物仍需由 Execution 重验和发布
#
# 职责
#   写入 Run/Evidence JSON｜计算内容哈希｜读取本地报告视图
#
# 调用链
#   SnapshotRunExecutor → persist_run → attempt staging；CLI 兼容读取 → load_report
# =============================================================================

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from ..domain.identifiers import RUN_ID_PATTERN
from .models import RunResult, SecurityContract, TargetScope
from ..errors import ErrorCode, JiejianError
from ..redaction import redact

_RUN_ID = re.compile(RUN_ID_PATTERN)


def persist_run(
    result: RunResult,
    plan: dict[str, Any],
    *,
    project_snapshot: dict[str, Any],
    target_snapshot: TargetScope,
    contract: SecurityContract,
    mutation_seed: int,
    started_at: datetime,
    finished_at: datetime,
    destination_dir: Path | None = None,
) -> None:
    """把运行计划、Evidence、报告和 manifest 写成完整 staging 工件树。

    核心数据
        report 汇总 Verdict 和全部 Evidence；manifest 记录运行、Contract、配置、
        seed、时间及每个 JSON 文件的 SHA-256，用于后续 Execution 重验。

    数据流
        RunResult + MutationPlan + 执行快照 → 临时目录内逐项写入
        → 计算 artifact_hashes → manifest → 完整目录替换到 destination_dir。

    关键说明
        本函数只形成 Runner staging 或旧兼容目录，不写数据库，也不完成最终发布。
        任一写入失败都会清理本次临时目录，不保留半成品作为可信结果。
    """

    final_dir = Path(result.artifact_dir) if destination_dir is None else destination_dir
    temporary_dir = final_dir.with_name(f".{final_dir.name}.tmp-{uuid4().hex}")
    try:
        temporary_dir.mkdir(parents=True, exist_ok=False)
        # case_counts 只汇总展示用 Verdict，不替代逐条 Evidence。
        case_counts: dict[str, int] = {}
        for item in result.evidence:
            case_counts[item.verdict.value] = case_counts.get(item.verdict.value, 0) + 1
        report = redact(
            {
                "schema_version": "1",
                "run_id": result.run_id,
                "project_id": result.project_id,
                "engine_version": result.engine_version,
                "verdict": result.verdict.value,
                "reason_codes": result.reason_codes,
                "summary": {"total": len(result.evidence), "case_counts": case_counts},
                "evidence": [
                    item.model_dump(mode="json") for item in result.evidence
                ],
            }
        )
        _atomic_write_json(temporary_dir / "mutation-plan.json", plan)
        _atomic_write_json(
            temporary_dir / "events.json",
            {
                "schema_version": "1",
                "cases": [
                    {
                        "case_id": item.case_id,
                        "verdict": item.verdict.value,
                        "reason_codes": item.reason_codes,
                    }
                    for item in result.evidence
                ],
            },
        )
        for item in result.evidence:
            payload = item.model_dump(mode="json")
            _atomic_write_json(
                temporary_dir / "cases" / item.case_id / "evidence.json",
                payload,
            )
            _atomic_write_json(
                temporary_dir / "evidence" / f"{item.evidence_id}.json",
                payload,
            )
        _atomic_write_json(temporary_dir / "report" / "report.json", report)
        # manifest 最后生成，确保哈希覆盖此前已经形成的全部 JSON 工件。
        artifact_hashes = {
            str(path.relative_to(temporary_dir)).replace("\\", "/"): _hash_file(path)
            for path in sorted(temporary_dir.rglob("*.json"))
        }
        manifest = {
            "schema_version": "1",
            "run_id": result.run_id,
            "project_id": result.project_id,
            "contract_id": contract.id,
            "contract_version": contract.version,
            "contract_hash": _hash_json(contract.model_dump(mode="json")),
            "engine_version": result.engine_version,
            "configuration_hash": _hash_json(project_snapshot),
            "mutation_seed": mutation_seed,
            "target_snapshot": target_snapshot.model_dump(mode="json"),
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "lifecycle": "COMPLETED",
            "verdict": result.verdict.value,
            "case_ids": [item.case_id for item in result.evidence],
            "evidence_ids": [item.evidence_id for item in result.evidence],
            "artifact_hashes": artifact_hashes,
        }
        _atomic_write_json(temporary_dir / "manifest.json", manifest)
        final_dir.parent.mkdir(parents=True, exist_ok=True)
        temporary_dir.replace(final_dir)
    except JiejianError:
        shutil.rmtree(temporary_dir, ignore_errors=True)
        raise
    except OSError as exc:
        shutil.rmtree(temporary_dir, ignore_errors=True)
        raise JiejianError(
            ErrorCode.ARTIFACT_WRITE,
            "运行产物写入失败",
            details={"reason": type(exc).__name__},
        ) from exc


def load_report(var_dir: Path, run_id: str) -> dict[str, Any]:
    """兼容读取旧布局或已发布布局中的本地 JSON 报告，并核对文件哈希。

    数据流
        run_id → 定位唯一报告与对应 manifest → 解析 JSON → 提取期望哈希
        → 常量时间比较 → 脱敏报告。

    关键说明
        这是 CLI 旧兼容读取入口，只校验报告文件及 manifest；需要数据库完成态、
        publication 和 Evidence 索引一致性时，应使用 PublishedResultReader。

    返回
        通过完整性校验并再次脱敏的报告字典。
    """

    if not _RUN_ID.fullmatch(run_id):
        raise JiejianError(ErrorCode.REPORT_NOT_FOUND, "运行 ID 格式无效")
    project_root = var_dir.resolve() / "projects"
    matches = list(project_root.glob(f"*/runs/{run_id}/report/report.json"))
    matches.extend(
        project_root.glob(f"*/runs/{run_id}/artifacts/report/report.json")
    )
    if len(matches) != 1:
        raise JiejianError(ErrorCode.REPORT_NOT_FOUND, "未找到唯一运行报告")
    report_path = matches[0]
    published_layout = report_path.parent.parent.name == "artifacts"
    run_dir = report_path.parents[2] if published_layout else report_path.parents[1]
    manifest_path = (
        run_dir / "publication-manifest.json"
        if published_layout
        else run_dir / "manifest.json"
    )
    try:
        document = json.loads(report_path.read_text(encoding="utf-8"))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise JiejianError(ErrorCode.REPORT_NOT_FOUND, "运行报告不可读取") from exc
    if not isinstance(document, dict) or not isinstance(manifest, dict):
        raise JiejianError(ErrorCode.REPORT_NOT_FOUND, "运行报告结构无效")
    if published_layout:
        entries = manifest.get("files")
        expected_hash = next(
            (
                item.get("sha256")
                for item in entries
                if isinstance(item, dict)
                and item.get("path") == "artifacts/report/report.json"
            ),
            None,
        ) if isinstance(entries, list) else None
    else:
        expected_hash = manifest.get("artifact_hashes", {}).get("report/report.json")
    if not isinstance(expected_hash, str) or not hmac.compare_digest(
        expected_hash, _hash_file(report_path)
    ):
        raise JiejianError(ErrorCode.REPORT_NOT_FOUND, "运行报告完整性校验失败")
    return redact(document)


def _atomic_write_json(path: Path, payload: Any) -> None:
    """先写同目录临时文件，再原子替换单个已脱敏 JSON 文件。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{uuid4().hex}")
    encoded = json.dumps(
        redact(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    try:
        temporary.write_text(f"{encoded}\n", encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _hash_json(payload: Any) -> str:
    """对已脱敏、键排序的紧凑 JSON 计算稳定 SHA-256。"""

    encoded = json.dumps(
        redact(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _hash_file(path: Path) -> str:
    """读取文件原始字节并计算 SHA-256，供 manifest 与读取校验使用。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()
