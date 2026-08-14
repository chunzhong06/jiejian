# 阶段 6 权限执行配置应用服务。
#
# 定位：读取 Profile 源文件、编译确定性计划、登记非秘密摘要并提交冻结请求。
# API、CLI 只调用本服务；Worker 只读取已写入的 request.json。

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable, Mapping
from importlib.metadata import version
from pathlib import Path
from typing import Any

from ..errors import ErrorCode, JiejianError
from ..domain.lifecycle import ProjectStatus
from ..protocols import ExecutionBudgetV2, ObserverRequirementKindV2, ObserverType
from ..storage import (
    PermissionExecutionProfileRecord,
    ProjectRecord,
    StorageUnitOfWork,
)
from ..verification.permission_coverage import build_permission_coverage_plan
from .permission_profile import (
    PERMISSION_EXECUTION_PROFILE_MAX_BYTES,
    PermissionExecutionProfileV2,
    parse_permission_execution_profile,
)
from .request_store import (
    ExecutionRequestStore,
    PersistedExecutionRequestV2,
    required_secret_names,
)
from .submission import ExecutionSubmissionService, SubmitExecutionV2
from .models import JobSubmissionResultV1


class PermissionExecutionService:
    """Profile 源治理与 V2 提交的唯一应用服务入口。"""

    def __init__(
        self,
        uow_factory: Callable[..., StorageUnitOfWork],
        request_store: ExecutionRequestStore,
        submission: ExecutionSubmissionService,
        *,
        environment_provider: Callable[[tuple[str, ...]], Mapping[str, str]],
        clock_us: Callable[[], int] | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._request_store = request_store
        self._submission = submission
        self._environment_provider = environment_provider
        self._clock_us = clock_us or (lambda: time.time_ns() // 1_000)

    def register(
        self,
        source_path: Path,
        *,
        revalidate: bool = False,
    ) -> PermissionExecutionProfileRecord:
        profile, metadata = self._compile_source(source_path)
        now_us = self._clock_us()
        with self._uow_factory() as work:
            existing = work.permission_execution_profiles.get(profile.profile_id)
            if existing is not None and existing.project_id != profile.project_id:
                raise JiejianError(
                    ErrorCode.PERMISSION_PROFILE_PROJECT_CONFLICT,
                    "权限 Profile 已绑定其他项目",
                )
            project = work.projects.get(profile.project_id)
            if project is not None:
                if project.name != profile.project_name:
                    raise JiejianError(
                        ErrorCode.PERMISSION_PROFILE_PROJECT_CONFLICT,
                        "权限 Profile 与项目身份不一致",
                    )
            else:
                work.projects.add(
                    ProjectRecord(
                        project_id=profile.project_id,
                        name=profile.project_name,
                        status=ProjectStatus.READY,
                        created_at_us=now_us,
                        updated_at_us=now_us,
                    )
                )
            if existing is not None:
                if not revalidate and not _metadata_matches(existing, metadata):
                    raise JiejianError(
                        ErrorCode.PERMISSION_PROFILE_SOURCE_DRIFT,
                        "权限 Profile 来源或确定性计划已变化，请显式重新校验",
                    )
                record = PermissionExecutionProfileRecord(
                    **metadata,
                    created_at_us=existing.created_at_us,
                    updated_at_us=max(now_us, existing.updated_at_us),
                )
                work.permission_execution_profiles.replace(record)
            else:
                record = PermissionExecutionProfileRecord(
                    **metadata,
                    created_at_us=now_us,
                    updated_at_us=now_us,
                )
                work.permission_execution_profiles.add(record)
            work.commit()
        return record

    def revalidate(self, profile_id: str) -> PermissionExecutionProfileRecord:
        record = self._record(profile_id)
        return self.register(Path(record.source_path), revalidate=True)

    def list(self, project_id: str) -> tuple[PermissionExecutionProfileRecord, ...]:
        with self._uow_factory() as work:
            if work.projects.get(project_id) is None:
                raise JiejianError(ErrorCode.PROJECT_NOT_FOUND, "项目不存在")
            return work.permission_execution_profiles.list_for_project(project_id)

    def current(self, profile_id: str, *, project_id: str | None = None) -> PermissionExecutionProfileV2:
        record = self._record(profile_id)
        if project_id is not None and record.project_id != project_id:
            raise JiejianError(ErrorCode.PERMISSION_PROFILE_PROJECT_CONFLICT, "权限 Profile 与项目不匹配")
        profile, metadata = self._compile_source(Path(record.source_path))
        if not _metadata_matches(record, metadata):
            raise JiejianError(
                ErrorCode.PERMISSION_PROFILE_SOURCE_DRIFT,
                "权限 Profile 来源或确定性计划已变化，请显式重新校验",
            )
        return profile

    def build_request(
        self,
        profile_id: str,
        *,
        project_id: str | None = None,
    ) -> PersistedExecutionRequestV2:
        profile, metadata = self._compile_source(Path(self._record(profile_id).source_path))
        record = self._record(profile_id)
        if project_id is not None and record.project_id != project_id:
            raise JiejianError(ErrorCode.PERMISSION_PROFILE_PROJECT_CONFLICT, "权限 Profile 与项目不匹配")
        if not _metadata_matches(record, metadata):
            raise JiejianError(
                ErrorCode.PERMISSION_PROFILE_SOURCE_DRIFT,
                "权限 Profile 来源或确定性计划已变化，请显式重新校验",
            )
        plan = self._compile_plan(profile)
        snapshot = profile.build_snapshot(plan)
        budget = ExecutionBudgetV2(
            max_requests=profile.target.max_requests,
            request_timeout_us=int(profile.target.timeout_seconds * 1_000_000),
            max_duration_us=profile.max_duration_us,
            max_response_bytes=profile.target.max_response_bytes,
            max_cases=profile.case_budget,
            max_parallel_cases=1,
        )
        return PersistedExecutionRequestV2(budget=budget, project_snapshot=snapshot)

    def submit(
        self,
        profile_id: str,
        *,
        project_id: str | None = None,
        idempotency_key: str,
        max_attempts: int = 3,
        now_us: int | None = None,
        available_at_us: int | None = None,
    ) -> tuple[JobSubmissionResultV1, PersistedExecutionRequestV2, tuple[str, ...]]:
        request = self.build_request(profile_id, project_id=project_id)
        names = required_secret_names(request)
        environment = self._environment_provider(names)
        fatal_names = _fatal_secret_names(request)
        if any(not environment.get(name) for name in fatal_names):
            raise JiejianError(ErrorCode.SECRET_MISSING, "执行所需环境变量未设置")
        values = tuple(value for name in names if (value := environment.get(name)))
        timestamp = self._clock_us() if now_us is None else now_us
        available = timestamp if available_at_us is None else available_at_us
        result = self._submission.submit(
            SubmitExecutionV2(
                request=request,
                idempotency_key=idempotency_key,
                max_attempts=max_attempts,
                now_us=timestamp,
                available_at_us=available,
            ),
            known_secrets=values,
        )
        return result, request, names

    def _record(self, profile_id: str) -> PermissionExecutionProfileRecord:
        with self._uow_factory() as work:
            record = work.permission_execution_profiles.get(profile_id)
        if record is None:
            raise JiejianError(ErrorCode.PERMISSION_PROFILE_NOT_FOUND, "权限 Profile 不存在")
        return record

    def _compile_source(
        self,
        source_path: Path,
    ) -> tuple[PermissionExecutionProfileV2, dict[str, Any]]:
        path = source_path.resolve()
        try:
            if not path.is_file() or path.stat().st_size > PERMISSION_EXECUTION_PROFILE_MAX_BYTES:
                raise OSError
            raw = path.read_bytes()
            profile = parse_permission_execution_profile(raw)
        except JiejianError:
            raise
        except (OSError, ValueError):
            raise JiejianError(ErrorCode.PERMISSION_PROFILE_INVALID, "权限 Profile 文件不可读取") from None
        plan = self._compile_plan(profile)
        source_hash = hashlib.sha256(raw).hexdigest()
        engine_version = version("jiejian")
        metadata = {
            "profile_id": profile.profile_id,
            "project_id": profile.project_id,
            "source_path": str(path),
            "source_hash": source_hash,
            "contract_id": profile.contract.contract_id,
            "contract_version": profile.contract.version,
            "contract_fingerprint": plan.contract_fingerprint,
            "plan_fingerprint": plan.plan_fingerprint,
            "engine_version": engine_version,
        }
        return profile, metadata

    @staticmethod
    def _compile_plan(profile: PermissionExecutionProfileV2):
        available_observers = tuple(
            ["http"]
            + [
                item.requirement_id
                for item in profile.observer_bindings
                if item.kind.value == "OBSERVER_SPEC" and item.requirement_id
            ]
        )
        return build_permission_coverage_plan(
            profile.contract,
            engine_version=version("jiejian"),
            seed=profile.seed,
            case_budget=profile.case_budget,
            available_subject_ids=tuple(item.subject_id for item in profile.subject_bindings),
            available_resource_ids=tuple(item.resource_id for item in profile.contract.resources),
            available_observers=available_observers,
            max_relation_depth=profile.max_relation_depth,
        )


def _metadata_matches(
    record: PermissionExecutionProfileRecord,
    metadata: Mapping[str, Any],
) -> bool:
    return all(getattr(record, key) == value for key, value in metadata.items())


def _fatal_secret_names(request: PersistedExecutionRequestV2) -> tuple[str, ...]:
    """只把实际执行主体和 OWNER_API 的缺失凭据作为提交前致命错误。"""

    snapshot = request.project_snapshot
    identity_ids = {item.identity_id for item in snapshot.subject_bindings}
    references = [
        identity.secret_ref
        for identity in snapshot.identities
        if identity.id in identity_ids
    ]
    references.extend(
        binding.owner_api_credential_ref
        for binding in snapshot.observer_bindings
        if binding.kind is ObserverRequirementKindV2.OBSERVER_SPEC
        and binding.observer_type is ObserverType.OWNER_API
        and binding.owner_api_credential_ref is not None
    )
    return tuple(dict.fromkeys(reference.removeprefix("env:") for reference in references))
