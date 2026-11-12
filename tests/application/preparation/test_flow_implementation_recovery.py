"""流程保存按真实缺口指向维护入口，补回对应后沿用同一份已准备输入。"""
import json
from uuid import uuid4

import pytest

from product.backend.domain.boundaries.entities import ActorImplementationBinding, ActionImplementationBinding, boundary_sha256
from product.backend.domain.errors import JiejianError
from product.protocols.preparation.operation_flow import OperationFlowDraft
from tests.support.builders.preparation.action_preparation import build_preparation_harness


@pytest.mark.parametrize('kind,label', [('actor','账号所属业务角色'),('action','业务操作')])
def test_missing_implementation_has_specific_recovery_and_preserves_original_flow(tmp_path,kind,label):
    harness=build_preparation_harness(tmp_path)
    core,project=harness.core,harness.project_id
    try:
        current=core.application_understanding.get(project)
        identity=harness.identities[0]
        draft=OperationFlowDraft.model_validate_json(json.dumps(dict(
            id='ofl_'+uuid4().hex,revision=1,business_action_id=harness.action.action_id,action_revision=1,
            subject_test_identity_id=identity.identity_id,resource_owner_test_identity_id=identity.identity_id,
            source_fingerprint=current.source_fingerprint,actual_resource_id='document-1',target_step_id='update',
            steps=[dict(id='update',purpose='TARGET',identity_id='CASE_SUBJECT',request_template=dict(method='PATCH',path='/documents/{case_resource_id}',
                body=dict(kind='JSON',value={'title':'changed'}),input_slots=[dict(slot_id='case_resource_id',source='CASE_RESOURCE_ID',consumer='PATH')]),
                classifier=dict(accepted=[dict(kind='STATUS_IN',statuses=[200])],denied=[]))],
            recovery=dict(method='POST',relative_path='/restore/{case_resource_id}',json_body={})) ))
        flow=core.operation_flows.candidate(project,draft)
        with core.uow_factory() as work:
            repository=work.business_boundaries
            if kind=='actor':
                original=repository.actor_binding(harness.actor.actor_id,1)
                values=dict(actor_id=original.actor_id,actor_revision=1,role_candidate_ids=())
                model,replace=ActorImplementationBinding,repository.replace_actor_binding
            else:
                original=repository.action_binding(harness.action.action_id,1)
                values=dict(action_id=original.action_id,action_revision=1,action_candidate_ids=())
                model,replace=ActionImplementationBinding,repository.replace_action_binding
            # 空定位是允许持久保存的待补充事实，不能被流程保存误报为接口更新。
            values.update(understanding_revision=current.revision,source_fingerprint=current.source_fingerprint)
            replace(model(**values,basis_version=1,binding_fingerprint=boundary_sha256(values),updated_at_us=original.updated_at_us+1))
            work.commit()
        with pytest.raises(JiejianError,match=label+'尚未完成对应'):
            core.operation_flows.save(project,flow)
        with core.uow_factory() as work:
            assert work.operation_flows.get(flow.id,1) is None
            restore=work.business_boundaries.replace_actor_binding if kind=='actor' else work.business_boundaries.replace_action_binding
            restore(original);work.commit()
        core.operation_flows.save(project,flow)
        assert core.operation_flows.read(project,flow.id,1)==flow
    finally:
        harness.close()
