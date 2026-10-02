# 验证验收脚本的跨应用事实与聚合。
from __future__ import annotations
import tests.acceptance.sample_test.validation.suite as sample_validation_suite
import tests.acceptance.sample_test.validation.summary as sample_validation_summary
import json
from pathlib import Path
import pytest
from tests.acceptance.sample_test import adapter as adapter_module
from tests.acceptance.sample_test import driver as suite_driver
from tests.acceptance.sample_test import oracle as oracle_module
from tests.acceptance.sample_test import registry as registry_module
from tests.scripts._support_sample_test import ROOT

def test_validation_registry_has_stable_public_cases_and_allow_controls() -> None:
    registry = registry_module
    cases = registry.load_public_registry(ROOT)
    payload = registry.public_registry_payload(ROOT, cases)
    encoded = json.dumps(payload, ensure_ascii=False)

    assert len(cases) == 30
    assert len({item.case_id for item in cases}) == 30
    assert {item.application_id for item in cases} == {
        "collaboration-space",
        "tenant-records",
    }
    assert all(item.allow_control_identity for item in cases)
    assert all(item.protected_effects for item in cases)
    assert all(item.state_selector for item in cases)
    assert {
        (
            item.application_id,
            item.mode,
            str(item.state_selector["implementation"]),
            str(item.state_selector["observation"]),
        )
        for item in cases
    } == {
        (application, mode, implementation, observation)
        for application in ("collaboration-space", "tenant-records")
        for mode in (
            "object_tenant_check_missing",
            "new_entry_inheritance",
            "feature_authorization_bypass",
            "delegation_authority_expansion",
            "deny_async_consequence",
        )
        for implementation, observation in (
            ("MODE_FAULT_PRESENT", "AVAILABLE"),
            ("MODE_GUARD_ACTIVE", "AVAILABLE"),
            ("MODE_GUARD_ACTIVE", "UNAVAILABLE"),
        )
    }
    for forbidden in (
        "expected_verdict",
        "breakpoint_type",
        "maximum_precision",
        "golden_answer",
    ):
        assert forbidden not in encoded

def test_private_oracle_is_outside_every_authorized_source_root_and_product_input() -> None:
    registry = registry_module
    cases = registry.load_public_registry(ROOT)
    evaluator_module = oracle_module
    evaluator = evaluator_module.PrivateOracleEvaluator(ROOT, cases)
    public_payload = registry.public_registry_payload(ROOT, cases)

    for case in cases:
        with pytest.raises(ValueError):
            evaluator.path.resolve().relative_to(case.source_root.resolve())
        assert evaluator.path.name not in {
            path.name for path in case.source_root.rglob("*") if path.is_file()
        }
    product_text = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in (ROOT / "product").rglob("*")
        if path.is_file() and path.suffix in {".py", ".ts", ".tsx", ".json"}
    )
    assert "private_oracle" not in product_text
    assert "expected_verdict" not in json.dumps(public_payload, ensure_ascii=False)

def test_validation_adapter_only_translates_public_trace_structure() -> None:
    registry = registry_module
    adapter = adapter_module
    case = registry.load_public_registry(ROOT)[0]
    identity_event = "validation-identity"
    delegation_event = "validation-delegation"
    trace = adapter._trace(
        case,
        records=(
            {
                "event_id": identity_event,
                "semantic_key": "server_identity_resolved",
                "sequence": 1,
                "kind": "IDENTITY",
                "subject_id": case.identity,
                "actor_id": "target-server",
            },
            {
                "event_id": delegation_event,
                "parent_event_id": identity_event,
                "semantic_key": "background_job_started",
                "sequence": 2,
                "kind": "DELEGATION",
                "subject_id": case.identity,
                "actor_id": "validation-worker",
            },
            {
                "event_id": "validation-effect",
                "parent_event_id": delegation_event,
                "delegated_from_event_id": delegation_event,
                "semantic_key": case.observation_config["trace_effect_key"],
                "sequence": 3,
                "kind": "FINAL_EFFECT",
                "subject_id": case.identity,
                "actor_id": "validation-worker",
            },
        ),
        case_id="case-validation-adapter",
        planned_subject_id=case.identity,
        role="deny",
        complete=True,
        evidence_ref="validation-adapter-evidence",
    )

    assert trace.events[0].actor_id == case.identity
    assert trace.events[1].actor_id == "validation-worker"
    assert trace.events[2].actor_id == "validation-worker"
    assert trace.events[2].effect_id == case.protected_effects[0]
    source = Path(adapter.__file__).read_text(encoding="utf-8")
    assert "core.verification.continuity" not in source
    assert "core.verification.breakpoints" not in source

