from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from jiejian.domain import (
    CaseLifecycle,
    CaseVerdict,
    Contract,
    ContractStatus,
    Job,
    JobState,
    Project,
    ProjectStatus,
    Run,
    RunLifecycle,
    RunVerdict,
    TestCase as DomainTestCase,
    revise_contract,
    set_case_verdict,
    set_run_verdict,
    transition_state,
    update_contract_rules,
)
from jiejian.errors import ErrorCode, JiejianError


def _advance(entity, *states):
    for state in states:
        entity = transition_state(entity, state, operator="unit-test")
    return entity


EXPECTED_TRANSITIONS = {
    Project: (
        "status",
        ProjectStatus,
        {
            ProjectStatus.DRAFT: (ProjectStatus.READY,),
            ProjectStatus.READY: (ProjectStatus.ARCHIVED,),
            ProjectStatus.ARCHIVED: (),
        },
    ),
    Contract: (
        "status",
        ContractStatus,
        {
            ContractStatus.DRAFT: (ContractStatus.REVIEW,),
            ContractStatus.REVIEW: (
                ContractStatus.ACTIVE,
                ContractStatus.REJECTED,
            ),
            ContractStatus.ACTIVE: (ContractStatus.SUPERSEDED,),
            ContractStatus.SUPERSEDED: (),
            ContractStatus.REJECTED: (),
        },
    ),
    Run: (
        "lifecycle",
        RunLifecycle,
        {
            RunLifecycle.QUEUED: (
                RunLifecycle.PREFLIGHT,
                RunLifecycle.CANCELLED,
            ),
            RunLifecycle.PREFLIGHT: (
                RunLifecycle.PLANNING,
                RunLifecycle.FAILED,
                RunLifecycle.CANCELLED,
                RunLifecycle.SAFETY_STOPPED,
            ),
            RunLifecycle.PLANNING: (
                RunLifecycle.EXECUTING,
                RunLifecycle.FAILED,
                RunLifecycle.CANCELLED,
                RunLifecycle.SAFETY_STOPPED,
            ),
            RunLifecycle.EXECUTING: (
                RunLifecycle.VERIFYING,
                RunLifecycle.FAILED,
                RunLifecycle.CANCELLED,
                RunLifecycle.SAFETY_STOPPED,
            ),
            RunLifecycle.VERIFYING: (
                RunLifecycle.REPORTING,
                RunLifecycle.FAILED,
                RunLifecycle.CANCELLED,
                RunLifecycle.SAFETY_STOPPED,
            ),
            RunLifecycle.REPORTING: (
                RunLifecycle.COMPLETED,
                RunLifecycle.FAILED,
                RunLifecycle.CANCELLED,
            ),
            RunLifecycle.COMPLETED: (),
            RunLifecycle.FAILED: (),
            RunLifecycle.CANCELLED: (),
            RunLifecycle.SAFETY_STOPPED: (),
        },
    ),
    DomainTestCase: (
        "lifecycle",
        CaseLifecycle,
        {
            CaseLifecycle.PLANNED: (
                CaseLifecycle.SNAPSHOTTED,
                CaseLifecycle.ERROR,
            ),
            CaseLifecycle.SNAPSHOTTED: (
                CaseLifecycle.EXECUTED,
                CaseLifecycle.ERROR,
            ),
            CaseLifecycle.EXECUTED: (
                CaseLifecycle.OBSERVED,
                CaseLifecycle.ERROR,
            ),
            CaseLifecycle.OBSERVED: (
                CaseLifecycle.CLEANED,
                CaseLifecycle.ERROR,
            ),
            CaseLifecycle.CLEANED: (
                CaseLifecycle.DONE,
                CaseLifecycle.ERROR,
            ),
            CaseLifecycle.DONE: (),
            CaseLifecycle.ERROR: (),
        },
    ),
    Job: (
        "state",
        JobState,
        {
            JobState.PENDING: (JobState.RUNNING, JobState.CANCELLED),
            JobState.RUNNING: (
                JobState.SUCCEEDED,
                JobState.RETRY_WAIT,
                JobState.FAILED,
                JobState.CANCELLED,
            ),
            JobState.RETRY_WAIT: (JobState.RUNNING, JobState.CANCELLED),
            JobState.SUCCEEDED: (),
            JobState.FAILED: (),
            JobState.CANCELLED: (),
        },
    ),
}

LEGAL_TRANSITION_CASES = [
    (entity_type, field, source, target)
    for entity_type, (field, enum_type, transitions) in EXPECTED_TRANSITIONS.items()
    for source in enum_type
    for target in transitions[source]
]

ILLEGAL_TRANSITION_CASES = [
    (entity_type, source, target)
    for entity_type, (_, enum_type, transitions) in EXPECTED_TRANSITIONS.items()
    for source in enum_type
    for target in enum_type
    if target not in transitions[source]
]


