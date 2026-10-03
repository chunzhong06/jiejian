# 验证对话候选与正式权限隔离、幂等保存、普通提案衔接和精确历史回读。
from copy import deepcopy
from uuid import uuid4

from tests.fixtures.control_plane import TestClient, create_app


def _content():
    return {
        "original_text": "负责人可以发布自己的资料。",
        "actors": [{"item_id": "pactr_1111111111111111", "write_mode": "CREATE",
            "display_name": "负责人", "description": "管理自己项目的资料", "effective_state": "ACTIVE"}],
        "actions": [{"item_id": "pactn_1111111111111111", "write_mode": "CREATE",
            "display_name": "发布资料", "description": "将资料持久发布", "primary_resource_concept": "项目资料",
            "operation_kind": "CHANGE", "state_changing": True, "effective_state": "ACTIVE",
            "effect_catalog": [{"item_id": "peff_1111111111111111", "business_label": "资料被发布",
                "effect_kind": "STATE_MUTATION", "resource_concept": "资料", "description": "资料已持久发布",
                "expected_state": "published"}]}],
        "permissions": [{"item_id": "pperm_1111111111111111", "write_mode": "CREATE", "effective_state": "ACTIVE",
            "subject_actor_item_id": "pactr_1111111111111111", "business_action_item_id": "pactn_1111111111111111",
            "resource_owner_actor_item_id": "pactr_1111111111111111", "relation": "OWNS", "expectation": "ALLOW",
            "protected_effect_item_ids": ["peff_1111111111111111"]}],
        "examples": [{"description": "负责人发布自己项目的资料，应该成功", "permission_item_id": "pperm_1111111111111111"}],
    }


def _project(client, path):
    path.mkdir()
    response = client.post("/api/applications/connect", json={"schema_version": "1", "source_root": str(path), "project_name": "普通资料应用"})
    assert response.status_code == 201, response.text
    return response.json()["data"]["project"]["project_id"]


def _save(client, prefix, content=None, **extra):
    context = client.get(prefix + "/rule-context")
    assert context.status_code == 200, context.text
    basis = context.json()["data"]["basis_id"]
    request = {"operation_id": uuid4().hex, "expected_basis_id": basis, "content": content or _content(), **extra}
    response = client.post(prefix + "/rule-candidates", json=request)
    assert response.status_code == 201, response.text
    return request, response.json()["data"]


def test_candidate_receipts_and_human_approval_survive_restart(tmp_path):
    var = tmp_path / "var"
    with TestClient(create_app(var, start_worker=False, environ={})) as client:
        project = _project(client, tmp_path / "source")
        prefix = f"/api/projects/{project}/business-boundaries"
        request, saved = _save(client, prefix)
        candidate_id = saved["candidate"]["candidate_id"]
        assert saved["assessment"] == "REVIEWABLE"
        assert client.get(prefix).json()["data"]["policy_epoch"] == 0
        assert client.post(prefix + "/rule-candidates", json=request).json()["data"] == saved
        changed = deepcopy(request)
        changed["content"]["original_text"] = "另一条约定"
        assert client.post(prefix + "/rule-candidates", json=changed).status_code == 409
        response = client.post(f"{prefix}/rule-candidates/{candidate_id}/proposals", json={"revision": 1, "operation_id": uuid4().hex})
        assert response.status_code == 201, response.text
        proposal_id = response.json()["data"]["proposal_id"]
        assert client.get(prefix).json()["data"]["policy_epoch"] == 0
        proposal = client.get(f"{prefix}/proposals/{proposal_id}").json()["data"]["proposal"]
        approved = client.post(f"{prefix}/proposals/{proposal_id}/approve", json={"schema_version": "1",
            "expected_fingerprint": proposal["proposal_fingerprint"], "reason": "已核对业务含义"})
        assert approved.status_code == 200, approved.text
        assert approved.json()["data"]["policy_epoch"] == 1
        context = client.get(prefix + "/rule-context").json()["data"]
        assert context["preparation"]["preparation_complete"] is False
        repeated = _content()
        for name in ("actors", "actions", "permissions"):
            repeated[name] = deepcopy(context[name])
            for item in repeated[name]:
                item["write_mode"] = "REFERENCE"
                if name == "actions":
                    item["effect_catalog"] = item.pop("effects")
        repeated["examples"][0]["permission_item_id"] = repeated["permissions"][0]["item_id"]
        _, already = _save(client, prefix, repeated)
        assert already["assessment"] == "ALREADY_CONFIRMED"
        assert already["reuse"]["actions"][0]["status"] == "MISSING"
        assert client.post(f"{prefix}/rule-candidates/{already['candidate']['candidate_id']}/proposals",
            json={"revision": 1, "operation_id": uuid4().hex}).status_code == 409
        assert client.get(prefix).json()["data"]["policy_epoch"] == 1
    with TestClient(create_app(var, start_worker=False, environ={})) as client:
        restored = client.get(f"{prefix}/rule-candidates/{candidate_id}?revision=1").json()["data"]
        assert restored["candidate"] == saved["candidate"]
        assert restored["proposal_id"] == proposal_id
        assert restored["decision"]["decision"] == "APPROVED"
        assert restored["assessment"] == "DECIDED"
        assert restored["issues"] == []
        receipt = client.get(f"{prefix}/rule-operations/SAVE/{request['operation_id']}").json()["data"]
        assert receipt["status"] == "FOUND"


