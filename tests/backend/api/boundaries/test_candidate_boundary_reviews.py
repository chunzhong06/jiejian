# 通过真实API核验一般业务边界决定、历史继承、缺口留存和并发回执，不复刻测试机数据。
from copy import deepcopy
from uuid import uuid4

from tests.fixtures.control_plane import TestClient, create_app
from tests.backend.api.boundaries._support_rule_candidates import _content, _project, _save
from tests.backend.api.boundaries._support_rule_candidates import scenario_content, decide, propose


def review(client, prefix, value, index=0, outcome="NOT_SEPARATE_ACTION", **extra):
    root = value["candidate"]
    issue = value["boundary_reviews"][index]
    command = {"operation_id": uuid4().hex, "expected_basis_id": root["basis_id"], "expected_revision": root["revision"],
        "issue_id": issue["issue_id"], "issue_fingerprint": issue["issue_fingerprint"], "outcome": outcome,
        "reason": "这是登录材料所需的基础入口，不是用户提出的独立业务动作。",
        "retained_requirement": "负责人发布自己的资料必须成功，评审不得发布负责人的资料。", **extra}
    response = client.post(f"{prefix}/rule-candidates/{root['candidate_id']}/boundary-decisions", json=command)
    assert response.status_code == 201, response.text
    return command, response.json()["data"]


def test_independent_questions_keep_two_choices_history_and_restart(tmp_path):
    var = tmp_path / "var"
    with TestClient(create_app(var, start_worker=False, environ={})) as client:
        project = _project(client, tmp_path / "source"); prefix = f"/api/projects/{project}/business-boundaries"
        content = scenario_content()
        second = deepcopy(content["scenarios"][0]); second["scenario_id"] = "rsc_2222222222222222"
        second["question"] = "是否保留评审拒绝要求？"; content["scenarios"].append(second)
        content["unresolved_questions"] = ["末尾斜杠需要单独建模吗？", "登录和用户信息接口是否单独建模？"]
        content["unsupported_constraints"] = ["version并发条件", "任意历史未开放", "两个入口未分别取证"]
        _, first = _save(client, prefix, content)
        _, one = decide(client, prefix, first); _, two = decide(client, prefix, one, scenario_index=1)
        original_choices = two["scenario_decisions"]
        _, three = review(client, prefix, two)
        _, four = review(client, prefix, three, 1)
        assert four["scenario_decisions"] == original_choices
        assert four["candidate"]["content"] == two["candidate"]["content"]
        assert four["candidate"]["schema_version"] == "3"
        assert len([item for item in four["issues"] if item["code"] == "RULE_KIND_UNSUPPORTED"]) == 3
        assert propose(client, prefix, four).status_code == 409
        for index, outcome in [(2, "PREPARATION_DEPENDENCY"), (3, "EVIDENCE_GAP"), (4, "COVERAGE_GAP")]:
            _, four = review(client, prefix, four, index, outcome)
        gaps = client.get(prefix + "/rule-context").json()["data"]["boundary_review_gaps"]
        assert len(gaps) == 3
        old = client.get(f"{prefix}/rule-candidates/{first['candidate']['candidate_id']}?revision=3").json()["data"]
        assert old["scenario_decisions"] == original_choices
        assert old["candidate"]["schema_version"] == "2"
    with TestClient(create_app(var, start_worker=False, environ={})) as client:
        latest = client.get(f"{prefix}/rule-candidates/{first['candidate']['candidate_id']}").json()["data"]
        assert latest["scenario_decisions"] == original_choices
        assert latest["boundary_reviews"] == four["boundary_reviews"]


