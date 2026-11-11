from product.backend.infrastructure.runtime.workflow_timing import workflow_timings, workflow_phase, link_workflow
import pytest


def test_phases_are_nested_bounded_and_do_not_capture_exceptions(tmp_path):
    with workflow_timings(operation_id='https://invalid.example/secret-body') as timing:
        link_workflow(run_id='run_'+'a'*32, raw_body='secret-body-must-not-appear')
        with workflow_phase('check.preview'):
            with pytest.raises(ValueError):
                with workflow_phase('check.plan'):
                    raise ValueError('secret-body-must-not-appear')
        for _ in range(2050):
            with workflow_phase('report.read'):
                pass
    assert len(timing.stages) == 2048 and timing.dropped == 4
    child = next(item for item in timing.stages if item['phase'] == 'check.plan')
    assert child['parent'] == 1 and child['outcome'] == 'INTERRUPTED'
    assert timing.save(tmp_path)
    text = next((tmp_path/'logs/workflow').glob('*.json')).read_text()
    assert len(text.encode()) < 2 * 1024 * 1024
    assert 'secret-body' not in text
    assert timing.references == {'run_id':'run_'+'a'*32}


def test_disabled_timing_does_not_read_a_clock(monkeypatch):
    monkeypatch.setattr('product.backend.infrastructure.runtime.workflow_timing.perf_counter_ns', lambda: pytest.fail('disabled clock'))
    with workflow_phase('check.preview'):
        pass


@pytest.mark.parametrize('mode', ['backwards', 'unavailable'])
def test_clock_failure_keeps_business_and_records_unknown_duration(monkeypatch, mode):
    readings = iter([10000, 2000])
    def clock():
        if mode == 'unavailable':
            raise OSError('diagnostic clock unavailable')
        return next(readings)
    monkeypatch.setattr('product.backend.infrastructure.runtime.workflow_timing.perf_counter_ns', clock)
    completed = False
    with workflow_timings() as timing:
        with workflow_phase('check.preview'):
            completed = True
    assert completed
    assert timing.stages[0]['duration_us'] is None
    assert timing.stages[0]['outcome'] == 'COMPLETE'


def test_unwritable_diagnostic_path_does_not_change_completed_operation(tmp_path):
    (tmp_path/'logs').write_text('occupied')
    with workflow_timings() as timing:
        with workflow_phase('check.submit'):
            result = 'accepted'
    assert result == 'accepted'
    assert timing.save(tmp_path) is False
    assert timing.stages[0]['outcome'] == 'COMPLETE'
