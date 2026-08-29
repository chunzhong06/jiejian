# =============================================================================
# 应用连接与理解服务
#
# 定位
#   普通用户选择目录之后，Project、应用理解持久状态和 endpoint 发现之间的应用编排层
#
# 职责
#   幂等建立 DRAFT Project｜确认 loopback endpoint｜授权并编排受控源码分析
#
# 边界
#   不创建 ExecutionProfile、PermissionContract 或检查计划；网络访问仅委托受预算约束的地址发现服务。
#
# 调用链
#   Projects API / Readiness → ApplicationUnderstandingService → UoW / TargetEndpointDiscovery
# =============================================================================

from __future__ import annotations

import hashlib
import os
import re
import time
from collections.abc import Callable
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from product.backend.core.application_understanding import (
    ActionCandidate,
    ActionRiskHint,
    ApplicationUnderstanding,
    CandidateConfidence,
    CandidateDecision,
    CandidateOrigin,
    RoleCandidate,
    candidate_id,
    canonical_role_key,
)
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.lifecycle import ProjectStatus
from product.backend.infra.storage import ProjectRecord, StorageUnitOfWork
from product.backend.workflows.application_understanding.endpoints import (
    EndpointDiscoveryResult,
    TargetEndpointDiscovery,
    normalize_loopback_endpoint,
)
from product.backend.workflows.application_understanding.analysis.analyzer import (
    ApplicationUnderstandingAnalyzer,
)
from product.backend.workflows.onboarding.discovery import canonical_folder, discover_folder
from product.backend.workflows.onboarding.models import DiscoveryResult
from product.protocols import TargetType


class ApplicationConnectionView(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
    )

    project: ProjectRecord
    understanding: ApplicationUnderstanding
    discovery: DiscoveryResult


