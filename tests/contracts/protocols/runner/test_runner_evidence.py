# 验证 Runner Evidence 语义载荷、观察完整性与秘密边界。

from __future__ import annotations
import pytest
from product.backend.domain.lifecycle import CaseVerdict
from product.backend.domain.verification.facts import ExecutionOutcome, ObservedEffect
from product.protocols.runner.evidence import build_evidence
from tests.support.builders.runtime.runner import evidence
pytestmark = pytest.mark.level2


def test_evidence_keeps_its_existing_frozen_fingerprint():
    # 合并前的确定性样本指纹；不能用本次待测编码器生成预期值。
    assert evidence().evidence_hash=='32cd1db8ac67950c1fdbf886002ba2b590d2a9eeb85214842a53ddb62ce18b97'


def test_shared_canonical_bytes_preserve_models_enums_and_mapping_keys():
    from types import MappingProxyType
    from pydantic import BaseModel
    from product.backend.domain.verification.permissions.contract import canonical_json_bytes

    class Item(BaseModel):
        items: tuple[CaseVerdict,str]

    value=MappingProxyType({2:Item(items=(CaseVerdict.SAFE,'界鉴')),'a':(1,False)})
    assert canonical_json_bytes(value)=='{"2":{"items":["SAFE","界鉴"]},"a":[1,false]}'.encode('utf-8')
    with pytest.raises(ValueError,match='Out of range float values'):
        canonical_json_bytes({'value':float('inf')})

def test_current_evidence_carries_execution_and_observation_facts() -> None:
    current_evidence = evidence()
    assert current_evidence.execution_fact.outcome is ExecutionOutcome.ACCEPTED
    assert current_evidence.observation_facts[0].effect is ObservedEffect.CONFIRMED

def test_incomplete_observation_requires_inconclusive_verdict() -> None:
    current_evidence = evidence(available=False, verdict=CaseVerdict.INCONCLUSIVE)
    assert current_evidence.verdict is CaseVerdict.INCONCLUSIVE

def test_evidence_rejects_missing_observation_fact_coverage() -> None:
    raw = evidence().model_dump(mode="python")
    raw.pop("evidence_id")
    raw.pop("evidence_hash")
    raw["observation_facts"] = ()
    with pytest.raises(ValueError, match="exactly cover"):
        build_evidence(**raw)


def test_evidence_builder_hashes_normalized_fact_and_reason_order() -> None:
    raw = evidence(resource_ids=("resource-a", "resource-z")).model_dump(mode="python")
    raw.pop("evidence_id")
    raw.pop("evidence_hash")
    raw["observation_facts"] = tuple(reversed(raw["observation_facts"]))
    raw["reason_codes"] = ("Z_REASON", "A_REASON")

    rebuilt = build_evidence(**raw)

    assert [item.resource_id for item in rebuilt.observation_facts] == [
        "resource-a",
        "resource-z",
    ]
    assert rebuilt.reason_codes == ("A_REASON", "Z_REASON")
