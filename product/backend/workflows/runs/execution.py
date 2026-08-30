# =============================================================================
# 内部生成执行输入工作流
#
# 定位
# SecuritySetupCompiler 生成资产、冻结执行请求与 Job 提交之间的唯一应用服务。
#
# 职责
# 登记 generated-only 执行输入｜解析 ACTIVE Contract｜编译覆盖计划｜冻结并提交执行请求
#
# 边界
# 不在入口进程执行目标；秘密只用于提交前完整性检查，并通过受控环境交给 Worker。
#
# 调用链
# SecuritySetupCompiler / API → ExecutionWorkflow → RunSubmission
# =============================================================================

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from product.backend import __version__
from product.backend.core.contracts.execution_binding import resolve_execution_contract
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.verification.permissions.coverage import build_permission_coverage_plan
from product.backend.infra.runtime.jobs.requests import ExecutionRequestStore, PersistedExecutionRequest, required_secret_names
from product.backend.infra.runtime.jobs.models import JobSubmissionResult
from product.backend.infra.storage import ExecutionProfileRecord, StorageUnitOfWork
from product.backend.workflows.runs.submission import RunSubmission, SubmitExecution
from product.protocols import (
    ExecutionBudget,
    ObserverRequirementKind,
    WebExecutionProfile,
    required_web_secret_refs,
)
from product.protocols.web.profile import (
    WEB_EXECUTION_PROFILE_MAX_BYTES,
    parse_web_execution_profile,
)
from product.protocols.execution_request import (
    ChangeVerificationContext,
    PermissionPolicySnapshot,
)


