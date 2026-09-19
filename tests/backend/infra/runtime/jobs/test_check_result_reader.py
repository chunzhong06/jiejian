# 以真实发布事务验证只读结果：索引与字节一致才暴露结论，篡改不改写持久状态。
import pytest
from sqlalchemy import event, text

from product.backend.core.errors import JiejianError
from product.backend.infra.artifacts.check_publication import CheckPublisher
from product.backend.workflows.checks.results import CheckResultReader
from product.protocols.check_result import CheckRunnerProgress, canonical_check_document
from tests.fixtures.check_publication import package_parts, NOW


def published(parts):
    var_dir, factory, job, directory, result = parts
    package = CheckPublisher(var_dir, factory, clock_us=lambda: NOW + 20).publish(directory)
    return CheckResultReader(var_dir=var_dir, uow_factory=factory), package


def test_result_reader_only_selects_and_never_recomputes_verdict(package_parts, monkeypatch):
    reader, package = published(package_parts)
    var_dir, factory, job, _, result = package_parts
    def forbidden(*args, **kwargs):
        raise AssertionError("result read must not recompute verdict")
    monkeypatch.setattr("product.backend.core.verification.checks.evaluate_check_case", forbidden)
    monkeypatch.setattr("product.backend.infra.artifacts.check_validation.validate_check_decisions", forbidden)
    statements = []
    engine = factory.args[0].kw["bind"]
    def capture(_conn, _cursor, statement, _parameters, _context, _many):
        statements.append(statement.lstrip().split()[0].upper())
    event.listen(engine, "before_cursor_execute", capture)
    try:
        status = reader.status(job.run_id)
        assert status.result_integrity == "VALID"
        assert status.run.verdict == result.verdict
        assert reader.list_for_project(job.project_id) == (status,)
        index = reader.evidence_index(job.run_id)
        assert len(index) == len(package.evidence)
        assert reader.evidence(job.run_id, index[0].evidence_id) in package.evidence
        assert "schema_version" not in status.model_dump()
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    assert set(statements) <= {"SELECT", "PRAGMA"}


@pytest.mark.parametrize("mutation", ["file", "receipt", "index", "run"])
def test_corrupt_published_metadata_suppresses_verdict_and_rejects_details(package_parts, mutation):
    reader, package = published(package_parts)
    _, factory, job, _, _ = package_parts
    if mutation == "file":
        path = package.directory / "result.json"
        path.write_bytes(path.read_bytes() + b" ")
    else:
        statement = {"receipt": "UPDATE check_publications SET manifest_hash = :value WHERE run_id = :run_id",
            "index": "UPDATE evidence_index SET byte_count = byte_count + 1 WHERE run_id = :run_id",
            "run": "UPDATE runs SET plan_fingerprint = :value WHERE run_id = :run_id"}[mutation]
        with factory() as work:
            work._require_session().execute(text(statement), {"run_id": job.run_id, "value": "0" * 64})
            work.commit()
    status = reader.status(job.run_id)
    assert status.result_integrity == "INVALID"
    assert status.run.verdict is None
    assert reader.list_for_project(job.project_id)[0].run.verdict is None
    with pytest.raises(JiejianError):
        reader.evidence_index(job.run_id)
    with factory() as work:
        assert work.runs.get(job.run_id).verdict is not None


def test_unpublished_and_project_or_evidence_mismatch_are_not_results(package_parts):
    var_dir, factory, job, _, _ = package_parts
    reader = CheckResultReader(var_dir=var_dir, uow_factory=factory)
    assert reader.status(job.run_id).result_integrity == "NOT_PUBLISHED"
    with pytest.raises(JiejianError, match="ARTIFACT_NOT_PUBLISHED"):
        reader.package(job.run_id)
    with pytest.raises(JiejianError, match="RECORD_NOT_FOUND"):
        reader.status(job.run_id, project_id="other-project")
    reader, _ = published(package_parts)
    with pytest.raises(JiejianError, match="RECORD_NOT_FOUND"):
        reader.evidence(job.run_id, "ev_" + "0" * 64)


def test_progress_is_bounded_display_only_and_rejects_other_attempt(package_parts):
    var_dir, factory, job, staging, result = package_parts
    reader = CheckResultReader(var_dir=var_dir, uow_factory=factory)
    progress = CheckRunnerProgress(run_id=job.run_id, job_id=job.job_id, attempt=job.attempt,
        fencing_token=job.fencing_token, request_hash=job.request_hash, phase="EXECUTING",
        completed_cases=1, planned_cases=len(result.case_results), observed_at_us=NOW + 12)
    path = staging.parent / "progress.json"
    path.write_bytes(canonical_check_document(progress))
    status = reader.status(job.run_id)
    assert status.progress.completed_cases == 1
    assert status.run.verdict is None and status.result_integrity == "NOT_PUBLISHED"
    path.write_bytes(canonical_check_document(progress.model_copy(update={"fencing_token": job.fencing_token + 1})))
    assert reader.status(job.run_id).progress is None
    path.write_bytes(canonical_check_document(progress).replace(b'"phase":"EXECUTING"', b'"phase":"EXECUTING","verdict":"PASS"'))
    assert reader.status(job.run_id).progress is None


def test_open_absence_never_claims_closed_window_or_decisive_proof(package_parts):
    from product.backend.workflows.checks.story import CheckStoryBuilder
    from product.protocols.check_result import CheckEvidence, CheckObservation, check_request_marker, parse_check_document, seal_check_evidence
    from product.protocols.check_runtime import parse_check_runtime

    var_dir, factory, job, staging, result = package_parts
    bundle = parse_check_runtime((staging / "runtime.json").read_bytes())
    sources = {proof.binding_fingerprint: proof for action in bundle.actions for proof in action.proofs}
    updated = []
    for case_result in result.case_results:
        old_path = staging / "evidence" / f"{case_result.evidence_ids[0]}.json"
        document = parse_check_document(old_path.read_bytes(), CheckEvidence)
        observations = tuple(CheckObservation(effect_id=proof.effect_id, proof_fingerprint=proof.proof_fingerprint,
            observer_id=sources[proof.binding_fingerprint].observer_id, level=proof.level, phase="AFTER",
            state="ABSENT", closure="OPEN", complete=True, reliable=True, correlated=True, authoritative=True,
            correlation_refs=(check_request_marker(job.run_id, job.job_id, job.attempt, document.case.case_id),),
            window_start_us=NOW + 12, window_end_us=NOW + 13) for proof in document.case.proof_requirements)
        fields = {name: getattr(document, name) for name in type(document).model_fields if name != "evidence_id"}
        fields["observations"] = observations
        changed = seal_check_evidence(**fields)
        old_path.unlink()
        (staging / "evidence" / f"{changed.evidence_id}.json").write_bytes(canonical_check_document(changed))
        updated.append(case_result.model_copy(update={"evidence_ids": (changed.evidence_id,)}))
    (staging / "result.json").write_bytes(canonical_check_document(result.model_copy(update={"case_results": tuple(updated)})))
    reader, _ = published(package_parts)
    story = CheckStoryBuilder(reader).build(job.run_id)
    assert story.verdict.value == "INCONCLUSIVE"
    for action in story.actions:
        assert action.decisive_proof_chain == ()
        assert all("已闭合" not in effect.judgement for effect in action.fact_comparison.effects)
