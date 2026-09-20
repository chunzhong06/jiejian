# 官方体验只编排已批准业务边界、正式准备和通用检查；会话资源受控且不预制安全结论。
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from enum import StrEnum
from threading import RLock
from typing import Literal
from uuid import uuid4

from pydantic import Field

from product.backend.core.action_preparation import RegisteredObserverReference
from product.backend.core.check_repair import CurrentRepairReference
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.test_identity import TestIdentityAuthMethod, TestIdentityCookie
from product.backend.infra.samples import OfficialSampleManager, OfficialSampleRuntime
from product.backend.infra.secrets import credential_ref
from product.backend.workflows.business_boundaries.official_recipe import official_boundary_recipe
from product.backend.workflows.checks.registry import CheckRuntimeRegistration, RegisteredCheckIdentity, RegisteredCheckProof, RegisteredAuxiliarySource
from product.backend.workflows.official_scenario import EXPORT_ACTION_KEY, VIEW_ACTION_KEY, SAMPLE_RESOURCE_ID, SAMPLE_PROJECT_ID
from product.backend.workflows.checks.local_observer_wiring import load_local_observer_wiring
from product.backend.workflows.test_identities import PreparedLoginState, TestIdentityStatus
from product.protocols.check_runtime import CheckIdentityVerification, CheckAuxiliarySource
from product.protocols.execution_v3 import WireModel
from product.protocols.observer import ObserverSpec
from product.backend.workflows.supplemental_contract import request_uuid


class OfficialScenarioVersion(StrEnum):
    VULNERABLE="VULNERABLE"
    EVIDENCE_LIMITED="EVIDENCE_LIMITED"
    FIXED="FIXED"


class OfficialExperienceView(WireModel):
    available: bool
    display_name: str
    unavailable_reason: str | None = None
    active: bool
    experience_id: str | None = None
    project_id: str | None = None
    origin: str | None = None
    scenario_prepared: bool
    scenario_version: OfficialScenarioVersion | None = None
    scenario_changed_at_us: int | None = None
    vulnerable_change_id: str | None = None
    repair_change_id: str | None = None
    pending_tasks: tuple[str,...] = Field(default=(),max_length=16)
    lifecycle: Literal["NOT_STARTED", "STARTING", "RUNNING", "STOPPING", "STOPPED", "FAILED", "UNKNOWN"] = "NOT_STARTED"
    history_project_id: str | None = None
    last_error_code: str | None = None
    operation_id: str | None = None
    operation_state: Literal["PENDING", "SUCCEEDED", "FAILED", "UNKNOWN"] | None = None


@dataclass
class _Experience:
    runtime: OfficialSampleRuntime
    project_id: str
    scenario_version: OfficialScenarioVersion = OfficialScenarioVersion.VULNERABLE
    scenario_prepared: bool = False
    prepared_source: str | None = None
    scenario_changed_at_us: int = 0
    active: bool = True
    vulnerable_change_id: str | None = None
    repair_change_id: str | None = None
    proposal_id: str | None = None
    pending_tasks: tuple[str,...] = ()


