# 官方体验只编排已批准业务边界、正式准备和通用检查；会话资源受控且不预制安全结论。
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from enum import StrEnum
from threading import RLock

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

    def status(self):
        current=self._current
        installation=self._manager.installation
        return OfficialExperienceView(available=installation.available,display_name=installation.display_name,
            unavailable_reason=installation.reason,active=bool(current and current.active and self._manager.active),
            experience_id=None if current is None else current.runtime.experience_id,
            project_id=None if current is None else current.project_id,origin=None if current is None else current.runtime.origin,
            scenario_prepared=bool(current and current.scenario_prepared),
            scenario_version=None if current is None else current.scenario_version,
            scenario_changed_at_us=None if current is None else current.scenario_changed_at_us,
            vulnerable_change_id=None if current is None else current.vulnerable_change_id,
            repair_change_id=None if current is None else current.repair_change_id,
            pending_tasks=() if current is None else current.pending_tasks)

    def start(self, *, consent):
        if consent is not True:
            raise JiejianError(ErrorCode.STATE_OPERATOR_REQUIRED,"启动官方示例前需要明确同意本机运行与源码复制")
        with self._lock:
            if self._current is not None and self._current.active:
                self.stop()
            runtime=self._manager.start(authorization_order="ENQUEUE_BEFORE_AUTHORIZE",owner_observation="AVAILABLE",blob_observation="AVAILABLE")
            try:
                connection=self._understanding.connect(runtime.source_root,project_name=runtime.display_name)
                project=connection.project.project_id
                value=self._understanding.confirm_endpoint(project,endpoint=runtime.origin,revision=connection.understanding.revision)
                value=self._understanding.authorize_source_analysis(project,revision=value.revision)
                self._understanding.analyze_source_for_change(project,revision=value.revision)
                self._current=_Experience(runtime,project,scenario_changed_at_us=self._clock(),pending_tasks=("HUMAN_BOUNDARY_APPROVAL_REQUIRED",))
                return self.status()
            except Exception:
                self._manager.stop(runtime.experience_id)
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
            self._manager.stop(current.runtime.experience_id)
            self._registry.unregister(project_id)
            self._secrets.clear_session(current.runtime.experience_id)
            current.active=False
            return True

    def stop(self):
        with self._lock:
            if self._current is not None and self._current.active:
                project=self._current.project_id
                self.stop_project(project)
                self._archive(project)
            return self.status()

    def close(self):
        self.stop()
