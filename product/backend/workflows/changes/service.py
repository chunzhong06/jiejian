# 重新扫描真实源码并原子登记 current Action/Permission 影响；Agent 声明不决定范围。
from __future__ import annotations

import time
from threading import RLock
from typing import Literal
from uuid import uuid4

from pydantic import Field

from product.backend.core.check_plan import CheckPlanGap
from product.backend.core.check_repair import CurrentRepairReference
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.source_changes import (
    CurrentActionChangeImpact, CurrentChangeAssessment, CurrentChangeAssessmentPayload, CurrentChangeManifest,
    SourceChangeSet, build_current_change_set, change_impact_fingerprint, normalize_relative_source_path,
)
from product.protocols.execution_v3 import ChangeContext, LogicalId, PermissionReference, WireModel


class SourceRevalidationInspection(WireModel):
    project_id: LogicalId
    change_id: LogicalId
    status: Literal["READY","NO_BASELINE","SOURCE_STALE","POLICY_STALE","MAPPING_REVIEW_REQUIRED"]
    preparation_gaps: tuple[CheckPlanGap, ...] = Field(default=(),max_length=4096)
    can_execute: bool = False


class CurrentChangeView(WireModel):
    manifest: CurrentChangeManifest
    change_set: SourceChangeSet
    assessment: CurrentChangeAssessment
    revalidation: SourceRevalidationInspection


def permission_refs(boundary):
    return tuple(PermissionReference(intent_id=item.intent_id,revision=item.revision,intent_hash=item.intent_hash)
        for item in sorted(boundary.permission_intents,key=lambda item:(item.intent_id,item.revision,item.intent_hash)))


