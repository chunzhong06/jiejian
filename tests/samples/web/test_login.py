# 验证官方 Sample 的人工登录只建立当前主机 HttpOnly 会话，并可访问受控资源。

from __future__ import annotations

import httpx


def test_sample_manual_login_sets_cookie_session(sample_server_factory) -> None:
    sample = sample_server_factory("fixed")
    base_url = f"http://127.0.0.1:{sample.port}"
    with httpx.Client(base_url=base_url, follow_redirects=False, trust_env=False) as client:
        login = client.post(
            "/login",
            data={"role": "owner", "password": "sample-owner-password"},
        )
        assert login.status_code == 303
        cookie = login.headers["set-cookie"]
        assert "HttpOnly" in cookie
        assert "SameSite=Lax" in cookie

        application = client.get("/")
        assert application.status_code == 200
        assert application.headers["content-type"].startswith("text/html")
        assert "修改、核对并恢复所有者资源" in application.text
        assert "resource_id" not in application.text

        resource = client.get("/resources/owner-resource")
        assert resource.status_code == 200
        assert resource.json()["owner_subject_id"] == "owner"


def test_inconclusive_sample_makes_confirmed_owner_read_unavailable(
    sample_server_factory,
) -> None:
    sample = sample_server_factory("inconclusive")
    base_url = f"http://127.0.0.1:{sample.port}"
    with httpx.Client(base_url=base_url, follow_redirects=False, trust_env=False) as client:
        login = client.post(
            "/login",
            data={"role": "owner", "password": "sample-owner-password"},
        )
        assert login.status_code == 303

        resource = client.get("/resources/owner-resource")
        assert resource.status_code == 503
        assert resource.json() == {"error": "resource_observer_unavailable"}