def _entity_at_state(entity_type, state):
    if entity_type is Project:
        return Project(name="demo", status=state)
    if entity_type is Contract:
        return Contract(rules=("ownership",), status=state)
    if entity_type is Run:
        return Run(
            contract_version=1,
            engine_version="0.1.0",
            lifecycle=state,
            verdict=RunVerdict.PASS,
        )
    if entity_type is DomainTestCase:
        return DomainTestCase(
            run_id=uuid4(),
            lifecycle=state,
            verdict=CaseVerdict.SAFE,
        )
    if entity_type is Job:
        return Job(job_type="run", state=state)
    raise AssertionError(f"未定义测试实体工厂：{entity_type!r}")


def test_state_sets_match_project_spec_section_9() -> None:
    assert {state.value for state in ProjectStatus} == {"DRAFT", "READY", "ARCHIVED"}
    assert {state.value for state in ContractStatus} == {
        "DRAFT",
        "REVIEW",
        "ACTIVE",
        "SUPERSEDED",
        "REJECTED",
    }
    assert {state.value for state in RunLifecycle} == {
        "QUEUED",
        "PREFLIGHT",
        "PLANNING",
        "EXECUTING",
        "VERIFYING",
        "REPORTING",
        "COMPLETED",
        "FAILED",
        "CANCELLED",
        "SAFETY_STOPPED",
    }
    assert {state.value for state in RunVerdict} == {
        "PASS",
        "BLOCK",
        "INCONCLUSIVE",
    }
    assert {state.value for state in CaseLifecycle} == {
        "PLANNED",
        "SNAPSHOTTED",
        "EXECUTED",
        "OBSERVED",
        "CLEANED",
        "DONE",
        "ERROR",
    }
    assert {state.value for state in CaseVerdict} == {
        "SAFE",
        "VULNERABLE",
        "INCONCLUSIVE",
        "SKIPPED",
        "ERROR",
    }
    assert {state.value for state in JobState} == {
        "PENDING",
        "RUNNING",
        "RETRY_WAIT",
        "SUCCEEDED",
        "FAILED",
        "CANCELLED",
    }


@pytest.mark.parametrize(
    ("entity_type", "field", "source", "target"),
    LEGAL_TRANSITION_CASES,
)
def test_all_specified_legal_transitions_succeed(
    entity_type, field, source, target
) -> None:
    entity = _entity_at_state(entity_type, source)

    transitioned = transition_state(entity, target, operator="matrix-test")

    assert getattr(transitioned, field) is target
    assert transitioned.events[-1].source == source.value
    assert transitioned.events[-1].target == target.value
    assert transitioned.events[-1].operator == "matrix-test"


@pytest.mark.parametrize(
    ("entity_type", "source", "target"),
    ILLEGAL_TRANSITION_CASES,
)
def test_all_other_same_machine_transitions_are_rejected(
    entity_type, source, target
) -> None:
    entity = _entity_at_state(entity_type, source)

    with pytest.raises(JiejianError) as captured:
        transition_state(entity, target, operator="matrix-test")

    assert captured.value.code == ErrorCode.STATE_INVALID_TRANSITION


def test_all_primary_legal_lifecycle_paths() -> None:
    project = _advance(Project(name="demo"), ProjectStatus.READY, ProjectStatus.ARCHIVED)
    assert project.status is ProjectStatus.ARCHIVED

    contract = _advance(
        Contract(rules=("ownership",)), ContractStatus.REVIEW, ContractStatus.ACTIVE
    )
    assert contract.status is ContractStatus.ACTIVE

    run = _advance(
        Run(contract_version=1, engine_version="0.1.0"),
        RunLifecycle.PREFLIGHT,
        RunLifecycle.PLANNING,
        RunLifecycle.EXECUTING,
        RunLifecycle.VERIFYING,
    )
    run = set_run_verdict(run, RunVerdict.PASS)
    run = _advance(run, RunLifecycle.REPORTING, RunLifecycle.COMPLETED)
    assert run.lifecycle is RunLifecycle.COMPLETED
    assert run.verdict is RunVerdict.PASS

    test_case = _advance(
        DomainTestCase(run_id=run.id),
        CaseLifecycle.SNAPSHOTTED,
        CaseLifecycle.EXECUTED,
        CaseLifecycle.OBSERVED,
    )
    test_case = set_case_verdict(test_case, CaseVerdict.SAFE)
    test_case = _advance(test_case, CaseLifecycle.CLEANED, CaseLifecycle.DONE)
    assert test_case.lifecycle is CaseLifecycle.DONE
    assert test_case.verdict is CaseVerdict.SAFE

    job = _advance(Job(job_type="run"), JobState.RUNNING, JobState.RETRY_WAIT)
    job = _advance(job, JobState.RUNNING, JobState.SUCCEEDED)
    assert job.state is JobState.SUCCEEDED


