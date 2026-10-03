# 控制面只监督固定Runtime Worker；长驻Node由Worker持有，重开不重放旧会话的启动请求。
from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path
import subprocess
import threading
import time
from uuid import uuid4

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.lifecycle import JobState
from product.backend.infra.runtime.jobs.attempts import JobAttempts
from product.backend.infra.runtime.jobs.models import (
    ConfirmRecovery, FatalFailure, FatalFailureCode, RecoveryOperator, RecoveryProofType,
    RecoveryReasonCode, RecoveryScan, WaitingFatalFailure,
)
from product.backend.infra.runtime.jobs.recovery import JobRecovery
from product.backend.infra.runtime.jobs.target_handlers.runtime_load import runtime_load_targets
from product.backend.infra.runtime.process.environment import ProcessEnvironmentRole, spawn_python_module
from product.backend.infra.runtime.process.tree import release_process_tree, terminate_process_tree
from product.backend.infra.runtime.worker.lifetime import WorkerLifetimeLock, worker_tree_name, write_worker_tree_identity

_LOGGER=logging.getLogger('jiejian.runtime.owned')


@dataclass
class _ManagedRuntime:
    project_id: str
    instance_id: str
    job_id: str
    lease_owner: str
    process: subprocess.Popen


class LocalRuntimeSupervisor:
    def __init__(self, var_dir: Path, uow_factory, *, node_executable_provider, environment_provider):
        self.var_dir=var_dir.resolve()
        self.control_session_id='rcs_'+uuid4().hex
        self._uow=uow_factory
        self._node=node_executable_provider
        self._environment=environment_provider
        self._targets=runtime_load_targets()
        self._attempts=JobAttempts(uow_factory,targets=self._targets)
        self._recovery=JobRecovery(uow_factory,targets=self._targets)
        self._stop=threading.Event()
        self._guard=threading.RLock()
        self._managed={}
        self._thread=None
        self._next_recovery=0

    def start(self):
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread=threading.Thread(target=self._loop,name='jiejian-runtime-supervisor',daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(5)
            if self._thread.is_alive():
                raise JiejianError(ErrorCode.PROCESS_TREE_FAILED,'运行监督尚未结束，请重新核对退出状态')
        with self._guard:
            projects=tuple(self._managed)
        for project in projects:
            self.stop_project(project)

    def stop_project(self, project_id, *, expected_instance_id=None):
        # 锁内只操作已拥有的进程句柄，不等待数据库，避免与归档事务互相等待。
        with self._guard:
            current=self._managed.get(project_id)
            if current is None:
                return
            if expected_instance_id is not None and current.instance_id != expected_instance_id:
                raise JiejianError(ErrorCode.STATE_PRECONDITION,'当前运行实例已变化，请重新读取')
            terminate_process_tree(current.process,timeout=5)
            self._managed.pop(project_id,None)
        self._finish_exited(current)

    def _loop(self):
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception:
                # 不写异常正文或环境内容；失败状态由持久Job和下一次只读核对表达。
                _LOGGER.error('运行监督本轮未完成',extra={'event_code':'RUNTIME_SUPERVISOR_FAILED'})
            self._stop.wait(.1)

    def tick(self):
        exited=[]
        with self._guard:
            for project,current in tuple(self._managed.items()):
                if current.process.poll() is not None:
                    release_process_tree(current.process)
                    self._managed.pop(project,None)
                    exited.append(current)
        for current in exited:
            self._finish_exited(current)
        now=time.time_ns()//1000
        if now>=self._next_recovery:
            self._recover(now)
            self._next_recovery=now+1_000_000
        with self._uow() as work:
            job=work.jobs.next_pending(now,target_types=self._targets.target_types)
            request=None if job is None else work.runtime_loads.get(job.runtime_load_id)
        if job is None:
            return
        if request is None or request.control_session_id != self.control_session_id:
            self._fail_waiting(job.job_id,'RUNTIME_SESSION_EXPIRED')
            return
        # 已有同一加载Worker但尚未claim时，不能让轮询重复启动第二个进程。
        with self._guard:
            existing=self._managed.get(job.project_id)
            if existing is not None and existing.job_id==job.job_id:
                return
        try:
            self.stop_project(job.project_id)
            if self._stop.is_set():
                return
            node=self._node()
            environment=dict(self._environment())
            environment.setdefault('JIEJIAN_VAR_DIR',str(self.var_dir))
            owner='runtime-worker-'+uuid4().hex
            def before_release(process,controller):
                write_worker_tree_identity(self.var_dir,job.job_id,owner,controller)
                self._managed[job.project_id]=_ManagedRuntime(job.project_id,request.instance_id,job.job_id,owner,process)
            with self._guard:
                spawn_python_module(environment,'product.backend.infra.runtime.worker.runtime_process',
                    '--var-dir',str(self.var_dir),'--job-id',job.job_id,'--lease-owner',owner,
                    '--control-session-id',self.control_session_id,'--node-executable',str(node),
                    role=ProcessEnvironmentRole.WORKER,cwd=self.var_dir,
                    tree_name=worker_tree_name(job.job_id,owner),before_release=before_release,
                    stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                    creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        except JiejianError as failure:
            self._fail_waiting(job.job_id,failure.code)
        except Exception:
            self._fail_waiting(job.job_id,'RUNTIME_WORKER_START_FAILED')

    def _fail_waiting(self, job_id, error_code):
        self._attempts.record_waiting_fatal_failure(WaitingFatalFailure(
            job_id=job_id,now_us=time.time_ns()//1000,error_code=error_code))

    def _finish_exited(self, managed):
        with self._uow() as work:
            job=work.jobs.get(managed.job_id)
        if job is None or job.state in {JobState.SUCCEEDED,JobState.FAILED,JobState.CANCELLED}:
            return
        now=time.time_ns()//1000
        if job.state in {JobState.PENDING,JobState.RETRY_WAIT}:
            self._fail_waiting(job.job_id,'RUNTIME_WORKER_EXITED')
        elif job.lease_owner==managed.lease_owner and job.lease_expires_at_us>now:
            self._attempts.record_fatal_failure(FatalFailure(job_id=job.job_id,lease_owner=job.lease_owner,
                fencing_token=job.fencing_token,now_us=now,reason_code=FatalFailureCode.WORKER_FATAL,
                error_code='RUNTIME_WORKER_EXITED'))

    def _recover(self, now):
        for candidate in self._recovery.list_recovery_candidates(RecoveryScan(now_us=now)):
            if WorkerLifetimeLock.execution_has_exited(self.var_dir,candidate.job_id,candidate.lease_owner):
                self._recovery.confirm_recovery(ConfirmRecovery(job_id=candidate.job_id,
                    lease_owner=candidate.lease_owner,fencing_token=candidate.fencing_token,now_us=now,
                    proof_type=RecoveryProofType.EXECUTION_EXITED,operator=RecoveryOperator.RECOVERY_CONTROLLER,
                    reason_code=RecoveryReasonCode.PROCESS_EXIT_CONFIRMED))
