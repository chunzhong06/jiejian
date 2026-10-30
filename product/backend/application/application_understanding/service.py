# 应用连接与理解服务
# 幂等建立 DRAFT Project、确认 loopback endpoint、授权并编排受控源码分析
# 不创建 ExecutionProfile、PermissionContract 或检查计划；网络访问仅委托受预算约束的地址发现服务。

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from collections.abc import Callable
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from product.backend.domain.applications.models import ActionCandidate, ActionRiskHint, ApplicationUnderstanding, CandidateConfidence, CandidateDecision, CandidateOrigin, CandidateSelection, RoleCandidate, candidate_id, canonical_role_key
from product.backend.domain.errors import ErrorCode, JiejianError
from product.backend.domain.lifecycle import ProjectStatus
from product.backend.domain.changes.models import SourceRevisionSnapshot, source_snapshot_id
from product.backend.infrastructure.storage import ProjectRecord, StorageUnitOfWork
from product.backend.application.application_understanding.endpoints import (
    EndpointDiscoveryResult,
    TargetEndpointDiscovery,
    normalize_loopback_endpoint,
)
from product.backend.application.application_understanding.analysis.analyzer import (
    ApplicationUnderstandingAnalyzer,
)
from product.backend.application.onboarding.discovery import canonical_folder, discover_folder
from product.backend.application.onboarding.models import DiscoveryResult
from product.backend.domain.verification.facts import TargetType


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
    """以 revision 防止并发确认覆盖；绑定有效性由业务边界和准备读取实时核对。"""

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

    def connection_preview(self, source_root: str | Path):
        """只读取同源项目；预览不恢复项目、不复制权限或扩大授权。"""
        source = canonical_folder(source_root)
        discover_folder(source)
        with self._uow_factory() as work:
            records = work.application_understanding.list_by_source_root(str(source))
            projects = [work.projects.get(item.project_id) for item in records]
            projects = [item for item in projects if item is not None]
            snapshot = self._connection_snapshot(str(source), projects)
            return {'source_root':str(source), 'snapshot':snapshot,
                'projects':[item.model_dump(mode='json') for item in projects]}

    @staticmethod
    def _connection_snapshot(source, projects):
        return hashlib.sha256(json.dumps([source, sorted((item.project_id, item.status.value, item.updated_at_us) for item in projects)],
            ensure_ascii=False, separators=(',', ':')).encode('utf-8')).hexdigest()

    def connect(self, source_root: str | Path, *, project_name: str | None = None,
                mode: Literal['AUTO', 'RESUME', 'NEW'] = 'AUTO', existing_project_id: str | None = None,
                expected_snapshot: str | None = None, operation_id: str | None = None) -> ApplicationConnectionView:
        """显式选择恢复或新建；全新接入只建空项目，同键回读不会重复创建。"""
        source = canonical_folder(source_root)
        discovery = discover_folder(source)
        source_text = str(source)
        if mode == 'NEW' and (operation_id is None or re.fullmatch(r'[0-9a-f]{32}', operation_id) is None):
            raise JiejianError(ErrorCode.INPUT_INVALID, '全新接入需要固定的操作标识')
        with self._uow_factory() as work:
            work.acquire_write_lock()
            records = work.application_understanding.list_by_source_root(source_text)
            projects = [work.projects.get(item.project_id) for item in records]
            if any(item is None for item in projects):
                raise JiejianError(ErrorCode.STORAGE_FAILURE, '应用理解记录引用的项目不存在')
            fresh_id = f'app_{operation_id}' if mode == 'NEW' else None
            if fresh_id and (saved := work.application_understanding.get(fresh_id)) is not None:
                project = work.projects.get(fresh_id)
                if saved.source_root != source_text or project is None or project_name and project.name != project_name.strip():
                    raise JiejianError(ErrorCode.STATE_PRECONDITION, '这个接入操作标识已经用于不同内容')
                return ApplicationConnectionView(project=project, understanding=saved, discovery=discovery)
            if mode != 'AUTO' and expected_snapshot != self._connection_snapshot(source_text, projects):
                raise JiejianError(ErrorCode.STATE_PRECONDITION, '同目录的项目记录已有变化，请重新读取后选择')
            existing = next((item for item in records if item.project_id == existing_project_id), None) if mode == 'RESUME' else next((item for item in records if work.projects.get(item.project_id).status is not ProjectStatus.ARCHIVED), None)
            if mode == 'RESUME' and existing is None:
                raise JiejianError(ErrorCode.STATE_PRECONDITION, '所选原项目不属于这个源码目录，请重新选择')
            if mode == 'AUTO' and records and existing is None:
                raise JiejianError(ErrorCode.STATE_PRECONDITION, '该目录有已移除的项目，请明确选择恢复原项目或全新接入', details={'reason':'APPLICATION_REENTRY_REQUIRED'})
            if existing is not None and mode != 'NEW':
                project = work.projects.get(existing.project_id)
                if project.status is ProjectStatus.ARCHIVED:
                    project = ProjectRecord(**(project.model_dump() | {'status':ProjectStatus.DRAFT,
                        'updated_at_us':max(self._clock_us(), project.updated_at_us)}))
                    work.projects.replace(project)
                    work.commit()
                return ApplicationConnectionView(project=project, understanding=existing, discovery=discovery)
            project_id = fresh_id or self._project_id(source)
            if work.projects.get(project_id) is not None:
                raise JiejianError(ErrorCode.STORAGE_CONSTRAINT, '应用目录身份与已有项目冲突')
            now_us = self._clock_us()
            name = (project_name or source.name or '本地应用').strip()
            if not name or len(name) > 128:
                raise JiejianError(ErrorCode.ONBOARDING_INPUT_INVALID, '应用名称长度必须在 1 到 128 个字符之间')
            project = ProjectRecord(project_id=project_id, name=name, status=ProjectStatus.DRAFT,
                target_type=TargetType.WEB, created_at_us=now_us, updated_at_us=now_us)
            understanding = ApplicationUnderstanding(project_id=project_id, source_root=source_text, created_at_us=now_us, updated_at_us=now_us)
            work.projects.add(project)
            work.application_understanding.add(understanding)
            work.commit()
        return ApplicationConnectionView(project=project, understanding=understanding, discovery=discovery)

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
        """保存当前目录的只读授权；源码整理不以应用运行或地址确认作为前提。"""

        with self._uow_factory() as work:
            current = work.application_understanding.get(project_id)
            if current is None:
                raise JiejianError(
                    ErrorCode.APPLICATION_UNDERSTANDING_NOT_FOUND,
                    "当前项目还没有应用连接记录",
                )
            self._require_revision(current, revision)
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

        return self._analyze_source(
            project_id,
            revision=revision,
        )

    def analyze_source_for_change(
        self,
        project_id: str,
        *,
        revision: int,
    ) -> ApplicationUnderstanding:
        """变化编排复用同一受控扫描与 revision 事务，后续按当前事实核验映射。"""

        return self._analyze_source(
            project_id,
            revision=revision,
        )

    def inspect_source_fingerprint(self, project_id: str) -> str:
        """按正式扫描边界只读计算当前源码身份，不保存候选、快照或 revision。"""

        current = self.get(project_id)
        if not current.source_analysis_authorized:
            raise JiejianError(
                ErrorCode.APPLICATION_ANALYSIS_NOT_AUTHORIZED,
                "尚未获得源码只读分析授权",
            )
        return self.analyzer.analyze(current.project_id, current.source_root).source_fingerprint

    def scan_source(self, project_id: str, *, revision: int):
        """准备受控分析，不持久化；交付事务可与源码理解更新一起提交。"""
        before = self.get(project_id)
        self._require_revision(before, revision)
        if not before.source_analysis_authorized:
            raise JiejianError(
                ErrorCode.APPLICATION_ANALYSIS_NOT_AUTHORIZED,
                "尚未获得源码只读分析授权",
            )
        # 扫描只读取已授权目录；录制、观察和正式检查各自保留真实运行前置。
        result = self.analyzer.analyze(before.project_id, before.source_root)
        return before, result

    def apply_source_analysis(self, work, before, result) -> ApplicationUnderstanding:
        """在调用者写事务中核对扫描起点并保存；不提交，也不自动重绑权限。"""
        current = work.application_understanding.get(before.project_id)
        if current is None:
            raise JiejianError(ErrorCode.APPLICATION_UNDERSTANDING_NOT_FOUND, "当前项目还没有应用连接记录")
        self._require_revision(current, before.revision)
        if not current.source_analysis_authorized:
            raise JiejianError(ErrorCode.APPLICATION_ANALYSIS_NOT_AUTHORIZED, "源码只读分析授权已失效")
        if current.source_root != before.source_root or current.confirmed_endpoint != before.confirmed_endpoint:
            raise JiejianError(ErrorCode.STATE_PRECONDITION, "源码分析期间应用连接已变化")
        now_us = self._clock_us()
        updated = self._validated_update(current, source_fingerprint=result.source_fingerprint,
            analysis_completed_at_us=now_us,
            role_candidates=self._merge_roles(current.role_candidates, result.role_candidates),
            action_candidates=self._merge_actions(current.action_candidates, result.action_candidates),
            revision=current.revision + 1, updated_at_us=max(now_us, current.updated_at_us))
        work.application_understanding.replace(updated)
        if work.source_changes.snapshot_for_fingerprint(before.project_id, result.source_fingerprint) is None:
            work.source_changes.add_snapshot(SourceRevisionSnapshot(
                snapshot_id=source_snapshot_id(before.project_id, result.source_fingerprint),
                project_id=before.project_id, source_fingerprint=result.source_fingerprint,
                understanding_revision=updated.revision, files=result.files, created_at_us=now_us))
        return updated

    def _analyze_source(
        self, project_id: str, *, revision: int,
    ) -> ApplicationUnderstanding:
        """执行同一受控扫描；调用者不能改变扫描根、忽略规则或预算。"""
        before, result = self.scan_source(project_id, revision=revision)
        with self._uow_factory() as work:
            work.acquire_write_lock()
            updated = self.apply_source_analysis(work, before, result)
            work.commit()
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

    def decide_candidates(
        self, project_id: str, *, revision: int,
        decisions: tuple[CandidateSelection, ...],
    ) -> ApplicationUnderstanding:
        """在同一 revision 下全有或全无地保存候选审阅；不生成或批准权限。"""
        if not 1 <= len(decisions) <= 256 or len({item.candidate_id for item in decisions}) != len(decisions):
            raise JiejianError(ErrorCode.ONBOARDING_INPUT_INVALID, "每批需包含 1 至 256 个不同候选")
        with self._uow_factory() as work:
            current = self._current_for_update(work, project_id, revision)
            roles = {item.candidate_id: item for item in current.role_candidates}
            actions = {item.candidate_id: item for item in current.action_candidates}
            # 所有项先在内存中完整校验，任何一项失败都不会保存前面的决定。
            for selection in decisions:
                candidates = roles if selection.kind == "ROLE" else actions
                selected = candidates.get(selection.candidate_id)
                if selected is None:
                    raise JiejianError(ErrorCode.APPLICATION_CANDIDATE_NOT_FOUND, "候选不属于当前应用或已被替换")
                if selected.stale or selected.decision is CandidateDecision.REVIEW_REQUIRED:
                    raise JiejianError(ErrorCode.APPLICATION_REVISION_CONFLICT, "候选需要重新分析或单独复核，批量决定未保存")
                decision = CandidateDecision(selection.decision)
                if decision is CandidateDecision.PROPOSED and selected.origin is CandidateOrigin.MANUAL:
                    raise JiejianError(ErrorCode.ONBOARDING_INPUT_INVALID, "手工候选不能改为系统待确认项")
                values = selected.model_dump(mode="python")
                values.update(decision=decision, display_name=self._display_name(
                    selection.display_name, max_length=128 if selection.kind == "ROLE" else 256))
                candidates[selection.candidate_id] = type(selected).model_validate(values)
            updated = self._save_candidate_update(work, current,
                role_candidates=tuple(roles[item.candidate_id] for item in current.role_candidates),
                action_candidates=tuple(actions[item.candidate_id] for item in current.action_candidates))
        return updated

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
        return updated

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
