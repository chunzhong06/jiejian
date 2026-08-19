# =============================================================================
# Execution Job 事件追加
#
# 定位
#   Job 状态服务写入有序审计事件的共享事务步骤
#
# 职责
#   分配下一序号｜写入脱敏事件｜保持状态写入与审计同一 UnitOfWork
#
# 边界
#   事件只描述已发生的生命周期变化，不决定状态，也不得包含秘密正文。
#
# 调用链
#   Queue / Attempt / Recovery services → append_job_event → Storage job_events
# =============================================================================

from __future__ import annotations

from product.backend.core.lifecycle import JobState
from product.backend.infra.storage import JobEventRecord, JobRecord, StorageUnitOfWork
from product.backend.infra.runtime.jobs.models import JobEventType

EventMetadata = dict[str, str | int | bool | None]


def append_job_event(
    work: StorageUnitOfWork,
    *,
    job: JobRecord,
    event_type: JobEventType,
    source_state: JobState | None,
    target_state: JobState | None,
    occurred_at_us: int,
    metadata: EventMetadata,
) -> None:
    """按当前事务内的末尾序号追加一个有限元数据事件。"""

    sequence = len(work.job_events.list_for_job(job.job_id)) + 1
    work.job_events.append(
        JobEventRecord(
            job_id=job.job_id,
            sequence=sequence,
            event_type=event_type.value,
            source_state=source_state,
            target_state=target_state,
            occurred_at_us=occurred_at_us,
            metadata=metadata,
        )
    )
