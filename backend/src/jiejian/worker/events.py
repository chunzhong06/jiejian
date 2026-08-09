"""Job Event 连续追加的共享事务边界。"""

from __future__ import annotations

from ..domain.lifecycle import JobState
from ..storage import JobEventRecord, JobRecord, StorageUnitOfWork
from .models import JobEventType

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
