# 验证项目列表从持久示例关联投影来源，不以名称或运行状态猜测身份。
from tests.fixtures.control_plane import TestClient, create_app


def test_project_list_preserves_sample_origin_without_runtime(tmp_path):
    app = create_app(tmp_path / "var", start_worker=False, environ={})
    with TestClient(app) as client:
        ids = []
        for name in ("sample", "ordinary"):
            source = tmp_path / name
            source.mkdir()
            response = client.post("/api/applications/connect", json={
                "schema_version": "1", "source_root": str(source), "project_name": "协作空间",
            })
            assert response.status_code == 201, response.text
            ids.append(response.json()["data"]["project"]["project_id"])
        with app.state.context.uow_factory() as work:
            work.sample_workspaces.save({
                "workspace_id": "historical-workspace", "project_id": ids[0],
                "source_root": str(tmp_path / "sample"), "scenario_version": "BASELINE",
                "created_at_us": 1,
            })
            work.commit()
        values = client.get("/api/projects").json()["data"]
        assert {item["project_id"]: item["official_sample"] for item in values} == {
            ids[0]: True, ids[1]: False,
        }
        assert all("source_root" not in item and "kernel_identity" not in item for item in values)
        # 移除后历史列表仍保留来源；查询不创建实例或重写项目状态。
        assert client.delete(f"/api/projects/{ids[0]}").status_code == 200
        assert [item["project_id"] for item in client.get("/api/projects").json()["data"]] == [ids[1]]
        history = client.get("/api/projects?include_archived=true").json()["data"]
        old = next(item for item in history if item["project_id"] == ids[0])
        assert old["official_sample"] is True and old["status"] == "ARCHIVED"
