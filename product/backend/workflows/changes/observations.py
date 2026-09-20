# 在授权扫描范围采集有界 Git 元数据；不可用观察不改变准备、计划或安全判断。
from __future__ import annotations

import time
from uuid import uuid4
from product.backend.core.errors import JiejianError
from product.backend.infra.source_identity import inspect_git_source


class CodeObservationService:
    def __init__(self, understanding, *, clock_us=None):
        self._understanding = understanding
        self._clock = clock_us or (lambda: time.time_ns() // 1000)

    def capture(self, project_id, source_fingerprint):
        value = dict(observation_id="obs_" + uuid4().hex, project_id=project_id,
            source_fingerprint=source_fingerprint, observed_at_us=self._clock(), git_status="UNAVAILABLE",
            head=None, has_local_changes=None, consistency="UNAVAILABLE", scope="AUTHORIZED_SOURCE_SCAN")
        try:
            before = self._understanding.get(project_id)
            if not before.source_analysis_authorized:
                return value
            first = self._understanding.inspect_source_fingerprint(project_id)
            git = inspect_git_source(before.source_root)
            second = self._understanding.inspect_source_fingerprint(project_id)
            final_git = inspect_git_source(before.source_root)
            after = self._understanding.get(project_id)
            if ((before.revision, before.source_root, before.source_analysis_authorized) !=
                (after.revision, after.source_root, after.source_analysis_authorized) or
                first != source_fingerprint or second != source_fingerprint or
                git.status == "UNAVAILABLE" or git != final_git):
                return value
            value.update(git_status=git.status, head=git.head, has_local_changes=git.has_local_changes, consistency="CONSISTENT")
        except (JiejianError, OSError, ValueError):
            pass
        return value

    def attach_run(self, work, run):
        value = self.capture(run.project_id, run.source_fingerprint)
        work.code_observations.add_link(value, kind="run", target_id=run.run_id,
            project_id=run.project_id, source_fingerprint=run.source_fingerprint)