class OfficialSampleExperience:
    def __init__(self, manager: OfficialSampleManager, *, understanding, boundaries, identities, secret_store,
                 registry, installer, bindings, preparation, changes, repairs, uow_factory, var_dir,
                 archive_project, clock_us=None):
        self._manager,self._understanding,self._boundaries=manager,understanding,boundaries
        self._identities,self._secrets,self._registry=identities,secret_store,registry
        self._installer,self._bindings,self._preparation=installer,bindings,preparation
        self._changes,self._repairs=changes,repairs
        self._uow_factory,self._var_dir,self._archive=uow_factory,var_dir,archive_project
        self._clock=clock_us or (lambda:time.time_ns()//1000)
        self._lock=RLock()
        self._current=None
        self._running_operation = None
        self._operation_cleanup_confirmed = False
        self._cleanup_uncertain = False

    def status(self):
        current=self._current
        installation=self._manager.installation
        with self._uow_factory() as work:
            operations, _ = work.environment_operations.list(1)
        operation = operations[0] if operations else None
        active = bool(current and current.active and self._manager.active)
        lifecycle = "RUNNING" if active else "NOT_STARTED"
        state = None if operation is None else operation["state"]
        if operation is not None:
            if state == "PENDING":
                if self._running_operation == operation["operation_id"]:
                    lifecycle = "STOPPING" if operation["operation"] == "stop" else "STARTING"
                else:
                    lifecycle, state = "UNKNOWN", "UNKNOWN"
            elif state == "UNKNOWN":
                lifecycle = "UNKNOWN"
            elif state == "FAILED":
                lifecycle = "RUNNING" if active else "FAILED"
            elif operation["operation"] == "stop" and operation["cleanup_confirmed"]:
                lifecycle = "STOPPED"
            elif not active:
                lifecycle = "UNKNOWN"
        return OfficialExperienceView(available=installation.available,display_name=installation.display_name,
            unavailable_reason=installation.reason,active=active,
            experience_id=None if current is None else current.runtime.experience_id,
            project_id=None if current is None else current.project_id,origin=None if current is None else current.runtime.origin,
            scenario_prepared=bool(current and current.scenario_prepared),
            scenario_version=None if current is None else current.scenario_version,
            scenario_changed_at_us=None if current is None else current.scenario_changed_at_us,
            vulnerable_change_id=None if current is None else current.vulnerable_change_id,
            repair_change_id=None if current is None else current.repair_change_id,
            pending_tasks=() if current is None else current.pending_tasks,
            lifecycle=lifecycle, history_project_id=None if operation is None else operation["project_id"],
            last_error_code=None if operation is None else operation["error_code"],
            operation_id=None if operation is None else operation["operation_id"], operation_state=state)

    def start(self, *, consent, operation_id=None):
        if consent is not True:
            raise JiejianError(ErrorCode.STATE_OPERATOR_REQUIRED,"启动官方示例前需要明确同意本机运行与源码复制")
        return self._operate("start", operation_id, lambda: self._start(consent=consent))

    def _start(self, *, consent):
        if consent is not True:
            raise JiejianError(ErrorCode.STATE_OPERATOR_REQUIRED,"启动官方示例前需要明确同意本机运行与源码复制")
        with self._lock:
            if self._current is not None and self._current.active:
                self._stop()
            if self._cleanup_uncertain:
                raise JiejianError(ErrorCode.STATE_PRECONDITION, "上一环境清理尚未确认")
            self._operation_cleanup_confirmed = False
            runtime=self._manager.start(authorization_order="ENQUEUE_BEFORE_AUTHORIZE",owner_observation="AVAILABLE",blob_observation="AVAILABLE")
            project = None
            try:
                self._operation_progress(experience_id=runtime.experience_id, project_id=None)
                connection=self._understanding.connect(runtime.source_root,project_name=runtime.display_name)
                project=connection.project.project_id
                self._operation_progress(project_id=project)
                value=self._understanding.confirm_endpoint(project,endpoint=runtime.origin,revision=connection.understanding.revision)
                value=self._understanding.authorize_source_analysis(project,revision=value.revision)
                self._understanding.analyze_source_for_change(project,revision=value.revision)
                self._current=_Experience(runtime,project,scenario_changed_at_us=self._clock(),pending_tasks=("HUMAN_BOUNDARY_APPROVAL_REQUIRED",))
                return self.status()
            except Exception:
                # 清理失败不能遮盖首次连接/分析错误，回执保留未确认清理事实。
                try:
                    self._manager.stop(runtime.experience_id)
                    # 已创建 Project 尚未归档时保留未知收口，不能把仅进程退出当成完整清理。
                    self._operation_cleanup_confirmed = project is None
                except Exception:
                    self._operation_cleanup_confirmed = False
                    self._cleanup_uncertain = True
                raise

    def boundary_proposal(self):
        with self._lock:
            current=self._require_active()
            if current.proposal_id is not None:
                return self._boundaries.proposal(current.project_id,current.proposal_id)
            recipe=official_boundary_recipe()
            understanding=self._understanding.get(current.project_id)
            # 这里只推荐实际发现的映射；正式 revision 与映射仍由普通 GUI 审阅批准。
            role_keys=("project_owner","member")
            action_keys=(EXPORT_ACTION_KEY,VIEW_ACTION_KEY)
            roles={item.canonical_key.casefold():item.candidate_id for item in understanding.role_candidates if not item.stale}
            actions={item.canonical_key:item.candidate_id for item in understanding.action_candidates if not item.stale}
            command=recipe.proposal_command
            actors=tuple(item.model_copy(update={"source_candidate_ids":() if key not in roles else (roles[key],)})
                for item,key in zip(command.proposed_actors,role_keys,strict=True))
            proposed_actions=tuple(item.model_copy(update={"source_candidate_ids":() if key not in actions else (actions[key],)})
                for item,key in zip(command.proposed_actions,action_keys,strict=True))
            proposal=self._boundaries.create_proposal(current.project_id,command.model_copy(update={"proposed_actors":actors,"proposed_actions":proposed_actions}))
            current.proposal_id=proposal.proposal.proposal_id
            return proposal

    def _matching_boundary(self, current):
        recipe=official_boundary_recipe().proposal_command
        boundary=self._boundaries.view(current.project_id)
        actors={item.display_name:item for item in boundary.actors}
        actions={item.display_name:item for item in boundary.actions}
        if len(actors)!=2 or len(actions)!=2 or len(boundary.permission_intents)!=3:
            return None
        actor_map,action_map,effect_map={},{},{}
        for item in recipe.proposed_actors:
            actual=actors.get(item.display_name)
            if actual is None or (actual.description,actual.effective_state)!=(item.description,item.effective_state):
                return None
            actor_map[item.item_id]=actual
        for item in recipe.proposed_actions:
            actual=actions.get(item.display_name)
            if actual is None or any(getattr(actual,key)!=getattr(item,key) for key in
                ("description","primary_resource_concept","operation_kind","state_changing","effective_state")):
                return None
            if len(actual.effect_catalog)!=len(item.effect_catalog):
                return None
            for expected,effect in zip(item.effect_catalog,actual.effect_catalog,strict=True):
                if effect.model_dump(mode="json",exclude={"effect_id"})!=expected.model_dump(mode="json",exclude={"item_id","effect_id"}):
                    return None
                effect_map[expected.item_id]=effect.effect_id
            action_map[item.item_id]=actual
        expected=set()
        for item in recipe.proposed_permissions:
            expected.add((actor_map[item.subject_actor_item_id].actor_id,action_map[item.business_action_item_id].action_id,
                actor_map[item.resource_owner_actor_item_id].actor_id,item.expectation.value,item.relation.value,
                tuple(sorted(effect_map[key] for key in item.protected_effect_item_ids))))
        actual={(item.subject_actor_id,item.business_action_id,item.resource_owner_actor_id,item.expectation.value,item.relation.value,
            item.protected_effect_ids) for item in boundary.permission_intents}
        if actual!=expected:
            return None
        return boundary,tuple(actor_map[item.item_id] for item in recipe.proposed_actors),tuple(action_map[item.item_id] for item in recipe.proposed_actions)

    def prepare(self):
        with self._lock:
            current=self._require_active()
            self._require_idle(current.project_id)
            matched=self._matching_boundary(current)
            if matched is None:
                current.pending_tasks=("HUMAN_BOUNDARY_APPROVAL_REQUIRED",)
                return self.status()
            boundary,actors,actions=matched
            if any(item.status!="CURRENT" for item in (*boundary.actor_bindings,*boundary.action_bindings)):
                current.pending_tasks=("HUMAN_IMPLEMENTATION_REBIND_REQUIRED",)
                return self.status()
            understanding=self._understanding.get(current.project_id)
            if self._understanding.inspect_source_fingerprint(current.project_id)!=understanding.source_fingerprint:
                current.pending_tasks=("REGISTER_SOURCE_CHANGE",)
                return self.status()
            if current.scenario_prepared and current.prepared_source==understanding.source_fingerprint:
                return self.status()
            identities=[]
            existing=self._identities.list(current.project_id)
            for actor,account,label,name in zip(actors,("alice","bob"),("Alice · 项目负责人","Bob · 普通成员"),
                ("JIEJIAN_SAMPLE_ALICE_SESSION","JIEJIAN_SAMPLE_BOB_SESSION"),strict=True):
                values=[item for item in existing if item.actor_id==actor.actor_id and item.actor_revision==actor.revision]
                if len(values)>1:
                    current.pending_tasks=("TEST_IDENTITY_SELECTION_REQUIRED",)
                    return self.status()
                identity=values[0] if values else self._identities.create(current.project_id,actor_id=actor.actor_id,actor_revision=actor.revision,label=label)
                if identity.status is not TestIdentityStatus.PREPARED:
                    reference=credential_ref("test-identity",current.project_id,identity.identity_id,"cookie-00")
                    self._secrets.set_session(current.runtime.experience_id,reference,current.runtime.secrets[name])
                    identity=self._identities.save_prepared_state(identity.identity_id,PreparedLoginState(auth_method=TestIdentityAuthMethod.COOKIE_SESSION,
                        cookies=(TestIdentityCookie(name="jiejian_sample_session",domain="127.0.0.1",path="/",secure=False,http_only=True,
                            same_site="LAX",value_secret_ref=reference),),prepared_at_us=self._clock()))
                identities.append(identity)
            self._manager.bind_effects(current.runtime.experience_id,export_effect_id=actions[0].effect_catalog[0].effect_id,
                view_effect_id=actions[1].effect_catalog[0].effect_id)
            references=self._register(current,actions,identities,understanding.source_fingerprint)
            recordings=self._installer.install(project_id=current.project_id,endpoint=current.runtime.origin,
                export_action_id=actions[0].action_id,view_action_id=actions[1].action_id,
                owner_identity_id=identities[0].identity_id,member_identity_id=identities[1].identity_id,
                source_fingerprint=understanding.source_fingerprint)
            for action,recording,reference in zip(actions,recordings,references,strict=True):
                self._bindings.register_observer(recording,effect_id=action.effect_catalog[0].effect_id,reference=reference,now_us=self._clock())
            current.scenario_prepared=self._preparation.get(current.project_id).preparation_complete
            current.prepared_source=understanding.source_fingerprint
            current.pending_tasks=() if current.scenario_prepared else ("PREPARATION_INCOMPLETE",)
            return self.status()

    def _register(self,current,actions,identities,source):
        wiring=load_local_observer_wiring(str(current.runtime.check_descriptor_path),var_dir=self._var_dir,action_id=actions[0].action_id,
            expected_origin=current.runtime.origin,expected_resource_id=SAMPLE_RESOURCE_ID)
        specs={item.observer_type.value:item for item in wiring.observers}
        blob=specs["AZURE_BLOB_OBJECT"]
        references=(RegisteredObserverReference(descriptor_id=current.runtime.experience_id,descriptor_fingerprint=wiring.descriptor_fingerprint,observer_id=blob.observer_id),
            RegisteredObserverReference(descriptor_id=current.runtime.experience_id,descriptor_fingerprint=wiring.descriptor_fingerprint,observer_id="sample-collaboration-read"))
        auxiliary=tuple(RegisteredAuxiliarySource(source=CheckAuxiliarySource(observer_id=spec.observer_id,
            descriptor_fingerprint=wiring.descriptor_fingerprint,observation_identity_id=identities[0].identity_id,
            level="DIAGNOSIS_REQUIRED" if kind=="STRUCTURED_AUDIT_LOG" else "SUPPORTING",source_label=kind,source_location="observer/"+kind.lower(),
            trace_namespace="sample-account" if kind=="STRUCTURED_AUDIT_LOG" else None),spec=spec)
            for kind,spec in specs.items() if kind!="AZURE_BLOB_OBJECT")
        view=ObserverSpec.model_validate_json(json.dumps(dict(observer_id=references[1].observer_id,observer_type="OWNER_API",
            target=dict(target_id="collaboration",locator=dict(locator_type="OWNER_API",relative_path_template="/api/projects/{resource_id}/collaboration"),
                normalization_id="collaboration",normalization_version="1"),phases=["BEFORE","AFTER"],required=True,
            budget=dict(timeout_us=1_000_000,max_rows=1,max_bytes=262144))))
        proofs=tuple(RegisteredCheckProof(reference=reference,effect=action.effect_catalog[0],spec=spec,observation_identity_id=identity.identity_id,
            source_label=action.effect_catalog[0].business_label,source_location="observer/"+spec.observer_type.value.lower(),
            closure_supported=True,resource_correlation_supported=True,exclusive_resource_window=True,
            auxiliary_sources=auxiliary if index==0 else ())
            for index,(action,identity,reference,spec) in enumerate(zip(actions,identities,references,(blob,view),strict=True)))
        mapped=tuple(RegisteredCheckIdentity(identity_id=identity.identity_id,verification=CheckIdentityVerification.model_validate_json(
            json.dumps(dict(namespace="sample-account",expected_application_subject_id=account,
                expected_actor_id=identity.actor_id,expected_actor_revision=identity.actor_revision,
                request=dict(method="GET",path="/api/session"),subject_json_path="$.account"))))
            for identity,account in zip(identities,("alice","bob"),strict=True))
        previous=self._registry.snapshot(current.project_id)
        self._registry.register(CheckRuntimeRegistration(project_id=current.project_id,source_fingerprint=source,identities=mapped,proofs=proofs),
            expected_fingerprint=None if previous is None else previous.fingerprint)
        return references

    def switch_version(self, *, version, repair_reference=None):
        with self._lock:
            current=self._require_active()
            self._require_idle(current.project_id)
            reference=None if repair_reference is None else CurrentRepairReference.model_validate(repair_reference)
            if version is OfficialScenarioVersion.FIXED:
                if reference is None:
                    raise JiejianError(ErrorCode.STATE_PRECONDITION,"修复版需要已发布原题引用")
                self._repairs.resolve(current.project_id,reference)
            self._manager.switch_behavior(current.runtime.experience_id,
                authorization_order="AUTHORIZE_BEFORE_ENQUEUE" if version is OfficialScenarioVersion.FIXED else "ENQUEUE_BEFORE_AUTHORIZE",
                owner_observation="UNAVAILABLE" if version is OfficialScenarioVersion.EVIDENCE_LIMITED else "AVAILABLE",
                blob_observation="UNAVAILABLE" if version is OfficialScenarioVersion.EVIDENCE_LIMITED else "AVAILABLE")
            current.scenario_version=version
            current.scenario_changed_at_us=self._clock()
            current.scenario_prepared=False
            change=self._changes.submit(current.project_id,reason="示例机械修复" if version is OfficialScenarioVersion.FIXED else "示例观察或实现条件切换",
                repair_reference=reference,submitted_by="LOCAL_GUI")
            if version is OfficialScenarioVersion.FIXED:
                current.repair_change_id=change.manifest.change_id
            else:
                current.vulnerable_change_id=change.manifest.change_id
            current.pending_tasks=("PREPARE_CURRENT_MATERIALS",)
            return self.status()

    def _require_active(self):
        current=self._current
        if current is None or not current.active or self._manager.active is None:
            raise JiejianError(ErrorCode.OFFICIAL_SAMPLE_CONFLICT,"官方示例体验当前未运行")
        return current

    def _require_idle(self,project_id):
        with self._uow_factory() as work:
            if any(item.state.value in {"PENDING","RUNNING","RETRY_WAIT"} for item in work.jobs.list_for_project(project_id)):
                raise JiejianError(ErrorCode.STATE_PRECONDITION,"官方示例仍有活动任务")

    def stop_project(self,project_id):
        with self._lock:
            current=self._current
            if current is None or not current.active or current.project_id!=project_id:
                return False
            self._require_idle(project_id)
            if self._cleanup_uncertain:
                raise JiejianError(ErrorCode.STATE_PRECONDITION, "环境清理尚未确认")
            try:
                self._manager.stop(current.runtime.experience_id)
            except Exception:
                # manager 可能已清空内存句柄；未知清理不能靠重试空 stop 伪装成功。
                self._cleanup_uncertain = True
                raise
            self._registry.unregister(project_id)
            self._secrets.clear_session(current.runtime.experience_id)
            current.active=False
            return True

    def stop(self, *, operation_id=None):
        return self._operate("stop", operation_id, self._stop)

    def _stop(self):
        with self._lock:
            if self._current is not None:
                project=self._current.project_id
                if self._current.active:
                    self.stop_project(project)
                # 前次归档失败仍必须完成该步骤，不能仅凭 active=false 报告停止成功。
                self._archive(project)
            else:
                with self._uow_factory() as work:
                    history, _ = work.environment_operations.list(2)
                previous = history[1] if len(history) > 1 else None
                if previous and (previous["experience_id"] or previous["state"] in {"PENDING", "UNKNOWN"}) and not (
                    previous["operation"] == "stop" and previous["state"] == "SUCCEEDED" and previous["cleanup_confirmed"]):
                    raise JiejianError(ErrorCode.STATE_PRECONDITION, "缺少本进程环境所有权，不能确认历史环境停止")
            self._operation_cleanup_confirmed = True
            return self.status()

    def close(self):
        if self._current is not None and self._current.active:
            self.stop()

    def _operation_progress(self, **fields):
        if self._running_operation is None:
            return
        with self._uow_factory() as work:
            value = work.environment_operations.get(self._running_operation)
            value.update(fields)
            work.environment_operations.save(value)
            work.commit()

    def _receipt_view(self, receipt):
        value = self.status()
        state = "UNKNOWN" if receipt["state"] == "PENDING" else receipt["state"]
        lifecycle = "UNKNOWN"
        if state == "SUCCEEDED" and receipt["operation"] == "stop" and receipt["cleanup_confirmed"]:
            lifecycle = "STOPPED"
        elif state == "FAILED":
            lifecycle = "FAILED"
        elif (state == "SUCCEEDED" and self._current is not None and self._current.active
              and self._current.runtime.experience_id == receipt["experience_id"] and self._manager.active is not None):
            lifecycle = "RUNNING"
        # 重放旧操作只返回其身份，不把当前另一实例冒充原回执。
        same = self._current is not None and self._current.runtime.experience_id == receipt["experience_id"]
        updates = dict(operation_id=receipt["operation_id"], operation_state=state, lifecycle=lifecycle,
            history_project_id=receipt["project_id"], last_error_code=receipt["error_code"],
            experience_id=receipt["experience_id"], project_id=receipt["project_id"], active=lifecycle == "RUNNING")
        if not same:
            updates.update(origin=None, scenario_prepared=False, scenario_version=None, scenario_changed_at_us=None,
                vulnerable_change_id=None, repair_change_id=None, pending_tasks=())
        return value.model_copy(update=updates)

    def _operate(self, operation, operation_id, action):
        """先持久接受一次操作，再执行已有生命周期；未知回执不重放副作用。"""
        operation_id = request_uuid(operation_id) if operation_id is not None else str(uuid4())
        with self._lock:
            with self._uow_factory() as work:
                existing = work.environment_operations.get(operation_id)
                if existing is not None:
                    if existing["operation"] not in (("start", "reset") if operation == "start" else ("stop",)):
                        raise JiejianError(ErrorCode.STATE_PRECONDITION, "操作标识已用于不同环境操作")
                    return self._receipt_view(existing)
                current = self._current
                latest, _ = work.environment_operations.list(1)
                indexed_current = current if current and (operation == "stop" or current.active) else None
                value = dict(operation_id=operation_id,
                    operation="reset" if operation == "start" and current and current.active else operation,
                    state="PENDING", started_at_us=max(self._clock(), latest[0]["started_at_us"] + 1 if latest else 0), finished_at_us=None,
                    project_id=indexed_current.project_id if indexed_current else latest[0]["project_id"] if operation == "stop" and latest else None,
                    experience_id=indexed_current.runtime.experience_id if indexed_current else latest[0]["experience_id"] if operation == "stop" and latest else None,
                    error_code=None, cleanup_confirmed=False)
                work.environment_operations.save(value)
                work.commit()
            self._running_operation = operation_id
            self._operation_cleanup_confirmed = False
            rejected_without_effect = False
            try:
                # 已知忙碌门禁在任何生命周期副作用之前拒绝；拒绝回执不污染仍运行的环境。
                if current is not None and current.active:
                    try:
                        self._require_idle(current.project_id)
                    except JiejianError:
                        rejected_without_effect = True
                        raise
                action()
            except Exception as exc:
                code = exc.code if isinstance(exc, JiejianError) else ErrorCode.OFFICIAL_SAMPLE_START_FAILED.value
                code = code if code in {item.value for item in ErrorCode} else ErrorCode.OFFICIAL_SAMPLE_START_FAILED.value
                try:
                    self._operation_progress(state="FAILED" if rejected_without_effect or self._operation_cleanup_confirmed else "UNKNOWN",
                        finished_at_us=max(self._clock(), value["started_at_us"]), error_code=code,
                        cleanup_confirmed=self._operation_cleanup_confirmed)
                except Exception:
                    # DB 回执保存失败时原 PENDING 在重启后投影 UNKNOWN，仍保留第一主错误。
                    pass
                if isinstance(exc, JiejianError):
                    raise
                raise JiejianError(ErrorCode(code), "官方环境操作未完成") from None
            else:
                self._operation_progress(state="SUCCEEDED", finished_at_us=max(self._clock(), value["started_at_us"]),
                    cleanup_confirmed=self._operation_cleanup_confirmed)
                return self.status()
            finally:
                self._running_operation = None

    def history(self, *, limit=25):
        if not 1 <= limit <= 100:
            raise JiejianError(ErrorCode.INPUT_INVALID, "环境历史上限为 100")
        with self._uow_factory() as work:
            items, has_more = work.environment_operations.list(limit)
        for item in items:
            item.pop("cleanup_confirmed")
            if item["state"] == "PENDING" and item["operation_id"] != self._running_operation:
                item["state"] = "UNKNOWN"
        return dict(items=items, has_more=has_more)
