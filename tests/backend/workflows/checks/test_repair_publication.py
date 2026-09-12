# 通过真实本地 TARGET、完整编译与 fenced publication 验证跨动作原题复验和空历史回归。
import hashlib
import json
import time
from uuid import uuid4

import pytest

from product.backend.core.check_plan import compile_project_check_plan
from product.backend.core.check_repair import repair_context, verify_current_repair
from product.backend.core.lifecycle import ProjectStatus
from product.backend.infra.artifacts.check_publication import CheckPublisher
from product.backend.infra.execution.check_executor import CheckExecutor
from product.backend.infra.runtime.jobs.check_requests import CheckRequestStore
from product.backend.infra.runtime.jobs.models import ClaimJob, SubmitJob
from product.backend.infra.storage import ProjectRecord
from product.backend.composition.worker import WorkerContainer
from product.backend.workflows.checks.repair import build_current_repair_contract
from product.backend.workflows.checks.results import CheckResultReader
from product.protocols.check_result import CheckAssetReference, CheckRunnerInput, canonical_check_document
from product.protocols.check_runtime import CheckRuntimeBundle, check_runtime_fingerprint, canonical_check_runtime_bytes
from product.protocols.execution_v3 import ChangeContext, PersistedExecutionRequestV3, canonical_execution_request_v3_bytes
from tests.fixtures.check_execution import execution_pair
from tests.fixtures.check_plan import prepared_action
from tests.fixtures.runtime_environment import runtime_identity_environment
from tests.backend.infra.execution.test_check_executor import check_target


def pair(port, *, contract=None, fault=None):
    prepared = (prepared_action(superset=True, state_changing=True), prepared_action(state_changing=True, action_number=2))
    if fault in {"standard", "identity", "subject", "owner", "resource", "permission", "effect"}:
        from product.backend.core.action_preparation import seal_binding
        from product.backend.core.assurance import compile_action_assurance
        changed = []
        for item in prepared:
            def binding(value):
                if value is None:
                    return None
                fields = {name: getattr(value, name) for name in type(value).model_fields if name != "binding_fingerprint"}
                if fault in {"identity", "owner"}:
                    fields.update(subject_identity_fingerprint="9" * 64, owner_identity_fingerprint="9" * 64)
                elif fault == "standard" and fields.get("observer_reference"):
                    fields["observer_reference"] = fields["observer_reference"].model_copy(update={"descriptor_fingerprint": "9" * 64})
                elif fault == "resource" and "actual_resource_id" in fields:
                    fields["actual_resource_id"] = "resource-2"
                return seal_binding(type(value), **fields)
            identities = tuple(identity.model_copy(update={"identity_fingerprint": "9" * 64})
                if fault == "identity" or (fault == "owner" and index == 0) or (fault == "subject" and index == 1)
                else identity for index, identity in enumerate(item.identities))
            permissions = item.permissions
            if fault == "permission":
                permissions = tuple(value.model_copy(update={"revision": 2}) for value in permissions)
            elif fault == "effect" and len(item.evidence) == 2:
                from tests.fixtures.assurance import permission, SECOND_EFFECT
                permissions = (item.permissions[0], permission(2, relation=item.permissions[1].relation,
                    expectation=item.permissions[1].expectation, effects=(SECOND_EFFECT,), business_action_id=item.action.action_id))
            assurance = compile_action_assurance(item.action, permissions)
            old_slots = {slot.slot_id: slot for slot in item.assurance.identity_requirements.slots}
            by_role = {(old_slots[value.slot_id].actor_id, old_slots[value.slot_id].actor_revision, old_slots[value.slot_id].ordinal): value for value in identities}
            identities = tuple(by_role[(slot.actor_id, slot.actor_revision, slot.ordinal)].model_copy(update={"slot_id": slot.slot_id}) for slot in assurance.identity_requirements.slots)
            changed.append(item.model_copy(update=dict(
                identities=identities, permissions=permissions, assurance=assurance,
                execution=binding(item.execution), resources=tuple(binding(value) for value in item.resources),
                evidence=tuple(binding(value) for value in item.evidence), recovery=binding(item.recovery),
                observer_capabilities=tuple(value.model_copy(update={"descriptor_fingerprint": "9" * 64}) for value in item.observer_capabilities) if fault == "standard" else item.observer_capabilities)))
        prepared = tuple(changed)
    parts = [execution_pair(port=port, state_changing=True, prepared=item)[1] for item in prepared]
    payload = parts[0].model_dump(mode="json")
    payload["actions"] += parts[1].model_dump(mode="json")["actions"]
    bundle = CheckRuntimeBundle.model_validate_json(json.dumps(payload))
    config_hash = check_runtime_fingerprint(bundle)
    plan = compile_project_check_plan(bundle.project_id, source_fingerprint=bundle.source_fingerprint,
        policy_epoch=1, engine_version="test-1", config_fingerprint=config_hash, actions=prepared)
    assert not plan.gaps, plan.model_dump_json()
    payload = plan.model_dump(mode="json", exclude={"gaps"})
    for action in payload["actions"]:
        action.pop("gaps")
    payload.update(config_fingerprint=config_hash, budget_fingerprint=bundle.budget.fingerprint())
    if contract is not None:
        payload.update(repair_context=repair_context(contract).model_dump(mode="json"), change_context=dict(
            change_id="chg_" + "3" * 32, impact_fingerprint="4" * 64,
            required_intent_ids=sorted(ref.intent_id for ref in contract.original_intents)))
    return PersistedExecutionRequestV3.model_validate_json(json.dumps(payload)), bundle


