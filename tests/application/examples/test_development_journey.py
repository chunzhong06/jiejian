from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from product.backend.application.examples.node_environment import NodeOfficialSampleExperience
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
    work = SimpleNamespace(runtime_loads=SimpleNamespace(operation=Mock(return_value=SimpleNamespace(source_fingerprint=fingerprint))),
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
    reader.project_readings.assert_called_once_with(project)
    experience.repairs.evaluate.assert_called_once_with(project, readings=readings)
