# 验证已发布要求与证据的只读对应关系，不运行目标或重新裁决。
from types import SimpleNamespace as N
from unittest.mock import Mock

import pytest

from product.backend.core.errors import JiejianError
from product.backend.infra.artifacts.check_publication import CheckPublisher
from product.backend.workflows.checks.results import CheckResultReader
from product.backend.workflows.checks.story import CheckStoryBuilder, _proof_coverage
from tests.fixtures.check_publication import package_parts, NOW


def _coverage(*, level="VERDICT_REQUIRED", state="CONFIRMED", closure="CLOSED", observations=()):
    requirement = N(effect_id="effect", proof_fingerprint="proof", binding_fingerprint="binding", level=level)
    proof = N(effect_id="effect", business_label="业务结果", source_label="冻结来源")
    fact = N(effect_id="effect", proof_fingerprint="proof", state=state, closure=closure)
    documents = (N(evidence_id="document", observations=observations),)
    return _proof_coverage(N(proof_requirements=(requirement,)), {"binding": proof}, documents, (fact,))[0]


def _observation(level, *, effect="effect", proof="proof"):
    return N(effect_id=effect, proof_fingerprint=proof, level=level)


def test_observation_level_separates_shared_document_references():
    result = _coverage(observations=(_observation("VERDICT_REQUIRED"), _observation("SUPPORTING"),
                                    _observation("DIAGNOSIS_REQUIRED")))
    assert result.evidence_refs == result.supporting_evidence_refs == ("document",)
    assert result.observed_state == "CONFIRMED" and result.source_label == "冻结来源"
    supporting = _coverage(level="SUPPORTING", observations=(_observation("SUPPORTING"),))
    assert supporting.evidence_refs == () and supporting.supporting_evidence_refs == ("document",)
    assert supporting.required_level == "SUPPORTING" and supporting.limitations


@pytest.mark.parametrize("observations", [(), (_observation("VERDICT_REQUIRED", effect="other"),),
    (_observation("VERDICT_REQUIRED", proof="other"),)])
def test_missing_or_unrelated_observations_never_invent_coverage(observations):
    result = _coverage(observations=observations)
    assert result.observed_state == "UNKNOWN" and result.evidence_refs == ()
    assert "本轮没有对应观察" in result.limitations


def test_open_absence_is_unknown_without_changing_existing_fact():
    result = _coverage(state="ABSENT", closure="OPEN", observations=(_observation("VERDICT_REQUIRED"),))
    assert result.observed_state == "UNKNOWN" and "观察窗口尚未闭合" in result.limitations
    closed = _coverage(state="ABSENT", observations=(_observation("VERDICT_REQUIRED"),))
    assert closed.observed_state == "ABSENT" and closed.limitations == ()


def test_static_published_package_preserves_verdict_case_scope_and_integrity(package_parts, monkeypatch):
    var_dir, factory, job, staging, _ = package_parts
    package = CheckPublisher(var_dir, factory, clock_us=lambda: NOW+20).publish(staging)
    reader = CheckResultReader(var_dir=var_dir, uow_factory=factory)
    builder = CheckStoryBuilder(reader)
    forbidden = Mock(side_effect=AssertionError("read projection must not execute or consult live registry"))
    monkeypatch.setattr("product.backend.core.verification.checks.evaluate_check_case", forbidden)
    monkeypatch.setattr("product.backend.workflows.checks.registry.CheckRuntimeRegistry.snapshot", forbidden)
    with monkeypatch.context() as context:
        context.setattr("product.backend.workflows.checks.story._proof_coverage", lambda *args: ())
        old_fields = builder.build(job.run_id).model_dump(exclude={"actions": {"__all__": {"proof_coverage"}}})
    result = builder.build(job.run_id)
    assert result.model_dump(exclude={"actions": {"__all__": {"proof_coverage"}}}) == old_fields
    assert result.verdict == package.result.verdict
    frozen = reader.package(job.run_id)
    cases = {case.case_id: case for action in frozen.request.actions for case in action.cases}
    for story in result.actions:
        assert [item.proof_fingerprint for item in story.proof_coverage] == [
            item.proof_fingerprint for item in cases[story.case_id].proof_requirements]
        assert all(item.observed_state == "UNKNOWN" and item.evidence_refs == () for item in story.proof_coverage)
    assert builder.build(job.run_id) == result
    forbidden.assert_not_called()
    (package.directory / "result.json").write_bytes(b"{}")
    with pytest.raises(JiejianError):
        builder.build(job.run_id)
