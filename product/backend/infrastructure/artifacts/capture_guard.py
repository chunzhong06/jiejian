# Runner只核对冻结引用、当前持久状态和原恢复起点；业务来源完整核对由提交/发布服务负责。
from product.backend.domain.errors import JiejianError
from product.backend.domain.lifecycle import ProjectStatus
from product.backend.domain.identities.models import identity_source_fingerprint




def capture_inputs_current(work,request,var_dir):
    project=work.projects.get(request.project_id)
    permission=work.permission_intents.latest(request.plan.permission.intent_id)
    action=request.plan.runtime.actions[0]
    root=work.business_boundaries.action(action.action_id)
    definition=work.business_boundaries.action_revision(action.action_id,action.action_revision)
    understanding=work.application_understanding.get(request.project_id)
    if (project is None or project.status is ProjectStatus.ARCHIVED or not work.proof_artifacts.authorized(request)
        or permission is None or permission.effective_state.value!='ACTIVE'
        or (permission.project_id,permission.revision,permission.intent_hash)!=(request.project_id,request.plan.permission.revision,request.plan.permission.intent_hash)
        or root is None or root.current_revision!=action.action_revision or definition is None
        or definition.semantic_fingerprint!=action.action_semantic_fingerprint or understanding is None
        or understanding.source_fingerprint!=request.plan.runtime.source_fingerprint):return False
    for identity in request.plan.runtime.identities:
        actual=work.test_identities.get(identity.identity_id)
        if actual is None or actual.project_id!=request.project_id or actual.prepared_at_us is None or identity_source_fingerprint(actual)!=identity.identity_fingerprint:return False
    execution=work.action_preparation.execution(action.action_id,action.action_revision)
    resource=work.action_preparation.resource(action.action_id,action.action_revision,request.plan.case.resource_owner_test_identity_id)
    recovery=work.action_preparation.recovery(action.action_id,action.action_revision) if action.state_changing else None
    if execution is None or execution.binding_fingerprint!=action.execution_binding_fingerprint or resource is None or resource.binding_fingerprint!=request.plan.case.resource_binding_fingerprint:
        return False
    if action.state_changing and (recovery is None or recovery.binding_fingerprint!=action.recovery.binding_fingerprint):return False
    if request.plan.restore is not None:
        from product.backend.infrastructure.artifacts.capture_baselines import read_capture_baseline
        try:
            return read_capture_baseline(var_dir,work,request.project_id,request.plan.restore.capture_id)==request.plan.restore
        except JiejianError:return False
    return True
