# =============================================================================
# Runner 旁路进度
#
# 定位
#   为正在执行的受限检查提供可删除、不可参与结果发布的阶段事件旁路。
#
# 职责
#   严格校验有界 JSONL 事件｜隔离写入失败｜按当前 Job 安全读取进度。
#
# 边界
#   不保存请求、响应、身份、资源或结论事实；不影响 Runner 生命周期、清理和结果协议。
#   事件使用独立展示时钟，不能消费或改变权威 RunnerResult 时间源。
# =============================================================================

from __future__ import annotations

import json
import re
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from product.backend.infra.artifacts.run_packages import attempt_paths_for
from product.backend.infra.storage import JobRecord


PROGRESS_MAX_EVENTS = 256
PROGRESS_MAX_BYTES = 64 * 1024
PROGRESS_MAX_LINE_BYTES = 2 * 1024
_CASE_ID_PATTERN = re.compile(r"^case-[0-9a-f]{32}$")
_BUSINESS_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_SENSITIVE_NAME_PARTS = (
    "secret",
    "token",
    "cookie",
    "password",
    "passwd",
    "bearer",
    "authorization",
)


class ProgressTwinRole(StrEnum):
    ALLOW_CONTROL = "ALLOW_CONTROL"
    DENY_VARIANT = "DENY_VARIANT"


class ProgressPhase(StrEnum):
    PREPARE = "PREPARE"
    BASELINE = "BASELINE"
    TARGET = "TARGET"
    OBSERVE = "OBSERVE"
    VERIFY = "VERIFY"
    RECOVERY = "RECOVERY"


class ProgressState(StrEnum):
    STARTED = "STARTED"
    COMPLETED = "COMPLETED"


class RunnerProgressEvent(BaseModel):
    """一条只包含业务阶段标识的严格旁路事件。"""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        frozen=True,
        hide_input_in_errors=True,
    )

    schema_version: Literal["1"] = "1"
    sequence: int = Field(ge=1)
    case_id: str = Field(min_length=1, max_length=128)
    action_id: str = Field(min_length=1, max_length=128)
    twin_role: ProgressTwinRole | None = None
    phase: ProgressPhase
    state: ProgressState
    recorded_at_us: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_business_ids(self) -> RunnerProgressEvent:
        if _CASE_ID_PATTERN.fullmatch(self.case_id) is None:
            raise ValueError("progress case_id is not a restricted case identifier")
        if _BUSINESS_ID_PATTERN.fullmatch(self.action_id) is None:
            raise ValueError("progress action_id is not a restricted business identifier")
        folded = self.action_id.casefold()
        if any(part in folded for part in _SENSITIVE_NAME_PARTS):
            raise ValueError("progress action_id contains a sensitive name")
        return self


class RunnerProgressWriter:
    """按事件预算追加旁路事件；任何自身故障都只禁用 writer。"""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._handle = None
        self._sequence = 1
        self._event_count = 0
        self._byte_count = 0
        self._enabled = False
        try:
            if path.exists() and path.stat().st_size:
                return
            self._handle = path.open("ab")
            self._enabled = True
        except Exception:
            self._disable()

    @property
    def enabled(self) -> bool:
        return self._enabled

    def record(
        self,
        *,
        case_id: str,
        action_id: str,
        twin_role: str | None,
        phase: str,
        state: str,
        recorded_at_us: int,
    ) -> bool:
        """校验并追加一条事件；失败时不向 Runner 抛出异常。"""

        if not self._enabled or self._handle is None:
            return False
        try:
            if self._event_count >= PROGRESS_MAX_EVENTS:
                self._disable()
                return False
            event = RunnerProgressEvent(
                sequence=self._sequence,
                case_id=case_id,
                action_id=action_id,
                twin_role=ProgressTwinRole(twin_role) if twin_role is not None else None,
                phase=ProgressPhase(phase),
                state=ProgressState(state),
                recorded_at_us=recorded_at_us,
            )
            encoded = json.dumps(
                event.model_dump(mode="json"),
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8") + b"\n"
            if len(encoded) > PROGRESS_MAX_LINE_BYTES or self._byte_count + len(encoded) > PROGRESS_MAX_BYTES:
                self._disable()
                return False
            self._handle.write(encoded)
            self._handle.flush()
            self._byte_count += len(encoded)
            self._event_count += 1
            self._sequence += 1
            return True
        except Exception:
            self._disable()
            return False

    append = record

    def close(self) -> None:
        try:
            if self._handle is not None:
                self._handle.close()
        except Exception:
            pass
        finally:
            self._handle = None
            self._enabled = False

    def _disable(self) -> None:
        self._enabled = False
        try:
            if self._handle is not None:
                self._handle.close()
        except Exception:
            pass
        finally:
            self._handle = None


class RunnerProgressReader:
    """只从当前 Job 的受限 attempt 路径读取完整、连续且未篡改的事件。"""

    def __init__(self, var_dir: Path) -> None:
        self.var_dir = var_dir.resolve()

    def read(self, job: JobRecord) -> tuple[RunnerProgressEvent, ...]:
        if job.attempt <= 0:
            return ()
        try:
            path = attempt_paths_for(self.var_dir, job).attempt_dir / "progress.jsonl"
            if path.stat().st_size > PROGRESS_MAX_BYTES:
                return ()
            raw = path.read_bytes()
            if not raw or not raw.endswith(b"\n"):
                return ()
            lines = raw.splitlines(keepends=True)
            if len(lines) > PROGRESS_MAX_EVENTS:
                return ()
            result: list[RunnerProgressEvent] = []
            expected = 1
            for line in lines:
                if len(line) > PROGRESS_MAX_LINE_BYTES or not line.endswith(b"\n"):
                    return ()
                event = RunnerProgressEvent.model_validate_json(line[:-1], strict=True)
                if event.sequence != expected:
                    return ()
                result.append(event)
                expected += 1
            return tuple(result)
        except Exception:
            return ()
