# 持久登录任务的提交、回读与控制；浏览器和秘密采集只在独立 Worker 中执行。
from __future__ import annotations

import hashlib
import json
import re
import time
from urllib.parse import urlsplit
from uuid import uuid4

from product.backend.application.test_identities.models import IdentityPreparationStatus, IdentityPreparationView, PREPARATION_TERMINAL
from product.backend.application.test_identities.service import TestIdentityStatus
from product.backend.application.test_identities.source import preparation_source
from product.backend.domain.boundaries.entities import boundary_sha256
from product.backend.domain.errors import ErrorCode, JiejianError
from product.backend.domain.lifecycle import JobState
from product.backend.infrastructure.identity.control import valid_identity_preparation_marker
from product.backend.infrastructure.runtime.jobs.events import append_job_event
from product.backend.infrastructure.runtime.jobs.models import JobEventType, RequestCancellation
from product.backend.infrastructure.runtime.paths import RuntimePaths
from product.backend.infrastructure.storage import JobRecord
from product.protocols.preparation.test_identity_preparation import IdentityPreparationRequest, canonical_identity_preparation_json_bytes
from product.protocols.web.target import WebTargetScope




# 控制面只持有持久任务的提交和读取能力；重建本对象不丢失原登录任务。
class IdentityPreparationManager:
    def __init__(self, var_dir, identities, secret_store, environment, *, application_understanding,
                 business_boundaries, uow_factory, job_queue, clock_us=None):
        self._paths = RuntimePaths(var_dir).ensure_layout()
        self._identities = identities
        self._understanding = application_understanding
        self._boundaries = business_boundaries
        self._uow = uow_factory
        self._queue = job_queue
        self._secrets, self._environment = secret_store, environment
        self._clock = clock_us or (lambda: time.time_ns() // 1000)
        self._wake = lambda: None

    def bind_worker(self, wake):
        self._wake = wake

    def source(self, identity):
        return preparation_source(identity, self._understanding.get(identity.project_id), self._boundaries.view(identity.project_id))

    def start(self, identity_id, *, operation_id=None):
        # 重试须复用 operation_id，回读原任务的当前状态，包括已完成或已取消的状态。
        # 开始新一轮登录应使用新标识；同一账号仍有活动任务时继续返回原任务。
        return self._start(identity_id, operation_id=operation_id)

    def _start(self, identity_id, *, operation_id=None, official_account=None):
        operation = operation_id or uuid4().hex
        if not re.fullmatch(r'[0-9a-f]{32}', operation):
            raise JiejianError(ErrorCode.INPUT_INVALID, '登录操作标识格式无效')
        preparation_id = 'prep_' + hashlib.sha256(f'{identity_id}:{operation}'.encode()).hexdigest()[:32]
        # 先查询原请求，再核对当前账号，避免已保存成功的重试被“账号已准备”拒绝。
        with self._uow() as work:
            existing = work.identity_preparations.get(preparation_id)
        if existing is not None:
            if existing['official_account'] != official_account:
                raise JiejianError(ErrorCode.STATE_PRECONDITION, '登录操作内容与原请求不一致')
            return self.status(preparation_id)
        identity = self._identities.get(identity_id)
        if identity.status is not TestIdentityStatus.NOT_PREPARED:
            raise JiejianError(ErrorCode.TEST_IDENTITY_NOT_READY, '请先核对或重置当前登录状态')
        endpoint, source = self.source(identity)
        parsed = urlsplit(endpoint)
        port = parsed.port or (443 if parsed.scheme == 'https' else 80)
        origin = f'{parsed.scheme}://{parsed.hostname}:{port}'
        request = IdentityPreparationRequest(schema_version='1', preparation_id=preparation_id,
            project_id=identity.project_id, identity_id=identity_id,
            target_scope=WebTargetScope(base_url=origin, allowed_origins=(origin,),
                allowed_hosts=(parsed.hostname,), allowed_ports=(port,), allow_private_network=True,
                follow_redirects=False, timeout_seconds=10.0, max_requests=256, max_response_bytes=1_048_576))
        now = self._clock()
        with self._uow() as work:
            work.acquire_write_lock()
            # 请求标识解决同次重试，账号所有者解决不同请求并发；两者都要在写锁内复核。
            generation, owner = work.test_identities.preparation_owner(identity_id)
            if owner:
                previous = work.identity_preparations.get(owner)
                previous_job = None if previous is None else work.jobs.get(previous['job_id'])
                if previous_job is not None and previous_job.state in {JobState.PENDING, JobState.RUNNING, JobState.RETRY_WAIT}:
                    return self._view(previous, previous_job)
                if previous is not None and previous['phase'] == 'CLEANUP_REQUIRED':
                    raise JiejianError(ErrorCode.STATE_PRECONDITION, '上次登录尚未完成清理，请先处理原任务')
            existing = work.identity_preparations.get(preparation_id)
            if existing is not None:
                return self._view(existing, work.jobs.get(existing['job_id']))
            current = work.test_identities.get(identity_id)
            if current is None or current.auth_method is not None or current.updated_at_us != identity.updated_at_us:
                raise JiejianError(ErrorCode.STATE_PRECONDITION, '账号条件已变化，请重新核对')
            raw = canonical_identity_preparation_json_bytes(request).decode('utf-8')
            digest = boundary_sha256({'request': json.loads(raw), 'source': source, 'generation': generation, 'official_account': official_account})
            job = JobRecord(job_id='job_' + uuid4().hex, project_id=identity.project_id,
                identity_preparation_id=preparation_id, operation_type='IDENTITY_PREPARATION', state=JobState.PENDING,
                idempotency_key=operation, request_hash=digest, attempt=0, max_attempts=1, available_at_us=now,
                fencing_token=0, created_at_us=now, updated_at_us=now)
            row = dict(preparation_id=preparation_id, project_id=identity.project_id, identity_id=identity_id,
                job_id=job.job_id, operation_id=operation, request_fingerprint=digest, source_fingerprint=source,
                authentication_generation=generation, request_json=raw, official_account=official_account,
                save_requested=False, phase='STARTING', error_code=None, created_at_us=now, updated_at_us=now)
            # 准备记录、Job、账号占用和提交事件必须一起提交，避免出现无法调度的登录。
            work.identity_preparations.add(row)
            work.jobs.add(job)
            work.test_identities.claim_preparation(identity_id, preparation_id)
            append_job_event(work, job=job, event_type=JobEventType.JOB_SUBMITTED, source_state=None,
                target_state=JobState.PENDING, occurred_at_us=now, metadata={})
            work.commit()
        # 调度唤醒发生在提交后；唤醒失败也不撤销持久任务，调用方可按原标识回读。
        self._wake()
        return self.status(preparation_id)

    def latest(self, identity_id):
        self._identities.get(identity_id)
        with self._uow() as work:
            rows = work.identity_preparations.list(identity_id=identity_id, limit=1)
        return None if not rows else self.status(rows[0]['preparation_id'])

    def requested(self, identity_id, operation_id):
        # 供响应丢失后的回执查询使用；没有命中时只返回缺失，不触发新登录。
        self._identities.get(identity_id)
        if re.fullmatch(r'[0-9a-f]{32}', operation_id) is None:
            raise JiejianError(ErrorCode.INPUT_INVALID, '登录操作标识格式无效')
        preparation_id = 'prep_' + hashlib.sha256(f'{identity_id}:{operation_id}'.encode()).hexdigest()[:32]
        with self._uow() as work:
            row = work.identity_preparations.get(preparation_id)
        return None if row is None else self.status(preparation_id)

    def list(self, project_id):
        with self._uow() as work:
            return tuple(self._view(row, work.jobs.get(row['job_id'])) for row in work.identity_preparations.list(project_id=project_id))

    def status(self, preparation_id):
        with self._uow() as work:
            row = work.identity_preparations.get(preparation_id)
            if row is None:
                raise JiejianError(ErrorCode.TEST_IDENTITY_NOT_FOUND, '登录准备任务不存在')
            return self._view(row, work.jobs.get(row['job_id']))

    def _view(self, row, job):
        # Job 决定是否取消或失败，浏览器标记只细分运行阶段；清理缺口单独展示。
        if job is None:
            raise JiejianError(ErrorCode.STORAGE_STATE, '登录任务关联不完整')
        phase = row['phase']
        if job.state is JobState.CANCELLED:
            phase = 'CANCELLED'
        elif job.state is JobState.FAILED:
            phase = 'FAILED'
        elif job.cancel_requested_at_us is not None and job.state is not JobState.SUCCEEDED:
            phase = 'CANCELLING'
        elif job.state is JobState.RUNNING and phase not in PREPARATION_TERMINAL:
            ready = self._paths.identity_preparations / row['preparation_id'] / 'browser.ready'
            phase = 'SAVING' if row['save_requested'] else 'WAITING_FOR_LOGIN' if valid_identity_preparation_marker(ready) else 'STARTING'
        cleanup_required = row['phase'] == 'CLEANUP_REQUIRED'
        if phase == 'CLEANUP_REQUIRED':
            phase = 'PREPARED' if job.state is JobState.SUCCEEDED else 'FAILED'
        messages = {'STARTING': '正在打开登录窗口', 'WAITING_FOR_LOGIN': '在登录窗口完成登录后，回到这里保存',
            'SAVING': '正在保存登录状态', 'CANCELLING': '正在停止并清理', 'PREPARED': '登录已保存',
            'FAILED': '登录已中断，请核对原任务后重新登录', 'CANCELLED': '本次登录已取消', 'UNSUPPORTED': '当前登录方式暂不支持安全保存'}
        return IdentityPreparationView(preparation_id=row['preparation_id'], identity_id=row['identity_id'],
            project_id=row['project_id'], job_id=job.job_id, status=IdentityPreparationStatus(phase),
            message=messages[phase], error_code=row['error_code'], cleanup_required=cleanup_required)

    def confirm(self, preparation_id):
        # 此处只持久化保存意图；Worker 观察该意图后才通知浏览器采集受控登录状态。
        value = self.status(preparation_id)
        if value.status.value in PREPARATION_TERMINAL:
            return value
        if value.status is not IdentityPreparationStatus.WAITING_FOR_LOGIN:
            raise JiejianError(ErrorCode.TEST_IDENTITY_NOT_READY, '登录窗口尚未就绪')
        with self._uow() as work:
            work.acquire_write_lock()
            row = work.identity_preparations.get(preparation_id)
            job = work.jobs.get(row['job_id'])
            if job.state is not JobState.RUNNING or job.cancel_requested_at_us is not None:
                raise JiejianError(ErrorCode.STATE_PRECONDITION, '登录任务已变化，请重新读取')
            work.identity_preparations.update(preparation_id, save_requested=True, now_us=self._clock())
            work.commit()
        return self.status(preparation_id)

    def cancel(self, preparation_id):
        # 返回取消请求的当前状态，不以请求被接受证明浏览器和临时凭据已经清理。
        value = self.status(preparation_id)
        if value.status.value not in PREPARATION_TERMINAL:
            self._queue.request_cancellation(RequestCancellation(job_id=value.job_id, now_us=self._clock()))
        return self.status(preparation_id)

    def start_official(self, identity_id, *, account, origin):
        identity = self._identities.get(identity_id)
        endpoint, _ = self.source(identity)
        if account not in {'curator', 'judge'} or endpoint.rstrip('/') != origin.rstrip('/') or urlsplit(origin).hostname != '127.0.0.1':
            raise JiejianError(ErrorCode.STATE_PRECONDITION, '示例登录地址需要重新核对')
        if identity.status is TestIdentityStatus.PREPARED:
            return None
        previous = self.latest(identity_id)
        if previous and previous.status.value not in PREPARATION_TERMINAL:
            return previous
        return self._start(identity_id, official_account=account)

    def prepare_official(self, identity_id, *, account, origin):
        value = self.start_official(identity_id, account=account, origin=origin)
        deadline = time.monotonic() + 40
        while value and value.status.value not in PREPARATION_TERMINAL and time.monotonic() < deadline:
            time.sleep(0.1)
            value = self.status(value.preparation_id)
        if value and value.status is not IdentityPreparationStatus.PREPARED:
            if value.status.value not in PREPARATION_TERMINAL:
                self.cancel(value.preparation_id)
            raise JiejianError(ErrorCode.IDENTITY_PREPARATION_FAILED, '示例登录未完成，请查看原任务')
        return value

    def active_runtime_paths(self):
        # 等待领取的持久任务也保护其目录，不能仅按当前进程中是否存在句柄判断活动性。
        with self._uow() as work:
            rows = work.identity_preparations.list(limit=256)
            return tuple(self._paths.identity_preparations / row['preparation_id'] for row in rows
                if work.jobs.get(row['job_id']).state in {JobState.PENDING, JobState.RUNNING, JobState.RETRY_WAIT})

    def close(self):
        # 进程属于 Worker；控制面关闭不抹去持久任务，也不删除仍被租约占用的目录。
        return None

    def reconcile_exited(self, job):
        """仅由已取得整棵执行树退出证明的监督器调用，精确收回未提交引用。"""
        if job.identity_preparation_id is None:
            return
        from product.backend.application.test_identities.login_execution import IdentityLoginSupervisor
        engine = IdentityLoginSupervisor(self._paths.root, self._identities, self._secrets, self._environment,
            application_understanding=self._understanding, business_boundaries=self._boundaries, reconcile=False)
        directory = self._paths.identity_preparations / job.identity_preparation_id
        # 本方法不终止进程；调用者负责退出证明，journal 负责限定本次可补偿的引用。
        complete = not directory.exists() or engine.cleanup_attempt(directory)
        with self._uow() as work:
            work.identity_preparations.update(job.identity_preparation_id,
                phase=('PREPARED' if job.state is JobState.SUCCEEDED else
                    'CANCELLED' if job.cancel_requested_at_us is not None or job.state is JobState.CANCELLED else 'FAILED') if complete else 'CLEANUP_REQUIRED',
                now_us=self._clock())
            work.commit()
        if not complete:
            raise JiejianError(ErrorCode.TEST_IDENTITY_SECRET_CLEANUP, '登录进程已结束，临时凭据仍需清理')
        if directory.exists():
            # 先收回临时引用，再向维护服务发布闲置事实；目录存在本身不是可删除依据。
            from product.backend.infrastructure.maintenance.inventory import mark_runtime_idle
            mark_runtime_idle(self._paths.root, directory, "identity-preparation")

    def retry_cleanup(self, preparation_id):
        # 未领取的任务没有执行树；有过 attempt 的终态任务仍须重验原 Worker 的退出收据。
        from product.backend.infrastructure.runtime.worker.lifetime import WorkerLifetimeLock
        with self._uow() as work:
            row = work.identity_preparations.get(preparation_id)
            if row is None:
                raise JiejianError(ErrorCode.TEST_IDENTITY_NOT_FOUND, '登录任务不存在')
            job = work.jobs.get(row['job_id'])
        if job.state in {JobState.PENDING, JobState.RUNNING, JobState.RETRY_WAIT}:
            raise JiejianError(ErrorCode.STATE_PRECONDITION, '原登录任务仍在收尾，请稍后读取')
        if job.attempt and not WorkerLifetimeLock.completed_execution_has_exited(self._paths.root, job.job_id):
            raise JiejianError(ErrorCode.PROCESS_TREE_FAILED, '尚未确认登录进程退出，暂不清理')
        self.reconcile_exited(job)
        return self.status(preparation_id)
