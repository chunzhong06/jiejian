# Observer 调用关联、游标与观察窗口模型。

from __future__ import annotations

import re
from typing import Literal

from pydantic import Field, model_validator

from .config import (
    ObserverModel,
    ObservationPhase,
    ObserverSpec,
    ObserverType,
    StructuredAuditLogLocator,
    _AUDIT_OFFSET_FILENAME_PATTERN,
    _HEX_PATTERN,
    _ID_PATTERN,
    _TEXT_PATTERN,
)

class Correlation(ObserverModel):
    case_id: str = Field(pattern=_ID_PATTERN)
    resource_id: str = Field(pattern=_ID_PATTERN)
    request_marker: str = Field(pattern=_TEXT_PATTERN)


class AuditLogStartCursor(ObserverModel):
    file_name: str = Field(pattern=_AUDIT_OFFSET_FILENAME_PATTERN)
    offset: int = Field(ge=0, le=9_223_372_036_854_775_807)
    anchor_start: int | None = Field(default=None, ge=0, le=9_223_372_036_854_775_807)
    anchor_length: int | None = Field(default=None, ge=0, le=256)
    anchor_sha256: str | None = Field(default=None, pattern=_HEX_PATTERN)

    @model_validator(mode="after")
    def validate_anchor(self) -> AuditLogStartCursor:
        anchor = (self.anchor_start, self.anchor_length, self.anchor_sha256)
        if self.offset == 0:
            if any(value is not None for value in anchor):
                raise ValueError("zero offset cannot carry an audit anchor")
        elif (
            self.anchor_start is None
            or self.anchor_length is None
            or self.anchor_length == 0
            or self.anchor_sha256 is None
            or self.anchor_start + self.anchor_length != self.offset
        ):
            raise ValueError("nonzero audit cursor requires a bounded content anchor")
        return self


class ObserverInvocation(ObserverModel):
    schema_version: Literal["1"] = "1"
    spec: ObserverSpec
    correlation: Correlation
    phase: ObservationPhase

    @model_validator(mode="after")
    def validate_invocation(self) -> ObserverInvocation:
        if self.spec.observer_type is ObserverType.STRUCTURED_AUDIT_LOG:
            raise ValueError("structured audit observers require AuditLogObserverInvocation")
        if self.spec.observer_type is ObserverType.ASYNC_TASK_STATUS:
            raise ValueError("async task observers require AsyncTaskObserverInvocation")
        if self.phase not in self.spec.phases:
            raise ValueError("observer invocation phase is not declared by the spec")
        return self


class AsyncTaskObserverInvocation(ObserverModel):
    schema_version: Literal["1"] = "1"
    spec: ObserverSpec
    correlation: Correlation
    phase: ObservationPhase

    @model_validator(mode="after")
    def validate_invocation(self) -> AsyncTaskObserverInvocation:
        if self.spec.observer_type is not ObserverType.ASYNC_TASK_STATUS:
            raise ValueError("async task invocation requires an async task observer")
        if self.phase is not ObservationPhase.EVENTUAL or self.phase not in self.spec.phases:
            raise ValueError("async task invocation requires the EVENTUAL phase")
        return self


class AuditLogObserverInvocation(ObserverModel):
    schema_version: Literal["1"] = "1"
    spec: ObserverSpec
    correlation: Correlation
    phase: ObservationPhase
    start_cursors: tuple[AuditLogStartCursor, ...] = ()

    @model_validator(mode="after")
    def validate_invocation(self) -> AuditLogObserverInvocation:
        if self.spec.observer_type is not ObserverType.STRUCTURED_AUDIT_LOG:
            raise ValueError("audit invocation requires a structured audit observer")
        if self.phase not in self.spec.phases:
            raise ValueError("observer invocation phase is not declared by the spec")
        if len({item.file_name for item in self.start_cursors}) != len(self.start_cursors):
            raise ValueError("audit log start cursors must be unique")
        locator = self.spec.target.locator
        if not isinstance(locator, StructuredAuditLogLocator):
            raise ValueError("audit invocation requires an audit locator")
        base = locator.relative_file_pattern[:-6]
        for item in self.start_cursors:
            if item.file_name != locator.relative_file_pattern and not (
                item.file_name.startswith(base + ".") and re.fullmatch(r"[a-z][a-z0-9_-]{0,48}\.[1-9][0-9]{0,8}\.jsonl", item.file_name)
            ):
                raise ValueError("audit log start cursor is outside the declared rotation family")
        object.__setattr__(self, "start_cursors", tuple(sorted(self.start_cursors, key=lambda item: item.file_name)))
        return self


class ObservationWindow(ObserverModel):
    phase: ObservationPhase
    started_at_us: int = Field(ge=0)
    finished_at_us: int = Field(ge=0)
    timeout_us: int = Field(ge=1, le=120_000_000)

    @model_validator(mode="after")
    def validate_window(self) -> ObservationWindow:
        if self.finished_at_us < self.started_at_us:
            raise ValueError("observation window cannot finish before it starts")
        if self.finished_at_us - self.started_at_us > self.timeout_us:
            raise ValueError("observation window exceeded its timeout")
        return self