def test_transition_rejects_state_from_another_machine() -> None:
    run = Run(contract_version=1, engine_version="0.1.0")

    with pytest.raises(JiejianError) as captured:
        transition_state(run, RunVerdict.PASS, operator="unit-test")

    assert captured.value.code == ErrorCode.STATE_INVALID_TARGET


def test_transition_rejects_unknown_state_string() -> None:
    project = Project(name="demo")

    with pytest.raises(JiejianError) as captured:
        transition_state(project, "UNKNOWN", operator="unit-test")

    assert captured.value.code == ErrorCode.STATE_INVALID_TARGET


def test_transition_requires_nonblank_operator() -> None:
    project = Project(name="demo")

    with pytest.raises(JiejianError) as captured:
        transition_state(project, ProjectStatus.READY, operator="  ")

    assert captured.value.code == ErrorCode.STATE_OPERATOR_REQUIRED


def test_transition_rejects_unregistered_entity() -> None:
    with pytest.raises(JiejianError) as captured:
        transition_state(object(), "READY", operator="unit-test")  # type: ignore[arg-type]

    assert captured.value.code == ErrorCode.STATE_INVALID_ENTITY


def test_empty_contract_cannot_be_activated() -> None:
    contract = Contract(status=ContractStatus.REVIEW)

    with pytest.raises(JiejianError) as captured:
        transition_state(contract, ContractStatus.ACTIVE, operator="unit-test")

    assert captured.value.code == ErrorCode.STATE_PRECONDITION


def test_transition_events_are_appended_without_rewriting_history() -> None:
    project = Project(name="demo")
    ready = transition_state(project, ProjectStatus.READY, operator="first")
    archived = transition_state(ready, ProjectStatus.ARCHIVED, operator="second")

    assert project.events == ()
    assert archived.events[:-1] == ready.events
    assert archived.events[0].source == ProjectStatus.DRAFT.value
    assert archived.events[0].target == ProjectStatus.READY.value
    assert archived.events[0].operator == "first"
    assert archived.events[1].source == ProjectStatus.READY.value
    assert archived.events[1].target == ProjectStatus.ARCHIVED.value
    assert archived.events[1].operator == "second"


def test_lifecycle_and_verdict_fields_are_distinct_types() -> None:
    with pytest.raises(ValidationError):
        Run(contract_version=1, engine_version="0.1.0", lifecycle=RunVerdict.PASS)
    with pytest.raises(ValidationError):
        Run(
            contract_version=1,
            engine_version="0.1.0",
            verdict=RunLifecycle.COMPLETED,
        )
    with pytest.raises(ValidationError):
        DomainTestCase(run_id=uuid4(), lifecycle=CaseVerdict.SAFE)
    with pytest.raises(ValidationError):
        DomainTestCase(run_id=uuid4(), verdict=CaseLifecycle.DONE)


def test_active_contract_is_not_modified_in_place() -> None:
    active = _advance(
        Contract(version=3, rules=("old",)),
        ContractStatus.REVIEW,
        ContractStatus.ACTIVE,
    )

    with pytest.raises(JiejianError) as captured:
        update_contract_rules(active, ("new",))
    assert captured.value.code == ErrorCode.CONTRACT_IMMUTABLE
    with pytest.raises(ValidationError):
        active.rules = ("new",)

    revision = revise_contract(active, ("new",))
    assert revision.id != active.id
    assert revision.version == 4
    assert revision.status is ContractStatus.DRAFT
    assert revision.supersedes_id == active.id
    assert active.rules == ("old",)


@pytest.mark.parametrize(
    "rules",
    [("ownership", "role"), ["ownership", "role"]],
)
def test_contract_rule_updates_accept_valid_sequences(rules) -> None:
    updated = update_contract_rules(Contract(), rules)
    assert updated.rules == ("ownership", "role")


def test_contract_rule_updates_revalidate_the_contract_model() -> None:
    with pytest.raises(ValidationError):
        update_contract_rules(Contract(), [123])  # type: ignore[list-item]


def test_superseded_contract_is_not_modified_in_place() -> None:
    superseded = Contract(
        rules=("old",),
        status=ContractStatus.SUPERSEDED,
    )

    with pytest.raises(JiejianError) as captured:
        update_contract_rules(superseded, ("new",))

    assert captured.value.code == ErrorCode.CONTRACT_IMMUTABLE


def test_completed_states_require_independent_verdicts() -> None:
    run = Run(
        contract_version=1,
        engine_version="0.1.0",
        lifecycle=RunLifecycle.REPORTING,
    )
    with pytest.raises(JiejianError) as run_error:
        transition_state(run, RunLifecycle.COMPLETED, operator="unit-test")
    assert run_error.value.code == ErrorCode.STATE_PRECONDITION

    test_case = DomainTestCase(run_id=uuid4(), lifecycle=CaseLifecycle.CLEANED)
    with pytest.raises(JiejianError) as case_error:
        transition_state(test_case, CaseLifecycle.DONE, operator="unit-test")
    assert case_error.value.code == ErrorCode.STATE_PRECONDITION
