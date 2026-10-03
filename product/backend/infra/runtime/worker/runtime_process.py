# 运行加载专用Worker：启动事实发布后继续拥有Node，不能跟随单个CHECK任务退出。
from __future__ import annotations

import argparse
import os
from pathlib import Path
import time

from product.backend.core.errors import JiejianError
from product.backend.core.lifecycle import JobState
from product.backend.infra.runtime.jobs.models import ClaimJob, CompleteCancellation, FatalFailure, FatalFailureCode
from product.backend.infra.runtime.process.controlled.node_owned import start_owned_node
from product.backend.infra.runtime.worker.lifetime import WorkerLifetimeLock, worker_tree_name
from product.protocols.runtime.node_runtime import NodeRuntimeLoadReceipt


def run(var_dir: Path, job_id: str, lease_owner: str, control_session_id: str, node_executable: Path) -> int:
    """仅接受固定Worker入口传来的任务引用；模块执行、端口核对与发布均在独立进程内。"""
    from product.backend.composition.worker import WorkerContainer
    context = WorkerContainer(var_dir,environ=os.environ)
    factory,attempts,publisher = context.uow_factory,context.runtime_attempts,context.runtime_load_jobs
    lifetime=None
    owned=None
    claim=None
    clock=lambda:time.time_ns()//1000
    try:
        lifetime=WorkerLifetimeLock.acquire(var_dir,job_id,lease_owner)
        with factory() as work:
            initial=work.jobs.get(job_id)
            request=None if initial is None or initial.runtime_load_id is None else work.runtime_loads.get(initial.runtime_load_id)
        if request is None or request.control_session_id != control_session_id:
            return 1
        claim=attempts.claim(ClaimJob(job_id=job_id,lease_owner=lease_owner,now_us=clock(),lease_duration_us=60_000_000))
        if claim is None:
            return 1

        def cancelled():
            with factory() as work:
                current=work.jobs.get(job_id)
            return (current is None or current.state is not JobState.RUNNING
                or current.lease_owner != lease_owner or current.fencing_token != claim.job.fencing_token
                or current.cancel_requested_at_us is not None or current.lease_expires_at_us <= clock())

        owned=start_owned_node(var_dir,request,node_executable,environ=dict(os.environ),cancelled=cancelled,
            record_owner_identity={'kind':'windows-job','name':worker_tree_name(job_id,lease_owner)})
        receipt=NodeRuntimeLoadReceipt(load_id=request.load_id,request_fingerprint=claim.job.request_hash,
            reference=owned.reference,started_at_us=clock())
        publisher.publish(job_id=job_id,attempt=claim.job.attempt,lease_owner=lease_owner,
            fencing_token=claim.job.fencing_token,receipt=receipt)
        # Job成功只表示本次加载完成；本Worker继续持有目标树，父控制面退出会回收整树。
        while owned.process.poll() is None:
            time.sleep(.1)
        return 0
    except Exception as error:
        if owned is not None:
            try:
                owned.stop()
                owned=None
            except JiejianError:
                # 所有权尚未确认收口时不写正常取消；父监督者还需核对整棵Worker树。
                return 1
        if claim is not None:
            try:
                with factory() as work:
                    current=work.jobs.get(job_id)
                if current is not None and current.state is JobState.RUNNING:
                    values=dict(job_id=job_id,lease_owner=lease_owner,fencing_token=claim.job.fencing_token,now_us=clock())
                    if current.cancel_requested_at_us is not None:
                        attempts.complete_cancellation(CompleteCancellation(**values))
                    else:
                        attempts.record_fatal_failure(FatalFailure(**values,reason_code=FatalFailureCode.WORKER_FATAL,
                            error_code=error.code if isinstance(error,JiejianError) else "RUNTIME_LOAD_FAILED"))
            except JiejianError:
                # 过期或丢失租约由控制面确认进程退出后恢复，不用过期执行者改写状态。
                pass
        return 1
    finally:
        try:
            if owned is not None:
                owned.stop()
        finally:
            if lifetime is not None:
                lifetime.release()
            context.close()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--var-dir',type=Path,required=True)
    parser.add_argument('--job-id',required=True)
    parser.add_argument('--lease-owner',required=True)
    parser.add_argument('--control-session-id',required=True)
    parser.add_argument('--node-executable',type=Path,required=True)
    args=parser.parse_args()
    from product.backend.infra.runtime.process.controlled.identity import require_python_environment
    require_python_environment()
    return run(args.var_dir.resolve(),args.job_id,args.lease_owner,args.control_session_id,args.node_executable)


if __name__=='__main__':
    raise SystemExit(main())
