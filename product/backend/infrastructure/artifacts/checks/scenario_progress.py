"""按冻结请求与 attempt 只读核对场景进展，既不写入账本，也不驱动执行。"""
from product.protocols.checks.scenario_execution import ScenarioExecutionJournal,ScenarioNodeProgress


def read_scenario_journal(path,request,job):
    """路径由既有 Job/attempt 定位；任意损坏或串题均不能作为请求状态。"""
    if path.is_symlink() or not path.is_file() or path.stat().st_size>1_048_576:
        return None
    document=ScenarioExecutionJournal.model_validate_json(path.read_bytes())
    if (document.run_id,document.job_id,document.attempt,document.fencing_token,document.request_hash)!=(
            job.run_id,job.job_id,job.attempt,job.fencing_token,job.request_hash):
        raise ValueError('scenario journal attempt mismatch')
    document.validate_request(request)
    fragments=path.parent/'scenario-progress'
    if fragments.is_symlink() or not fragments.is_dir():raise ValueError('scenario progress directory missing')
    nodes=list(document.nodes)
    for index,initial in enumerate(document.nodes):
        # 兼容此前单片段；新执行只追加不可变修订，选择连续历史中的末条。
        versions=[]
        for path in fragments.glob(f'{index}-*.json'):
            suffix=path.stem.split('-')[-1]
            if not suffix.isdecimal():raise ValueError('scenario progress revision invalid')
            versions.append(int(suffix))
        if len(versions)>68 or sorted(versions)!=list(range(1,len(versions)+1)):
            raise ValueError('scenario progress revision gap')
        fragment=fragments/(f'{index}-{max(versions)}.json' if versions else f'{index}.json')
        if fragment.is_symlink():raise ValueError('scenario progress link')
        if not fragment.exists():continue
        if not fragment.is_file() or fragment.stat().st_size>16384:raise ValueError('scenario progress size')
        node=ScenarioNodeProgress.model_validate_json(fragment.read_bytes())
        if (node.experiment_id,node.invocation_id,node.case_ids,node.experiment_label,node.invocation_label)!=(
                initial.experiment_id,initial.invocation_id,initial.case_ids,initial.experiment_label,initial.invocation_label):
            raise ValueError('scenario progress node mismatch')
        nodes[index]=node
    document=document.model_copy(update=dict(nodes=tuple(nodes)))
    return document
