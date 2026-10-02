# 验证只读观察解释区分过程、阶段和真实缺口，保留原始证据及结论语义。
import pytest

from product.backend.workflows.checks.observation_reading import observation_reading
from product.protocols.check_result import CheckObservation


def observation(**changes):
    values = dict(effect_id="bef_" + "a" * 32, proof_fingerprint="f" * 64, observer_id="observer", level="SUPPORTING",
        phase="EVENTUAL", state="UNKNOWN", closure="UNKNOWN", complete=False, reliable=False,
        correlated=False, authoritative=True, window_start_us=1, window_end_us=2,
        correlation_refs=(), reason_codes=())
    return CheckObservation(**(values | changes))


@pytest.mark.parametrize("changes,kind,label", [
    ({"phase": "BASELINE", "reason_codes": ("AUDIT_TAG_NOT_FOUND", "REQUIRED_OBSERVER_INCOMPLETE")}, "REFERENCE", "操作前尚无本次事件"),
    ({"phase": "RECOVERY", "reason_codes": ("OBSERVATION_UNINTERPRETED",)}, "REFERENCE", "恢复对照记录"),
    ({"reason_codes": ("SOURCE_RECORDS_AVAILABLE", "REQUIRED_OBSERVER_INCOMPLETE")}, "PROCESS", "已取得关联过程记录"),
    ({"reason_codes": ("SOURCE_WINDOW_EMPTY", "EFFECT_PROJECTOR_UNSUPPORTED")}, "PROCESS", "观察窗口内未见消息"),
    ({"reason_codes": ("EFFECT_PROJECTOR_UNSUPPORTED",)}, "UNSUPPORTED", "不支持判断此类后果"),
    ({"reason_codes": ("TEMPORAL_WINDOW_OPEN",)}, "WAITING", "此阶段尚未完成观察"),
    ({"state": "ABSENT", "closure": "OPEN", "complete": True, "reliable": True, "correlated": True}, "WAITING", "此阶段暂未观察到"),
    ({"reason_codes": ("OBSERVER_PHASE_UNAVAILABLE",)}, "NOT_COLLECTED", "本阶段不采集"),
    ({"reason_codes": ("MAPPING_TYPE_INVALID",)}, "INCOMPLETE", "来源字段不匹配"),
    ({"reason_codes": ("OPERATION_CORRELATION_INVALID",)}, "INCOMPLETE", "记录关联未核对"),
    ({"reason_codes": ("SOURCE_REQUIRES_MIGRATION",)}, "UNSUPPORTED", "旧来源需要重新准备"),
    ({"reason_codes": ("RECORD_REQUEST_INCOMPLETE",)}, "INCOMPLETE", "业务记录尚未闭合"),
])
def test_published_reading_does_not_rewrite_evidence(changes, kind, label):
    item = observation(**changes)
    before = item.model_dump_json()
    reading = observation_reading(item)
    assert (reading.kind, reading.label) == (kind, label)
    assert item.model_dump_json() == before


@pytest.mark.parametrize("reason,kind", [
    ("AUDIT_TIMEOUT", "UNAVAILABLE"), ("OWNER_API_UNAVAILABLE", "UNAVAILABLE"),
    ("AZURE_QUEUE_MESSAGE_LIMIT", "INCOMPLETE"), ("AUDIT_CHAIN_INVALID", "INCOMPLETE"),
    ("OBSERVER_CORRELATION_INVALID", "INCOMPLETE"),
])
def test_partial_process_records_do_not_hide_real_gaps(reason, kind):
    value = observation_reading(observation(phase="BASELINE", reason_codes=("SOURCE_RECORDS_AVAILABLE", "AUDIT_TAG_NOT_FOUND", reason)))
    assert value.kind == kind and value.attention


def test_process_marker_cannot_upgrade_necessary_proof():
    value = observation_reading(observation(level="VERDICT_REQUIRED", reason_codes=("SOURCE_RECORDS_AVAILABLE", "REQUIRED_OBSERVER_INCOMPLETE")))
    assert value.kind == "INCOMPLETE" and value.attention


@pytest.mark.parametrize("state,label", [("CONFIRMED", "后台任务已完成"), ("ABSENT", "未发现对应任务")])
def test_task_reading_does_not_claim_artifact_exists(state, label):
    item = observation(state=state, complete=True, reliable=True, correlated=True, closure="CLOSED")
    value = observation_reading(item, source_type="ASYNC_TASK_STATUS")
    assert value.kind == "PROCESS" and value.label == label
    assert observation_reading(item, source_type="AZURE_BLOB_OBJECT").kind == "OBSERVED"
    assert observation_reading(item.model_copy(update={"reliable": False}), source_type="ASYNC_TASK_STATUS").attention


def test_confirmed_but_untrusted_and_unknown_reasons_remain_gaps():
    assert observation_reading(observation(state="CONFIRMED")).kind == "INCOMPLETE"
    assert observation_reading(observation(reason_codes=("NEW_UNKNOWN_FAILURE",))).attention
