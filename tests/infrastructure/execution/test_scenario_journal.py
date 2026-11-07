"""进展可并发阅读；保留旧文件句柄也不能阻断下一条请求账本。"""
from types import SimpleNamespace

import pytest

from product.backend.infrastructure.execution.scenario_journal import ScenarioJournal
from product.backend.infrastructure.artifacts.checks.scenario_progress import read_scenario_journal
from product.backend.domain.errors import JiejianError


def test_immutable_node_progress_survives_an_open_reader_and_rejects_replay(tmp_path):
    case='case_'+'1'*32
    group=SimpleNamespace(experiment_id='normal',invocation_id='publish',case_ids=(case,))
    node=SimpleNamespace(id='publish',label='发布资料')
    experiment=SimpleNamespace(id='normal',label='正常流程',invocations=(node,))
    request=SimpleNamespace(scenario=SimpleNamespace(fingerprint='2'*64,
        invocations=(group,),document=SimpleNamespace(experiments=(experiment,))))
    job=SimpleNamespace(run_id='run_'+'3'*32,job_id='job_'+'4'*32,attempt=1,fencing_token=1,request_hash='5'*64)
    journal=ScenarioJournal(request,job,tmp_path,lambda:100)
    journal.record(case,'INTENT_SAVED')
    with (journal.fragments/'0-1.json').open('rb') as original:
        journal.record(case,'RECEIVED')
        journal.record(case,'RECOVERY_INTENT')
        journal.record(case,'RECOVERED')
        assert b'INTENT_SAVED' in original.read()
        current=read_scenario_journal(journal.path,request,job).nodes[0]
        assert current.request=='RECEIVED' and current.recovered_cases==(case,)
    (journal.fragments/'0-2.json').unlink()
    with pytest.raises(ValueError,match='revision gap'):
        read_scenario_journal(journal.path,request,job)
    with pytest.raises(JiejianError,match='已有请求意图'):
        journal.record(case,'INTENT_SAVED')
