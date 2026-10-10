# 共用规则候选和本地应用构造器，不导入或执行其他测试用例。
from uuid import uuid4


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


