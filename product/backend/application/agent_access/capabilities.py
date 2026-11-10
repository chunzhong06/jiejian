from __future__ import annotations

import json
import time
from contextlib import nullcontext
from typing import Literal
from dataclasses import dataclass
from typing import Callable
from urllib.parse import urlencode

from pydantic import BaseModel, Field, ValidationError, create_model
from pydantic_core import to_jsonable_python

from product.backend.application.agent_access.tasks import TaskInput
from product.backend.application.agent_access.github_issues import IssueSource, IssueDelivery
from product.backend.application.checks.routines import SaveCheckRoutine
from product.backend.application.checks.routine_execution import SaveRoutineRevision, BindRoutine
from product.protocols.checks.routine_reference import RoutineReference
from product.backend.application.checks.service import ExternalRecheckCommand
from product.backend.application.preparation.materials.models import MaterialChange
from product.backend.application.preparation.proofs.commands import (
    AdoptProofSource, CancelProofPreflight, GrantProofScope, SaveProofSource, StartProofPreflight,
)
from product.backend.domain.boundaries.rule_candidates import RuleCandidateSave
from product.backend.domain.errors import ErrorCode, JiejianError
from product.backend.domain.identities.models import AuthenticationProfile
from product.backend.domain.changes.models import RuleChangeTarget
from product.backend.domain.checks.repair import CurrentRepairReference
from product.backend.domain.recording.models import RecordingPurpose
from product.protocols.preparation.operation_flow import OperationFlow, OperationFlowDraft
from product.protocols.preparation.proof_sources import RelationshipSourceMapping
from product.backend.application.preparation.flow_trials import TrialSelection,StartFlowTrial
from product.protocols.runtime.node_runtime import SqliteDatabaseCapture
from product.protocols.runtime.database_capture import DatabaseCapture
from product.protocols.web.environment import FrozenEnvironment
from product.protocols.checks.execution_request import PermissionReference
from product.protocols.checks.scenarios import BusinessScenarioRevision,ScenarioReference
from product.backend.application.preparation.models import RuleCaseDataSelection
from product.backend.infrastructure.runtime.jobs.models import RequestCancellation


@dataclass(frozen=True)
class Capability:
    key: str
    title: str
    domain: str
    level: str
    model: type[BaseModel]
    handler: Callable
    approval: bool = False
    recover: Callable | None = None
    cancel: Callable | None = None
    describe: Callable | None = None

    def __post_init__(self):
        # 生命周期试点必须成组登记；未迁移能力仍走已有适配，不伪报支持范围。
        hooks = (self.recover, self.cancel, self.describe)
        if any(hook is not None for hook in hooks) and not all(callable(hook) for hook in hooks):
            raise ValueError('能力的恢复、取消与说明必须完整登记')

    def accept(self, arguments):
        try:
            return self.model.model_validate_json(json.dumps(arguments, allow_nan=False))
        except (ValidationError, ValueError):
            raise JiejianError(ErrorCode.INPUT_INVALID, '请按当前能力的参数说明整理内容') from None

    def invoke(self, project, arguments, operation):
        return self.handler(project, arguments, operation)


def parameters(model_name, **fields):
    return create_model(model_name, __base__=TaskInput, **fields)


Empty = parameters('NoArguments')
Revision = parameters('BusinessRevision', revision=(int, Field(ge=0)))
Identity = parameters('IdentityReference', identity_id=(str, ...))
FlowReference = parameters('FlowReference', flow_id=(str, ...), revision=(int, Field(ge=1)))
SourceReference = parameters('SourceReference', source_id=(str, ...))
CandidateReference = parameters('CandidateReference', candidate_id=(str, ...), revision=(int | None, None))
PreparationReference = parameters('PreparationReference', preparation_id=(str, ...))
RecordingReference = parameters('RecordingReference', recording_id=(str, ...))
RecordingStart = parameters('RecordingStart', business_action_id=(str, ...), action_revision=(int, Field(ge=1)),
    subject_test_identity_id=(str, ...), resource_owner_test_identity_id=(str, ...), subject_slot_id=(str, ...),
    resource_owner_slot_id=(str, ...), duration_seconds=(int, Field(default=60, ge=1, le=3600)),
    purpose=(Literal['TARGET', 'OBSERVATION', 'RECOVERY'], 'TARGET'), parent_recording_id=(str | None, None),
    effect_id=(str | None, None), material_candidate=(bool, True))
RunReference = parameters('RunReference', run_id=(str, ...))
RuntimeOptions = parameters('RuntimeOptions', entry=(str, Field(min_length=1, max_length=512)),
    port=(int, Field(ge=1024, le=65535)), revision=(int, Field(ge=0)),
    build_script=(str | None, None), allow_install_scripts=(bool, False),
    sqlite=(tuple[SqliteDatabaseCapture, ...], ()),databases=(tuple[DatabaseCapture,...],()))
RuntimeStart = create_model('RuntimeStart', __base__=RuntimeOptions,
    preview_fingerprint=(str, Field(pattern=r'^[0-9a-f]{64}$')))
IdentityCreate = parameters('IdentityCreate', actor_id=(str, ...), actor_revision=(int, Field(ge=1)),
    label=(str, Field(min_length=1, max_length=128)))
IdentityConfigure = parameters('IdentityConfigure', identity_id=(str, ...),
    profile=(AuthenticationProfile, ...), expected_updated_at_us=(int, Field(ge=0)))
CheckScope = parameters('CheckScope', change_id=(str | None, None), external_recheck=(ExternalRecheckCommand | None,None),
    routine=(RoutineReference|None,None),
    scenario=(ScenarioReference|None,None),
    selected_permissions=(tuple[PermissionReference, ...] | None, Field(default=None, min_length=1, max_length=4096)))
CheckStart = create_model('CheckStart', __base__=CheckScope, expected_plan_fingerprint=(str, Field(pattern=r'^[0-9a-f]{64}$')))
ChangeReference = parameters('ChangeReference', change_id=(str | None, None))
ChangeRegistration = parameters('ChangeRegistration', expected_registration_fingerprint=(str, Field(pattern=r'^[0-9a-f]{64}$')),
    reason=(str, Field(min_length=1, max_length=2000)), claimed_paths=(tuple[str, ...], ()),
    repair_reference=(CurrentRepairReference | None, None), rule_targets=(tuple[RuleChangeTarget, ...], ()))
DeliveryReference = parameters('DeliveryReference', delivery_id=(str, ...), expected_version=(int, Field(ge=1)))
MaintenancePreview = parameters('MaintenancePreview', operation=(str, Field(pattern=r'^(clear-assistant-cache|clear-logs|clear-temporary|clear-all|repair-runtime)$')))
MaintenanceExecution = parameters('MaintenanceExecution', plan_id=(str, ...), operation=(str, Field(pattern=r'^(clear-assistant-cache|clear-logs|clear-temporary|clear-all|repair-runtime)$')),
    item_ids=(list[str] | None, None))