class ApplicationUnderstandingService:
    """以 revision 防止网络探测期间的并发确认覆盖。"""

    def __init__(
        self,
        uow_factory: Callable[..., StorageUnitOfWork],
        *,
        endpoint_discovery: TargetEndpointDiscovery | None = None,
        analyzer: ApplicationUnderstandingAnalyzer | None = None,
        clock_us: Callable[[], int] | None = None,
        reserved_control_origin: str | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self.endpoint_discovery = endpoint_discovery or TargetEndpointDiscovery()
        self.analyzer = analyzer or ApplicationUnderstandingAnalyzer()
        self._clock_us = clock_us or (lambda: time.time_ns() // 1_000)
        self._reserved_control_origin = reserved_control_origin
        self._permission_binding_refresher: Callable[[str], None] | None = None

    def set_permission_binding_refresher(
        self,
        refresher: Callable[[str], None],
    ) -> None:
        """安装源码理解变化后的权限实现绑定失效器。"""

        self._permission_binding_refresher = refresher

    def connect(
        self,
        source_root: str | Path,
        *,
        project_name: str | None = None,
    ) -> ApplicationConnectionView:
        """受限识别目录并幂等建立不依赖 Profile 的项目连接。"""

        source = canonical_folder(source_root)
        discovery = discover_folder(source)
        source_text = str(source)
        with self._uow_factory() as work:
            existing = work.application_understanding.get_by_source_root(source_text)
            if existing is not None:
                project = work.projects.get(existing.project_id)
                if project is None:
                    raise JiejianError(
                        ErrorCode.STORAGE_FAILURE,
                        "应用理解记录引用的项目不存在",
                    )
                if project.status is ProjectStatus.ARCHIVED:
                    now_us = self._clock_us()
                    project = ProjectRecord(
                        **(
                            project.model_dump()
                            | {
                                "name": (project_name or project.name).strip(),
                                "status": ProjectStatus.DRAFT,
                                "updated_at_us": max(now_us, project.updated_at_us),
                            }
                        )
                    )
                    work.projects.replace(project)
                    work.commit()
                return ApplicationConnectionView(
                    project=project,
                    understanding=existing,
                    discovery=discovery,
                )

            project_id = self._project_id(source)
            if work.projects.get(project_id) is not None:
                raise JiejianError(
                    ErrorCode.STORAGE_CONSTRAINT,
                    "应用目录身份与已有项目冲突",
                )
            now_us = self._clock_us()
            name = (project_name or source.name or "本地应用").strip()
            if not name or len(name) > 128:
                raise JiejianError(
                    ErrorCode.ONBOARDING_INPUT_INVALID,
                    "应用名称长度必须在 1 到 128 个字符之间",
                )
            project = ProjectRecord(
                project_id=project_id,
                name=name,
                status=ProjectStatus.DRAFT,
                target_type=TargetType.WEB,
                created_at_us=now_us,
                updated_at_us=now_us,
            )
            understanding = ApplicationUnderstanding(
                project_id=project_id,
                source_root=source_text,
                created_at_us=now_us,
                updated_at_us=now_us,
            )
            work.projects.add(project)
            work.application_understanding.add(understanding)
            work.commit()
        return ApplicationConnectionView(
            project=project,
            understanding=understanding,
            discovery=discovery,
        )

    def get(self, project_id: str) -> ApplicationUnderstanding:
        with self._uow_factory() as work:
            record = work.application_understanding.get(project_id)
        if record is None:
            raise JiejianError(
                ErrorCode.APPLICATION_UNDERSTANDING_NOT_FOUND,
                "当前项目还没有应用连接记录",
            )
        return record

    def discover_endpoints(self, project_id: str) -> EndpointDiscoveryResult:
        record = self.get(project_id)
        return self.endpoint_discovery.discover(record.source_root)

    def confirm_endpoint(
        self,
        project_id: str,
        *,
        endpoint: str,
        revision: int,
    ) -> ApplicationUnderstanding:
        """探测成功后以乐观锁保存授权地址；并发修改时不覆盖较新事实。"""

        before = self.get(project_id)
        self._require_revision(before, revision)
        normalized_input = normalize_loopback_endpoint(endpoint)
        if normalized_input == self._reserved_control_origin:
            raise JiejianError(
                ErrorCode.SELF_TARGET_FORBIDDEN,
                "当前地址是界鉴自身服务，请填写实际被检查应用地址",
            )
        source_fingerprint = self.endpoint_discovery.source_fingerprint(
            before.source_root
        )
        normalized, observation = self.endpoint_discovery.probe(normalized_input)
        if not observation.reachable:
            raise JiejianError(
                ErrorCode.APPLICATION_ENDPOINT_UNREACHABLE,
                "本地应用未在安全探测预算内响应，尚未保存授权",
            )

        with self._uow_factory() as work:
            current = work.application_understanding.get(project_id)
            if current is None:
                raise JiejianError(
                    ErrorCode.APPLICATION_UNDERSTANDING_NOT_FOUND,
                    "当前项目还没有应用连接记录",
                )
            self._require_revision(current, revision)
            now_us = self._clock_us()
            updated = self._validated_update(
                current,
                confirmed_endpoint=normalized,
                endpoint_source_fingerprint=source_fingerprint,
                endpoint_confirmed_at_us=now_us,
                endpoint_last_checked_at_us=now_us,
                endpoint_reachable=True,
                revision=current.revision + 1,
                updated_at_us=max(now_us, current.updated_at_us),
            )
            work.application_understanding.replace(updated)
            work.commit()
        self._refresh_permission_bindings(project_id)
        return updated

    def endpoint_status(
        self,
        record: ApplicationUnderstanding,
    ) -> Literal["NEEDS_CONFIRMATION", "CONFIRMED", "UNAVAILABLE"]:
        """重新核对配置指纹和可达性，不把短暂探测结果写成第二份状态。"""

        if record.confirmed_endpoint is None:
            return "NEEDS_CONFIRMATION"
        try:
            current_fingerprint = self.endpoint_discovery.source_fingerprint(
                record.source_root
            )
        except JiejianError:
            return "NEEDS_CONFIRMATION"
        if current_fingerprint != record.endpoint_source_fingerprint:
            return "NEEDS_CONFIRMATION"
        _, observation = self.endpoint_discovery.probe(record.confirmed_endpoint)
        return "CONFIRMED" if observation.reachable else "UNAVAILABLE"

    def authorize_source_analysis(
        self,
        project_id: str,
        *,
        revision: int,
    ) -> ApplicationUnderstanding:
        """在 endpoint 已经由用户确认后，单独保存源码只读分析授权。"""

        with self._uow_factory() as work:
            current = work.application_understanding.get(project_id)
            if current is None:
                raise JiejianError(
                    ErrorCode.APPLICATION_UNDERSTANDING_NOT_FOUND,
                    "当前项目还没有应用连接记录",
                )
            self._require_revision(current, revision)
            if current.confirmed_endpoint is None:
                raise JiejianError(
                    ErrorCode.APPLICATION_ENDPOINT_INVALID,
                    "请先确认当前应用的本地访问地址",
                )
            if current.source_analysis_authorized:
                return current
            now_us = self._clock_us()
            updated = self._validated_update(
                current,
                source_analysis_authorized=True,
                source_analysis_authorized_at_us=now_us,
                revision=current.revision + 1,
                updated_at_us=max(now_us, current.updated_at_us),
            )
            work.application_understanding.replace(updated)
            work.commit()
        return updated

    def analyze_source(
        self,
        project_id: str,
        *,
        revision: int,
    ) -> ApplicationUnderstanding:
        """离线分析授权目录，并以 revision 防止长扫描覆盖并发修改。"""

        before = self.get(project_id)
        self._require_revision(before, revision)
        if not before.source_analysis_authorized:
            raise JiejianError(
                ErrorCode.APPLICATION_ANALYSIS_NOT_AUTHORIZED,
                "尚未获得源码只读分析授权",
            )
        if before.confirmed_endpoint is None:
            raise JiejianError(
                ErrorCode.APPLICATION_ENDPOINT_INVALID,
                "请先确认当前应用的本地访问地址",
            )
        result = self.analyzer.analyze(before.project_id, before.source_root)

        with self._uow_factory() as work:
            current = work.application_understanding.get(project_id)
            if current is None:
                raise JiejianError(
                    ErrorCode.APPLICATION_UNDERSTANDING_NOT_FOUND,
                    "当前项目还没有应用连接记录",
                )
            self._require_revision(current, revision)
            if not current.source_analysis_authorized:
                raise JiejianError(
                    ErrorCode.APPLICATION_ANALYSIS_NOT_AUTHORIZED,
                    "源码只读分析授权已失效",
                )
            now_us = self._clock_us()
            updated = self._validated_update(
                current,
                source_fingerprint=result.source_fingerprint,
                analysis_completed_at_us=now_us,
                role_candidates=self._merge_roles(
                    current.role_candidates,
                    result.role_candidates,
                ),
                action_candidates=self._merge_actions(
                    current.action_candidates,
                    result.action_candidates,
                ),
                revision=current.revision + 1,
                updated_at_us=max(now_us, current.updated_at_us),
            )
            work.application_understanding.replace(updated)
            work.commit()
        self._refresh_permission_bindings(project_id)
        return updated

    def decide_role(
        self,
        project_id: str,
        candidate_id_value: str,
        *,
        revision: int,
        decision: CandidateDecision,
        display_name: str | None = None,
    ) -> ApplicationUnderstanding:
        """保存用户对单个角色候选的决定，不把决定转换为权限规则。"""

        return self._decide_candidate(
            project_id,
            candidate_id_value,
            revision=revision,
            decision=decision,
            display_name=display_name,
            candidate_type="role",
        )

    def decide_action(
        self,
        project_id: str,
        candidate_id_value: str,
        *,
        revision: int,
        decision: CandidateDecision,
        display_name: str | None = None,
    ) -> ApplicationUnderstanding:
        """保存用户对单个动作候选的决定；risk hint 仍不是漏洞严重度。"""

        return self._decide_candidate(
            project_id,
            candidate_id_value,
            revision=revision,
            decision=decision,
            display_name=display_name,
            candidate_type="action",
        )

    def add_manual_role(
        self,
        project_id: str,
        *,
        revision: int,
        display_name: str,
    ) -> ApplicationUnderstanding:
        """增加用户明确确认、且不会被后续源码扫描删除的角色。"""

        name = self._display_name(display_name)
        try:
            key = canonical_role_key(name)
        except ValueError:
            raise JiejianError(
                ErrorCode.ONBOARDING_INPUT_INVALID,
                "角色名称无法形成稳定标识",
            ) from None
        with self._uow_factory() as work:
            current = self._current_for_update(work, project_id, revision)
            if any(item.canonical_key == key for item in current.role_candidates):
                raise JiejianError(
                    ErrorCode.APPLICATION_CANDIDATE_CONFLICT,
                    "该角色已经存在，请直接确认已有候选",
                )
            manual = RoleCandidate(
                candidate_id=candidate_id("role", key),
                canonical_key=key,
                display_name=name,
                confidence=CandidateConfidence.HIGH,
                decision=CandidateDecision.CONFIRMED,
                origin=CandidateOrigin.MANUAL,
            )
            updated = self._save_candidate_update(
                work,
                current,
                role_candidates=tuple(
                    sorted(
                        (*current.role_candidates, manual),
                        key=lambda item: item.canonical_key,
                    )
                ),
            )
        self._refresh_permission_bindings(project_id)
        return updated

    def add_manual_action(
        self,
        project_id: str,
        *,
        revision: int,
        display_name: str,
        risk_hint: ActionRiskHint = ActionRiskHint.UNKNOWN,
    ) -> ApplicationUnderstanding:
        """增加用户明确确认的业务动作，不生成执行计划或允许/拒绝预期。"""

        name = self._display_name(display_name, max_length=256)
        normalized = re.sub(r"\s+", " ", name.casefold()).strip()
        key = f"manual:{normalized}"[:256]
        with self._uow_factory() as work:
            current = self._current_for_update(work, project_id, revision)
            if any(item.canonical_key == key for item in current.action_candidates):
                raise JiejianError(
                    ErrorCode.APPLICATION_CANDIDATE_CONFLICT,
                    "该业务动作已经存在",
                )
            manual = ActionCandidate(
                candidate_id=candidate_id("action", key),
                canonical_key=key,
                display_name=name,
                confidence=CandidateConfidence.HIGH,
                risk_hint=risk_hint,
                decision=CandidateDecision.CONFIRMED,
                origin=CandidateOrigin.MANUAL,
            )
            updated = self._save_candidate_update(
                work,
                current,
                action_candidates=tuple(
                    sorted(
                        (*current.action_candidates, manual),
                        key=lambda item: item.canonical_key,
                    )
                ),
            )
        self._refresh_permission_bindings(project_id)
        return updated

    def _decide_candidate(
        self,
        project_id: str,
        candidate_id_value: str,
        *,
        revision: int,
        decision: CandidateDecision,
        display_name: str | None,
        candidate_type: Literal["role", "action"],
    ) -> ApplicationUnderstanding:
        if decision not in {
            CandidateDecision.PROPOSED,
            CandidateDecision.CONFIRMED,
            CandidateDecision.REJECTED,
        }:
            raise JiejianError(
                ErrorCode.ONBOARDING_INPUT_INVALID,
                "候选只能处于待确认、已确认或已排除状态",
            )
        with self._uow_factory() as work:
            current = self._current_for_update(work, project_id, revision)
            candidates = (
                current.role_candidates
                if candidate_type == "role"
                else current.action_candidates
            )
            selected = next(
                (item for item in candidates if item.candidate_id == candidate_id_value),
                None,
            )
            if selected is None:
                raise JiejianError(
                    ErrorCode.APPLICATION_CANDIDATE_NOT_FOUND,
                    "候选不存在或已被重新分析替换",
                )
            if (
                decision is CandidateDecision.PROPOSED
                and selected.origin is CandidateOrigin.MANUAL
            ):
                # 手工候选从用户明确添加开始即有确认事实，只能排除或恢复，不能伪造系统发现历史。
                raise JiejianError(
                    ErrorCode.ONBOARDING_INPUT_INVALID,
                    "手工补充候选只能恢复为已确认或保持已排除",
                )
            values = selected.model_dump(mode="python")
            values.update(
                decision=decision,
                stale=False,
                display_name=(
                    self._display_name(
                        display_name,
                        max_length=128 if candidate_type == "role" else 256,
                    )
                    if display_name is not None
                    else selected.display_name
                ),
            )
            candidate_class = (
                RoleCandidate if candidate_type == "role" else ActionCandidate
            )
            replacement = candidate_class.model_validate(values)
            next_candidates = tuple(
                replacement if item.candidate_id == candidate_id_value else item
                for item in candidates
            )
            updates = (
                {"role_candidates": next_candidates}
                if candidate_type == "role"
                else {"action_candidates": next_candidates}
            )
            updated = self._save_candidate_update(work, current, **updates)
        self._refresh_permission_bindings(project_id)
        return updated

    def _refresh_permission_bindings(self, project_id: str) -> None:
        if self._permission_binding_refresher is not None:
            self._permission_binding_refresher(project_id)

    def _current_for_update(
        self,
        work: StorageUnitOfWork,
        project_id: str,
        revision: int,
    ) -> ApplicationUnderstanding:
        current = work.application_understanding.get(project_id)
        if current is None:
            raise JiejianError(
                ErrorCode.APPLICATION_UNDERSTANDING_NOT_FOUND,
                "当前项目还没有应用连接记录",
            )
        self._require_revision(current, revision)
        return current

    def _save_candidate_update(
        self,
        work: StorageUnitOfWork,
        current: ApplicationUnderstanding,
        **candidate_updates: object,
    ) -> ApplicationUnderstanding:
        now_us = self._clock_us()
        updated = self._validated_update(
            current,
            **candidate_updates,
            revision=current.revision + 1,
            updated_at_us=max(now_us, current.updated_at_us),
        )
        work.application_understanding.replace(updated)
        work.commit()
        return updated

    @staticmethod
    def _merge_roles(
        current: tuple[RoleCandidate, ...],
        detected: tuple[RoleCandidate, ...],
    ) -> tuple[RoleCandidate, ...]:
        fresh = {item.canonical_key: item for item in detected}
        merged: list[RoleCandidate] = []
        for previous in current:
            replacement = fresh.pop(previous.canonical_key, None)
            if replacement is not None:
                values = replacement.model_dump(mode="python")
                values.update(
                    display_name=previous.display_name,
                    decision=previous.decision,
                    origin=previous.origin,
                    stale=False,
                )
                merged.append(RoleCandidate.model_validate(values))
            elif previous.origin is CandidateOrigin.MANUAL:
                merged.append(previous.model_copy(update={"stale": False}))
            elif previous.decision is not CandidateDecision.PROPOSED:
                merged.append(previous.model_copy(update={"stale": True}))
        merged.extend(fresh.values())
        return tuple(sorted(merged, key=lambda item: item.canonical_key))

    @staticmethod
    def _merge_actions(
        current: tuple[ActionCandidate, ...],
        detected: tuple[ActionCandidate, ...],
    ) -> tuple[ActionCandidate, ...]:
        fresh = {item.canonical_key: item for item in detected}
        merged: list[ActionCandidate] = []
        for previous in current:
            replacement = fresh.pop(previous.canonical_key, None)
            if replacement is not None:
                values = replacement.model_dump(mode="python")
                values.update(
                    display_name=previous.display_name,
                    decision=previous.decision,
                    origin=previous.origin,
                    stale=False,
                )
                merged.append(ActionCandidate.model_validate(values))
            elif previous.origin is CandidateOrigin.MANUAL:
                merged.append(previous.model_copy(update={"stale": False}))
            elif previous.decision is not CandidateDecision.PROPOSED:
                merged.append(previous.model_copy(update={"stale": True}))
        merged.extend(fresh.values())
        return tuple(sorted(merged, key=lambda item: item.canonical_key))

    @staticmethod
    def _display_name(value: str, *, max_length: int = 128) -> str:
        name = value.strip()
        if not name or len(name) > max_length or any(ord(char) < 32 for char in name):
            raise JiejianError(
                ErrorCode.ONBOARDING_INPUT_INVALID,
                f"显示名称长度必须在 1 到 {max_length} 个字符之间",
            )
        return name

    @staticmethod
    def _project_id(source_root: Path) -> str:
        identity = os.path.normcase(str(source_root)).encode("utf-8")
        return f"app_{hashlib.sha256(identity).hexdigest()[:32]}"

    @staticmethod
    def _require_revision(
        record: ApplicationUnderstanding,
        revision: int,
    ) -> None:
        if revision != record.revision:
            raise JiejianError(
                ErrorCode.APPLICATION_REVISION_CONFLICT,
                "应用理解状态已更新，请刷新后重试",
            )

    @staticmethod
    def _validated_update(
        record: ApplicationUnderstanding,
        **updates: object,
    ) -> ApplicationUnderstanding:
        values = record.model_dump(mode="python")
        values.update(updates)
        return ApplicationUnderstanding.model_validate(values)