def test_validation_representatives_run_both_real_apps_without_public_oracle_leak(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.acceptance.sample_test.validation import evaluation as validation
    continuity_calls = 0
    breakpoint_calls = 0
    real_assess = validation.assess_authorization_continuity
    real_locator = validation.BreakpointLocator

    def tracked_assess(*args, **kwargs):
        nonlocal continuity_calls
        continuity_calls += 1
        return real_assess(*args, **kwargs)

    class TrackedBreakpointLocator:
        def locate(self, *args, **kwargs):
            nonlocal breakpoint_calls
            breakpoint_calls += 1
            return real_locator().locate(*args, **kwargs)

    monkeypatch.setattr(validation, "assess_authorization_continuity", tracked_assess)
    monkeypatch.setattr(validation, "BreakpointLocator", TrackedBreakpointLocator)
    summary = sample_validation_suite.run_validation_suite(
        ROOT,
        tmp_path,
        repetitions=1,
        representative_only=True,
    )
    encoded = json.dumps(summary, ensure_ascii=False)

    assert summary["status"] == "accepted"
    assert summary["case_count"] == 6
    assert continuity_calls == 6
    assert breakpoint_calls == 6
    assert summary["full_method_sources"] == {
        "case_verdict": (
            "product.backend.core.verification.permissions.evaluation."
            "evaluate_permission_case"
        ),
        "authorization_continuity": (
            "product.backend.core.verification.continuity."
            "assess_authorization_continuity"
        ),
        "breakpoint": (
            "product.backend.core.verification.breakpoints."
            "BreakpointLocator.locate"
        ),
    }
    assert summary["applications"] == ["collaboration-space", "tenant-records"]
    results = summary["results"]
    assert len(results) == 6
    assert {item["verdict"] for item in results} == {
        "BLOCK",
        "PASS",
        "INCONCLUSIVE",
    }
    assert all("expected" not in key and "golden" not in key for key in summary)
    assert "expected_verdict" not in encoded
    assert "golden_answer" not in encoded
    assert all(item["allow_control_valid"] for item in results if item["verdict"] != "INCONCLUSIVE")
    assert summary["method_metrics"]["full"]["wrong_pass_vulnerable"] == 0
    assert summary["method_metrics"]["full"]["wrong_pass_evidence_gap"] == 0
    assert summary["method_metrics"]["full"]["exact_match_count"] == 6
    assert summary["method_metrics"]["full"]["effect_decision_correct_count"] == 6
    assert (
        summary["method_metrics"]["full"]["continuity_or_orphan_correct_count"]
        == 6
    )
    assert summary["method_metrics"]["full"]["actual_identity_attributed_count"] == 6
    assert summary["method_metrics"]["full"]["allow_control_valid_count"] == 6
    assert summary["method_metrics"]["full"]["recovery_success_count"] == 6
    assert (
        summary["method_metrics"]["full"]["repair_verification_applicable_count"]
        == 2
    )
    assert (
        summary["method_metrics"]["full"]["repair_verification_success_count"]
        == 2
    )
    assert summary["method_metrics"]["http_only"]["exact_match_count"] == 4
    assert summary["method_metrics"]["http_only"]["wrong_pass_evidence_gap"] == 2
    assert summary["method_metrics"]["single_state"]["exact_match_count"] == 6
    assert (
        summary["method_metrics"]["authorization_regression"][
            "wrong_pass_evidence_gap"
        ]
        == 2
    )
    assert summary["repeat_consistency"]["inconsistent_case_count"] == 0
    assert (tmp_path / "runtime" / "validation").is_dir()

    presentation = sample_validation_summary.build_presentation_summary(summary)
    assert presentation["case_count"] == 6
    assert presentation["application_count"] == 2
    assert presentation["mode_count"] == 1
    assert presentation["state_count"] == 3
    assert presentation["full_exact_match_count"] == 6
    assert presentation["http_wrong_pass_per_matrix"] == 2
    assert "results" not in presentation
    assert "method_metrics" not in presentation
    published_path = tmp_path / "published" / "latest-validation-summary.json"
    suite_driver._publish_summary(published_path, summary)
    assert json.loads(published_path.read_text(encoding="utf-8")) == presentation
