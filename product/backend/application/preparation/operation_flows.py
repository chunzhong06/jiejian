from __future__ import annotations

import time
from urllib.parse import urlsplit
from product.backend.domain.errors import ErrorCode,JiejianError
from product.backend.domain.boundaries.entities import boundary_sha256
from product.backend.domain.preparation.bindings import ActionExecutionBinding,ActionResourceBinding,ActionRecoveryBinding,seal_binding
from product.backend.application.preparation.bindings.sources import binding_source_fields


def load_operation_material(work,binding):
    flow=work.operation_flows.get(binding.operation_flow_id,binding.operation_flow_revision)
    if flow is None or not work.operation_flows.adopted(flow.id,flow.revision):
        raise JiejianError(ErrorCode.STATE_PRECONDITION,'操作流程修订不可用')
    if hasattr(binding,'flow_sha256') and boundary_sha256(flow.model_dump(mode='json'))!=binding.flow_sha256:
        raise JiejianError(ErrorCode.STATE_PRECONDITION,'操作流程内容已变化')
    return flow


def execution_material(work,var_dir,binding):
    if binding.operation_flow_id is not None:
        flow=load_operation_material(work,binding)
        return flow,flow.target_scope
    from product.backend.infrastructure.recording.flows import recorded_flow_path,read_recorded_flow
    from product.backend.infrastructure.recording.request_store import RecordingRequestStore
    recording=work.recordings.get(binding.source_recording_id)
    if recording is None:raise JiejianError(ErrorCode.STATE_PRECONDITION,'原录制不存在')
    job=work.jobs.get_by_recording(recording.recording_id)
    source=RecordingRequestStore(var_dir).load(job.job_id,expected_hash=job.request_hash)
    return read_recorded_flow(recorded_flow_path(var_dir,recording),expected_hash=binding.flow_sha256),source.target_scope


