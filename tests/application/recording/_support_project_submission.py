# 所属业务域的共享测试构造器；不导入测试用例。

def _arguments(context):
    position = context.harness.core.preparation.get(context.project_id).actions[0].assurance_contract.identity_requirements.permissions[0]
    return dict(business_action_id=context.harness.action.action_id, action_revision=1,
        subject_test_identity_id=context.harness.identities[0].identity_id,
        resource_owner_test_identity_id=context.harness.identities[0].identity_id,
        subject_slot_id=position.subject_slot_id, resource_owner_slot_id=position.resource_owner_slot_id,
        duration_seconds=60, idempotency_key="supplement")
