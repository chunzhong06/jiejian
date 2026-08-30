# 公共 JSON Schema 的唯一注册表与确定性检查入口。

from __future__ import annotations

import argparse
import importlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal


SCHEMA_ROOT = Path(__file__).resolve().parent / "schemas"


@dataclass(frozen=True, slots=True)
class SchemaEntry:
    """把一个受版本治理的根文档绑定到唯一 Schema 生成器。"""

    path: str
    target: str
    generator: Literal["model", "function"] = "model"


SCHEMA_REGISTRY: tuple[SchemaEntry, ...] = (
    SchemaEntry("artifacts/artifact-check-request.schema.json", "product.protocols.artifacts:ArtifactCheckRequest"),
    SchemaEntry("artifacts/artifact-result-manifest.schema.json", "product.protocols.artifacts:ArtifactResultManifest"),
    SchemaEntry("artifacts/artifact-scan-result.schema.json", "product.protocols.artifacts:ArtifactScanResult"),
    SchemaEntry("artifacts/publication-manifest.schema.json", "product.backend.infra.artifacts.run_packages:PublicationManifest"),
    SchemaEntry("contracts/differential-experiment-plan.schema.json", "product.backend.core.verification.differential:DifferentialExperimentPlan"),
    SchemaEntry("contracts/normalized-permission-plan.schema.json", "product.backend.core.verification.permissions.contract:NormalizedPermissionPlan"),
    SchemaEntry("contracts/permission-contract.schema.json", "product.backend.core.verification.permissions.contract:PermissionContract"),
    SchemaEntry("contracts/permission-mutation-plan.schema.json", "product.backend.core.verification.permissions.coverage:PermissionMutationPlan"),
    SchemaEntry("execution/http.schema.json", "product.protocols.web.request:HttpRequestTemplate"),
    SchemaEntry("execution/web-execution-profile.schema.json", "product.protocols.web.profile:WebExecutionProfile"),
    SchemaEntry("identity/identity-preparation-request.schema.json", "product.protocols.test_identity_preparation:IdentityPreparationRequest"),
    SchemaEntry("identity/identity-preparation-result.schema.json", "product.protocols.test_identity_preparation:IdentityPreparationResult"),
    SchemaEntry("observer/async-task-observer-invocation.schema.json", "product.protocols.observer.invocation:AsyncTaskObserverInvocation"),
    SchemaEntry("observer/audit-log-observer-invocation.schema.json", "product.protocols.observer.invocation:AuditLogObserverInvocation"),
    SchemaEntry("observer/observation-envelope.schema.json", "product.protocols.observer.result:ObservationEnvelope"),
    SchemaEntry("observer/observer-invocation.schema.json", "product.protocols.observer.invocation:ObserverInvocation"),
    SchemaEntry("observer/observer-outcome.schema.json", "product.protocols.observer.result:ObserverOutcome"),
    SchemaEntry("observer/observer-spec.schema.json", "product.protocols.observer.config:ObserverSpec"),
    SchemaEntry("recording/flow-draft-review-command.schema.json", "product.protocols.flow_draft:flow_draft_review_command_schema", "function"),
    SchemaEntry("recording/flow-draft.schema.json", "product.protocols.flow_draft:FlowDraft"),
    SchemaEntry("recording/flow.schema.json", "product.protocols.recording_flow:Flow"),
    SchemaEntry("recording/recording-event.schema.json", "product.protocols.recording:RecordingEvent"),
    SchemaEntry("recording/recording-runner-request.schema.json", "product.protocols.recording:RecordingRunnerRequest"),
    SchemaEntry("recording/recording-runner-result.schema.json", "product.protocols.recording:RecordingRunnerResult"),
    SchemaEntry("reports/report-package-manifest.schema.json", "product.protocols.report:ReportPackageManifest"),
    SchemaEntry("reports/report.schema.json", "product.protocols.report:report_json_schema", "function"),
    SchemaEntry("runner/evidence.schema.json", "product.protocols.runner.evidence:Evidence"),
    SchemaEntry("runner/persisted-execution-request.schema.json", "product.protocols.execution_request:PersistedExecutionRequest"),
    SchemaEntry("runner/runner-input.schema.json", "product.protocols.runner.input:RunnerInput"),
    SchemaEntry("runner/runner-result.schema.json", "product.protocols.runner.result:RunnerResult"),
    SchemaEntry("runner/trusted-result-receipt.schema.json", "product.backend.infra.artifacts.run_packages:TrustedResultReceipt"),
)


def render_schema(entry: SchemaEntry) -> bytes:
    """从运行时真源生成稳定、无 BOM 且带末尾换行的 Schema。"""

    module_name, separator, attribute_name = entry.target.partition(":")
    if not separator:
        raise ValueError(f"Schema target is invalid: {entry.target}")
    target = getattr(importlib.import_module(module_name), attribute_name)
    schema: dict[str, Any] = target() if entry.generator == "function" else target.model_json_schema()
    return (json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def synchronize_schemas(*, update: bool = False, root: Path = SCHEMA_ROOT) -> tuple[str, ...]:
    """检查全部登记文件；只有显式 update 才把运行时真源写回仓库。"""

    paths = tuple(entry.path for entry in SCHEMA_REGISTRY)
    if paths != tuple(sorted(paths)) or len(paths) != len(set(paths)):
        raise RuntimeError("Schema 注册表必须按路径排序且不得重复")

    expected_paths = set(paths)
    actual_paths = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*.schema.json")
        if path.is_file()
    }
    issues = [f"未登记 Schema：{path}" for path in sorted(actual_paths - expected_paths)]

    for entry in SCHEMA_REGISTRY:
        path = root / Path(entry.path)
        expected = render_schema(entry)
        if update:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(expected)
        elif not path.is_file():
            issues.append(f"缺少 Schema：{entry.path}")
        elif path.read_bytes() != expected:
            issues.append(f"Schema 漂移：{entry.path}")
    return tuple(issues)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="检查或显式更新界鉴公共 JSON Schema")
    parser.add_argument("--update", action="store_true", help="按运行时协议真源更新已登记 Schema")
    arguments = parser.parse_args(argv)
    issues = synchronize_schemas(update=arguments.update)
    if issues:
        for issue in issues:
            print(issue, file=sys.stderr)
        return 1
    print("Schema 已更新。" if arguments.update else "Schema 与运行时协议一致。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
