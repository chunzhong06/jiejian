# 验证候选批量审阅的原子性、版本门禁和不创建权限的边界。
from pathlib import Path

from tests.fixtures.control_plane import TestClient, create_app


def test_batch_decisions_are_atomic_and_versioned(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    app = create_app(tmp_path / "var", start_worker=False)
    with TestClient(app) as client:
        core = app.state.context
        connected = core.application_understanding.connect(source)
        project = connected.project.project_id
        view = core.application_understanding.add_manual_role(project, revision=0, display_name="项目负责人")
        view = core.application_understanding.add_manual_action(project, revision=view.revision, display_name="查看项目")
        role, action = view.role_candidates[0], view.action_candidates[0]
        path = f"/api/projects/{project}/candidate-decisions"
        items = [dict(kind="ROLE", candidate_id=role.candidate_id, decision="REJECTED", display_name=role.display_name),
                 dict(kind="ACTION", candidate_id=action.candidate_id, decision="REJECTED", display_name=action.display_name)]
        body = dict(schema_version="1", revision=view.revision, decisions=items)
        invalid = dict(items[1], candidate_id="action_" + "f" * 32)
        assert client.put(path, json={**body, "decisions": [items[0], invalid]}).status_code == 404
        assert core.application_understanding.get(project) == view
        assert client.put(path, json={**body, "decisions": [items[0], items[0]]}).status_code == 400
        assert core.application_understanding.get(project) == view
        response = client.put(path, json=body)
        assert response.status_code == 200
        current = response.json()["data"]
        assert current["revision"] == view.revision + 1
        assert current["role_candidates"][0]["decision"] == "REJECTED"
        assert current["action_candidates"][0]["decision"] == "REJECTED"
        assert client.put(path, json=body).status_code == 409
        assert core.application_understanding.get(project).revision == view.revision + 1
        boundary = core.business_boundaries.view(project)
        assert not boundary.permission_intents
        assert not boundary.actors


def test_batch_rejects_unknown_fields_and_stale_candidates(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    app = create_app(tmp_path / "var", start_worker=False)
    with TestClient(app) as client:
        core = app.state.context
        project = core.application_understanding.connect(source).project.project_id
        view = core.application_understanding.add_manual_role(project, revision=0, display_name="成员")
        role = view.role_candidates[0]
        body = dict(schema_version="1", revision=view.revision, decisions=[
            dict(kind="ROLE", candidate_id=role.candidate_id, decision="CONFIRMED", display_name="成员")])
        path = f"/api/projects/{project}/candidate-decisions"
        assert client.put(path, json={**body, "approve_permissions": True}).status_code == 422
        with core.uow_factory() as work:
            work.application_understanding.replace(view.model_copy(update={
                "role_candidates": (role.model_copy(update={"stale": True}),)}))
            work.commit()
        assert client.put(path, json=body).status_code == 409
        assert core.application_understanding.get(project).role_candidates[0].stale
