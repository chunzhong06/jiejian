"""每个 attempt 单独创建，网络前落盘意图；中断后 reader 只解释进展，不重放请求。"""
import os
from product.backend.domain.errors import ErrorCode,JiejianError
from product.protocols.checks.scenario_execution import ScenarioExecutionJournal,ScenarioNodeProgress


class ScenarioJournal:
    def __init__(self,request,runner_input,attempt_dir,clock):
        self.path=attempt_dir/'scenario-execution.json'
        self.fragments=attempt_dir/'scenario-progress'
        self.clock=clock
        self._versions={}
        labels={(experiment.id,invocation.id):(experiment.label,invocation.label)
            for experiment in request.scenario.document.experiments for invocation in experiment.invocations}
        self.document=ScenarioExecutionJournal(run_id=runner_input.run_id,job_id=runner_input.job_id,
            attempt=runner_input.attempt,fencing_token=runner_input.fencing_token,request_hash=runner_input.request_hash,
            scenario_fingerprint=request.scenario.fingerprint,nodes=tuple(ScenarioNodeProgress(
                experiment_id=item.experiment_id,invocation_id=item.invocation_id,case_ids=item.case_ids,
                experiment_label=labels[item.experiment_id,item.invocation_id][0],
                invocation_label=labels[item.experiment_id,item.invocation_id][1],
                observed_at_us=clock()) for item in request.scenario.invocations))
        attempt_dir.mkdir(parents=True,exist_ok=True)
        # 既有账本说明这个 attempt 曾进入执行；即使记录仍为未开始，也不自动重开。
        try:
            self.fragments.mkdir(exist_ok=False)
            with self.path.open('xb') as stream:
                self._write(stream,self.document)
        except OSError:
            raise JiejianError(ErrorCode.STATE_PRECONDITION,'本次场景已有执行记录或无法保存请求意图') from None

    def _write(self,stream,document):
        stream.write(document.model_dump_json().encode())
        stream.flush()
        os.fsync(stream.fileno())

    def record(self,case_id,event):
        matches=[index for index,item in enumerate(self.document.nodes) if case_id in item.case_ids]
        if not matches:
            return
        index=matches[0]
        node=self.document.nodes[index]
        updates=dict(observed_at_us=self.clock())
        if event in {'INTENT_SAVED','RECEIVED','UNCONFIRMED'}:
            if event=='INTENT_SAVED' and node.request!='NOT_STARTED':
                raise JiejianError(ErrorCode.STATE_PRECONDITION,'场景节点已有请求意图，不能重复发送')
            updates['request']=event
        elif event=='RECOVERY_INTENT':
            if case_id in node.recovery_intents:
                raise JiejianError(ErrorCode.STATE_PRECONDITION,'这个节点的恢复已尝试，不能自动重复')
            updates['recovery_intents']=(*node.recovery_intents,case_id)
        elif event=='RECOVERED':
            updates['recovered_cases']=(*node.recovered_cases,case_id)
        else:
            raise ValueError('unknown scenario journal event')
        nodes=list(self.document.nodes)
        nodes[index]=ScenarioNodeProgress.model_validate(node.model_dump()|updates)
        # 已发布片段不可变，读者持有旧文件也不妨碍提交下一条进展。
        # Windows 上替换正在阅读的文件可能失败，请求账本不能受界面轮询时机影响。
        version=self._versions.get(index,0)+1
        destination=self.fragments/f'{index}-{version}.json'
        temporary=destination.with_suffix('.tmp')
        try:
            with temporary.open('wb') as stream:
                self._write(stream,nodes[index])
            os.replace(temporary,destination)
        except OSError:
            raise JiejianError('SCENARIO_PROGRESS_WRITE_FAILED','无法保存场景执行进展，请核对原执行记录') from None
        finally:
            temporary.unlink(missing_ok=True)
        self._versions[index]=version
        self.document=self.document.model_copy(update=dict(nodes=tuple(nodes)))