class OperationFlowService:
    """保存候选与显式采用共用现有准备绑定；查询和导入不发出目标请求。"""
    def __init__(self,uow_factory,boundaries,identities,*,var_dir,clock_us=None):
        self._uow,self._boundaries,self._identities=uow_factory,boundaries,identities
        self._var_dir,self._clock=var_dir,clock_us or (lambda:time.time_ns()//1000)

    def context(self,project_id):
        with self._uow() as work:
            boundary=self._boundaries.view(project_id,work=work)
            understanding=work.application_understanding.get(project_id)
            flows=[]
            executions={}
            for item in work.operation_flows.latest(project_id):
                document=item['document']
                key=(document.business_action_id,document.action_revision)
                if key not in executions:
                    executions[key]=work.action_preparation.execution(*key)
                execution=executions[key]
                in_use=execution is not None and (execution.operation_flow_id,execution.operation_flow_revision)==(document.id,document.revision)
                configuration_current=understanding is not None and document.source_fingerprint==understanding.source_fingerprint and document.target_scope.base_url==understanding.confirmed_endpoint and any((action.action_id,action.revision)==(document.business_action_id,document.action_revision) for action in boundary.actions)
                flows.append(dict(document=document.model_dump(mode='json'),adopted=item['adopted'],in_use=in_use,configuration_current=configuration_current))
            return dict(project_id=project_id,source_fingerprint=None if understanding is None else understanding.source_fingerprint,
                endpoint=None if understanding is None else understanding.confirmed_endpoint,
                recordings=[dict(recording_id=item.recording_id,action_id=item.business_action_id,label='操作录制',created_at_us=item.created_at_us) for item in work.recordings.list_for_project(project_id) if item.state.value=='COMPLETED' and item.purpose.value=='TARGET'],
                actions=[dict(action_id=action.action_id,revision=action.revision,label=action.display_name,state_changing=action.state_changing) for action in boundary.actions],
                flows=flows)

    def save(self,project_id,document):
        with self._uow() as work:
            work.acquire_write_lock()
            self._context(work,project_id,document)
            previous=work.operation_flows.get(document.id,document.revision)
            if previous is not None:
                if previous==document:return document
                raise JiejianError(ErrorCode.STATE_PRECONDITION,'此修订已存在，请重新读取流程')
            latest=next((item['document'] for item in work.operation_flows.latest(project_id) if item['document'].id==document.id),None)
            if document.revision!=(1 if latest is None else latest.revision+1):
                raise JiejianError(ErrorCode.STATE_PRECONDITION,'流程已变化，请读取当前修订')
            work.operation_flows.add(document,self._clock())
            work.commit()
            return document

    def candidate(self,project_id,draft):
        from product.protocols.preparation.operation_flow import OperationFlow,operation_resource_injection
        from product.protocols.web.workflow import HttpWorkflowBinding,ResetEndpointStrategy,ResetNotRequiredStrategy
        from product.protocols.web.target import WebTargetScope
        from pydantic import ValidationError
        with self._uow() as work:
            understanding=work.application_understanding.get(project_id)
            if understanding is None or not understanding.confirmed_endpoint:
                raise JiejianError(ErrorCode.STATE_PRECONDITION,'请先确认运行地址')
            endpoint=urlsplit(understanding.confirmed_endpoint)
            target=WebTargetScope(base_url=understanding.confirmed_endpoint,allowed_origins=(understanding.confirmed_endpoint,),allowed_hosts=(endpoint.hostname,),allowed_ports=(endpoint.port or 80,),allow_private_network=True)
            try:
                workflow=HttpWorkflowBinding(workflow_id=draft.id,source_flow_id=draft.id,action_id=draft.business_action_id,
                    steps=draft.steps,target_step_id=draft.target_step_id,reset_strategy=ResetEndpointStrategy(path=draft.recovery.relative_path) if draft.recovery is not None else ResetNotRequiredStrategy())
                injection=operation_resource_injection(workflow)
                document=OperationFlow(**draft.model_dump(exclude={'steps','target_step_id'}),project_id=project_id,
                    target_scope=target,workflow=workflow,resource_injection=injection)
            except (ValueError,ValidationError):
                raise JiejianError(ErrorCode.INPUT_INVALID,'请核对步骤依赖、资源位置和动态值来源') from None
            self._context(work,project_id,document)
            return document

    def adopt(self,project_id,flow_id,revision):
        # 执行、资源和恢复在同一事务切换，不能暴露混用不同修订的半份材料。
        with self._uow() as work:
            work.acquire_write_lock()
            document=work.operation_flows.get(flow_id,revision)
            if document is None:raise JiejianError(ErrorCode.INPUT_INVALID,'流程不存在')
            action,identity,understanding=self._context(work,project_id,document)
            common=binding_source_fields(work,action,identity,understanding,self._clock(),document.resource_owner_test_identity_id)
            origin=dict(operation_flow_id=document.id,operation_flow_revision=document.revision)
            flow=dict(flow_id=document.id,flow_sha256=boundary_sha256(document.model_dump(mode='json')),resource_injection=document.resource_injection)
            execution=seal_binding(ActionExecutionBinding,**common,**origin,**flow)
            resource=seal_binding(ActionResourceBinding,**common,**origin,**flow,actual_resource_id=document.actual_resource_id)
            bindings=[(execution,work.action_preparation.execution(action.action_id,action.revision)),
                (resource,work.action_preparation.resource(action.action_id,action.revision,document.resource_owner_test_identity_id))]
            if document.recovery is not None:
                owner=work.test_identities.get(document.resource_owner_test_identity_id)
                recovery_common=binding_source_fields(work,action,owner,understanding,self._clock(),owner.identity_id)
                recovery=seal_binding(ActionRecoveryBinding,**recovery_common,**origin,step_id='restore',request_template=document.recovery)
                bindings.append((recovery,work.action_preparation.recovery(action.action_id,action.revision)))
            elif action.state_changing:
                raise JiejianError(ErrorCode.STATE_PRECONDITION,'改变数据的操作需要明确恢复步骤')
            if work.operation_flows.adopted(flow_id,revision) and all(old is not None and old.binding_fingerprint==value.binding_fingerprint for value,old in bindings):
                return dict(flow_id=flow_id,revision=revision,adopted=True,reused=True)
            for value,_ in bindings:
                work.action_preparation.replace(value)
            work.operation_flows.adopt(flow_id,revision,self._clock())
            work.commit()
            return dict(flow_id=flow_id,revision=revision,adopted=True)

    def _context(self,work,project_id,document):
        understanding=work.application_understanding.get(project_id)
        boundary=self._boundaries.view(project_id,work=work)
        action=next((item for item in boundary.actions if (item.action_id,item.revision)==(document.business_action_id,document.action_revision)),None)
        identity=work.test_identities.get(document.subject_test_identity_id)
        owner=work.test_identities.get(document.resource_owner_test_identity_id)
        if (document.project_id!=project_id or understanding is None or action is None or document.source_fingerprint!=understanding.source_fingerprint
            or document.target_scope.base_url!=understanding.confirmed_endpoint or identity is None or owner is None
            or any(item.project_id!=project_id or item.prepared_at_us is None for item in (identity,owner))):
            raise JiejianError(ErrorCode.STATE_PRECONDITION,'流程的应用、操作、账号或运行地址已变化')
        from product.backend.application.business_boundaries.inspection import inspect_action_binding,inspect_actor_binding
        implementation=inspect_action_binding(action.action_id,action.revision,work.business_boundaries.action_binding(action.action_id,action.revision),understanding)
        actors=[inspect_actor_binding(item.actor_id,item.actor_revision,work.business_boundaries.actor_binding(item.actor_id,item.actor_revision),understanding) for item in (identity,owner)]
        if implementation.status.value!='CURRENT' or any(item.status.value!='CURRENT' for item in actors):
            raise JiejianError(ErrorCode.STATE_PRECONDITION,'请先核对业务操作与源码的对应')
        if document.source_recording_id is not None:
            source=work.recordings.get(document.source_recording_id)
            if source is None or (source.project_id,source.business_action_id,source.action_revision,source.state.value)!=(project_id,action.action_id,action.revision,'COMPLETED'):
                raise JiejianError(ErrorCode.STATE_PRECONDITION,'流程引用的真实录制不可用')
        return action,identity,understanding

    def recording_candidate(self,project_id,recording_id):
        from product.backend.infrastructure.recording.flows import recorded_flow_path,read_recorded_flow
        from product.backend.domain.recording.models import RecordingState
        with self._uow() as work:
            recording=work.recordings.get(recording_id)
            if recording is None or recording.project_id!=project_id or recording.state is not RecordingState.COMPLETED:
                raise JiejianError(ErrorCode.STATE_PRECONDITION,'请选择本应用已确认的真实录制')
            flow=read_recorded_flow(recorded_flow_path(self._var_dir,recording))
            draft=work.flow_drafts.latest(recording_id)
            target=None if draft is None else next((item for item in draft.draft.steps if item.id==flow.target_step_id),None)
            resource=None if target is None else next((item for item in target.resource_candidates if item.candidate_id==draft.draft.resource_candidate_id),None)
            if resource is None:raise JiejianError(ErrorCode.STATE_PRECONDITION,'录制缺少已确认的资源位置')
            from product.backend.application.preparation.bindings.recording_candidates import recorded_resource_value
            return dict(recording_id=recording_id,steps=[dict(id=step.id,purpose=step.purpose.value,identity_id='CASE_SUBJECT',request_template=step.request_template.model_dump(mode='json'),classifier=step.classifier.model_dump(mode='json'),depends_on_step_ids=step.depends_on_step_ids) for step in flow.steps],target_step_id=flow.target_step_id,actual_resource_id=recorded_resource_value(recording,target,resource))

    @staticmethod
    def openapi_candidates(document):
        if not isinstance(document,dict) or str(document.get('openapi','')).split('.')[:2] not in (['3','0'],['3','1']):
            raise JiejianError(ErrorCode.INPUT_INVALID,'请选择 OpenAPI 3.0 或 3.1 JSON 文档')
        pending=[document]
        count=0
        while pending:
            item=pending.pop();count+=1
            if count>20000:raise JiejianError(ErrorCode.INPUT_INVALID,'接口文档超出导入预算')
            if isinstance(item,dict):
                if '$ref' in item:raise JiejianError(ErrorCode.INPUT_INVALID,'当前导入需要已展开引用的文档，不读取外部引用')
                pending.extend(item.values())
            elif isinstance(item,list):pending.extend(item)
        paths=document.get('paths',{})
        if not isinstance(paths,dict):raise JiejianError(ErrorCode.INPUT_INVALID,'接口路径必须是对象')
        result=[]
        for path,methods in paths.items():
            if not isinstance(path,str) or not path.startswith('/') or path.startswith('//') or not isinstance(methods,dict):continue
            for method,operation in methods.items():
                if method.upper() not in {'GET','POST','PUT','PATCH','DELETE'} or not isinstance(operation,dict):continue
                schema=operation
                for name in ('requestBody','content','application/json','schema'):
                    schema=schema.get(name,{}) if isinstance(schema,dict) else {}
                properties=schema.get('properties',{}) if isinstance(schema,dict) else {}
                if not isinstance(properties,dict):raise JiejianError(ErrorCode.INPUT_INVALID,'接口字段声明必须是对象')
                label=operation.get('summary') or operation.get('operationId') or path
                if not isinstance(label,str) or len(label)>256 or len(path)>512:
                    raise JiejianError(ErrorCode.INPUT_INVALID,'接口名称或路径超出限制')
                result.append(dict(method=method.upper(),path=path,label=label,
                    fields=[name for name in properties if isinstance(name,str) and not any(word in name.casefold() for word in ('password','token','secret','cookie','authorization'))][:32]))
                if len(result)>128:raise JiejianError(ErrorCode.INPUT_INVALID,'接口数量超出导入预算')
        return result
