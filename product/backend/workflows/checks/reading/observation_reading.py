# 将已发布观察解释为来源记录、阶段或缺口；不改写证据和安全结论。
from __future__ import annotations

from typing import Literal

from product.protocols.checks.check_result import CheckObservation
from product.protocols.checks.execution_request import WireModel


class ObservationReading(WireModel):
    kind: Literal["REFERENCE", "PROCESS", "OBSERVED", "WAITING", "UNSUPPORTED", "UNAVAILABLE", "INCOMPLETE", "NOT_COLLECTED"]
    label: str
    detail: str
    attention: bool = False


def observation_reading(item: CheckObservation, *, source_type: str | None = None) -> ObservationReading:
    """仅解释同 Run 的事实；来源类型只取冻结配置，不从显示名称猜测。"""
    reasons = set(item.reason_codes)
    auxiliary = item.level != "VERDICT_REQUIRED"

    def reading(kind, label, detail, attention=False):
        return ObservationReading(kind=kind, label=label, detail=detail, attention=attention)

    # 实际读取、关联与预算缺口优先；不能被“已有部分记录”或阶段名称掩盖。
    if 'SOURCE_REQUIRES_MIGRATION' in reasons:
        return reading('UNSUPPORTED','旧来源需要重新准备','旧应用专用核验已停止用于新检查。历史证据保留，请通过通用记录组件重新准备来源。',True)
    if reasons & {'RECORD_REQUEST_INCOMPLETE','RECORD_HISTORY_INCOMPLETE','RECORD_SOURCE_INVALID'}:
        return reading('INCOMPLETE','业务记录尚未闭合','本次请求未确认完成，或记录存在连续性缺口，不能据此证明业务后果没有发生。',True)
    if reasons & {"OBSERVER_CORRELATION_INVALID", "OPERATION_CORRELATION_INVALID", "HISTORY_GENERATION_CHANGED"}:
        return reading("INCOMPLETE", "记录关联未核对", "记录与本次操作、资源或历史版本未能准确对应，不能用于证明本次业务后果。", True)
    if any("TIMEOUT" in code or "TIMED_OUT" in code for code in reasons):
        return reading("UNAVAILABLE", "来源读取超时", "未在本次预算内取得完整记录。检查来源响应与读取预算后，重新检查。", True)
    if reasons & {"MAPPING_MISSING", "MAPPING_REQUIRED", "MAPPING_TYPE_INVALID", "MAPPING_REDACTED", "JSON_INVALID", "JSON_OBJECT_REQUIRED"}:
        return reading("INCOMPLETE", "来源字段不匹配", "来源字段缺失或格式不符；核对字段映射，重新预检查并采用修订后的配置。", True)
    if any(code.endswith(("_UNAVAILABLE", "_ROOT_MISSING", "_SECRET_MISSING")) for code in reasons if code != "OBSERVER_PHASE_UNAVAILABLE"):
        return reading("UNAVAILABLE", "来源未能读取", "本次未能读取对应来源。检查服务、读取授权和账号会话后，发起新的检查。", True)
    if any("LIMIT" in code for code in reasons):
        return reading("INCOMPLETE", "记录读取不完整", "本次读取达到数量、大小或扫描上限，不能把部分记录当作完整观察。", True)
    if reasons & {"AUDIT_EVENT_INVALID", "AUDIT_EVENT_CONFLICT", "AUDIT_CHAIN_INVALID", "AUDIT_CURSOR_UNMATCHED", "AUDIT_CURSOR_AMBIGUOUS", "AUDIT_INVALID_UTF8", "AUDIT_DUPLICATE_KEY"}:
        return reading("INCOMPLETE", "来源记录不完整", "记录格式、连续性或读取锚点未通过核对，保留已取得记录，但不能据此形成完整证明。", True)
    if "OBSERVER_PHASE_UNAVAILABLE" in reasons:
        return reading("NOT_COLLECTED", "本阶段不采集", "该来源没有安排在此阶段采集；这一条不是读取失败。")
    if "AUDIT_TAG_NOT_FOUND" in reasons and item.phase in {"BASELINE", "BEFORE"}:
        return reading("REFERENCE", "操作前尚无本次事件", "此时操作尚未开始；后续是否取得关联事件，需查看操作后和最终观察。")
    if item.phase in {"BASELINE", "BEFORE", "RECOVERY"} and reasons & {"OBSERVATION_UNINTERPRETED", "DISCLOSURE_PROJECTION_INCOMPLETE"}:
        return reading("REFERENCE", "恢复对照记录" if item.phase == "RECOVERY" else "初始对照记录", "这一阶段用于状态对照，不单独判断操作后果；是否核对完成，以本项的初始条件和恢复条件为准。")
    if auxiliary and "SOURCE_RECORDS_AVAILABLE" in reasons:
        return reading("PROCESS", "已取得关联过程记录", "已取得本次操作的关联记录，可用于追踪执行；记录中的派发或完成事件不能单独证明最终业务结果。")
    if auxiliary and "SOURCE_WINDOW_EMPTY" in reasons:
        return reading("PROCESS", "观察窗口内未见消息", "只说明本次队列读取窗口没有关联消息；消息可能已被消费，不能据此认定业务后果未发生。")
    trusted = item.complete and item.reliable and item.correlated and item.authoritative
    if auxiliary and source_type == "ASYNC_TASK_STATUS" and trusted and item.closure == "CLOSED":
        if item.state == "CONFIRMED":
            return reading("PROCESS", "后台任务已完成", "任务来源记录了完成结果；交付物是否真实形成，仍由独立的必要证明确认。")
        if item.state == "ABSENT":
            return reading("PROCESS", "未发现对应任务", "本次任务来源未发现对应任务；同步业务操作可以不创建后台任务，最终后果仍需独立证明。")
    if "EFFECT_PROJECTOR_UNSUPPORTED" in reasons:
        return reading("UNSUPPORTED", "不支持判断此类后果", "当前来源没有解释这类业务后果的能力。需要为该要求配置受支持的证明来源。", True)
    if item.state == "UNKNOWN" or not trusted:
        if reasons & {"TEMPORAL_WINDOW_OPEN", "OBSERVATION_WINDOW_INCOMPLETE", "COMPLETION_UNCONFIRMED"}:
            return reading("WAITING", "此阶段尚未完成观察", "这一阶段未取得完成条件；若本轮没有更晚的有效观察，仍不能确认最终结果。")
        return reading("INCOMPLETE", "证明依据不足", "本条记录未形成完整、可靠且对应本次操作的证明。需核对来源与关联条件，再发起新的检查。", True)
    if item.state == "ABSENT" and item.closure != "CLOSED":
        return reading("WAITING", "此阶段暂未观察到", "观察窗口尚未闭合，不能确认该业务后果不存在。")
    return reading("OBSERVED", "已观察到业务结果" if item.state == "CONFIRMED" else "闭合窗口内未发生", "本条仅说明已观察的业务事实，是否符合权限要求由本轮完整检查判断。")
