"""共享有限任务状态机；终态只表示任务生命周期，不证明业务效果。"""

ORDER={'NOT_CREATED':0,'QUEUED':1,'RUNNING':2,'SUCCESS':3,'FAILED':3,'TIMED_OUT':3,'CANCELLED':3}


def task_transition(previous,previous_task,current,current_task):
    if current not in ORDER or (previous_task is not None and current_task!=previous_task):
        raise ValueError('ASYNC_TASK_STATE_CONFLICT')
    if previous is not None and (ORDER[current]<ORDER[previous] or ORDER[previous]==3 and current!=previous):
        raise ValueError('ASYNC_TASK_STATE_CONFLICT')
    return ORDER[current]==3
