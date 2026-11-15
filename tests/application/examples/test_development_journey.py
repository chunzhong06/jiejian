from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from product.backend.application.examples.node_environment import NodeOfficialSampleExperience
from product.backend.application.examples.journey import OfficialDevelopmentJourney
from product.backend.domain.errors import JiejianError
from product.backend.domain.lifecycle import RunVerdict


@pytest.mark.parametrize('change_id,linked_run,context_change,error', [
    (None,None,None,None),
    ('change-1','run-1','change-1',None),
    ('change-1',None,None,None),
    ('change-1','run-1','different-change','STATE_PRECONDITION'),
    ('change-1','foreign-run','change-1','RECORD_NOT_FOUND'),
])
def test_journey_shares_history_with_repair_and_keeps_exact_delivery_run(change_id,linked_run,context_change,error):
    project, fingerprint = 'project', 'a'*64
    workspace = dict(workspace_id='wsp_'+'1'*32, scenario_version='BASELINE')
    work = SimpleNamespace(jobs=SimpleNamespace(list_for_project=Mock(return_value=())),runtime_loads=SimpleNamespace(operation=Mock(return_value=SimpleNamespace(source_fingerprint=fingerprint))),
        development=SimpleNamespace(delivery_for_change=Mock(return_value=SimpleNamespace(delivery_id='delivery-1')),
            latest_check_run=Mock(return_value=linked_run)))
    status = SimpleNamespace(result_integrity='VALID', run=SimpleNamespace(run_id='run-1', verdict=RunVerdict.PASS))
    package = SimpleNamespace(request=SimpleNamespace(source_fingerprint=fingerprint, policy_epoch=1,
        change_context=SimpleNamespace(change_id=context_change)))
    other = SimpleNamespace(result_integrity='VALID', run=SimpleNamespace(run_id='another-run', verdict=RunVerdict.BLOCK))
    readings = ((other, package), (status, package)) if change_id else ((status, package), (other, package))
    reader = Mock()
    reader.status.side_effect = AssertionError('must reuse project reading')
    reader.project_readings.return_value = readings
    reader.package.side_effect = AssertionError('must reuse verified package')
    reader.list_for_project.side_effect = AssertionError('must retain package in reading')
    experience = NodeOfficialSampleExperience(None, runtime=None,
        understanding=SimpleNamespace(inspect_source_fingerprint=Mock(return_value=fingerprint)),
        boundaries=SimpleNamespace(view=Mock(return_value=SimpleNamespace(policy_epoch=1))),
        identities=None, identity_preparations=None, preparation=None, proofs=None, artifacts=None, installer=None,
        changes=SimpleNamespace(delivery_details=Mock(side_effect=AssertionError('must not reread through delivery details'))),
        reader=reader, repairs=SimpleNamespace(evaluate=Mock(return_value=SimpleNamespace(tasks=()))),
        uow_factory=lambda: nullcontext(work), archive_project=None, cancel_check=None)
    experience._active = Mock(return_value=SimpleNamespace(project_id=project))
    experience._workspace = Mock(return_value=workspace)
    experience._change_id = Mock(return_value=change_id)

    if error:
        with pytest.raises(JiejianError) as caught:experience.development_journey()
        assert caught.value.code == error
    else:
        journey = experience.development_journey()
        checked = change_id is None or linked_run is not None
        assert journey.run_id == ('run-1' if checked else None)
        assert journey.verdict == ('PASS' if checked else None)
        assert journey.can_optimize is checked
        assert journey.stage == ('BASELINE_RESULT' if checked else 'BASELINE_CHECK')
    reader.project_readings.assert_called_once_with(project)
    experience.repairs.evaluate.assert_called_once_with(project, readings=readings)


@pytest.mark.parametrize('facts,stage', [
    ({},'STATE_UNAVAILABLE'),
    ({'policy_epoch':0},'REQUIREMENTS'),
    ({'policy_epoch':1},'BASELINE_CHECK'),
    ({'policy_epoch':1,'run_id':'run-1','verdict':'INCONCLUSIVE'},'CHECK_RESULT'),
    ({'policy_epoch':1,'implementation':'FIXED'},'CHANGED_CHECK'),
    ({'policy_epoch':1,'implementation':'CUSTOM','run_id':'run-1','verdict':'PASS'},'CUSTOM'),
])
def test_reading_stage_does_not_treat_implementation_names_or_unknown_facts_as_success(facts,stage):
    values=dict(project_id='project',implementation='BASELINE',reason='按已发布事实读取')
    journey=OfficialDevelopmentJourney(**(values|facts))
    assert journey.stage==stage
    assert journey.model_dump(mode='json')['stage']==stage
    assert not journey.can_optimize and not journey.repair_verified


@pytest.mark.parametrize('values,vulnerable,expose',[
    ({'can_optimize':True},True,False),
    ({'can_optimize':True,'has_active_tasks':True},False,False),
    ({'implementation':'VULNERABLE','verdict':'BLOCK','run_id':'current'},False,True),
    ({'implementation':'VULNERABLE','verdict':'INCONCLUSIVE'},False,False),
    ({'implementation':'CUSTOM','can_optimize':True},False,False),
])
def test_change_options_explain_actual_preconditions(values,vulnerable,expose):
    model=OfficialDevelopmentJourney(**(dict(project_id='project',implementation='BASELINE',policy_epoch=1,reason='当前事实')|values))
    options={item.version:item for item in model.change_options}
    assert options['VULNERABLE'].available is vulnerable
    assert options['EXPOSE_REVOKE'].available is expose
    assert all(item.reason for item in options.values() if not item.available)
    assert model.transition_basis != model.model_copy(update={'policy_epoch':2}).transition_basis


@pytest.mark.parametrize('project,basis',[('other','current'),('project','stale')])
def test_switch_rejects_other_project_or_stale_basis_before_writing(project,basis):
    from threading import RLock
    service=object.__new__(NodeOfficialSampleExperience)
    service._lock=RLock()
    service._active=Mock(return_value=SimpleNamespace(project_id='project'))
    service._workspace=Mock(return_value=dict(workspace_id='wsp_'+'1'*32))
    service._idle=Mock()
    service.development_reader=SimpleNamespace(receipt=Mock(return_value=None))
    service.development_journey=Mock(return_value=SimpleNamespace(transition_basis='current'))
    with pytest.raises(JiejianError) as caught:
        service.switch_version(version='VULNERABLE',expected_project_id=project,expected_basis=basis)
    assert caught.value.code=='STATE_PRECONDITION'


def test_version_request_requires_project_and_basis_together():
    from pydantic import ValidationError
    from product.backend.interfaces.http.routers.applications.experience import OfficialSampleVersionRequest
    with pytest.raises(ValidationError):
        OfficialSampleVersionRequest(schema_version='1',version='VULNERABLE',project_id='project')
