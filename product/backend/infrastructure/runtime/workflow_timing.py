"""显式本地诊断会话的有界阶段计时；记录不参与业务状态或证据接受。"""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import wraps
import json
import re
from threading import Lock
from pathlib import Path
from time import perf_counter_ns
from uuid import uuid4

_active = ContextVar('workflow_timing', default=None)
_parent = ContextVar('workflow_timing_parent', default=None)
PHASES = frozenset({'http.request', 'preparation.read', 'check.preview', 'check.freeze',
    'check.submit', 'check.runtime', 'check.plan', 'check.guidance', 'check.execute',
    'report.publish', 'report.read', 'worker.job'})


def _read_clock():
    # 计量失败仅丢失时长；不能阻止原操作，也不能用负时长冒充有效样本。
    try:
        value = perf_counter_ns()
        return value if isinstance(value, int) and value >= 0 else None
    except Exception:
        return None


@dataclass
class WorkflowTimings:
    session_id: str = field(default_factory=lambda: uuid4().hex)
    stages: list = field(default_factory=list)
    dropped: int = 0
    _sequence: int = 0
    references: dict = field(default_factory=dict)
    _lock: Lock = field(default_factory=Lock, repr=False)

    def document(self):
        return {'schema_version': '1', 'session_id': self.session_id,
                'clock': 'process_monotonic', 'references': self.references, 'stages': self.stages, 'dropped': self.dropped}

    def save(self, var_dir: Path):
        """仅写所属实例日志；诊断保存失败不改变已经形成的业务回执。"""
        try:
            directory = var_dir / 'logs' / 'workflow'
            directory.mkdir(parents=True, exist_ok=True)
            (directory / (self.session_id + '.json')).write_text(
                json.dumps(self.document(), separators=(',', ':')), encoding='utf-8')
        except OSError:
            return False
        return True


@contextmanager
def workflow_timings(**references):
    """调用者明确开启一次会话；不读取目标、表单或任意关联属性。"""
    current = _active.get()
    if current is not None:
        yield current
        return
    value = WorkflowTimings()
    token = _active.set(value)
    parent = _parent.set(None)
    try:
        link_workflow(**references)
        yield value
    finally:
        _parent.reset(parent)
        _active.reset(token)


def link_workflow(**references):
    value = _active.get()
    if value is None:
        return
    patterns = {'job_id': r'job_[0-9a-f]{32}', 'run_id': r'run_[0-9a-f]{32}', 'operation_id': r'[0-9a-f]{32}'}
    for key, reference in references.items():
        if key in patterns and isinstance(reference, str) and re.fullmatch(patterns[key], reference):
            with value._lock:
                value.references[key] = reference


@contextmanager
def workflow_phase(name):
    value = _active.get()
    if value is None:
        yield
        return
    if name not in PHASES:
        raise ValueError('unknown workflow phase')
    with value._lock:
        full = value._sequence >= 2048
        if full:
            value.dropped += 1
        else:
            value._sequence += 1
            sequence = value._sequence
    if full:
        yield
        return
    parent = _parent.get()
    parent_token = _parent.set(sequence)
    started = _read_clock()
    outcome = 'COMPLETE'
    try:
        yield
    except BaseException:
        outcome = 'INTERRUPTED'
        raise
    finally:
        _parent.reset(parent_token)
        # 固定字段不接收异常正文、URL、账号或业务载荷；2048条远小于2MiB预算。
        ended = _read_clock()
        duration = (ended - started) // 1000 if started is not None and ended is not None and ended >= started else None
        event = dict(sequence=sequence, parent=parent, phase=name,
            duration_us=duration, outcome=outcome)
        with value._lock:
            value.stages.append(event)


def timed_workflow(name):
    def decorate(function):
        @wraps(function)
        def measured(*args, **kwargs):
            with workflow_phase(name):
                return function(*args, **kwargs)
        return measured
    return decorate
