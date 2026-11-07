"""历史只读的调用规模和恢复关联；实际执行与 fence 由真实应用测试覆盖。"""
from collections import Counter
from contextlib import contextmanager
from types import SimpleNamespace as NS
import pytest
from product.backend.application.preparation.flow_trials import FlowTrialService
from product.backend.domain.lifecycle import JobState

@pytest.mark.parametrize('count',[10,20,40])
def test_history_reads_each_fact_once_and_retains_recovery_semantics(count):
    calls=Counter()
    class Request:
        def __init__(self,index):
            self.trial_id=str(index)
            self.plan=NS(mode='RESTORE' if index==1 else 'TRIAL',origin_trial_id='0' if index==1 else None,state_changing=True)
        def model_dump(self,**_):return dict(trial_id=self.trial_id)
    requests=[Request(i) for i in range(count)]
    class Report:
        recovery='REQUEST_ACCEPTED'
        flow_attempted=True
        def model_dump(self,**_):return dict(recovery=self.recovery)
    class Trials:
        def list(self,project):
            assert project=='project';calls['list']+=1;return requests
        def report(self,project,trial):
            assert project=='project';calls['report']+=1;return Report() if trial=='1' else None
    class Jobs:
        def get_by_flow_trial(self,trial):
            calls['job']+=1
            return NS(project_id='project',job_id='job'+trial,state=JobState.SUCCEEDED,attempt=1)
    @contextmanager
    def uow():yield NS(flow_trials=Trials(),jobs=Jobs(),begin_read_snapshot=lambda:None)
    service=object.__new__(FlowTrialService);service._uow=uow
    result=service.history('project')
    assert len(result)==count
    assert not result[0]['recovery_pending'] and not result[1]['recovery_pending']
    assert all(item['recovery_pending'] for item in result[2:])
    assert calls==dict(list=1,report=count,job=count)

pytestmark=[pytest.mark.level3]