def test_receipt_conflict_and_no_agent_forgery(tmp_path):
    with TestClient(create_app(tmp_path / "var", start_worker=False, environ={})) as client:
        project = _project(client, tmp_path / "source"); prefix = f"/api/projects/{project}/business-boundaries"
        content = _content(); content["unresolved_questions"] = ["是否单独建模登录？"]
        _, first = _save(client, prefix, content)
        command, selected = review(client, prefix, first)
        url = f"{prefix}/rule-candidates/{first['candidate']['candidate_id']}/boundary-decisions"
        assert client.post(url, json=command).json()["data"] == selected
        assert client.post(url, json={**command, "outcome": "DEFER"}).status_code == 409
        assert client.post(url, json={**command, "operation_id": uuid4().hex}).status_code == 409
        assert client.post(url, json={**command, "submitted_via": "LOCAL_GUI"}).status_code == 422
        receipt = client.get(prefix + "/rule-operations/DECIDE/" + command["operation_id"]).json()["data"]
        assert receipt["candidate"]["candidate"]["revision"] == selected["candidate"]["revision"]
        assert selected["assessment"] == "REVIEWABLE"
        assert propose(client, prefix, selected).status_code == 201
        assert client.get(prefix).json()["data"]["policy_epoch"] == 0


def test_revision_carries_unrelated_decisions_and_invalidates_changed_business(tmp_path):
    with TestClient(create_app(tmp_path / "var", start_worker=False, environ={})) as client:
        project = _project(client, tmp_path / "source"); prefix = f"/api/projects/{project}/business-boundaries"
        content = _content(); content["unresolved_questions"] = ["是否单独建模登录？"]
        _, first = _save(client, prefix, content); _, selected = review(client, prefix, first)
        candidate_id = first["candidate"]["candidate_id"]
        content["examples"][0]["description"] += "补充说明"
        _, same = _save(client, prefix, content, candidate_id=candidate_id, expected_revision=2)
        assert same["boundary_reviews"][0]["status"] == "RESOLVED"
        content["original_text"] += "所有发布均需要复核。"
        _, changed = _save(client, prefix, content, candidate_id=candidate_id, expected_revision=3)
        assert changed["boundary_reviews"][0]["status"] == "STALE"
        assert changed["boundary_reviews"][0]["decision"] == selected["boundary_reviews"][0]["decision"]
        assert propose(client, prefix, changed).status_code == 409
        _, reconfirmed = review(client, prefix, changed)
        assert reconfirmed["boundary_reviews"][0]["status"] == "RESOLVED"


def test_true_gaps_survive_archive_new_candidate_and_cannot_be_erased(tmp_path):
    with TestClient(create_app(tmp_path / "var", start_worker=False, environ={})) as client:
        project = _project(client, tmp_path / "source"); prefix = f"/api/projects/{project}/business-boundaries"
        content = _content(); content["unsupported_constraints"] = ["两个入口尚未取证"]
        _, first = _save(client, prefix, content)
        command, gap = review(client, prefix, first, outcome="COVERAGE_GAP")
        candidate_id = first["candidate"]["candidate_id"]
        base = {"operation_id": uuid4().hex, "expected_basis_id": gap["candidate"]["basis_id"], "candidate_id": candidate_id, "expected_revision": 2}
        assert client.post(prefix + "/rule-candidates", json={**base, "content": _content()}).status_code == 409
        assert client.post(f"{prefix}/rule-candidates/{candidate_id}/boundary-decisions", json={**command,
            "operation_id": uuid4().hex, "expected_revision": 2, "outcome": "NOT_SEPARATE_ACTION"}).status_code == 400
        assert client.put(f"{prefix}/rule-candidates/{candidate_id}/visibility", json={"revision":2,"expected_version":0,"archived":True}).status_code == 200
        _save(client, prefix, _content())
        context = client.get(prefix + "/rule-context").json()["data"]
        assert len(context["boundary_review_gaps"]) == 1
        assert context["boundary_review_gaps"][0]["message"] == "两个入口尚未取证"