class CurrentSourceChangeService:
    """同实例串行提交；事务重读权限与理解版本，扫描事实不冒充登记成功。"""

    def __init__(self, *, uow_factory, understanding, boundaries, plan_reader=None, repair_resolver=None, clock_us=None):
        self._uow_factory,self._understanding,self._boundaries = uow_factory,understanding,boundaries
        self._plan_reader = plan_reader
        self._repair_resolver = repair_resolver
        self._clock = clock_us or (lambda:time.time_ns()//1000)
        self._lock = RLock()
        self.code_observations = None

    def set_dependencies(self, *, plan_reader, repair_resolver):
        self._plan_reader,self._repair_resolver = plan_reader,repair_resolver

    def submit(self, project_id, *, reason, claimed_paths=(), repair_reference=None, submitted_by="LOCAL_GUI"):
        with self._lock:
            try:
                paths = tuple(sorted({normalize_relative_source_path(path) for path in claimed_paths},key=lambda path:(path.casefold(),path)))
            except (TypeError,ValueError):
                raise JiejianError(ErrorCode.STATE_PRECONDITION,"代码变化路径必须位于授权源码根内") from None
            if len(claimed_paths)>128:
                raise JiejianError(ErrorCode.STATE_PRECONDITION,"代码变化声明超出边界")
            reference = None if repair_reference is None else CurrentRepairReference.model_validate(repair_reference)
            if reference is not None:
                if self._repair_resolver is None:
                    raise JiejianError(ErrorCode.STATE_PRECONDITION,"修复引用服务尚未就绪")
                self._repair_resolver(project_id,reference)
            with self._uow_factory() as work:
                before = work.application_understanding.get(project_id)
                if before is None:
                    raise JiejianError(ErrorCode.APPLICATION_UNDERSTANDING_NOT_FOUND,"应用连接记录不存在")
                boundary = self._boundaries.view(project_id,work=work)
                policy = self._policy(work,project_id)
                baseline = None if before.source_fingerprint is None else work.source_changes.snapshot_for_fingerprint(project_id,before.source_fingerprint)
            manifest = CurrentChangeManifest(change_id="chg_"+uuid4().hex,project_id=project_id,reason=reason,
                claimed_paths=paths,repair_reference=reference,submitted_by=submitted_by,created_at_us=self._clock())
            updated = self._understanding.analyze_source_for_change(project_id,revision=before.revision)
            with self._uow_factory() as work:
                actual = work.application_understanding.get(project_id)
                current_boundary = self._boundaries.view(project_id,work=work)
                if (actual is None or (actual.revision,actual.source_fingerprint)!=(updated.revision,updated.source_fingerprint)
                    or self._policy(work,project_id)!=policy or permission_refs(current_boundary)!=permission_refs(boundary)):
                    raise JiejianError(ErrorCode.STATE_PRECONDITION,"源码分析期间正式权限或理解已变化")
                snapshot = work.source_changes.snapshot_for_fingerprint(project_id,updated.source_fingerprint)
                if snapshot is None:
                    raise JiejianError(ErrorCode.STATE_PRECONDITION,"源码扫描未形成完整快照")
                change = build_current_change_set(manifest,baseline,snapshot)
                assessment = self._assess(work,current_boundary,actual,change)
                work.source_changes.add_current_change(manifest,change,assessment)
                if self.code_observations is not None:
                    observation = self.code_observations.capture(project_id, snapshot.source_fingerprint)
                    work.code_observations.add_link(observation, kind="change", target_id=manifest.change_id,
                        project_id=project_id, source_fingerprint=snapshot.source_fingerprint)
                work.commit()
            # 登记回执和可执行 inspection 分开；准备缺口不撤销已经成功保存的变化事实。
            return self.view(project_id,manifest.change_id)

    def get(self, project_id, change_id):
        with self._uow_factory() as work:
            value = work.source_changes.current_change(project_id,change_id)
        if value is None:
            raise JiejianError(ErrorCode.STATE_PRECONDITION,"代码变化记录不存在或不属于当前项目")
        return value

    def list(self, project_id, *, limit=50):
        with self._uow_factory() as work:
            values = work.source_changes.current_changes(project_id,limit=limit)
        return tuple(self.view(project_id,value[0].change_id) for value in values)

    def latest(self, project_id):
        values = self.list(project_id,limit=1)
        return values[0] if values else None

    def latest_for_repair(self, project_id, reference):
        with self._uow_factory() as work:
            value = work.source_changes.latest_current_for_repair(project_id,reference)
        return None if value is None else self.view(project_id,value[0].change_id)

    def context(self, project_id, change_id):
        _manifest,_change,assessment = self.get(project_id,change_id)
        return ChangeContext(change_id=change_id,impact_fingerprint=assessment.impact_fingerprint,
            required_intent_ids=tuple(item.intent_id for item in assessment.payload.permission_refs))

    def view(self, project_id, change_id):
        manifest,change,assessment = self.get(project_id,change_id)
        return CurrentChangeView(manifest=manifest,change_set=change,assessment=assessment,
            revalidation=self.inspect_revalidation(project_id,change_id))

    def inspect_revalidation(self, project_id, change_id):
        _manifest,change,assessment = self.get(project_id,change_id)
        def result(status, *, gaps=(), executable=False):
            return SourceRevalidationInspection(project_id=project_id,change_id=change_id,status=status,
                preparation_gaps=gaps,can_execute=executable)
        if change.status == "NO_BASELINE":
            return result("NO_BASELINE")
        with self._uow_factory() as work:
            snapshot = work.source_changes.snapshot(change.current_snapshot_id)
            boundary = self._boundaries.view(project_id,work=work)
        if boundary.policy_epoch!=assessment.payload.policy_epoch or permission_refs(boundary)!=assessment.payload.permission_refs:
            return result("POLICY_STALE")
        try:
            current = self._understanding.inspect_source_fingerprint(project_id)
        except (JiejianError,OSError):
            return result("SOURCE_STALE")
        if snapshot is None or current!=snapshot.source_fingerprint:
            return result("SOURCE_STALE")
        if any(item.status != "CURRENT" for item in (*boundary.actor_bindings,*boundary.action_bindings)):
            return result("MAPPING_REVIEW_REQUIRED")
        if self._plan_reader is None:
            return result("READY")
        preview = self._plan_reader(project_id)
        return result("READY",gaps=preview.gaps,executable=preview.can_execute)

    @staticmethod
    def _policy(work, project_id):
        state = work.permission_intents.policy_state(project_id)
        return (0 if state is None else state.policy_epoch,tuple(sorted((item.intent_id,item.revision,item.intent_hash,item.policy_epoch)
            for item in work.permission_intents.list_latest(project_id))))

    @staticmethod
    def _assess(work, boundary, understanding, change):
        all_refs = permission_refs(boundary)
        refs = {item.intent_id:item for item in all_refs}
        actor_status = {item.actor_id:item.status for item in boundary.actor_bindings}
        action_status = {item.action_id:item.status for item in boundary.action_bindings}
        candidates = {item.candidate_id:item for item in (*understanding.role_candidates,*understanding.action_candidates)}
        impacts = []
        for action in boundary.actions:
            permissions = tuple(item for item in boundary.permission_intents if item.business_action_id == action.action_id)
            actors = {(item.subject_actor_id,item.subject_actor_revision) for item in permissions} | {
                (item.resource_owner_actor_id,item.resource_owner_actor_revision) for item in permissions}
            binding = work.business_boundaries.action_binding(action.action_id,action.revision)
            ids = set(() if binding is None else binding.action_candidate_ids)
            for actor_id,revision in actors:
                actor = work.business_boundaries.actor_binding(actor_id,revision)
                ids.update(() if actor is None else actor.role_candidate_ids)
            paths = {item.relative_path for identity in ids if identity in candidates for item in candidates[identity].evidence}
            relevant = tuple(sorted(paths & set(change.changed_paths),key=lambda path:(path.casefold(),path)))
            review = change.status == "NO_BASELINE" or action_status.get(action.action_id)!="CURRENT" or any(actor_status.get(actor)!="CURRENT" for actor,_ in actors)
            classification = "MAPPING_REVIEW_REQUIRED" if review else "DIRECTLY_AFFECTED" if relevant else "NO_DIRECT_EVIDENCE"
            impacts.append(CurrentActionChangeImpact(action_id=action.action_id,action_revision=action.revision,
                permission_refs=tuple(refs[item.intent_id] for item in sorted(permissions,key=lambda item:item.intent_id)),
                classification=classification,relevant_paths=relevant,reason_codes=(classification,)))
        payload = CurrentChangeAssessmentPayload(policy_epoch=boundary.policy_epoch,permission_refs=all_refs,
            action_impacts=tuple(sorted(impacts,key=lambda item:item.action_id)))
        values = dict(change_id=change.change_id,project_id=change.project_id,change_fingerprint=change.change_fingerprint,
            complete=change.status=="COMPARABLE",reason_codes=() if change.status=="COMPARABLE" else ("NO_BASELINE",),payload=payload)
        hashed = dict(values,payload=payload.model_dump(mode="json"))
        return CurrentChangeAssessment(**values,impact_fingerprint=change_impact_fingerprint(hashed),created_at_us=change.created_at_us)
