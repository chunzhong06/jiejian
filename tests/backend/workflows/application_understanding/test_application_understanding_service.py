# 验证 DRAFT 应用连接、endpoint 确认、revision 冲突与服务重启恢复。

from __future__ import annotations

import json
from pathlib import Path

import pytest

from product.backend.core.application_understanding import (
    ActionRiskHint,
    CandidateDecision,
    CandidateOrigin,
)
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.lifecycle import ProjectStatus
from product.backend.workflows.application_understanding.endpoints import (
    EndpointProbeObservation,
    TargetEndpointDiscovery,
)
from product.backend.workflows.context import ApplicationCore


def _reachable_discovery(endpoint: str) -> TargetEndpointDiscovery:
    def probe(candidate, limits):
        return EndpointProbeObservation(
            reachable=candidate == endpoint,
            status_code=200 if candidate == endpoint else None,
            detail="测试服务已响应" if candidate == endpoint else "测试服务未响应",
        )

    return TargetEndpointDiscovery(probe=probe)


def test_connection_and_confirmed_endpoint_recover_after_service_restart(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    endpoint = "http://127.0.0.1:4555"
    (source / "openapi.json").write_text(
        json.dumps({"openapi": "3.1.0", "servers": [{"url": endpoint}]}),
        encoding="utf-8",
    )
    var_dir = tmp_path / "var"
    discovery = _reachable_discovery(endpoint)
    first = ApplicationCore(var_dir, environ={}, endpoint_discovery=discovery)
    try:
        connection = first.application_understanding.connect(
            source,
            project_name="示例应用",
        )
        repeated = first.application_understanding.connect(source)
        assert connection.project == repeated.project
        assert connection.project.status is ProjectStatus.DRAFT
        assert connection.understanding.confirmed_endpoint is None
        candidates = first.application_understanding.discover_endpoints(
            connection.project.project_id
        )
        assert candidates.default_endpoint == endpoint
        confirmed = first.application_understanding.confirm_endpoint(
            connection.project.project_id,
            endpoint=endpoint,
            revision=connection.understanding.revision,
        )
        assert confirmed.revision == 1
        assert confirmed.confirmed_endpoint == endpoint
    finally:
        first.close()

    restarted = ApplicationCore(
        var_dir,
        environ={},
        endpoint_discovery=discovery,
    )
    try:
        recovered = restarted.application_understanding.get(
            connection.project.project_id
        )
        readiness = restarted.project_readiness.get(connection.project.project_id)
        assert recovered.confirmed_endpoint == endpoint
        assert readiness.application_connected is True
        assert readiness.endpoint_status == "CONFIRMED"
        assert readiness.next_required_action == "AUTHORIZE_SOURCE_ANALYSIS"
    finally:
        restarted.close()


def test_unreachable_endpoint_and_stale_revision_are_not_persisted(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    application = ApplicationCore(
        tmp_path / "var",
        environ={},
        endpoint_discovery=_reachable_discovery("http://127.0.0.1:4999"),
    )
    try:
        connected = application.application_understanding.connect(source)
        with pytest.raises(JiejianError) as unreachable:
            application.application_understanding.confirm_endpoint(
                connected.project.project_id,
                endpoint="http://127.0.0.1:4888",
                revision=0,
            )
        assert unreachable.value.code == ErrorCode.APPLICATION_ENDPOINT_UNREACHABLE.value
        assert application.application_understanding.get(
            connected.project.project_id
        ).confirmed_endpoint is None

        with pytest.raises(JiejianError) as conflict:
            application.application_understanding.confirm_endpoint(
                connected.project.project_id,
                endpoint="http://127.0.0.1:4999",
                revision=1,
            )
        assert conflict.value.code == ErrorCode.APPLICATION_REVISION_CONFLICT.value
    finally:
        application.close()


def test_control_origin_is_rejected_before_probe_without_fixed_port(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    probes: list[str] = []

    def probe(candidate, _limits):
        probes.append(candidate)
        return EndpointProbeObservation(
            reachable=candidate == "http://127.0.0.1:8765",
            status_code=200,
            detail="测试服务已响应",
        )

    application = ApplicationCore(
        tmp_path / "var",
        environ={},
        control_origin="http://127.0.0.1:9000",
        endpoint_discovery=TargetEndpointDiscovery(probe=probe),
    )
    try:
        connected = application.application_understanding.connect(source)
        with pytest.raises(JiejianError) as captured:
            application.application_understanding.confirm_endpoint(
                connected.project.project_id,
                endpoint="http://127.0.0.1:9000",
                revision=0,
            )
        assert captured.value.code == ErrorCode.SELF_TARGET_FORBIDDEN.value
        assert captured.value.to_dict()["message"] == (
            "当前地址是界鉴自身服务，请填写实际被检查应用地址"
        )
        assert probes == []
        assert application.application_understanding.get(
            connected.project.project_id
        ).confirmed_endpoint is None

        confirmed = application.application_understanding.confirm_endpoint(
            connected.project.project_id,
            endpoint="http://127.0.0.1:8765",
            revision=0,
        )
        assert confirmed.confirmed_endpoint == "http://127.0.0.1:8765"
        assert probes == ["http://127.0.0.1:8765"]
    finally:
        application.close()


def test_source_analysis_requires_authorization_and_recovers_candidates(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "app.py").write_text(
        "roles = ['owner']\n@app.get('/documents')\ndef list_documents(): pass\n",
        encoding="utf-8",
    )
    endpoint = "http://127.0.0.1:4666"
    var_dir = tmp_path / "var"
    discovery = _reachable_discovery(endpoint)
    application = ApplicationCore(
        var_dir,
        environ={},
        endpoint_discovery=discovery,
    )
    try:
        connected = application.application_understanding.connect(source)
        confirmed = application.application_understanding.confirm_endpoint(
            connected.project.project_id,
            endpoint=endpoint,
            revision=0,
        )
        with pytest.raises(JiejianError) as unauthorized:
            application.application_understanding.analyze_source(
                connected.project.project_id,
                revision=confirmed.revision,
            )
        assert (
            unauthorized.value.code
            == ErrorCode.APPLICATION_ANALYSIS_NOT_AUTHORIZED.value
        )

        authorized = application.application_understanding.authorize_source_analysis(
            connected.project.project_id,
            revision=confirmed.revision,
        )
        analyzed = application.application_understanding.analyze_source(
            connected.project.project_id,
            revision=authorized.revision,
        )
        assert analyzed.source_fingerprint is not None
        assert analyzed.role_candidates[0].canonical_key == "owner"
        assert analyzed.action_candidates[0].canonical_key == "GET /documents"
    finally:
        application.close()

    restarted = ApplicationCore(
        var_dir,
        environ={},
        endpoint_discovery=discovery,
    )
    try:
        recovered = restarted.application_understanding.get(
            connected.project.project_id
        )
        assert recovered.source_analysis_authorized is True
        assert recovered.role_candidates == analyzed.role_candidates
        assert recovered.action_candidates == analyzed.action_candidates
    finally:
        restarted.close()


def test_candidate_decisions_and_manual_items_survive_source_reanalysis(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    source_file = source / "app.py"
    source_file.write_text(
        "roles = ['owner']\n@app.get('/documents')\ndef list_documents(): pass\n",
        encoding="utf-8",
    )
    endpoint = "http://127.0.0.1:4777"
    application = ApplicationCore(
        tmp_path / "var",
        environ={},
        endpoint_discovery=_reachable_discovery(endpoint),
    )
    try:
        connected = application.application_understanding.connect(source)
        current = application.application_understanding.confirm_endpoint(
            connected.project.project_id,
            endpoint=endpoint,
            revision=0,
        )
        current = application.application_understanding.authorize_source_analysis(
            connected.project.project_id,
            revision=current.revision,
        )
        current = application.application_understanding.analyze_source(
            connected.project.project_id,
            revision=current.revision,
        )
        owner = next(item for item in current.role_candidates if item.canonical_key == "owner")
        list_documents = next(
            item
            for item in current.action_candidates
            if item.canonical_key == "GET /documents"
        )
        current = application.application_understanding.decide_role(
            connected.project.project_id,
            owner.candidate_id,
            revision=current.revision,
            decision=CandidateDecision.CONFIRMED,
            display_name="所有者",
        )
        current = application.application_understanding.decide_action(
            connected.project.project_id,
            list_documents.candidate_id,
            revision=current.revision,
            decision=CandidateDecision.CONFIRMED,
            display_name="查看文档",
        )
        current = application.application_understanding.add_manual_role(
            connected.project.project_id,
            revision=current.revision,
            display_name="访客",
        )
        current = application.application_understanding.add_manual_action(
            connected.project.project_id,
            revision=current.revision,
            display_name="导出审计记录",
            risk_hint=ActionRiskHint.READ,
        )

        source_file.write_text(
            "roles = ['auditor']\n@app.post('/reports')\ndef create_report(): pass\n",
            encoding="utf-8",
        )
        rescanned = application.application_understanding.analyze_source(
            connected.project.project_id,
            revision=current.revision,
        )

        roles = {item.canonical_key: item for item in rescanned.role_candidates}
        assert roles["owner"].decision is CandidateDecision.CONFIRMED
        assert roles["owner"].display_name == "所有者"
        assert roles["owner"].stale is True
        assert roles["访客"].origin is CandidateOrigin.MANUAL
        assert roles["访客"].stale is False
        assert roles["auditor"].decision is CandidateDecision.PROPOSED

        actions = {item.canonical_key: item for item in rescanned.action_candidates}
        assert actions["GET /documents"].decision is CandidateDecision.CONFIRMED
        assert actions["GET /documents"].display_name == "查看文档"
        assert actions["GET /documents"].stale is True
        manual = next(
            item
            for item in rescanned.action_candidates
            if item.display_name == "导出审计记录"
        )
        assert manual.origin is CandidateOrigin.MANUAL
        assert manual.stale is False
        assert actions["POST /reports"].decision is CandidateDecision.PROPOSED
    finally:
        application.close()


def test_detected_and_manual_candidates_follow_distinct_reversible_states(
    tmp_path: Path,
) -> None:
    """系统候选可回到待确认；手工候选只能在已确认与已排除之间恢复。"""

    source = tmp_path / "source"
    source.mkdir()
    (source / "app.py").write_text(
        "roles = ['owner']\n@app.get('/documents')\ndef list_documents(): pass\n",
        encoding="utf-8",
    )
    endpoint = "http://127.0.0.1:4888"
    application = ApplicationCore(
        tmp_path / "var",
        environ={},
        endpoint_discovery=_reachable_discovery(endpoint),
    )
    try:
        connected = application.application_understanding.connect(source)
        current = application.application_understanding.confirm_endpoint(
            connected.project.project_id,
            endpoint=endpoint,
            revision=connected.understanding.revision,
        )
        current = application.application_understanding.authorize_source_analysis(
            connected.project.project_id,
            revision=current.revision,
        )
        current = application.application_understanding.analyze_source(
            connected.project.project_id,
            revision=current.revision,
        )
        detected_role = current.role_candidates[0]
        detected_action = current.action_candidates[0]

        for candidate_type, candidate in (
            ("role", detected_role),
            ("action", detected_action),
        ):
            decide = (
                application.application_understanding.decide_role
                if candidate_type == "role"
                else application.application_understanding.decide_action
            )
            current = decide(
                connected.project.project_id,
                candidate.candidate_id,
                revision=current.revision,
                decision=CandidateDecision.CONFIRMED,
            )
            current = decide(
                connected.project.project_id,
                candidate.candidate_id,
                revision=current.revision,
                decision=CandidateDecision.REJECTED,
            )
            current = decide(
                connected.project.project_id,
                candidate.candidate_id,
                revision=current.revision,
                decision=CandidateDecision.PROPOSED,
            )
            candidates = (
                current.role_candidates
                if candidate_type == "role"
                else current.action_candidates
            )
            restored = next(
                item for item in candidates if item.candidate_id == candidate.candidate_id
            )
            assert restored.decision is CandidateDecision.PROPOSED
            assert restored.origin is CandidateOrigin.DETECTED

        current = application.application_understanding.add_manual_role(
            connected.project.project_id,
            revision=current.revision,
            display_name="审核员",
        )
        manual = next(
            item for item in current.role_candidates if item.origin is CandidateOrigin.MANUAL
        )
        current = application.application_understanding.decide_role(
            connected.project.project_id,
            manual.candidate_id,
            revision=current.revision,
            decision=CandidateDecision.REJECTED,
        )
        with pytest.raises(JiejianError) as invalid_history:
            application.application_understanding.decide_role(
                connected.project.project_id,
                manual.candidate_id,
                revision=current.revision,
                decision=CandidateDecision.PROPOSED,
            )
        assert invalid_history.value.code == ErrorCode.ONBOARDING_INPUT_INVALID.value
        restored_manual = application.application_understanding.decide_role(
            connected.project.project_id,
            manual.candidate_id,
            revision=current.revision,
            decision=CandidateDecision.CONFIRMED,
        )
        manual_after = next(
            item
            for item in restored_manual.role_candidates
            if item.candidate_id == manual.candidate_id
        )
        assert manual_after.decision is CandidateDecision.CONFIRMED
        assert manual_after.origin is CandidateOrigin.MANUAL
        assert application.project_readiness.get(
            connected.project.project_id
        ).next_required_action == "REVIEW_DISCOVERY"
    finally:
        application.close()
