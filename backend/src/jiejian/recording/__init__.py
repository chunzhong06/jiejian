"""阶段 3 录制能力的惰性公开导出，避免 Worker 导入 Playwright。"""

from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = [
    "BrowserRecordingAdapter",
    "FlowDraftProcessor",
    "FlowDraftReviewer",
    "RecordingApplicationService",
    "RecordingBrowserSession",
    "RecordingCompletionResultV1",
    "RecordingPage",
    "RecordingRequestStore",
    "RecordingSubmissionResultV1",
    "RecordingFinalizationView",
    "RecordingStatusView",
    "RecordingWorkflow",
    "SubmitRecordingV1",
]

_EXPORTS = {
    "BrowserRecordingAdapter": (".browser", "BrowserRecordingAdapter"),
    "RecordingBrowserSession": (".browser", "RecordingBrowserSession"),
    "RecordingPage": (".browser", "RecordingPage"),
    "FlowDraftProcessor": (".processing", "FlowDraftProcessor"),
    "FlowDraftReviewer": (".review", "FlowDraftReviewer"),
    "RecordingApplicationService": (".application", "RecordingApplicationService"),
    "RecordingCompletionResultV1": (".application", "RecordingCompletionResultV1"),
    "RecordingSubmissionResultV1": (".application", "RecordingSubmissionResultV1"),
    "SubmitRecordingV1": (".application", "SubmitRecordingV1"),
    "RecordingRequestStore": (".request_store", "RecordingRequestStore"),
    "RecordingFinalizationView": (".workflow", "RecordingFinalizationView"),
    "RecordingStatusView": (".workflow", "RecordingStatusView"),
    "RecordingWorkflow": (".workflow", "RecordingWorkflow"),
}


def __getattr__(name: str) -> Any:
    try:
        module_name, attribute = _EXPORTS[name]
    except KeyError:
        raise AttributeError(name) from None
    value = getattr(import_module(module_name, __name__), attribute)
    globals()[name] = value
    return value
