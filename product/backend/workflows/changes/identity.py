# 将已冻结内容身份与当前授权源码作只读比较；不回填历史 Git、不参与检查执行或安全判断。
from __future__ import annotations

import time
from typing import Literal
from pydantic import Field

from product.backend.core.errors import JiejianError
from product.backend.infra.source_identity import GitSourceContext, inspect_git_source
from product.protocols.execution_v3 import Hash, LogicalId, WireModel


class SourceIdentityRecord(WireModel):
    fingerprint: Hash
    snapshot_id: str | None
    file_count: int | None = Field(default=None, ge=0, le=512)
    git_status: Literal["NOT_RECORDED"] = "NOT_RECORDED"


class SourceIdentityComparison(WireModel):
    project_id: LogicalId
    run_id: str | None = None
    change_id: str | None = None
    comparison: Literal["SAME", "CHANGED", "NO_BASELINE", "UNAVAILABLE"]
    recorded: SourceIdentityRecord | None
    current_fingerprint: Hash | None
    current_git: GitSourceContext
    observed_at_us: int = Field(ge=0)
    target_version: Literal["NOT_INDEPENDENTLY_IDENTIFIED"] = "NOT_INDEPENDENTLY_IDENTIFIED"


class SourceIdentityReader:
    """GUI 只读投影：历史输入只来自精确变化或校验通过的发布包，GET 不持久化。"""

    def __init__(self, *, uow_factory, understanding, changes, results):
        self._uow_factory, self._understanding = uow_factory, understanding
        self._changes, self._results = changes, results

    def for_change(self, project_id: str, change_id: str) -> SourceIdentityComparison:
        _, change, _ = self._changes.get(project_id, change_id)
        with self._uow_factory() as work:
            snapshot = work.source_changes.snapshot(change.current_snapshot_id)
        fingerprint = snapshot.source_fingerprint if snapshot and snapshot.project_id == project_id else None
        return self._compare(project_id, fingerprint, change_id=change_id)

    def for_run(self, project_id: str, run_id: str) -> SourceIdentityComparison:
        package = self._results.package(run_id, project_id=project_id)
        return self._compare(project_id, package.request.source_fingerprint, run_id=run_id)

    def _compare(self, project_id, fingerprint, *, run_id=None, change_id=None):
        recorded = None
        if fingerprint is not None:
            with self._uow_factory() as work:
                snapshot = work.source_changes.snapshot_for_fingerprint(project_id, fingerprint)
            recorded = SourceIdentityRecord(fingerprint=fingerprint,
                snapshot_id=None if snapshot is None else snapshot.snapshot_id,
                file_count=None if snapshot is None else len(snapshot.files))
        current, git, comparison = None, GitSourceContext(status="UNAVAILABLE"), "UNAVAILABLE"
        try:
            before = self._understanding.get(project_id)
            # inspector 自身核验授权；拒绝时不启动 Git，不暴露本地路径。
            if not before.source_analysis_authorized:
                raise ValueError("source access not authorized")
            current = self._understanding.inspect_source_fingerprint(project_id)
            middle = self._understanding.get(project_id)
            if (before.revision, before.source_root, True) != (middle.revision, middle.source_root, middle.source_analysis_authorized):
                raise ValueError("source context changed")
            git = inspect_git_source(before.source_root)
            after = self._understanding.get(project_id)
            second = self._understanding.inspect_source_fingerprint(project_id)
            if (before.revision, before.source_root, current) != (after.revision, after.source_root, second):
                current, git = None, GitSourceContext(status="UNAVAILABLE")
            else:
                comparison = "NO_BASELINE" if recorded is None else "SAME" if current == fingerprint else "CHANGED"
        except (JiejianError, OSError, ValueError):
            current, git = None, GitSourceContext(status="UNAVAILABLE")
        return SourceIdentityComparison(project_id=project_id, run_id=run_id, change_id=change_id,
            comparison=comparison, recorded=recorded, current_fingerprint=current, current_git=git,
            observed_at_us=time.time_ns() // 1000)