def test_constraint_overinterpretation_requires_human_and_preserves_original(tmp_path):
    with TestClient(create_app(tmp_path / "var", start_worker=False, environ={})) as client:
        project = _project(client, tmp_path / "source"); prefix = f"/api/projects/{project}/business-boundaries"
        content = _content(); content["unsupported_constraints"] = ["必须证明系统从建立以来没有发生发布"]
        _, first = _save(client, prefix, content)
        _, corrected = review(client, prefix, first, outcome="AGENT_OVERINTERPRETATION",
            reason="原要求针对本次操作过程，没有要求证明任意历史。",
            retained_requirement="本次操作中发生发布就属于违规，随后撤回也不能抵消，必须保留过程证据。")
        assert corrected["candidate"]["content"]["unsupported_constraints"] == content["unsupported_constraints"]
        assert corrected["assessment"] == "REVIEWABLE"
        proposed = propose(client, prefix, corrected).json()["data"]
        proposal = client.get(f"{prefix}/proposals/{proposed['proposal_id']}").json()["data"]["proposal"]
        approved = client.post(f"{prefix}/proposals/{proposed['proposal_id']}/approve", json={"schema_version":"1",
            "expected_fingerprint":proposal["proposal_fingerprint"],"reason":"确认实际规则"})
        assert approved.status_code == 200, approved.text
        # 此夹具未接入运行地址；批准只生成正式规则，不生成检查或安全结论。
        assert client.get(f"/api/projects/{project}/runs").json()["data"] == []


def test_local_authorization_and_explicit_rule_references(tmp_path):
    from fastapi.testclient import TestClient as RawTestClient
    from tests.fixtures.control_plane import TEST_CONTROL_ORIGIN
    app = create_app(tmp_path / "var", start_worker=False, environ={})
    with TestClient(app) as client:
        project = _project(client, tmp_path / "source"); prefix = f"/api/projects/{project}/business-boundaries"
        content = _content(); content["unresolved_questions"] = ["负责人发布自己的资料是否需要保留？"]
        _, first = _save(client, prefix, content)
        command, saved = review(client, prefix, first, outcome="REPRESENTED_BY_RULES",
            permission_item_ids=[content["permissions"][0]["item_id"]], reason="原文明确要求保留负责人的正常发布。",
            retained_requirement="负责人发布自己资料必须成功。")
        assert saved["assessment"] == "REVIEWABLE"
        url = f"{prefix}/rule-candidates/{first['candidate']['candidate_id']}/boundary-decisions"
        fresh = {**command,"operation_id":uuid4().hex,"expected_revision":2}
        assert client.post(url, json=fresh, headers={"Origin":"https://foreign.invalid"}).status_code == 403
        raw = RawTestClient(app, base_url=TEST_CONTROL_ORIGIN)
        try:
            assert raw.post(url, json=fresh, headers={"Origin":TEST_CONTROL_ORIGIN}).status_code == 403
        finally:
            raw.close()
        assert client.post(url, json={**fresh,"permission_item_ids":["pperm_ffffffffffffffff"]}).status_code == 400
        assert client.post(url, json={**fresh,"permission_item_ids":[]}).status_code == 422
        assert client.post(url, json={**fresh,"reason":"   "}).status_code == 422


def test_legacy_human_review_and_pending_scenarios_remain_project_obligations(tmp_path):
    with TestClient(create_app(tmp_path / "var", start_worker=False, environ={})) as client:
        project = _project(client, tmp_path / "source"); prefix = f"/api/projects/{project}/business-boundaries"
        content = scenario_content(); content["unresolved_questions"] = ["登录是否独立建模？"]
        _, first = _save(client, prefix, content)
        _, deferred = decide(client, prefix, first, action="DEFER")
        assert deferred["candidate"]["schema_version"] == "2"
        assert len(client.get(prefix + "/rule-context").json()["data"]["boundary_review_gaps"]) == 2
        _, resolved_scope = review(client, prefix, deferred)
        gaps = client.get(prefix + "/rule-context").json()["data"]["boundary_review_gaps"]
        assert len(gaps) == 1 and gaps[0]["message"] == content["scenarios"][0]["question"]
        _, resolved_all = decide(client, prefix, resolved_scope)
        assert resolved_all["candidate"]["schema_version"] == "3"
        assert not client.get(prefix + "/rule-context").json()["data"]["boundary_review_gaps"]