class ProductCapabilities:
    """HTTP 与 MCP 共用的业务能力目录；每个处理器只委托所属用例。

    level 描述动作性质，approval 表示执行前必须取得本机决定。Agent 可以
    在 PREPARE 权限下提交执行建议，该建议不会因此获得 EXECUTE 授权。
    """

    def __init__(self, core):
        self.core, self.items = core, {}
        add = self._add
        add('environments.read','读取环境与部署声明','应用与来源','READ',Empty,
            lambda p,a,o:core.application_environments.context(p))
        add('environments.save','整理环境配置','应用与来源','PREPARE',
            parameters('EnvironmentConfiguration',configuration=(FrozenEnvironment,...),expected_revision=(int,Field(ge=0))),
            lambda p,a,o:core.application_environments.save(p,a.configuration,expected_revision=a.expected_revision))
        add('environments.preview','核对切换连接的影响','应用与来源','READ',
            parameters('EnvironmentPreview',environment_id=(str,...),revision=(int,Field(ge=1))),
            lambda p,a,o:core.application_environments.activation_preview(p,**a.model_dump()))
        add('environments.activate','切换当前测试环境','应用与来源','PREPARE',
            parameters('EnvironmentSelection',environment_id=(str,...),revision=(int,Field(ge=1)),expected_revision=(int,Field(ge=0)),impact_fingerprint=(str,Field(pattern=r'^[0-9a-f]{64}$'))),
            lambda p,a,o:core.application_environments.activate(p,**a.model_dump()),approval=True)
        add('sources.read','读取接口来源与人工关联','应用与来源','READ',Empty,
            lambda p,a,o:core.application_sources.context(p))
        add('sources.preview','查看已净化来源与差异','应用与来源','PREPARE',
            parameters('ApiSourcePreview',candidate_id=(str,Field(pattern=r'^imp_[0-9a-f]{32}$')),source_id=(str|None,None)),
            lambda p,a,o:core.application_sources.preview_candidate(p,**a.model_dump()))
        add('sources.accept','保存已审阅的来源修订','应用与来源','PREPARE',
            parameters('ApiSourceAcceptance',candidate_id=(str,Field(pattern=r'^imp_[0-9a-f]{32}$')),
                source_id=(str,...),name=(str,Field(min_length=1,max_length=128)),expected_revision=(int,Field(ge=0)),expected_fingerprint=(str,Field(pattern=r'^[0-9a-f]{64}$'))),
            lambda p,a,o:core.application_sources.accept(p,**a.model_dump()))
        add('sources.candidate','将请求整理为待审业务候选','应用与来源','PREPARE',
            parameters('ApiRequestCandidate',source_id=(str,...),item_id=(str,...),expected_revision=(int,Field(ge=0))),
            lambda p,a,o:core.application_sources.propose_action(p,**a.model_dump()))
        add('sources.annotate','维护请求说明与业务关联','应用与来源','PREPARE',
            parameters('ApiRequestAnnotation',source_id=(str,...),item_id=(str,...),label=(str,Field(min_length=1,max_length=256)),
                action_id=(str|None,None),expected_revision=(int,Field(ge=0))),
            lambda p,a,o:core.application_sources.annotate(p,**a.model_dump()))
        add('application.read', '读取应用与业务线索', '接入与业务', 'READ', Empty,
            lambda p, a, o: self.read_application(p))
        add('application.analyze', '重新读取已授权业务源码', '接入与业务', 'PREPARE', Revision,
            lambda p, a, o: core.application_understanding.analyze_source(p, revision=a.revision))
        add('application.authorize_source', '确认读取当前项目的业务源码', '接入与业务', 'EXECUTE', Revision,
            lambda p, a, o: core.application_understanding.authorize_source_analysis(p, revision=a.revision), approval=True)
        add('application.endpoint', '确认当前应用访问地址', '接入与业务', 'EXECUTE',
            parameters('ApplicationEndpoint', revision=(int, Field(ge=0)), endpoint=(str, Field(min_length=1, max_length=2048))),
            lambda p, a, o: core.application_understanding.confirm_endpoint(p, revision=a.revision, endpoint=a.endpoint), approval=True)
        add('application.readiness', '查看接入和后续条件', '接入与业务', 'READ', Empty,
            lambda p, a, o: core.application_progress.readiness(p))
        add('rules.context', '读取权限要求与候选说明', '权限规则', 'READ', Empty,
            lambda p, a, o: core.rule_candidates.context(p))
        add('rules.save', '整理权限候选', '权限规则', 'PREPARE', RuleCandidateSave,
            lambda p, a, o: core.rule_candidates.save(p, a, submitted_via='MCP'))
        add('rules.candidate', '读取候选和待审要求', '权限规则', 'READ', CandidateReference,
            lambda p, a, o: core.rule_candidates.show(p, a.candidate_id, a.revision))
        add('rules.read', '查看已批准权限', '权限规则', 'READ', Empty,
            lambda p, a, o: core.business_boundaries.view(p))
        add('runtime.read', '查看实际运行实例', '运行环境', 'READ', Empty,
            lambda p, a, o: core.node_runtime.state(p, verify_artifacts=False))
        add('runtime.preview', '准备启动方案', '运行环境', 'READ', RuntimeOptions,
            lambda p, a, o: core.node_runtime.preview(p, **a.model_dump(exclude={'sqlite','databases'}), sqlite=a.sqlite,databases=a.databases))
        add('runtime.start', '准备依赖并启动应用', '运行环境', 'EXECUTE', RuntimeStart,
            lambda p, a, o: core.node_runtime.start(p, **a.model_dump(exclude={'sqlite','databases'}), sqlite=a.sqlite,databases=a.databases,
                operation_id=o, consent_execute=True), approval=True)
        add('runtime.operation', '查询原启动请求', '运行环境', 'READ', parameters('RuntimeOperation', operation_id=(str, ...)),
            lambda p, a, o: core.node_runtime.operation(p, a.operation_id))
        add('identities.list', '读取现有测试账号', '账号与身份', 'READ', Empty,
            lambda p, a, o: core.test_identities.list(p))
        add('identities.create', '建立所需测试主体', '账号与身份', 'PREPARE', IdentityCreate,
            lambda p, a, o: core.test_identities.create(p, **a.model_dump(), operation_id=o))
        add('identities.options', '复用已有认证结构', '账号与身份', 'READ', Identity,
            lambda p, a, o: self._identity(p, a.identity_id, lambda: core.test_identities.authentication_options(a.identity_id)))
        add('identities.configure', '设置账号核验方式', '账号与身份', 'PREPARE', IdentityConfigure,
            lambda p, a, o: self._identity(p, a.identity_id, lambda: core.test_identities.configure_authentication(
                a.identity_id, a.profile, expected_updated_at_us=a.expected_updated_at_us)))
        add('identities.login', '打开账号独立登录窗口', '账号与身份', 'EXECUTE', Identity,
            lambda p, a, o: self._identity(p, a.identity_id, lambda: core.identity_preparations.start(a.identity_id, operation_id=o)), approval=True)
        add('identities.verify', '核对已有账号登录', '账号与身份', 'EXECUTE', Identity,
            lambda p, a, o: self._identity(p, a.identity_id, lambda: core.identity_preparations.start(a.identity_id, operation_id=o, verify_only=True)), approval=True)
        add('identities.preparation', '读取原登录任务', '账号与身份', 'READ', PreparationReference,
            lambda p, a, o: self._preparation(p, a.preparation_id))
        add('flows.context', '读取已有操作与数据设置', '操作与数据', 'READ', Empty,
            lambda p, a, o: core.operation_flows.context(p))
        add('scenarios.context','读取业务场景与准确动作','操作与数据','READ',Empty,
            lambda p,a,o:core.business_scenarios.context(p))
        add('scenarios.read','读取准确业务场景修订','操作与数据','READ',ScenarioReference,
            lambda p,a,o:core.business_scenarios.read(p,a.scenario_id,a.revision).model_dump(mode='json'))
        add('scenarios.save','保存业务场景候选','操作与数据','PREPARE',BusinessScenarioRevision,
            lambda p,a,o:core.business_scenarios.save(p,a,submitted_via='MCP'))
        add('flows.read', '读取准确流程修订', '操作与数据', 'READ', FlowReference,
            lambda p, a, o: core.operation_flows.read(p, a.flow_id, a.revision))
        add('recordings.start', '打开独立业务录制窗口', '操作与数据', 'EXECUTE', RecordingStart,
            lambda p, a, o: self._start_recording(p, a, o), approval=True)
        add('recordings.status', '查看原录制的进度', '操作与数据', 'READ', RecordingReference,
            lambda p, a, o: self._recording_status(p, a.recording_id))
        add('recordings.context', '解释已采集的步骤与资源位置', '操作与数据', 'READ', RecordingReference,
            lambda p, a, o: core.agent_workflow.read(p, 'RECORDING', recording_id=a.recording_id))
        add('flows.recording', '复用已确认录制的操作步骤', '操作与数据', 'READ', RecordingReference,
            lambda p, a, o: core.operation_flows.recording_candidate(p, a.recording_id))
        add('flows.openapi', '从接口定义整理步骤候选', '操作与数据', 'READ',
            parameters('OpenApiDocument', document=(dict, ...)),
            lambda p, a, o: core.operation_flows.openapi_candidates(a.document))
        add('flows.candidate', '从步骤整理操作候选', '操作与数据', 'READ', OperationFlowDraft,
            lambda p, a, o: core.operation_flows.candidate(p, a))
        add('flows.save', '保存操作与恢复步骤', '操作与数据', 'PREPARE', OperationFlow,
            lambda p, a, o: core.operation_flows.save(p, a))
        add('flows.trial.preview','预览一次场景试运行','操作与数据','READ',TrialSelection,
            lambda p,a,o:core.flow_trials.preview(p,a))
        add('flows.trial.start','执行已确认的场景试运行','操作与数据','EXECUTE',StartFlowTrial,
            lambda p,a,o:core.flow_trials.start(p,a),approval=True,
            recover=lambda p,o:core.flow_trials.requested(p,o['operation_id']),
            cancel=lambda p,o,j:core.flow_trials.cancel(p,j.flow_trial_id),describe=self._describe_trial)
        add('flows.trial.history','读取场景试运行历史','操作与数据','READ',Empty,
            lambda p,a,o:core.flow_trials.history(p))
        trial_reference=parameters('FlowTrialReference',trial_id=(str,Field(pattern=r'^ftr_[0-9a-f]{32}$')))
        add('flows.trial.read','读取原场景试运行','操作与数据','READ',trial_reference,
            lambda p,a,o:core.flow_trials.read(p,a.trial_id))
        add('flows.trial.cancel','取消原场景试运行','操作与数据','EXECUTE',trial_reference,
            lambda p,a,o:core.flow_trials.cancel(p,a.trial_id),approval=True)
        add('flows.adopt', '采用这份操作与恢复步骤', '操作与数据', 'EXECUTE', FlowReference,
            lambda p, a, o: core.operation_flows.adopt(p, a.flow_id, a.revision), approval=True)
        add('materials.read', '读取材料缺口与可复用内容', '检查材料', 'READ', Empty,
            lambda p, a, o: core.preparation_guidance.context(p))
        add('materials.rule_data', '读取各条规则的测试数据', '检查材料', 'READ', Empty,
            lambda p, a, o: core.preparation.case_data(p))
        add('materials.select_data', '选择这条规则的测试数据', '检查材料', 'PREPARE', RuleCaseDataSelection,
            lambda p, a, o: core.preparation.bind_case_data(p, **{
                **a.model_dump(exclude={'permission'}), 'permission': a.permission}))
        add('materials.preview', '核对材料更换影响', '检查材料', 'READ', MaterialChange,
            lambda p, a, o: core.preparation_materials.preview(p, a))
        add('materials.apply', '采用材料更换', '检查材料', 'EXECUTE', MaterialChange,
            lambda p, a, o: core.preparation_materials.apply(p, a), approval=True)
        add('proofs.context', '读取结果证明配置与缺口', '结果证明', 'READ', Empty,
            lambda p, a, o: core.proof_preparation.context(p))
        add('proofs.sqlite_candidate', '从已声明数据库准备判断方式', '结果证明', 'READ',
            parameters('SqliteProofCandidate', basis_id=(str, ...), action_id=(str, ...), effect_id=(str, ...),
                resource_binding_id=(str, ...), database_path=(str, ...), table=(str, ...), protected_column=(str, ...),
                tenant_column=(str|None,None),condition_state_column=(str|None,None),identity_tenant_path=(str|None,None),
                relationship_mapping=(RelationshipSourceMapping|None,None)),
            lambda p, a, o: core.proof_preparation.sqlite_candidate(p, **a.model_dump()))
        add('proofs.save', '保存结果判断方式候选', '结果证明', 'PREPARE', SaveProofSource,
            lambda p, a, o: core.proof_preparation.save(p, a, submitted_via='MCP', client_name='协作任务')['result'])
        from product.protocols.preparation.proof_sources import AsyncExportMapping
        add('proofs.database_candidate','从服务库声明整理判断方式','结果证明','READ',
            parameters('DatabaseProofCandidate',basis_id=(str,...),action_id=(str,...),effect_id=(str,...),resource_binding_id=(str,...),
                connection_id=(str,...),protected_column=(str,...),tenant_column=(str|None,None),condition_state_column=(str|None,None),
                identity_tenant_path=(str|None,None),relationship_mapping=(RelationshipSourceMapping|None,None)),
            lambda p,a,o:core.proof_preparation.database_candidate(p,**a.model_dump()))
        add('proofs.file_candidate','整理直接或异步文件证明','结果证明','READ',
            parameters('FileProofCandidate',basis_id=(str,...),action_id=(str,...),effect_id=(str,...),resource_binding_id=(str,...),
                collection=(str,Field(pattern=r'^[A-Za-z][A-Za-z0-9_]{0,63}$')),async_export=(AsyncExportMapping|None,None)),
            lambda p,a,o:core.proof_preparation.file_candidate(p,**{name:getattr(a,name) for name in type(a).model_fields}))
        add('proofs.scope', '确认业务记录读取范围', '结果证明', 'EXECUTE', GrantProofScope,
            lambda p, a, o: core.proof_preparation.grant_scope(p, a)['result'], approval=True)
        add('proofs.preflight', '核对结果证明能否取得', '结果证明', 'EXECUTE', StartProofPreflight,
            lambda p, a, o: core.proof_preparation.start(p, a)['result'], approval=True)
        add('proofs.adopt', '采用已核对的结果证明', '结果证明', 'EXECUTE', AdoptProofSource,
            lambda p, a, o: core.proof_preparation.adopt(p, a)['result'], approval=True)
        add('checks.preview', '核对本次检查范围', '检查与结果', 'READ', CheckScope,
            lambda p, a, o: core.checks.preview(p, change_id=a.change_id, selected_permissions=a.selected_permissions, external_recheck=a.external_recheck,scenario_reference=a.scenario,routine_reference=a.routine))
        add('checks.plans', '读取完整检查方案目录与旧保存范围', '检查与结果', 'READ',
            parameters('RoutineCatalog',after=(str|None,Field(default=None,pattern=r'^csp_[0-9a-f]{32}$')),limit=(int,Field(default=50,ge=1,le=50))),
            lambda p,a,o:core.check_routines.revisions.catalog(p,a.after,a.limit))
        add('checks.plan_save', '保存完整检查方案的新修订', '检查与结果', 'PREPARE', SaveRoutineRevision,
            lambda p,a,o:core.check_routines.revisions.save(p,a))
        add('checks.plan_read', '读取准确的检查方案修订', '检查与结果', 'READ',
            parameters('RoutineRevision',routine_id=(str,Field(pattern=r'^csp_[0-9a-f]{32}$')),revision=(int,Field(ge=1))),
            lambda p,a,o:core.check_routines.revisions.read(p,a.routine_id,a.revision))
        add('checks.plan_binding_preview', '核对方案在当前环境的材料与变化', '检查与结果', 'READ',
            parameters('RoutineBindingPreview',routine_id=(str,Field(pattern=r'^csp_[0-9a-f]{32}$')),revision=(int,Field(ge=1))),
            lambda p,a,o:core.check_routines.revisions.binding_preview(p,a.routine_id,a.revision))
        add('checks.plan_bind', '确认方案在当前环境的公开绑定', '检查与结果', 'PREPARE',
            create_model('BindRoutineRequest',__base__=BindRoutine,routine_id=(str,Field(pattern=r'^csp_[0-9a-f]{32}$'))),
            lambda p,a,o:core.check_routines.revisions.bind(p,a.routine_id,BindRoutine(**a.model_dump(exclude={'routine_id'}))))
        add('checks.routines', '读取保存的检查范围及变化', '检查与结果', 'READ', Empty,
            lambda p, a, o: core.check_routines.list(p))
        add('checks.remember', '保存本次规则选择供以后使用', '检查与结果', 'PREPARE', SaveCheckRoutine,
            lambda p, a, o: core.check_routines.save(p, a))
        add('checks.start', '执行已核对的检查', '检查与结果', 'EXECUTE', CheckStart,
            lambda p, a, o: self._start_check(p, a, o), approval=True,
            recover=self._check_receipt,cancel=lambda p,o,j:core.checks.cancel(p,o['result']['run_id']),
            describe=self._describe_check)
        add('checks.status', '读取本次检查与结果状态', '检查与结果', 'READ', RunReference,
            lambda p, a, o: core.check_results.status(a.run_id, project_id=p))
        add('checks.compare', '比较准确检查记录的变化与限制', '检查与结果', 'READ',
            parameters('CompareRuns',baseline=(str,Field(pattern=r'^run_[0-9a-f]{32}$')),current=(str,Field(pattern=r'^run_[0-9a-f]{32}$')),
                earlier=(str|None,Field(default=None,pattern=r'^run_[0-9a-f]{32}$')),after=(str|None,Field(default=None,pattern=r'^[0-9a-f]{64}$')),
                limit=(int,Field(default=25,ge=1,le=50))),
            lambda p,a,o:core.check_comparison.compare(p,a.baseline,a.current,earlier=a.earlier,after=a.after,limit=a.limit))
        add('results.report', '理解检查要求和实际结果', '检查与结果', 'READ', RunReference,
            lambda p, a, o: core.check_story.build(a.run_id, project_id=p))
        add('results.evidence', '读取具体场景的证明记录', '检查与结果', 'READ',
            parameters('EvidenceReference', run_id=(str, ...), case_id=(str, ...), evidence_id=(str, ...), record_id=(str | None, None)),
            lambda p, a, o: core.check_results.evidence_records(a.run_id, a.evidence_id, a.case_id, project_id=p, record_id=a.record_id))
        add('checks.cancel', '停止本次检查并收口', '检查与结果', 'EXECUTE', RunReference,
            lambda p, a, o: core.checks.cancel(p, a.run_id), approval=True)
        add('changes.preview', '核对实际代码变化与修复目标', '修改与复验', 'READ', Empty,
            lambda p, a, o: core.development.registration_preview(p))
        add('changes.history', '读取修改与验证关联', '修改与复验', 'READ', Empty,
            lambda p, a, o: core.development_reader.history(p))
        add('changes.register', '登记实际修改与涉及的权限', '修改与复验', 'PREPARE', ChangeRegistration,
            lambda p, a, o: core.development.register_change(p, **a.model_dump(exclude={'repair_reference','rule_targets'}),
                repair_reference=a.repair_reference, rule_targets=a.rule_targets, operation_id=o, submitted_by='Agent 协作'))
        add('changes.load', '加载这次交付并保留复验关联', '修改与复验', 'EXECUTE', DeliveryReference,
            lambda p, a, o: core.runtime_activation.activate(p, a.delivery_id, operation_id=o, expected_version=a.expected_version), approval=True)
        add('changes.status', '查询原交付加载', '修改与复验', 'READ', parameters('DeliveryOperation', operation_id=(str, ...)),
            lambda p, a, o: core.runtime_activation.receipt(p, a.operation_id))
        add('repair.read', '读取原问题与正常功能要求', '修改与复验', 'READ', Empty,
            lambda p, a, o: core.project_repair.evaluate(p))
        add('repair.requirements', '读取这份报告的原题要求', '修改与复验', 'READ', RunReference,
            lambda p, a, o: self._repair_requirements(p, a.run_id))
        add('proofs.status', '查询原证明核对', '结果证明', 'READ', parameters('PreflightReference', preflight_id=(str, ...)),
            lambda p, a, o: core.proof_preparation.status(p, a.preflight_id))
        add('recovery.activity', '找回正在执行或未收口的任务', '恢复与维护', 'READ', Empty,
            lambda p, a, o: core.application_progress.activity(p))
        add('system.status', '读取执行服务状态', '恢复与维护', 'READ', Empty,
            lambda p, a, o: core.worker_status())
        add('maintenance.status', '查看本机存储与维护状态', '恢复与维护', 'READ', Empty,
            lambda p, a, o: core.maintenance.status())
        add('maintenance.preview', '整理本机清理计划', '恢复与维护', 'PREPARE', MaintenancePreview,
            lambda p, a, o: core.maintenance.preview(a.operation))
        add('maintenance.execute', '按已列明的计划清理本机存储', '恢复与维护', 'EXECUTE', MaintenanceExecution,
            lambda p, a, o: core.maintenance.execute(a.plan_id, expected_scope=a.operation, item_ids=a.item_ids), approval=True)
        add('updates.status', '读取当前版本与更新状态', '恢复与维护', 'READ', Empty,
            lambda p, a, o: core.updates.info())
        add('updates.preview', '核对本地更新包兼容性', '恢复与维护', 'PREPARE',
            parameters('UpdatePreview', directory=(str, Field(min_length=1, max_length=32768)), return_path=(str, '/')),
            lambda p, a, o: core.updates.preview(a.directory, a.return_path), approval=True)

        add('github.issue_draft','准备当前问题的GitHub工单正文','协作交付','READ',IssueSource,
            lambda p,a,o:core.github_issues.draft(p,a))
        add('github.issue_create','在 GitHub 中跟进这个问题','协作交付','EXECUTE',IssueDelivery,
            lambda p,a,o:core.github_issues.send(p,a,o),approval=True)

    def _add(self, key, title, domain, level, model, handler, approval=False, **lifecycle):
        self.items[key] = Capability(key, title, domain, level, model, handler, approval, **lifecycle)

    def get(self, key):
        if key not in self.items:
            raise JiejianError(ErrorCode.INPUT_INVALID, '当前产品未提供这项协作能力')
        return self.items[key]

    def catalog(self, *, schemas=False):
        # 常规上下文只交付摘要，参数 Schema 按需读取，避免每轮重复装入所有表单。
        return [dict(key=c.key, title=c.title, domain=c.domain, level=c.level, requires_review=c.approval,
            **({'arguments': c.model.model_json_schema()} if schemas else {})) for c in self.items.values()]

    def read_application(self, project):
        current = self.core.application_understanding.get(project)
        value = self.public(current)
        # Agent 修复需要定位已授权目录；这不授予额外文件读取或源码写入权限。
        if not current.source_analysis_authorized:
            value.pop('source_root', None)
        for key in ('source_fingerprint', 'endpoint_source_fingerprint'):
            value.pop(key, None)
        for key in ('role_candidates', 'action_candidates'):
            for candidate in value.get(key, []):
                candidate.pop('evidence', None)
        return value

    def _identity(self, project, identity, action):
        if not any(item.identity_id == identity for item in self.core.test_identities.list(project)):
            raise JiejianError(ErrorCode.RECORD_NOT_FOUND, '账号不属于当前应用')
        return action()

    def _preparation(self, project, preparation):
        result = self.core.identity_preparations.status(preparation)
        if result.project_id != project:
            raise JiejianError(ErrorCode.RECORD_NOT_FOUND, '登录任务不属于当前应用')
        return result

    def _start_recording(self, project, arguments, operation):
        values = arguments.model_dump(exclude={'purpose'})
        result = self.core.project_recordings.submit(project, **values, purpose=RecordingPurpose(arguments.purpose),
            resource_owner_confirmed=True, idempotency_key=operation, headless=False)
        return dict(recording_id=result.result.recording.recording_id, job_id=result.result.job.job_id,
            action_id=arguments.business_action_id, state=result.result.job.state.value)

    def _recording_status(self, project, recording):
        value = self.core.recording_lifecycle.status(recording)
        if value.recording.project_id != project:
            raise JiejianError(ErrorCode.RECORD_NOT_FOUND, '录制不属于当前应用')
        return dict(recording_id=recording, state=value.recording.state.value, capture_phase=value.capture_phase,
            draft_revision=None if value.draft is None else value.draft.revision,
            step_count=0 if value.draft is None else len(value.draft.steps))

    def _repair_requirements(self, project, run):
        self.core.check_results.status(run, project_id=project)
        return dict(requirements=self.core.check_repairs.contracts(run))

    def activity(self, project):
        return self.core.application_progress.activity(project)['items']

    def latest_check(self, project, operations):
        """投影任务最近一次已提交检查；仅读权威 Run，不重复展开报告和证据。"""
        operation = next((item for item in reversed(operations)
            if item['capability'] == 'checks.start' and item['state'] == 'SUCCEEDED'), None)
        if operation is None:
            return None
        with self.core.uow_factory() as work:
            run = work.runs.get(operation['result']['run_id'])
            if run is None or run.project_id != project:
                raise JiejianError(ErrorCode.STORAGE_STATE, '协作任务的检查关联不完整')
            return dict(run_id=run.run_id, lifecycle=run.lifecycle.value,
                verdict=None if run.verdict is None else run.verdict.value,
                selected_scope=operation['arguments'].get('selected_permissions') is not None,
                revalidation=operation['arguments'].get('change_id') is not None)

    def goal_outcome(self, project, task):
        """完成依据来自原业务所有者；协作结束和安全通过始终分开。"""
        task = {**task, 'operations':task['operations'][task.get('goal_operation_baseline',0):]}
        purpose, refs = task['purpose'], task['references']
        check = self.latest_check(project, task['operations'])
        if purpose in ('CHECK','UNDERSTAND') and refs.get('run_id') and not check:
            read = refs['run_id'] in task.get('read_reports', [])
            return dict(fulfilled=read, title='指定报告已读取' if read else '等待读取指定报告',
                destination='/reports?run_id='+refs['run_id'])
        if purpose in ('REPAIR','CHECK_AND_REPAIR'):
            sources = {refs['run_id']} if refs.get('run_id') else set()
            with self.core.uow_factory() as work:
                for operation in task['operations']:
                    if operation['capability']=='checks.start' and operation['state']=='SUCCEEDED':
                        run = work.runs.get(operation['result']['run_id'])
                        if run and run.verdict and run.verdict.value=='BLOCK': sources.add(run.run_id)
            if purpose=='CHECK_AND_REPAIR' and not sources:
                ready = bool(check and check['lifecycle']=='COMPLETED' and check['verdict']=='PASS')
                return dict(fulfilled=ready, title='本次检查未发现权限问题' if ready else '等待检查及必要的问题处理',
                    destination='/reports?run_id='+check['run_id'] if check else '/reports?plan=1')
            repair = self.core.project_repair.evaluate(project)
            relevant = [item for item in repair.tasks if any(event.source_run_id in sources for event in item.history)]
            verified = bool(relevant) and all(item.status == 'VERIFIED' for item in relevant)
            return dict(fulfilled=verified, title='原问题已解决，正常功能保留' if verified else '原问题仍需取得完整复验依据',
                destination='/reports?run_id='+check['run_id'] if check else '/changes')
        if purpose == 'CHECK':
            ready = check is not None and check['lifecycle'] == 'COMPLETED' and check['verdict'] is not None
            return dict(fulfilled=ready, title='本次检查报告已形成' if ready else '等待本次检查报告',
                destination='/reports?run_id='+check['run_id'] if check else '/reports?plan=1')
        if purpose == 'RULES':
            saved = any(item['capability'] == 'rules.save' and item['state'] == 'SUCCEEDED' for item in task['operations'])
            ready = saved and not self.pending_reviews(project, task['operations'])
            return dict(fulfilled=ready, title='权限要求已处理' if ready else '权限要求尚需整理或审阅', destination='/permissions')
        if purpose == 'SETUP':
            editor = task.get('editor')
            if editor and editor['kind']=='SCENARIO':
                document=editor['document']
                saved=any(item['capability']=='scenarios.save' and item['state']=='SUCCEEDED'
                    and item['result']['id']==document['id'] and item['result']['revision']>=document['revision'] for item in task['operations'])
                ready=saved and not self.pending_reviews(project,task['operations'])
                return dict(fulfilled=ready,
                    title='业务场景已整理并审阅' if ready else '业务场景候选等待审阅' if saved else '等待业务场景候选',
                    destination='/testing?'+urlencode(dict(scenario=document['id'])))
            if editor and editor['kind'] == 'FLOW':
                flows = self.core.operation_flows.context(project)['flows']
                ready = any(item['document']['id'] == editor['flow_id'] and
                    item['document']['revision'] >= editor['revision'] and item['in_use'] and
                    item['configuration_current'] for item in flows)
                return dict(fulfilled=ready, title='本次流程已核对并用于检查' if ready else '等待本次流程补全及审阅采用',
                    destination='/testing?'+urlencode(dict(action_id=editor['action_id'],flow_id=editor['flow_id'],resume_draft='1')))
            if editor and editor['kind'] == 'PROOF':
                sources = self.core.proof_preparation.context(project)['sources']
                saved = {item['result']['source_id'] for item in task['operations']
                    if item['capability']=='proofs.save' and item['state']=='SUCCEEDED'}
                ready = any(item['source_id'] in saved and item['config']['action_id']==editor['action_id'] and
                    item['config']['effect_id']==editor['effect_id'] and item['adopted'] and item['usable'] for item in sources)
                return dict(fulfilled=ready, title='本次结果证明已核对并采用' if ready else '等待结果证明补全及审阅采用',
                    destination='/preparation?proof_sources=1&action_id='+editor['action_id'])
            preview = self.core.checks.preview(project)
            return dict(fulfilled=preview.can_execute, title='本次检查材料已齐备' if preview.can_execute else '检查材料仍有缺口', destination='/preparation')
        if purpose == 'UNDERSTAND':
            ready = task.get('application_read', False)
            return dict(fulfilled=ready, title='应用业务内容已读取' if ready else '等待读取应用业务内容', destination='/application')
        if purpose == 'MAINTENANCE':
            executed = [item for item in task['operations'] if item['capability']=='maintenance.execute']
            ready = bool(executed) and all(item['state']=='SUCCEEDED' for item in executed)
            return dict(fulfilled=ready, title='维护操作已取得结果' if ready else '等待本次维护结果', destination='/storage')
        # 未声明产物判据的目标留给用户核对，不能退化为按工具调用次数宣布完成。
        return dict(fulfilled=False, title='核对本次产物后结束协作', destination='/preparation' if purpose == 'SETUP' else '/application')

    def pending_reviews(self, project, operations, *, work=None):
        latest_flows = {}
        latest_proofs = {}
        latest_scenarios={item['result']['id']:max(other['result']['revision'] for other in operations
            if other['capability']=='scenarios.save' and other['state']=='SUCCEEDED' and other['result']['id']==item['result']['id'])
            for item in operations if item['capability']=='scenarios.save' and item['state']=='SUCCEEDED'}
        for item in operations:
            if item['capability']=='flows.save' and item['state']=='SUCCEEDED':
                result=item['result']
                latest_flows[result['id']]=max(latest_flows.get(result['id'],0),result['revision'])
            if item['capability']=='proofs.save' and item['state']=='SUCCEEDED':
                result=item['result']
                latest_proofs[result['source_id']]=max(latest_proofs.get(result['source_id'],0),result['revision'])
        candidates = [item['result']['candidate']['candidate_id'] for item in operations
            if item['capability'] == 'rules.save' and item['state'] == 'SUCCEEDED']
        reviews = self.core.rule_candidates.pending_reviews(project, candidates, work=work)
        for item in reviews:
            item['action_label'] = '审阅权限要求'
        with (self.core.uow_factory() if work is None else nullcontext(work)) as work:
            for operation in operations:
                if operation['capability']=='scenarios.save' and operation['state']=='SUCCEEDED':
                    result=operation['result']
                    if result['revision']==latest_scenarios[result['id']] and work.business_scenarios.reviewed_revision(project,result['id'])<result['revision']:
                        reviews.append(dict(id=result['id']+'@'+str(result['revision']),title='核对 Agent 整理的业务实验',
                            action_label='审阅场景与正常对照',destination='/testing?'+urlencode(dict(scenario=result['id'],revision=result['revision']))))
                if operation['capability']=='proofs.save' and operation['state']=='SUCCEEDED':
                    result=operation['result']
                    if result['revision']!=latest_proofs[result['source_id']]:
                        continue
                    source=work.proof_sources.source(project,result['source_id'])
                    if source is None:
                        raise JiejianError(ErrorCode.STORAGE_STATE,'协作任务的证明关联不完整')
                    adoption=work.proof_sources.adoption(project,source.source_id)
                    if adoption is None or adoption.revision!=source.revision:
                        reviews.append(dict(id=source.source_id,title='核对 Agent 整理的结果判断依据',action_label='审阅判断方式与读取范围',
                            destination='/preparation?'+urlencode(dict(proof_sources='1',source_id=source.source_id,revision=result['revision']))))
                if operation['capability'] == 'flows.save' and operation['state'] == 'SUCCEEDED':
                    result = operation['result']
                    if result['revision'] != latest_flows[result['id']]:
                        continue
                    document = work.operation_flows.get(result['id'], result['revision'])
                    if document is None or document.project_id != project:
                        raise JiejianError(ErrorCode.STORAGE_STATE, '协作任务的流程关联不完整')
                    used=work.action_preparation.execution(document.business_action_id,document.action_revision)
                    adopted=used is not None and used.operation_flow_id==document.id and used.operation_flow_revision>=document.revision
                    if not adopted:
                        reviews.append(dict(id=document.id+'@'+str(document.revision), title='核对 Agent 整理的执行与恢复步骤',
                            action_label='比较并审阅流程', destination='/testing?'+urlencode(dict(action_id=document.business_action_id,
                            flow_id=document.id, revision=document.revision, review='1'))))
                if operation['capability'] != 'recordings.start' or operation['state'] != 'SUCCEEDED':
                    continue
                recording = work.recordings.get(operation['result']['recording_id'])
                if recording is None or recording.project_id != project:
                    raise JiejianError(ErrorCode.STORAGE_STATE, '协作任务的录制关联不完整')
                if recording.state.value == 'PENDING_REVIEW':
                    reviews.append(dict(id=recording.recording_id, title='确认录制的目标操作与测试数据',
                        action_label='核对录制步骤', destination=self._recording_destination(recording)))
        return reviews

    @staticmethod
    def _recording_destination(recording):
        kind = {'TARGET': 'execution', 'OBSERVATION': 'evidence', 'RECOVERY': 'recovery'}[recording.purpose.value]
        return '/preparation?' + urlencode(dict(action_id=recording.business_action_id, material_kind=kind,
            member_id=recording.effect_id if kind == 'evidence' else recording.resource_owner_test_identity_id,
            recording_id=recording.recording_id))

    @staticmethod
    def _operation_job(work, result):
        # 交付加载回执属于开发用例；按其真实加载引用找 Job，不额外保存一份生命周期。
        if not isinstance(result, dict):
            return None
        if result.get('job_id'):
            return work.jobs.get(result['job_id'])
        if result.get('runtime_load_id'):
            return work.jobs.get_by_runtime_load(result['runtime_load_id'])
        return None

    def operation_progress(self, project, operations, *, limit=8, work=None):
        """回读本任务提交的后台生命周期；成功回执与后台终态各自展示，不重复读报告包。"""
        items = []
        with (self.core.uow_factory() if work is None else nullcontext(work)) as work:
            for operation in operations:
                result = operation['result']
                if not isinstance(result, dict) or not (result.get('job_id') or result.get('runtime_load_id')):
                    continue
                job = self._operation_job(work, result)
                if job is None or job.project_id != project:
                    raise JiejianError(ErrorCode.STORAGE_STATE, '协作任务的业务执行关联不完整')
                phase = 'CANCELLING' if job.cancel_requested_at_us is not None and job.state.value not in ('SUCCEEDED', 'FAILED', 'CANCELLED') else job.state.value
                if job.run_id:
                    destination = '/reports?run_id=' + job.run_id
                elif job.flow_trial_id:
                    trial=work.flow_trials.get(project,job.flow_trial_id)
                    destination='/testing?action_id='+trial.plan.flow.business_action_id+'&trial_id='+job.flow_trial_id
                elif job.identity_preparation_id:
                    destination = '/preparation?identities=1&preparation_id=' + job.identity_preparation_id
                elif job.preflight_id:
                    destination = '/preparation?proof_sources=1&preflight_id=' + job.preflight_id
                elif job.recording_id:
                    recording = work.recordings.get(job.recording_id)
                    destination = self._recording_destination(recording)
                else:
                    destination = '/application'
                items.append(dict(id=job.job_id, label=operation['title'], phase=phase, destination=destination))
        return items[-limit:] if limit else items

    def _start_check(self, project, arguments, operation):
        result = self.core.checks.submit(project, **arguments.model_dump(exclude={'selected_permissions','external_recheck','scenario','routine'}), selected_permissions=arguments.selected_permissions, external_recheck=arguments.external_recheck,scenario_reference=arguments.scenario,routine_reference=arguments.routine, idempotency_key=operation)
        return dict(run_id=result.run.run_id, job_id=result.job.job_id, state=result.job.state.value)

    def cancel_owned(self, project, operations):
        """只取消回执明确归属本任务的执行，不停止同项目其他人的工作或整个运行实例。"""
        progress = self.operation_progress(project, operations, limit=None)
        active = {item['id'] for item in progress if item['phase'] not in ('SUCCEEDED', 'FAILED', 'CANCELLED')}
        for operation in operations:
            result = operation['result']
            with self.core.uow_factory() as work:
                job = self._operation_job(work, result)
            if job is None or job.job_id not in active:
                continue
            key = operation['capability']
            capability = self.items.get(key)
            if capability is not None and capability.cancel is not None:
                capability.cancel(project, operation, job)
            elif key in ('identities.login', 'identities.verify'):
                self.core.identity_preparations.cancel(result['preparation_id'])
            elif key in ('runtime.start', 'changes.load'):
                self.core.node_runtime.cancel(project, operation['operation_id'])
            elif key == 'proofs.preflight':
                self.core.proof_preparation.cancel(project, CancelProofPreflight(
                    operation_id=operation['operation_id'], preflight_id=result['preflight_id']))
            elif key == 'recordings.start':
                self.core.job_queue.request_cancellation(RequestCancellation(job_id=job.job_id, now_us=time.time_ns() // 1000))

    def receipt(self, project, operation):
        """适配各业务所有者的原请求查询；这里不以当前资源状态猜测写入是否成功。"""
        key, identifier, args = operation['capability'], operation['operation_id'], operation['arguments']
        if key=='github.issue_create':return self.core.github_issues.reconcile(project,operation)
        capability = self.items.get(key)
        if capability is not None and capability.recover is not None:
            return capability.recover(project, operation)
        if key == 'runtime.start': return self.core.node_runtime.operation(project, identifier)
        if key == 'identities.create': return self.core.test_identities.created(project, identifier)
        if key in ('identities.login', 'identities.verify'):
            return self._identity(project, args['identity_id'], lambda: self.core.identity_preparations.requested(args['identity_id'], identifier))
        if key == 'materials.apply': return self.core.preparation_materials.receipt(project, identifier)
        if key == 'changes.register': return self.core.development_reader.receipt(project, 'DELIVER', identifier)
        if key == 'changes.load': return self.core.runtime_activation.receipt(project, identifier)
        if key == 'proofs.save': return self.core.proof_preparation.receipt(project, 'SAVE_SOURCE', identifier)['result']
        if key == 'proofs.preflight': return self.core.proof_preparation.receipt(project, 'START_PREFLIGHT', identifier)['result']
        if key == 'recordings.start':
            with self.core.uow_factory() as work:
                job = work.jobs.get_by_idempotency(project, 'BROWSER_RECORDING', identifier)
                return None if job is None else dict(recording_id=job.recording_id, job_id=job.job_id, state=job.state.value)
        return None

    def describe(self, project, key, arguments):
        """把本次具名参数映射成可审阅的业务对象；真实执行仍核对自己的当前前提。"""
        rows = []
        values = arguments.model_dump(mode='json')
        capability = self.items.get(key)
        if capability is not None and capability.describe is not None:
            return capability.describe(project, arguments)
        if key=='github.issue_create':return self.core.github_issues.describe(project,arguments)
        if key.startswith('runtime.'):
            rows += [dict(label='运行入口', value=values['entry']), dict(label='本地端口', value=str(values['port']))]
            for database in values.get('sqlite', []):
                rows.append(dict(label='观察业务数据', value=database['relative_path'] + ' / ' + '、'.join(item['table'] for item in database['tables'])))
            if values.get('build_script'): rows.append(dict(label='构建步骤', value=values['build_script']))
        elif key.startswith('identities.') and 'identity_id' in values:
            identity = next((item for item in self.core.test_identities.list(project) if item.identity_id == values['identity_id']), None)
            if identity is None: raise JiejianError(ErrorCode.RECORD_NOT_FOUND, '账号不属于当前应用')
            rows.append(dict(label='测试账号', value=identity.label))
        elif key == 'recordings.start':
            identities = {item.identity_id: item for item in self.core.test_identities.list(project)}
            action = next((item for item in self.core.business_boundaries.view(project).actions if item.action_id == values['business_action_id']), None)
            if action is None or not {values['subject_test_identity_id'], values['resource_owner_test_identity_id']} <= identities.keys():
                raise JiejianError(ErrorCode.RECORD_NOT_FOUND, '录制操作或账号不属于当前应用')
            rows += [dict(label='录制操作', value=action.display_name),
                dict(label='操作账号', value=identities[values['subject_test_identity_id']].label),
                dict(label='数据所有者', value=identities[values['resource_owner_test_identity_id']].label)]
        elif key == 'flows.adopt':
            document=self.core.operation_flows.read(project,values['flow_id'],values['revision'])
            actions=self.core.business_boundaries.view(project).actions
            action=next((item for item in actions if (item.action_id,item.revision)==(document.business_action_id,document.action_revision)),None)
            if action is None:
                raise JiejianError(ErrorCode.STATE_PRECONDITION,'业务操作已变化，请重新审阅流程')
            rows += [dict(label='业务操作',value=action.display_name),dict(label='采用修订',value=str(document.revision)),
                dict(label='执行请求',value='；'.join(step.request_template.method+' '+step.request_template.path for step in document.workflow.steps)),
                dict(label='采用后',value='后续检查使用这份流程；既有报告及旧修订保留')]
        elif key.startswith('proofs.') and 'source_id' in values:
            source = self.core.proof_preparation.show(project, values['source_id'])
            config = source['config']
            rows.append(dict(label='结果证明', value=config.get('label') or config.get('name') or '当前业务结果的已选来源'))
            if key == 'proofs.scope':
                context = self.core.proof_preparation.context(project)
                resources = [item['resource_id'] for item in context['resources']
                    if item['resource_binding_id'] == config['resource_binding_id']
                    or item.get('case_specific') and item['action_id'] == config['action_id']]
                rows.append(dict(label='测试数据', value='、'.join(dict.fromkeys(resources))))
                if config.get('database_path'):
                    rows.append(dict(label='数据库与表', value=config['database_path'] + ' / ' + config['table']))
                    rows.append(dict(label='读取字段', value='、'.join(config['observed_columns'])))
        elif key == 'maintenance.execute':
            rows.append(dict(label='影响范围', value='本机已预览的存储清理计划，应用、规则与报告保留'))
        elif key == 'application.authorize_source':
            rows.append(dict(label='读取范围', value='当前已选项目的业务源码'))
        elif key == 'application.endpoint':
            rows.append(dict(label='应用访问地址', value=values['endpoint']))
        return rows

    def _describe_trial(self, project, arguments):
        rows = []
        preview=self.core.flow_trials.preview(project,arguments.selection)
        if preview['plan_hash']!=arguments.plan_hash:
            raise JiejianError(ErrorCode.STATE_PRECONDITION,'场景或账号已变化，请重新预览')
        plan=preview['plan'];case=plan['case']
        identities={item.identity_id:item.label for item in self.core.test_identities.list(project)}
        rows += [dict(label='目标地址',value=plan['runtime']['target']['base_url']),
            dict(label='场景修订',value=str(plan['flow']['revision'])),dict(label='操作账号',value=identities[case['subject_test_identity_id']]),
            dict(label='资源所有者',value=identities[case['resource_owner_test_identity_id']]),dict(label='资源编号',value=case['resource_id']),
            dict(label='请求预算',value=str(plan['runtime']['budget']['max_requests'])+' 次'),
            dict(label='本次操作',value='只执行原恢复请求' if plan['mode']=='RESTORE' else '执行一次场景，保留有限步骤事实')]
        if plan['mode']=='TRIAL':
            rows += [dict(label='受检操作' if step['purpose']=='TARGET' else '准备步骤',value=step['request_template']['method']+' '+step['request_template']['path']) for step in plan['flow']['workflow']['steps']]
        if plan['state_changing']:
            recovery=plan['flow']['recovery'];rows.append(dict(label='恢复请求',value=recovery['method']+' '+recovery['relative_path']))
        return rows

    def _describe_check(self, project, arguments):
        rows = []
        values = arguments.model_dump(mode='json')
        scope = arguments
        plan = self.core.checks.preview(project, change_id=scope.change_id, selected_permissions=scope.selected_permissions, external_recheck=scope.external_recheck,scenario_reference=scope.scenario,routine_reference=scope.routine)
        if plan.plan_fingerprint != values['expected_plan_fingerprint']:
            raise JiejianError(ErrorCode.STATE_PRECONDITION, '检查范围已变化，请读取新的检查预览')
        if scope.external_recheck is not None:
            rows.append(dict(label='原问题',value=scope.external_recheck.reference.source_run_id))
            rows.append(dict(label='本次部署声明',value=scope.external_recheck.deployment_statement+'；部署版本未核对'))
        if scope.routine is not None:
            document=self.core.check_routines.revisions.read(project,scope.routine.routine_id,scope.routine.revision)
            rows.append(dict(label='检查方案',value=document.name+' · 第 '+str(document.revision)+' 修订'))
            rows.append(dict(label='环境绑定',value=scope.routine.binding_id))
        rows.append(dict(label='本次范围', value=f'{plan.action_count} 项业务操作，{plan.case_count} 个场景'))
        rows.append(dict(label='检查依据', value='已批准的权限要求及必需正常对照'))
        if plan.selection is not None:
            rows.append(dict(label='本次未检查', value=f'{len(plan.selection.omitted)} 条规则；未决要求保持未覆盖'))
        return rows

    def routine_context(self, project, references):
        keys={'routine_id','routine_revision','binding_id'}
        if not keys.intersection(references):
            return None
        import re
        from pydantic import ValidationError
        routine,revision=references.get('routine_id',''),references.get('routine_revision','')
        if re.fullmatch(r'csp_[0-9a-f]{32}',routine) is None or re.fullmatch(r'[1-9][0-9]{0,8}',revision) is None:
            raise JiejianError(ErrorCode.INPUT_INVALID,'方案交接需要准确方案标识与修订')
        binding=None
        if 'binding_id' in references:
            try:
                reference=RoutineReference(routine_id=routine,revision=int(revision),binding_id=references['binding_id'])
            except ValidationError as exc:
                raise JiejianError(ErrorCode.INPUT_INVALID,'方案交接的环境绑定引用无效') from exc
            with self.core.uow_factory() as work:
                document,binding=self.core.check_routines.revisions.resolve(project,reference,work)
        else:
            document=self.core.check_routines.revisions.read(project,routine,int(revision))
        return dict(document=document.model_dump(mode='json'),binding=None if binding is None else binding.model_dump(mode='json'))

    def _check_receipt(self, project, operation):
        with self.core.uow_factory() as work:
            job = work.jobs.get_by_idempotency(project, 'CHECK', operation['operation_id'])
            return dict(run_id=job.run_id, job_id=job.job_id, state=job.state.value) if job else None

    @classmethod
    def public(cls, value):
        """保留用例的产品投影，移除执行权限及秘密引用，供任务持久化和机器读取。"""
        value = to_jsonable_python(value)
        if isinstance(value, BaseModel):
            value = value.model_dump(mode='json')
        if isinstance(value, dict):
            hidden = {'secret_ref', 'secret_refs', 'secret', 'password', 'cookie', 'cookies', 'token',
                'access_token', 'refresh_token', 'environment', 'storage_state', 'fencing_token', 'lease_owner',
                'authority_id', 'control_session_id', 'runtime_reference'}
            return {key: cls.public(item) for key, item in value.items() if key not in hidden and not key.endswith(('_secret_ref','_secret_refs'))}
        if isinstance(value, (list, tuple)):
            return [cls.public(item) for item in value]
        return value
