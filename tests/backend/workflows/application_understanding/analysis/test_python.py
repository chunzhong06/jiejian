# 验证 Python AST 检测器只接受明确的权限组结构。

from __future__ import annotations

import json
from pathlib import Path

from product.backend.workflows.application_understanding.analysis.analyzer import (
    ApplicationUnderstandingAnalyzer,
)


def test_role_discovery_requires_explicit_group_structures(tmp_path: Path) -> None:
    (tmp_path / "roles.py").write_text(
        """
from enum import StrEnum

class UserRole(StrEnum):
    OWNER = "owner"

token_payload = {"owner_subject_id": "owner-subject", "attacker_id": "attacker"}
permissions = ["read:order", "write:order", "peer_id"]

def allowed(user):
    require_role("admin")
    return user.role == "member"
""".strip(),
        encoding="utf-8",
    )
    (tmp_path / "client.ts").write_text(
        "const permissions = ['owner_subject_id', 'attacker_id', 'peer_id']\n",
        encoding="utf-8",
    )
    (tmp_path / "openapi.json").write_text(
        json.dumps(
            {
                "openapi": "3.1.0",
                "x-roles": ["auditor"],
                "components": {
                    "securitySchemes": {
                        "oauth": {
                            "type": "oauth2",
                            "flows": {
                                "clientCredentials": {
                                    "tokenUrl": "/token",
                                    "scopes": {
                                        "read:order": "读取订单",
                                        "write:order": "修改订单",
                                    },
                                }
                            },
                        }
                    }
                },
                "paths": {},
            }
        ),
        encoding="utf-8",
    )

    result = ApplicationUnderstandingAnalyzer().analyze("project-a", tmp_path)

    assert {item.canonical_key for item in result.role_candidates} == {
        "admin",
        "auditor",
        "member",
        "owner",
    }
