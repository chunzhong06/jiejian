# 验证对话候选与正式权限隔离、幂等保存、普通提案衔接和精确历史回读。

import pytest
from copy import deepcopy
from uuid import uuid4

from tests.support.builders.control_plane import TestClient, create_app


from tests.support.builders.boundary_candidates import _content, _project, _save, confirm_scope


def test_archive_is_reversible_persistent_and_cannot_hide_pending_approval(tmp_path):
    var = tmp_path / "var"
    with TestClient(create_app(var, start_worker=False, environ={})) as client:
        project = _project(client, tmp_path / "source")
        other = _project(client, tmp_path / "other")
        prefix = f"/api/projects/{project}/business-boundaries"
        _, saved = _save(client, prefix)
        candidate_id = saved["candidate"]["candidate_id"]
        url = f"{prefix}/rule-candidates/{candidate_id}/visibility"
        command = {"archived": True, "revision": 1, "expected_version": 0}
        assert client.put(url.replace(project, other), json=command).status_code == 404
        response = client.put(url, json=command)
        assert response.status_code == 200, response.text
        assert response.json()["data"] == {"archived": True, "version": 1}
        assert client.put(url, json=command).status_code == 409
        assert client.get(prefix + "/rule-context?include_preparation=false").json()["data"]["candidates"] == []
        summary = client.get(prefix + "/rule-context?archived=true&include_preparation=false").json()["data"]
        assert summary["preparation"] is None
        assert summary["candidates"][0]["counts"] == {"actors": 1, "actions": 1, "permissions": 1, "examples": 1}
        assert client.post(f"{prefix}/rule-candidates/{candidate_id}/proposals", json={"revision":1,"operation_id":uuid4().hex}).status_code == 409
    with TestClient(create_app(var, start_worker=False, environ={})) as client:
        restored = client.get(f"{prefix}/rule-candidates/{candidate_id}").json()["data"]
        assert restored["candidate"] == saved["candidate"]
        assert restored["visibility"] == {"archived": True, "version": 1}
        assert client.put(url, json={"archived":False,"revision":1,"expected_version":1}).status_code == 200
        ready = confirm_scope(client, prefix, restored)
        proposal = client.post(f"{prefix}/rule-candidates/{candidate_id}/proposals", json={"revision":ready["candidate"]["revision"],"operation_id":uuid4().hex})
        assert proposal.status_code == 201, proposal.text
        assert client.put(url, json={"archived":True,"revision":ready["candidate"]["revision"],"expected_version":2}).status_code == 409
        assert client.get(prefix).json()["data"]["policy_epoch"] == 0


def test_candidate_receipts_and_human_approval_survive_restart(tmp_path):
    var = tmp_path / "var"
    with TestClient(create_app(var, start_worker=False, environ={})) as client:
        project = _project(client, tmp_path / "source")
        prefix = f"/api/projects/{project}/business-boundaries"
        request, saved = _save(client, prefix)
        candidate_id = saved["candidate"]["candidate_id"]
        assert saved["assessment"] == "NEEDS_CHANGES"
        assert any(item["code"] == "SCOPE_DECISION_REQUIRED" for item in saved["issues"])
        assert client.get(prefix).json()["data"]["policy_epoch"] == 0
        assert client.post(prefix + "/rule-candidates", json=request).json()["data"] == saved
        changed = deepcopy(request)
        changed["content"]["original_text"] = "另一条约定"
        assert client.post(prefix + "/rule-candidates", json=changed).status_code == 409
        ready = confirm_scope(client, prefix, saved)
        response = client.post(f"{prefix}/rule-candidates/{candidate_id}/proposals", json={"revision": ready["candidate"]["revision"], "operation_id": uuid4().hex})
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
        already = confirm_scope(client, prefix, already)
        assert already["assessment"] == "REVIEWABLE"
        assert already["reuse"]["actions"][0]["status"] == "MISSING"
        reused = client.post(f"{prefix}/rule-candidates/{already['candidate']['candidate_id']}/proposals",
            json={"revision": already['candidate']['revision'], "operation_id": uuid4().hex})
        assert reused.status_code == 201, reused.text
        reused_id=reused.json()['data']['proposal_id']
        reused_proposal=client.get(f'{prefix}/proposals/{reused_id}').json()['data']['proposal']
        unchanged=client.post(f'{prefix}/proposals/{reused_id}/approve',json={'schema_version':'1',
            'expected_fingerprint':reused_proposal['proposal_fingerprint'],'reason':'核对新一轮来源，沿用原权限'})
        assert unchanged.status_code==200, unchanged.text
        assert client.get(prefix).json()["data"]["policy_epoch"] == 1
    with TestClient(create_app(var, start_worker=False, environ={})) as client:
        restored = client.get(f"{prefix}/rule-candidates/{candidate_id}?revision={ready["candidate"]["revision"]}").json()["data"]
        assert restored["candidate"] == ready["candidate"]
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
            if field == 'examples':
                issue = next(item for item in saved['issues'] if item['code']=='PERMISSION_EXAMPLE_REQUIRED')
                assert issue['permission_item_ids'] == [content['permissions'][0]['item_id']]
                assert issue['path'] == 'candidate.content.examples'
                assert not any(item['code']=='NEEDS_CLARIFICATION' for item in saved['issues'])
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
        ready = confirm_scope(client, prefix, first)
        created = client.post(f"{prefix}/rule-candidates/{first_id}/proposals", json={"revision": ready["candidate"]["revision"], "operation_id": uuid4().hex}).json()["data"]
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
        second = confirm_scope(client, prefix, second)
        response = client.post(f"{prefix}/rule-candidates/{second['candidate']['candidate_id']}/proposals",
            json={"revision": second["candidate"]["revision"], "operation_id": uuid4().hex})
        assert response.status_code == 201, response.text
        proposal = client.get(f"{prefix}/proposals/{response.json()['data']['proposal_id']}").json()["data"]["proposal"]
        assert len(proposal["proposed_permissions"]) == 2
        preserved = [p for p in proposal["proposed_permissions"] if p["intent_id"] is not None]
        assert len(preserved) == 1
        assert preserved[0]["write_mode"] == "REFERENCE"
        assert preserved[0]["effective_state"] == "ACTIVE"

pytestmark = [pytest.mark.level3]
