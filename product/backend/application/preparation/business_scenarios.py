"""组织已准备动作的业务实验；保存草稿不授权请求，也不代用户批准权限。"""
import time
from product.backend.domain.errors import ErrorCode,JiejianError


class BusinessScenarioService:
    def __init__(self,uow_factory,checks,clock_us=None):
        self._uow,self._checks=uow_factory,checks
        self._clock=clock_us or (lambda:time.time_ns()//1000)

    def context(self,project_id):
        listing=self.listing(project_id)
        preview=self._checks.preview(project_id)
        with self._uow() as work:
            identities=[dict(identity_id=item.identity_id,label=item.label) for item in work.test_identities.list_for_project(project_id)]
            actions=[]
            for item in preview.actions:
                revision=work.business_boundaries.action_revision(item.action_id,item.action_revision)
                execution=work.action_preparation.execution(item.action_id,item.action_revision)
                trial_flow=None if execution is None or execution.operation_flow_id is None else dict(
                    flow_id=execution.operation_flow_id,revision=execution.operation_flow_revision)
                actions.append(dict(item.model_dump(mode='json'),label=revision.display_name if revision is not None else '业务动作',
                    trial_flow=trial_flow,creates_resource=execution is not None and execution.resource_injection.consumer.value.startswith('RESPONSE_')))
        return dict(project_id=project_id,documents=listing['documents'],
            actions=actions,identities=identities,
            gaps=[item.model_dump(mode='json') for item in preview.gaps])

    def listing(self,project_id):
        with self._uow() as work:
            if work.projects.get(project_id) is None:
                raise JiejianError(ErrorCode.PROJECT_NOT_FOUND,'应用不存在')
            return dict(project_id=project_id,documents=work.business_scenarios.summaries(project_id))

    def read(self,project_id,scenario_id,revision):
        with self._uow() as work:
            document=work.business_scenarios.get(project_id,scenario_id,revision)
            if document is None:
                raise JiejianError(ErrorCode.RECORD_NOT_FOUND,'没有找到这份场景修订')
            return document

    def save(self,project_id,document,*,submitted_via='LOCAL_GUI'):
        if document.project_id!=project_id:
            raise JiejianError(ErrorCode.INPUT_INVALID,'场景属于其他应用')
        with self._uow() as work:
            work.acquire_write_lock()
            if work.projects.get(project_id) is None:
                raise JiejianError(ErrorCode.PROJECT_NOT_FOUND,'应用不存在')
            previous=work.business_scenarios.get(project_id,document.id,document.revision)
            if previous is not None:
                if previous==document:
                    if submitted_via=='LOCAL_GUI':
                        work.business_scenarios.mark_reviewed(project_id,document.id,document.revision,self._clock())
                        work.commit()
                    return previous
                raise JiejianError(ErrorCode.STATE_PRECONDITION,'修订已保存，请读取后继续编辑')
            latest=work.business_scenarios.current(project_id,document.id)
            if document.revision!=(1 if latest is None else latest.revision+1):
                raise JiejianError(ErrorCode.STATE_PRECONDITION,'场景修订已变化')
            permissions={}
            for experiment in document.experiments:
                for invocation in experiment.invocations:
                    for item in invocation.items:
                        permission=work.permission_intents.get_revision(item.permission.intent_id,item.permission.revision)
                        if permission is None or permission.project_id!=project_id or permission.intent_hash!=item.permission.intent_hash:
                            raise JiejianError(ErrorCode.STATE_PRECONDITION,'场景引用的正式权限不存在或摘要不符')
                        if experiment.kind=='NORMAL' and permission.expectation.value!='ALLOW':
                            raise JiejianError(ErrorCode.INPUT_INVALID,'正常业务对照只能引用允许的动作')
                        permissions[(item.permission.intent_id,item.permission.revision,item.permission.intent_hash)]=(permission.business_action_id,permission.conditions)
            from product.protocols.checks.scenarios import validate_experiment_variants
            try:
                validate_experiment_variants(document,permissions)
            except ValueError:
                raise JiejianError(ErrorCode.INPUT_INVALID,'变体与正常流程没有形成所声明的差异；撤销实验需要引用实际撤销状态下的权限') from None
            work.business_scenarios.add(document,self._clock(),reviewed=submitted_via=='LOCAL_GUI')
            work.commit()
        return document
