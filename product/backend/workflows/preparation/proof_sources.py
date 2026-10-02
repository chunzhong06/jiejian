# 管理来源候选、GUI读取授权与独立预检查；所有状态由当前事实投影，查询不访问目标。
import time
from uuid import uuid4

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.lifecycle import ProjectStatus, JobState
from product.backend.core.boundaries.entities import boundary_sha256, ImplementationBindingStatus
from product.backend.workflows.business_boundaries.inspection import inspect_action_binding, inspect_actor_binding
from product.backend.workflows.recording.source import identity_source_fingerprint
from product.backend.infra.observers.source_contracts import audit_source_contract
from product.backend.infra.runtime.jobs.models import RequestCancellation
from product.protocols.node_runtime import NodeRuntimeReference
from product.protocols.proof_sources import ProofSourceRevision, SourceReadScope, ProofPreflightInput, proof_fingerprint, ManagedProofSourceConfig, source_identity_paths
from product.protocols.check_runtime import CheckIdentity, CheckIdentityVerification
from product.protocols.web.target import WebTargetScope
from product.protocols.web.request import HttpRequestTemplate


class ProofPreparationService:
    def __init__(self, *, var_dir, uow_factory, boundaries, credentials, runtime_reader, source_inspector, jobs, queue, clock_us=None):
        self.var_dir, self._uow, self._boundaries = var_dir, uow_factory, boundaries
        self._credentials, self._runtime_reader, self.jobs, self._queue = credentials, runtime_reader, jobs, queue
        self._source_inspector = source_inspector
        self._clock = clock_us or (lambda: time.time_ns() // 1000)
        self.control_session_id = 'pcs_' + uuid4().hex
        # 主组合根安装真实MCP授权检查；默认只允许本地GUI，不能默认信任任意Agent标识。
        self.authority_active = lambda project_id, authority: authority == 'LOCAL_GUI'

    def _facts(self, work, project_id):
        project = work.projects.get(project_id)
        if project is None or project.status is ProjectStatus.ARCHIVED:
            raise JiejianError(ErrorCode.STATE_PRECONDITION, '应用不存在或已归档')
        boundary = self._boundaries.view(project_id, work=work)
        understanding = work.application_understanding.get(project_id)
        identities = work.test_identities.list_for_project(project_id)
        resources = tuple(item for action in boundary.actions for item in work.action_preparation.resources(action.action_id, action.revision))
        observed_source = None
        try:
            observed_source = self._source_inspector(project_id)
            runtime = self._runtime_reader(project_id)
            if (not isinstance(runtime, NodeRuntimeReference) or runtime.source_fingerprint != observed_source
                    or understanding is None or understanding.source_fingerprint != observed_source):
                runtime = None
        except JiejianError:
            runtime = None
        basis = boundary_sha256(dict(boundary=boundary.model_dump(mode='json'),
            observed_source=observed_source,
            understanding=None if understanding is None else understanding.source_fingerprint,
            identities=[dict(reference=identity_source_fingerprint(item),prepared_at_us=item.prepared_at_us,
                refreshed_at_us=item.refreshed_at_us,updated_at_us=item.updated_at_us) for item in identities],
            resources=[item.binding_fingerprint for item in resources],
            runtime=None if runtime is None else runtime.model_dump(mode='json')))
        return boundary, understanding, identities, resources, runtime, 'pb_' + basis

    @staticmethod
    def _resource_id(binding):
        return 'res_' + binding.binding_fingerprint[:32]

    def context(self, project_id):
        with self._uow() as work:
            boundary, understanding, identities, resources, runtime, basis = self._facts(work, project_id)
            return dict(project_id=project_id, basis_id=basis, runtime_available=runtime is not None,
                runtime_origin=None if runtime is None else f'http://127.0.0.1:{runtime.port}',
                actions=[dict(action_id=item.action_id, revision=item.revision, label=item.display_name,
                    effects=[dict(effect_id=effect.effect_id, label=effect.business_label, kind=effect.effect_kind.value)
                        for effect in item.effect_catalog]) for item in boundary.actions],
                identities=[dict(identity_id=item.identity_id, label=item.label, actor_id=item.actor_id,
                    prepared=item.prepared_at_us is not None) for item in identities],
                resources=[dict(resource_binding_id=self._resource_id(item), action_id=item.business_action_id,
                    action_revision=item.action_revision, resource_id=item.actual_resource_id,
                    owner_identity_id=item.resource_owner_test_identity_id) for item in resources],
                sources=[self._source_view(work, item, basis, runtime) for item in work.proof_sources.list(project_id)],
                read_scopes=[item.model_dump(mode='json') for item in work.proof_sources.scopes(project_id)],
                supported_source_kinds=['MANAGED_TRANSACTION_RECORDS'], max_response_bytes=262144, max_path_depth=8,
                source_contracts=['TRANSACTION_HISTORY_V1','RESOURCE_FIELDS_V1'],
                source_requirements=['受保护资源通过通用事务记录组件读写','身份接口、角色字段与被保护字段由当前应用配置','普通自报JSON不作为完整历史依据'],
                gui_url=f'#/tests?materials=1&proof_sources=1&project_id={project_id}')

    def _source_view(self, work, source, basis, runtime=None):
        attempts = work.proof_sources.preflights(source.project_id, source.source_id, source.revision, limit=1)
        attempt = None
        if attempts:
            request, job, report = self.jobs.read(work, source.project_id, attempts[0].preflight_id)
            attempt = dict(preflight_id=request.preflight_id, state=job.state.value,
                current_basis=request.basis_id == basis, report=None if report is None else report.model_dump(mode='json'))
        adoption = work.proof_sources.adoption(source.project_id, source.source_id)
        supported = isinstance(source.config,ManagedProofSourceConfig)
        scope = next((item for item in work.proof_sources.scopes(source.project_id)
                      if supported and runtime is not None and self._scope_matches(item, source.config, runtime)), None)
        return dict(source_id=source.source_id, revision=source.revision, config=source.config.model_dump(mode='json'),
            submitted_via=source.submitted_via, client_name=source.client_name,
            adopted=supported and adoption is not None and adoption.revision == source.revision,
            supported=supported, requires_migration=not supported,
            read_scope_confirmed=scope is not None, matching_read_scope_id=None if scope is None else scope.scope_id,
            preflight=attempt)

    def show(self, project_id, source_id):
        with self._uow() as work:
            *_, runtime, basis = self._facts(work, project_id)
            source = work.proof_sources.source(project_id, source_id)
            if source is None:
                raise JiejianError(ErrorCode.RECORD_NOT_FOUND, '证明来源不存在')
            return dict(project_id=project_id, basis_id=basis, **self._source_view(work, source, basis, runtime))

    def _operation(self, project_id, kind, command, execute):
        fingerprint = proof_fingerprint(command)
        with self._uow() as work:
            work.acquire_write_lock()
            prior = work.preparation_recovery.receipt(command.operation_id, project_id=project_id, operation_kind=kind)
            if prior is not None:
                if prior['request_fingerprint'] != fingerprint:
                    raise JiejianError(ErrorCode.STATE_PRECONDITION, '这次操作标识已经用于另一份输入')
                return prior
            result = execute(work)
            receipt = dict(schema_version='1', project_id=project_id, operation_id=command.operation_id,
                operation_kind=kind, request_fingerprint=fingerprint, created_at_us=self._clock(), result=result)
            work.preparation_recovery.add_receipt(receipt, operation_kind=kind)
            work.commit()
            return receipt

    def receipt(self, project_id, kind, operation_id):
        with self._uow() as work:
            value = work.preparation_recovery.receipt(operation_id, project_id=project_id, operation_kind=kind)
            if value is None:
                raise JiejianError(ErrorCode.RECORD_NOT_FOUND, '尚未找到这次准备操作回执')
            return value

    def _current(self, work, project_id, command):
        facts = self._facts(work, project_id)
        if facts[-1] != command.basis_id:
            raise JiejianError(ErrorCode.STATE_PRECONDITION, '权限、账号、材料或运行实例已变化，请重新读取准备情况')
        return facts

    def _selection(self, work, project_id, config, facts):
        if not isinstance(config,ManagedProofSourceConfig):
            raise JiejianError(ErrorCode.STATE_PRECONDITION,'旧来源核验方式已停止使用，请通过通用记录组件重新准备来源',details={'reason':'PROOF_SOURCE_REQUIRES_MIGRATION'})
        boundary, understanding, identities, resources, runtime, basis = facts
        action = next((item for item in boundary.actions if (item.action_id,item.revision) == (config.action_id,config.action_revision)), None)
        effect = None if action is None else next((item for item in action.effect_catalog if item.effect_id == config.effect_id), None)
        resource = next((item for item in resources if self._resource_id(item) == config.resource_binding_id
            and (item.business_action_id,item.action_revision) == (config.action_id,config.action_revision)), None)
        known = {item.identity_id:item for item in identities}
        if (effect is None or resource is None or config.observation_identity_id != resource.resource_owner_test_identity_id
                or not {item.identity_id for item in config.identity_claims} <= set(known)):
            raise JiejianError(ErrorCode.STATE_PRECONDITION, '来源未对应当前动作、效果和已确认的资源所有者')
        expected_kind = 'STATE_MUTATION' if config.source_contract_id=='TRANSACTION_HISTORY_V1' else 'DATA_DISCLOSURE'
        if effect.effect_kind.value != expected_kind or set(config.protected_projection) != set(effect.protected_projection):
            raise JiejianError(ErrorCode.STATE_PRECONDITION,'来源类型或受保护字段与已确认的业务要求不一致')
        return action, effect, resource, known

    def save(self, project_id, command, *, submitted_via='LOCAL_GUI', client_name='本机用户'):
        def execute(work):
            facts = self._current(work, project_id, command)
            self._selection(work, project_id, command.config, facts)
            old = None if command.source_id is None else work.proof_sources.source(project_id, command.source_id)
            if (command.source_id is None) != (command.expected_revision is None) or (command.source_id is not None
                    and (old is None or old.revision != command.expected_revision)):
                raise JiejianError(ErrorCode.STATE_PRECONDITION, '来源候选已有更新，请读取后再保存')
            value = ProofSourceRevision(project_id=project_id, source_id=command.source_id or 'psr_' + uuid4().hex,
                revision=1 if old is None else old.revision + 1, config=command.config,
                basis_id=command.basis_id, fingerprint=proof_fingerprint(command.config), submitted_via=submitted_via,
                client_name=client_name, created_at_us=self._clock())
            work.proof_sources.save(value, expected_revision=command.expected_revision)
            return dict(source_id=value.source_id, revision=value.revision, state='CANDIDATE')
        return self._operation(project_id, 'SAVE_SOURCE', command, execute)

    def _source(self, work, project_id, command):
        source = work.proof_sources.source(project_id, command.source_id)
        if source is None or source.revision != command.revision:
            raise JiejianError(ErrorCode.STATE_PRECONDITION, '来源修订已变化')
        return source

    @staticmethod
    def _scope_matches(scope, config, runtime):
        return (isinstance(config,ManagedProofSourceConfig) and scope.origin == f'http://127.0.0.1:{runtime.port}'
            and config.read_scope_id in (None,scope.scope_id)
            and {*source_identity_paths(config),config.relative_path_template} <= set(scope.path_templates)
            and {item.identity_id for item in config.identity_claims} <= set(scope.identity_ids)
            and config.resource_binding_id in scope.resource_binding_ids
            and config.max_response_bytes <= scope.max_response_bytes and config.timeout_us <= scope.timeout_us)

    def grant_scope(self, project_id, command):
        def execute(work):
            facts = self._current(work, project_id, command)
            source = self._source(work, project_id, command)
            self._selection(work, project_id, source.config, facts)
            runtime = facts[4]
            if runtime is None:
                raise JiejianError(ErrorCode.STATE_PRECONDITION, '请先启动当前应用的受控实例')
            config = source.config
            if config.read_scope_id is not None:
                current = work.proof_sources.scope(project_id,config.read_scope_id)
                if current is None or not self._scope_matches(current,config,runtime):
                    raise JiejianError(ErrorCode.STATE_PRECONDITION,
                        '来源引用的读取授权已失效。请更新来源候选中的授权关联，再确认新的读取范围。',
                        details={'reason':'PROOF_READ_SCOPE_STALE'})
                return dict(scope_id=current.scope_id,state='GRANTED')
            scope = SourceReadScope(scope_id='prs_' + uuid4().hex, project_id=project_id,
                origin=f'http://127.0.0.1:{runtime.port}', path_templates=(*source_identity_paths(config),config.relative_path_template),
                identity_ids=tuple(item.identity_id for item in config.identity_claims),
                resource_binding_ids=(config.resource_binding_id,), max_response_bytes=config.max_response_bytes,
                timeout_us=config.timeout_us, created_at_us=self._clock())
            work.proof_sources.add_scope(scope)
            return dict(scope_id=scope.scope_id, state='GRANTED')
        return self._operation(project_id, 'GRANT_SCOPE', command, execute)

    def start(self, project_id, command, *, authority_id='LOCAL_GUI'):
        def execute(work):
            facts = self._current(work, project_id, command)
            source = self._source(work, project_id, command)
            config = source.config
            action, effect, resource, known = self._selection(work, project_id, config, facts)
            runtime = facts[4]
            if runtime is None or not self.authority_active(project_id, authority_id):
                raise JiejianError(ErrorCode.STATE_PRECONDITION, '受控实例或执行授权已失效')
            scopes = [item for item in work.proof_sources.scopes(project_id) if self._scope_matches(item,config,runtime)]
            if not scopes:
                raise JiejianError(ErrorCode.STATE_PRECONDITION, '请在界面确认这次读取范围', details={'reason':'PROOF_READ_SCOPE_REQUIRED'})
            identities, roles = self._identities(work, source, facts, known)
            contract = audit_source_contract(self.var_dir, runtime, config)
            if contract is not None and effect.effect_kind.value != contract.approved_effect_kind:
                contract = None
            claims = {item.identity_id:item.application_subject_id for item in config.identity_claims}
            origin = f'http://127.0.0.1:{runtime.port}'
            request = ProofPreflightInput(preflight_id='ppf_' + uuid4().hex, project_id=project_id,
                source_id=source.source_id, source_revision=source.revision, source_fingerprint=source.fingerprint,
                config=config, scope=scopes[0], basis_id=command.basis_id, control_session_id=self.control_session_id,
                authority_id=authority_id, target=WebTargetScope(base_url=origin, allowed_origins=(origin,),
                    allowed_hosts=('127.0.0.1',), allowed_ports=(runtime.port,), allow_private_network=True,
                    max_requests=len(identities)+1, max_response_bytes=config.max_response_bytes,
                    timeout_seconds=config.timeout_us/1_000_000), identities=identities, identity_roles=roles,
                resource_id=resource.actual_resource_id, owner_subject_id=claims[resource.resource_owner_test_identity_id],
                runtime_reference=runtime, contract=contract, created_at_us=self._clock())
            job = self.jobs.submit(work, request, operation_id=command.operation_id)
            return dict(preflight_id=request.preflight_id, job_id=job.job_id, state=job.state.value)
        return self._operation(project_id, 'START_PREFLIGHT', command, execute)

    def _identities(self, work, source, facts, known):
        boundary, understanding, _, _, _, _ = facts
        action_binding = work.business_boundaries.action_binding(source.config.action_id,source.config.action_revision)
        if inspect_action_binding(source.config.action_id,source.config.action_revision,action_binding,understanding).status is not ImplementationBindingStatus.CURRENT:
            raise JiejianError(ErrorCode.STATE_PRECONDITION, '业务动作实现尚未对应当前源码')
        roles, identities = {}, []
        for claim in source.config.identity_claims:
            record = known[claim.identity_id]
            binding = work.business_boundaries.actor_binding(record.actor_id,record.actor_revision)
            if inspect_actor_binding(record.actor_id,record.actor_revision,binding,understanding).status is not ImplementationBindingStatus.CURRENT:
                raise JiejianError(ErrorCode.STATE_PRECONDITION, '测试账号的角色实现尚未对应当前源码')
            candidates = [item for item in understanding.role_candidates if item.candidate_id in binding.role_candidate_ids]
            if claim.application_role not in {item.canonical_key for item in candidates}:
                raise JiejianError(ErrorCode.STATE_PRECONDITION, '来源合同需要明确的应用角色对应')
            actor = next(item for item in boundary.actors if (item.actor_id,item.revision)==(record.actor_id,record.actor_revision))
            roles[record.identity_id] = claim.application_role
            identities.append(CheckIdentity(identity_id=record.identity_id, actor_id=record.actor_id,
                actor_revision=record.actor_revision, identity_fingerprint=identity_source_fingerprint(record),
                label=record.label, actor_label=actor.display_name, binding=self._credentials.profile_identity(record).binding,
                verification=CheckIdentityVerification(namespace='application-account', expected_application_subject_id=claim.application_subject_id,
                    expected_actor_id=record.actor_id, expected_actor_revision=record.actor_revision,
                    request=HttpRequestTemplate(method='GET',path=claim.request_path),subject_json_path='$.'+'.'.join(claim.subject_path))))
        return tuple(identities), roles

    def status(self, project_id, preflight_id):
        with self._uow() as work:
            request, job, report = self.jobs.read(work,project_id,preflight_id)
            return dict(preflight_id=preflight_id,source_id=request.source_id,revision=request.source_revision,
                state=job.state.value, report=None if report is None else report.model_dump(mode='json'))

    def _adoptable(self, work, project_id, source, preflight_id, facts):
        request, job, report = self.jobs.read(work,project_id,preflight_id)
        if (request.source_id != source.source_id or request.source_revision != source.revision
                or request.source_fingerprint != source.fingerprint or request.basis_id != facts[-1]
                or report is None or report.assessment != 'USABLE' or request.contract is None
                or facts[4] != request.runtime_reference
                or not isinstance(source.config,ManagedProofSourceConfig)
                or audit_source_contract(self.var_dir,request.runtime_reference,source.config) != request.contract
                or work.proof_sources.scope(project_id,request.scope.scope_id) != request.scope):
            raise JiejianError(ErrorCode.STATE_PRECONDITION,'请对当前来源和准备条件完成一次独立预检查')
        return request

    def adoption_preview(self, project_id, source_id, preflight_id):
        with self._uow() as work:
            facts = self._facts(work,project_id)
            source = work.proof_sources.source(project_id,source_id)
            if source is None:
                raise JiejianError(ErrorCode.RECORD_NOT_FOUND,'证明来源不存在')
            request = self._adoptable(work,project_id,source,preflight_id,facts)
            action,effect,resource,_ = self._selection(work,project_id,source.config,facts)
            previous = work.action_preparation.evidence(action.action_id,action.revision,effect.effect_id)
            return dict(project_id=project_id,basis_id=facts[-1],source_id=source_id,revision=source.revision,
                preflight_id=preflight_id,action_label=action.display_name,effect_label=effect.business_label,
                replaces_existing=previous is not None,identity_claims=[item.model_dump(mode='json') for item in source.config.identity_claims],
                source_path=source.config.relative_path_template,resource_id=resource.actual_resource_id,
                collection=source.config.collection,mappings={key:'.'.join(path) for key,path in source.config.mappings.items()},
                expected_state=effect.expected_state,protected_projection=source.config.protected_projection,
                retained=['权限规则','操作材料','测试账号','恢复材料'],recheck=['结果证明','恢复后的结果核对'],
                gui_url=f'#/tests?materials=1&proof_sources=1&project_id={project_id}&source={source_id}&action_id={action.action_id}')

    def adopt(self, project_id, command):
        def execute(work):
            from product.backend.core.preparation.bindings import ActionEvidenceBinding,ActionEvidenceKind,RegisteredObserverReference,seal_binding
            from product.backend.workflows.preparation.bindings import PreparationBindingService
            from product.protocols.proof_sources import ProofSourceAdoption
            facts = self._current(work,project_id,command)
            source = self._source(work,project_id,command)
            self._adoptable(work,project_id,source,command.preflight_id,facts)
            action,effect,resource,known = self._selection(work,project_id,source.config,facts)
            reference = RegisteredObserverReference(descriptor_id=source.source_id,
                descriptor_fingerprint=source.fingerprint,observer_id='json_' + source.source_id[4:])
            common = PreparationBindingService._common(work,action,known[source.config.observation_identity_id],
                facts[1],self._clock(),resource.resource_owner_test_identity_id)
            binding = seal_binding(ActionEvidenceBinding,**common,effect_id=effect.effect_id,
                kind=ActionEvidenceKind.REGISTERED_OBSERVER,observer_reference=reference)
            work.action_preparation.replace(binding)
            work.proof_sources.adopt(ProofSourceAdoption(project_id=project_id,source_id=source.source_id,
                revision=source.revision,source_fingerprint=source.fingerprint,preflight_id=command.preflight_id,
                binding_fingerprint=binding.binding_fingerprint,created_at_us=self._clock()))
            return dict(source_id=source.source_id,revision=source.revision,state='ADOPTED')
        return self._operation(project_id,'ADOPT_SOURCE',command,execute)

    def active_sources(self, project_id):
        """重启后从持久采用记录重建投影；新实例必须重新预检查，不复制旧READY。"""
        result = []
        with self._uow() as work:
            facts = self._facts(work,project_id)
            for source in work.proof_sources.list(project_id,limit=256):
                adoption = work.proof_sources.adoption(project_id,source.source_id)
                if adoption is None or adoption.revision != source.revision:
                    continue
                binding = work.action_preparation.evidence(source.config.action_id,source.config.action_revision,source.config.effect_id)
                if binding is None or binding.binding_fingerprint != adoption.binding_fingerprint:
                    continue
                for candidate in work.proof_sources.preflights(project_id,source.source_id,source.revision):
                    try:
                        request = self._adoptable(work,project_id,source,candidate.preflight_id,facts)
                        action,effect,resource,_ = self._selection(work,project_id,source.config,facts)
                        result.append((source,request,effect,resource,binding))
                        break
                    except JiejianError:
                        continue
        return tuple(result)

    def runtime_registration(self, project_id):
        from product.backend.workflows.preparation.proof_registration import runtime_registration
        return runtime_registration(project_id,self.active_sources(project_id))

    def frozen_sources(self, project_id):
        from product.protocols.proof_sources import FrozenJsonProofSource
        return tuple(FrozenJsonProofSource(source_id=source.source_id,revision=source.revision,
            source_fingerprint=source.fingerprint,config=source.config,contract=request.contract,
            owner_subject_id=request.owner_subject_id,identity_roles=request.identity_roles)
            for source,request,*_ in self.active_sources(project_id))

    def job_authorized(self, job):
        if job.preflight_id is None:
            return True
        with self._uow() as work:
            request = work.proof_sources.preflight(job.project_id,job.preflight_id)
            return (request is not None and request.control_session_id == self.control_session_id
                and self.authority_active(job.project_id,request.authority_id)
                and work.proof_sources.scope(job.project_id,request.scope.scope_id) == request.scope)

    def cancel(self, project_id, command):
        def execute(work):
            request, job, report = self.jobs.read(work,project_id,command.preflight_id)
            if job.state in {JobState.PENDING,JobState.RETRY_WAIT,JobState.RUNNING}:
                result = self._queue.request_cancellation(RequestCancellation(job_id=job.job_id,now_us=self._clock()), work=work)
                state = result.job.state.value
            else:
                state = job.state.value
            return dict(preflight_id=request.preflight_id,state=state)
        return self._operation(project_id,'CANCEL_PREFLIGHT',command,execute)

    def revoke_scope(self, project_id, command):
        def execute(work):
            work.proof_sources.revoke(project_id,command.scope_id,self._clock())
            for job in work.jobs.list_for_project(project_id):
                if job.preflight_id is None or job.state not in {JobState.PENDING,JobState.RETRY_WAIT,JobState.RUNNING}:
                    continue
                request = work.proof_sources.preflight(project_id,job.preflight_id)
                if request.scope.scope_id == command.scope_id:
                    self._queue.request_cancellation(RequestCancellation(job_id=job.job_id,now_us=self._clock()),work=work)
            return dict(scope_id=command.scope_id,state='REVOKED')
        return self._operation(project_id,'REVOKE_SCOPE',command,execute)

    def cancel_unauthorized(self):
        """撤权同步取消受影响Job；重新授予权限也不会复活旧授权提交的任务。"""
        with self._uow() as work:
            projects = work.projects.list_all()
        for project in projects:
            with self._uow() as work:
                jobs = work.jobs.list_for_project(project.project_id)
            for job in jobs:
                if (job.preflight_id is not None and job.state in {JobState.PENDING,JobState.RETRY_WAIT,JobState.RUNNING}
                        and not self.job_authorized(job)):
                    try:
                        self._queue.request_cancellation(RequestCancellation(job_id=job.job_id,now_us=self._clock()))
                    except JiejianError as error:
                        if error.code != ErrorCode.JOB_TERMINAL_CONFLICT.value:
                            raise