class ExecutionWorkflow:
    """只从项目绑定的 ACTIVE ContractVersion 构造当前执行请求。"""

    def __init__(
        self,
        uow_factory: Callable[..., StorageUnitOfWork],
        request_store: ExecutionRequestStore,
        submission: RunSubmission,
        *,
        environment_provider: Callable[[tuple[str, ...]], Mapping[str, str]],
        clock_us: Callable[[], int] | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._request_store = request_store
        self._submission = submission
        self._environment_provider = environment_provider
        self._clock_us = clock_us or (lambda: time.time_ns() // 1_000)
        self._generated_profile_validator: (
            Callable[[ExecutionProfileRecord, WebExecutionProfile], None] | None
        ) = None
        self._permission_policy_snapshot_resolver: (
            Callable[[str], PermissionPolicySnapshot] | None
        ) = None

    def set_generated_profile_validator(
        self,
        validator: Callable[[ExecutionProfileRecord, WebExecutionProfile], None],
    ) -> None:
        """安装普通模式生成资产的实时权威输入校验器。"""

        self._generated_profile_validator = validator

    def set_permission_policy_snapshot_resolver(
        self,
        resolver: Callable[[str], PermissionPolicySnapshot],
    ) -> None:
        """安装执行请求所需的长期权限策略冻结器。"""

        self._permission_policy_snapshot_resolver = resolver

    def register_generated(self, source_path: Path) -> ExecutionProfileRecord:
        """校验并登记编译器生成的执行输入；外部 Profile 一律拒绝。"""

        # --- 阶段：读取并规范化声明源 ---
        profile, raw, source_hash = self._read_source(source_path)
        now_us = self._clock_us()
        # --- 阶段：在同一事务内核对治理绑定并保存元数据 ---
        with self._uow_factory() as work:
            project = work.projects.get(profile.project_id)
            if project is None or project.name != profile.project_name:
                raise JiejianError(ErrorCode.EXECUTION_PROFILE_PROJECT_CONFLICT, "Profile 必须绑定已登记项目")
            if project.target_type is not profile.target_type:
                raise JiejianError(ErrorCode.PROJECT_TARGET_INVALID, "项目与 Profile 的 target_type 不一致")
            governed = work.contract_versions.get(profile.project_id, profile.contract_id, profile.contract_version)
            contract = resolve_execution_contract(project, governed)
            plan = self._compile_plan(profile, contract)
            metadata = self._metadata(profile, source_path, source_hash, contract, plan)
            existing = work.execution_profiles.get(profile.profile_id)
            if existing is not None and existing.project_id != profile.project_id:
                raise JiejianError(ErrorCode.EXECUTION_PROFILE_PROJECT_CONFLICT, "Profile 已绑定其他项目")
            record = ExecutionProfileRecord(
                **metadata,
                created_at_us=existing.created_at_us if existing else now_us,
                updated_at_us=max(now_us, existing.updated_at_us) if existing else now_us,
            )
            self._validate_generated_profile(record, profile)
            if existing is None:
                work.execution_profiles.add(record)
            else:
                work.execution_profiles.replace(record)
            work.commit()
        return record

    def current(self, profile_id: str, *, project_id: str | None = None) -> WebExecutionProfile:
        record, profile, _, _, metadata = self._validated(profile_id, project_id=project_id)
        if not _metadata_matches(record, metadata):
            raise JiejianError(ErrorCode.EXECUTION_PROFILE_SOURCE_DRIFT, "Profile 发生漂移，请显式重新校验")
        return profile

    def build_request(
        self,
        profile_id: str,
        *,
        project_id: str | None = None,
        change_context: ChangeVerificationContext | None = None,
    ) -> PersistedExecutionRequest:
        """从已登记 Profile 和 ACTIVE Contract 构造带预算的不可变执行快照。"""

        record, profile, contract, plan, metadata = self._validated(profile_id, project_id=project_id)
        if not _metadata_matches(record, metadata):
            raise JiejianError(ErrorCode.EXECUTION_PROFILE_SOURCE_DRIFT, "Profile 发生漂移，请显式重新校验")
        snapshot = profile.build_snapshot(contract, plan)
        paired_case_ids = {
            case.case_id
            for twin in snapshot.differential_plan.twins
            for case in (twin.allow_case, twin.deny_case)
        }
        execution_case_count = 2 * len(snapshot.differential_plan.twins) + sum(
            case.case_id not in paired_case_ids for case in snapshot.plan.cases
        )
        scope = profile.target.scope
        budget = ExecutionBudget(
            max_requests=scope.max_requests,
            request_timeout_us=int(scope.timeout_seconds * 1_000_000),
            max_duration_us=profile.max_duration_us,
            max_response_bytes=scope.max_response_bytes,
            max_cases=max(profile.case_budget, execution_case_count),
            max_parallel_cases=1,
        )
        if self._permission_policy_snapshot_resolver is None:
            raise JiejianError(ErrorCode.STATE_PRECONDITION, "权限策略冻结器尚未装配")
        permission_policy = self._permission_policy_snapshot_resolver(profile.project_id)
        return PersistedExecutionRequest(
            budget=budget,
            permission_policy=permission_policy,
            project_snapshot=snapshot,
            change_context=change_context,
        )

    def submit(
        self,
        profile_id: str,
        *,
        project_id: str | None = None,
        change_context: ChangeVerificationContext | None = None,
        idempotency_key: str,
        max_attempts: int = 3,
        now_us: int | None = None,
        available_at_us: int | None = None,
        run_id: str | None = None,
        job_id: str | None = None,
    ) -> tuple[JobSubmissionResult, PersistedExecutionRequest, tuple[str, ...]]:
        """验证必需秘密存在后提交冻结请求；返回秘密名称而非秘密正文。"""

        request = self.build_request(
            profile_id,
            project_id=project_id,
            change_context=change_context,
        )
        names = required_secret_names(request)
        environment = self._environment_provider(names)
        fatal_names = _fatal_secret_names(request)
        # 安全不变量：致命秘密必须在创建 Job 前可用，避免排入注定失败且可能泄漏上下文的任务。
        if any(not environment.get(name) for name in fatal_names):
            raise JiejianError(ErrorCode.SECRET_MISSING, "执行所需环境变量未设置")
        timestamp = self._clock_us() if now_us is None else now_us
        available = timestamp if available_at_us is None else available_at_us
        result = self._submission.submit(
            SubmitExecution(
                request=request,
                idempotency_key=idempotency_key,
                max_attempts=max_attempts,
                now_us=timestamp,
                available_at_us=available,
                run_id=run_id,
                job_id=job_id,
            ),
            known_secrets=tuple(value for name in names if (value := environment.get(name))),
        )
        return result, request, names

    def _record(self, profile_id: str) -> ExecutionProfileRecord:
        with self._uow_factory() as work:
            record = work.execution_profiles.get(profile_id)
        if record is None:
            raise JiejianError(ErrorCode.EXECUTION_PROFILE_NOT_FOUND, "Web 执行配置（WebExecutionProfile）不存在")
        return record

    def _validated(self, profile_id: str, *, project_id: str | None):
        record = self._record(profile_id)
        if project_id is not None and record.project_id != project_id:
            raise JiejianError(ErrorCode.EXECUTION_PROFILE_PROJECT_CONFLICT, "Profile 与项目不匹配")
        profile, _, source_hash = self._read_source(Path(record.source_path))
        self._validate_generated_profile(record, profile)
        with self._uow_factory() as work:
            project = work.projects.get(record.project_id)
            governed = work.contract_versions.get(record.project_id, record.contract_id, record.contract_version)
            contract = resolve_execution_contract(project, governed) if project is not None else None
        if contract is None:
            raise JiejianError(ErrorCode.CONTRACT_NOT_ACTIVE, "Profile 绑定的契约版本不存在")
        plan = self._compile_plan(profile, contract)
        metadata = self._metadata(profile, Path(record.source_path), source_hash, contract, plan)
        return record, profile, contract, plan, metadata

    def _validate_generated_profile(
        self,
        record: ExecutionProfileRecord,
        profile: WebExecutionProfile,
    ) -> None:
        validator = self._generated_profile_validator
        if validator is not None:
            validator(record, profile)

    @staticmethod
    def _read_source(source_path: Path) -> tuple[WebExecutionProfile, bytes, str]:
        path = source_path.resolve()
        try:
            if not path.is_file() or path.stat().st_size > WEB_EXECUTION_PROFILE_MAX_BYTES:
                raise OSError
            raw = path.read_bytes()
            profile = parse_web_execution_profile(raw)
        except JiejianError:
            raise
        except (OSError, ValueError):
            raise JiejianError(ErrorCode.EXECUTION_PROFILE_INVALID, "Web 执行配置（WebExecutionProfile）文件不可读取") from None
        return profile, raw, hashlib.sha256(raw).hexdigest()

    @staticmethod
    def _metadata(profile, source_path, source_hash, contract, plan) -> dict[str, Any]:
        return {
            "profile_id": profile.profile_id,
            "project_id": profile.project_id,
            "source_path": str(source_path.resolve()),
            "source_hash": source_hash,
            "contract_id": contract.contract_id,
            "contract_version": contract.version,
            "contract_fingerprint": plan.contract_fingerprint,
            "plan_fingerprint": plan.plan_fingerprint,
            "engine_version": __version__,
        }

    @staticmethod
    def _compile_plan(profile: WebExecutionProfile, contract):
        available_observations = tuple(item.requirement_id for item in profile.observer_bindings)
        return build_permission_coverage_plan(
            contract,
            engine_version=__version__,
            seed=profile.seed,
            case_budget=profile.case_budget,
            available_subject_ids=tuple(item.subject_id for item in profile.subject_bindings),
            available_resource_ids=tuple(item.resource_id for item in contract.resources),
            available_observations=available_observations,
            max_relation_depth=profile.max_relation_depth,
        )


def _metadata_matches(record: ExecutionProfileRecord, metadata: Mapping[str, Any]) -> bool:
    return all(getattr(record, key) == value for key, value in metadata.items())


def _fatal_secret_names(request: PersistedExecutionRequest) -> tuple[str, ...]:
    snapshot = request.project_snapshot
    references = list(required_web_secret_refs(snapshot))
    return tuple(dict.fromkeys(reference.removeprefix("env:") for reference in references))