def publish(container, target, request, bundle):
    state = target[1]
    state["cases"] = {case.case_id: case for action in request.actions for case in action.cases}
    secrets = {identity.binding.secret_ref.removeprefix("env:"): f"credential-{index}"
        for index, identity in enumerate(bundle.identities, 1)}
    request_hash = hashlib.sha256(canonical_execution_request_v3_bytes(request)).hexdigest()
    job_id, run_id = "job_" + uuid4().hex, "run_" + uuid4().hex
    store = CheckRequestStore(container.paths.root)
    store.write(job_id, request)
    store.write_bundle(job_id, bundle)
    now = time.time_ns() // 1000
    container.job_queue.submit(SubmitJob(project_id=request.project_id, operation_type="CHECK", idempotency_key=job_id,
        request_hash=request_hash, plan_fingerprint=request.plan_fingerprint, source_fingerprint=request.source_fingerprint,
        policy_epoch=1, engine_version="test-1", max_attempts=1, available_at_us=now, now_us=now, run_id=run_id, job_id=job_id))
    job = container.job_attempts.claim(ClaimJob(job_id=job_id, lease_owner="repair-l3", now_us=now,
        lease_duration_us=120_000_000)).job
    runner = CheckRunnerInput(run_id=run_id, job_id=job_id, attempt=1, lease_owner=job.lease_owner,
        fencing_token=job.fencing_token, created_at_us=now, request_hash=request_hash, config_hash=request.config_fingerprint,
        assets=(CheckAssetReference(logical_id="request", sha256=request_hash), CheckAssetReference(logical_id="runtime", sha256=request.config_fingerprint)))
    attempt = container.paths.jobs / job_id / "attempts" / "1-1"
    output = CheckExecutor(request, bundle, runner, environ=secrets, attempt_dir=attempt, cancellation_requested=lambda: False).execute()
    staging = attempt / "staging"
    (staging / "evidence").mkdir(parents=True)
    (staging / "request.json").write_bytes(canonical_execution_request_v3_bytes(request))
    (staging / "runtime.json").write_bytes(canonical_check_runtime_bytes(bundle))
    (staging / "result.json").write_bytes(canonical_check_document(output.result))
    for document in output.evidence:
        (staging / "evidence" / f"{document.evidence_id}.json").write_bytes(canonical_check_document(document))
    CheckPublisher(container.paths.root, container.uow_factory).publish(staging)
    return CheckResultReader(var_dir=container.paths.root, uow_factory=container.uow_factory).package(run_id)


@pytest.mark.parametrize("historical_safe,new_safe,expected,fault", [(True, True, "VERIFIED", None), (False, True, "VERIFIED", None), (False, False, "INCONCLUSIVE", None),
    (True, True, "INCONCLUSIVE", "standard"), (True, True, "INCONCLUSIVE", "identity"), (True, True, "NOT_VERIFIED", "forbidden"),
    (True, True, "INCONCLUSIVE", "subject"), (True, True, "INCONCLUSIVE", "owner"), (True, True, "INCONCLUSIVE", "resource"),
    (True, True, "STALE", "permission"), (True, True, "STALE", "effect")])
def test_real_published_superset_and_empty_regressions_keep_original_control(check_target, tmp_path, historical_safe, new_safe, expected, fault):
    request, bundle = pair(check_target[0])
    var_dir = tmp_path / "var"
    from product.backend.infra.storage import default_database_path, upgrade_database
    upgrade_database(default_database_path(var_dir))
    container = WorkerContainer(var_dir, environ=runtime_identity_environment(var_dir))
    try:
        now = time.time_ns() // 1000
        with container.uow_factory() as work:
            work.projects.add(ProjectRecord(project_id=request.project_id, name="跨动作原题", status=ProjectStatus.READY, created_at_us=now, updated_at_us=now))
            work.commit()
        check_target[1].update(deny_effect=True, allow_effect=historical_safe)
        source = publish(container, check_target, request, bundle)
        deny = next(item for item in source.result.case_results if item.verdict == "VULNERABLE")
        contract = build_current_repair_contract(source, deny.case_id)
        assert len(contract.regressions) == (2 if historical_safe else 0)
        assert len(contract.selected_control.identity.protected_effect_ids) == 1
        if historical_safe:
            assert any(len(item.identity.protected_effect_ids) == 2 for item in contract.regressions)
        source_bytes = canonical_check_document(source.result)
        request, bundle = pair(check_target[0], contract=contract, fault=fault)
        check_target[1].update(deny_effect=fault == "forbidden", allow_effect=new_safe)
        current = publish(container, check_target, request, bundle)
        verification = verify_current_repair(contract, request=current.request, bundle=current.bundle,
            result=current.result, evidence=current.evidence, expected_change_context=request.change_context)
        assert verification.status == expected, verification.model_dump_json()
        assert canonical_check_document(source.result) == source_bytes
    finally:
        container.engine.dispose()