def test_unclear_unsupported_and_uncovered_rules_cannot_become_proposals(tmp_path):
    with TestClient(create_app(tmp_path / "var", start_worker=False, environ={})) as client:
        project = _project(client, tmp_path / "source")
        prefix = f"/api/projects/{project}/business-boundaries"
        for field, value in (("unresolved_questions", ["是否允许撤回后再次发布？"]),
                             ("unsupported_constraints", ["并发时最多只能存在一份发布结果"]),
                             ("examples", [])):
            content = _content()
            content[field] = value
            _, saved = _save(client, prefix, content)
            assert saved["assessment"] == "NEEDS_CHANGES"
            response = client.post(f"{prefix}/rule-candidates/{saved['candidate']['candidate_id']}/proposals",
                json={"revision": 1, "operation_id": uuid4().hex})
            assert response.status_code == 409
        assert client.get(prefix).json()["data"]["policy_epoch"] == 0


def test_candidate_revisions_do_not_overwrite_and_cross_project_isolation(tmp_path):
    with TestClient(create_app(tmp_path / "var", start_worker=False, environ={})) as client:
        project = _project(client, tmp_path / "source")
        other = _project(client, tmp_path / "other")
        prefix = f"/api/projects/{project}/business-boundaries"
        _, first = _save(client, prefix)
        candidate_id = first["candidate"]["candidate_id"]
        _, second = _save(client, prefix, candidate_id=candidate_id, expected_revision=1)
        assert second["candidate"]["revision"] == 2
        assert client.get(f"{prefix}/rule-candidates/{candidate_id}?revision=1").json()["data"]["candidate"] == first["candidate"]
        assert client.get(f"/api/projects/{other}/business-boundaries/rule-candidates/{candidate_id}").status_code == 404
        old = {"operation_id": uuid4().hex, "expected_basis_id": first["candidate"]["basis_id"],
            "candidate_id": candidate_id, "expected_revision": 1, "content": _content()}
        assert client.post(prefix + "/rule-candidates", json=old).status_code == 409
        old["expected_revision"] = 2
        old["content"]["original_text"] = "password=do-not-persist-this"
        rejected = client.post(prefix + "/rule-candidates", json=old)
        assert rejected.status_code >= 400
        assert "do-not-persist-this" not in rejected.text


def test_new_rule_preserves_existing_permissions_and_stale_basis_is_rejected(tmp_path):
    with TestClient(create_app(tmp_path / "var", start_worker=False, environ={})) as client:
        project = _project(client, tmp_path / "source")
        prefix = f"/api/projects/{project}/business-boundaries"
        _, first = _save(client, prefix)
        first_id = first["candidate"]["candidate_id"]
        created = client.post(f"{prefix}/rule-candidates/{first_id}/proposals", json={"revision": 1, "operation_id": uuid4().hex}).json()["data"]
        proposal = client.get(f"{prefix}/proposals/{created['proposal_id']}").json()["data"]["proposal"]
        approved = client.post(f"{prefix}/proposals/{created['proposal_id']}/approve", json={"schema_version": "1",
            "expected_fingerprint": proposal["proposal_fingerprint"], "reason": "确认第一条"})
        assert approved.status_code == 200
        stale = client.post(prefix + "/rule-candidates", json={"operation_id": uuid4().hex,
            "expected_basis_id": first["candidate"]["basis_id"], "content": _content()})
        assert stale.status_code == 409
        context = client.get(prefix + "/rule-context").json()["data"]
        content = _content()
        content["actors"] = []
        content["actions"][0]["item_id"] = "pactn_2222222222222222"
        content["actions"][0]["display_name"] = "发布另一类资料"
        permission = content["permissions"][0]
        permission["item_id"] = "pperm_2222222222222222"
        permission["business_action_item_id"] = "pactn_2222222222222222"
        permission["subject_actor_item_id"] = permission["resource_owner_actor_item_id"] = context["actors"][0]["item_id"]
        content["examples"][0]["permission_item_id"] = permission["item_id"]
        _, second = _save(client, prefix, content)
        response = client.post(f"{prefix}/rule-candidates/{second['candidate']['candidate_id']}/proposals",
            json={"revision": 1, "operation_id": uuid4().hex})
        assert response.status_code == 201, response.text
        proposal = client.get(f"{prefix}/proposals/{response.json()['data']['proposal_id']}").json()["data"]["proposal"]
        assert len(proposal["proposed_permissions"]) == 2
        preserved = [p for p in proposal["proposed_permissions"] if p["intent_id"] is not None]
        assert len(preserved) == 1
        assert preserved[0]["write_mode"] == "REFERENCE"
        assert preserved[0]["effective_state"] == "ACTIVE"
