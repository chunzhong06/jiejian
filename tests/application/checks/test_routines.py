from types import SimpleNamespace
from uuid import uuid4

import pytest

from product.backend.application.checks.routines import SaveCheckRoutine
from product.backend.domain.errors import JiejianError
from product.protocols.checks.execution_request import PermissionReference
from tests.support.builders.preparation.action_preparation import build_preparation_harness


def test_saved_selection_is_persistent_idempotent_and_detects_changed_rule(tmp_path,monkeypatch):
    harness=build_preparation_harness(tmp_path)
    try:
        service,project=harness.core.check_routines,harness.project_id
        boundary=harness.core.business_boundaries.view(project)
        intent=boundary.permission_intents[0]
        reference=PermissionReference(intent_id=intent.intent_id,revision=intent.revision,intent_hash=intent.intent_hash)
        command=SaveCheckRoutine(operation_id=uuid4().hex,selected_permissions=[reference])
        saved=service.save(project,command)
        assert service.save(project,command)==saved
        assert len(service.list(project))==1
        assert service.list(project)[0]['current'] is True
        assert 'verdict' not in saved and 'ready' not in saved
        changed=intent.model_copy(update={'revision':intent.revision+1})
        monkeypatch.setattr(service.boundaries,'view',lambda *args,**kwargs:SimpleNamespace(permission_intents=[changed]))
        stale=service.list(project)[0]
        assert stale['current'] is False
        assert stale['stale_intents']==[intent.intent_id]
        with pytest.raises(JiejianError,match='已变化'):
            service.save(project,SaveCheckRoutine(operation_id=uuid4().hex,selected_permissions=[reference]))
        assert service.list(project)[0]['selected_permissions']==saved['selected_permissions']
    finally:
        harness.close()


def test_all_rules_routine_does_not_freeze_old_rule_membership(tmp_path):
    harness=build_preparation_harness(tmp_path)
    try:
        service,project=harness.core.check_routines,harness.project_id
        value=service.save(project,SaveCheckRoutine(operation_id=uuid4().hex))
        assert service.list(project)[0]['mode']=='ALL'
        assert value['selected_permissions'] is None
        service.delete(project,value['routine_id'])
        assert service.list(project)==[]
    finally:
        harness.close()
