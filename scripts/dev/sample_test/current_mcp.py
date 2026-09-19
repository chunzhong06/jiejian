# 唯一 Official 实例的受控 MCP 责任验收；秘密仅在 SDK 会话内存，副作用回执未知不重发。
from contextlib import ExitStack, asynccontextmanager
from functools import partial

from . import current_api

CLIENT_NAME = "界鉴验收客户端"
REASON = "受控验收核对当前修复源码，未修改文件"
RUN_KEY = "official-mcp-responsibility-check"


def _error(code):
    from .official import SampleTestError
    raise SampleTestError(code) from None


@asynccontextmanager
async def _sdk_client(origin, token):
    import httpx2
    from mcp.client import Client
    from mcp.client.streamable_http import streamable_http_client
    from mcp.types import Implementation
    async with httpx2.AsyncClient(headers={"Authorization": "Bearer " + token, "Origin": origin},
            follow_redirects=True, timeout=120) as http:
        async with Client(streamable_http_client(origin + "/mcp", http_client=http, terminate_on_close=False),
                client_info=Implementation(name=CLIENT_NAME, version="1"), read_timeout_seconds=120) as client:
            yield client


class SDKSession:
    """SDK 在专用异步线程运行，主线程继续使用同步 Playwright；不启动用户 AI 客户端。"""
    def __init__(self, origin, token):
        self.origin, self.token, self.stack = origin, token, ExitStack()

    def __enter__(self):
        from anyio.from_thread import start_blocking_portal
        try:
            self.portal = self.stack.enter_context(start_blocking_portal())
            self.client = self.stack.enter_context(self.portal.wrap_async_context_manager(_sdk_client(self.origin, self.token)))
            return self
        except Exception:
            self.stack.close()
            raise
        finally:
            self.token = None

    def call(self, name, arguments):
        return self.portal.call(partial(self.client.call_tool, name, arguments))

    def __exit__(self, *exc):
        try:
            self.stack.close()
        finally:
            self.client = self.portal = self.token = None


def _call(session, name, arguments, *, denied=False):
    from mcp import MCPError
    try:
        value = session.call(name, arguments)
    except MCPError as exc:
        if denied and exc.code == -32043 and isinstance(exc.data, dict) and exc.data.get("error_code") == "MCP_PERMISSION_REQUIRED":
            return None
        _error("MCP_CALL_REJECTED")
    except Exception as exc:
        # 固定公开码与异常类别以外不暴露 SDK 响应、headers 或原异常正文。
        _error("MCP_RECEIPT_UNKNOWN:" + type(exc).__name__)
    if denied:
        _error("MCP_EXPECTED_DENIAL_MISSING")
    if value.is_error or not isinstance(value.structured_content, dict):
        _error("MCP_RECEIPT_INVALID")
    return value.structured_content


def _snapshot(client, project):
    runs = client.call("GET", f"/api/projects/{project}/runs")
    changes = client.call("GET", f"/api/projects/{project}/source-changes")
    if any(item["run"]["project_id"] != project for item in runs) or any(item["manifest"]["project_id"] != project for item in changes):
        _error("MCP_SNAPSHOT_PROJECT_MISMATCH")
    return {item["run"]["run_id"] for item in runs}, {item["manifest"]["change_id"] for item in changes}


def _deny_without_writes(session, client, project, tool, args):
    before = _snapshot(client, project)
    _call(session, tool, args, denied=True)
    if _snapshot(client, project) != before:
        _error("MCP_DENIAL_CREATED_STATE")


def _recover_run(client, project, before_runs, state):
    try:
        added = set(current_api.project_run_ids(client, project)) - before_runs
        if len(added) == 1:
            run_id = added.pop()
            status = client.call("GET", f"/api/runs/{run_id}")
            if status.get("run", {}).get("project_id") == project:
                state.active_run_id = run_id
                state.active_run_job_id = (status.get("job") or {}).get("job_id")
    except Exception:
        # 补查仅服务失败清理；读失败不能替换首个未知写入回执，也不能诱导再次提交。
        return


def cleanup(client, gui, state):
    """只撤销本场景的临时权限与新建配对；每次删除前回读，已有用户配对永久保留。"""
    if not state.mcp_cleanup_pending:
        return
    project = state.mcp_project_id
    rows = client.call("GET", f"/api/projects/{project}/runs")
    if any(item["run"]["lifecycle"] in {"QUEUED", "RUNNING"} for item in rows):
        _error("MCP_CLEANUP_ACTIVE_RUN")
    access = client.call("GET", "/api/mcp/access")
    grants = {item["project_id"]: item["level"] for item in access["project_grants"]}
    if access["paired"] and grants.get(project, "READ") != "READ":
        gui.mcp_level(project, "READ")
    if state.mcp_created_pairing and client.call("GET", "/api/mcp/access")["paired"]:
        if state.mcp_forget_attempted:
            _error("MCP_PAIRING_CLEANUP_UNRESOLVED")
        state.mcp_forget_attempted = True
        try:
            gui.mcp_forget()
        except Exception as exc:
            # GUI 回执未知先查持久事实；只有仍存在时才使用公开失败清理入口。
            if client.call("GET", "/api/mcp/access")["paired"]:
                from .official import SampleTestError
                if isinstance(exc, SampleTestError) and str(exc).startswith("GUI_ACTION_REJECTED:"):
                    # 服务端明确拒绝（包括凭据权限阻塞）不是未知回执，不换通道重复写入。
                    raise
                client.call("POST", "/api/mcp/access/forget")
        if client.call("GET", "/api/mcp/access")["paired"]:
            _error("MCP_PAIRING_CLEANUP_INCOMPLETE")
    elif not state.mcp_created_pairing and not client.call("GET", "/api/mcp/access")["paired"]:
        _error("MCP_EXISTING_PAIRING_LOST")
    state.mcp_cleanup_pending = False
    gui._mark("mcp-cleanup")


def run(client, gui, project, runs, state, *, session_factory=SDKSession):
    """在原三轮后只增加一个普通 Run；失败交由 Official 先取消活动任务再收口配对。"""
    token = credential = None
    state.mcp_project_id = project
    initial = client.call("GET", "/api/mcp/access")
    if initial["paired"] and not initial["accepting_connections"]:
        _error("MCP_EXISTING_PAIRING_PAUSED")
    state.mcp_cleanup_pending = True
    state.mcp_created_pairing = not initial["paired"]
    try:
        # 未配对分支在点击前记录所有权，回执未知时也能按公开 paired 状态清理，绝不重新 pair。
        credential = client.call("POST", "/api/mcp/access/reveal") if initial["paired"] else gui.mcp_pair()
        token = credential.get("access_token")
        if not isinstance(token, str) or not 32 <= len(token) <= 256:
            _error("MCP_CREDENTIAL_RECEIPT_INVALID")
        credential = None
        with session_factory(client.origin, token) as session:
            token = None
            gui.mcp_level(project, "READ")
            shown = _call(session, "jiejian_project_show", {"project_id": project})
            preview = _call(session, "jiejian_check_status", {"project_id": project})
            if shown.get("project_id") != project or preview.get("project_id") != project:
                _error("MCP_READ_PROJECT_MISMATCH")
            if preview.get("action_count") != 2 or preview.get("case_count") != 3 or preview.get("can_execute") is not True:
                _error("MCP_FULL_PLAN_UNAVAILABLE")
            gui.mcp_connected(CLIENT_NAME)
            _deny_without_writes(session, client, project, "jiejian_change_submit", {"project_id": project, "reason": REASON, "claimed_paths": []})
            gui.mcp_level(project, "PREPARE")
            _deny_without_writes(session, client, project, "jiejian_check_run", {"project_id": project, "idempotency_key": "official-mcp-denied"})
            prior = _snapshot(client, project)
            change = _call(session, "jiejian_change_submit", {"project_id": project, "reason": REASON, "claimed_paths": []})
            change_id = change.get("change_id")
            if (change.get("project_id") != project or not isinstance(change_id, str)
                    or change.get("submitted_by") != "MCP · " + CLIENT_NAME or change.get("reason") != REASON
                    or any(change.get(key) != [] for key in ("claimed_paths", "added_paths", "modified_paths", "removed_paths"))):
                _error("MCP_CHANGE_FACTS_MISMATCH")
            current = _snapshot(client, project)
            if current != (prior[0], prior[1] | {change_id}) or change_id in prior[1]:
                _error("MCP_CHANGE_COUNT_MISMATCH")
            saved = client.call("GET", f"/api/projects/{project}/source-changes/{change_id}")
            if saved["manifest"].get("repair_reference") is not None:
                _error("MCP_ORDINARY_CHANGE_HAS_REPAIR")
            gui.mcp_change(change)
            gui.mcp_level(project, "EXECUTE")
            gui.history_search(project, runs[0]["run_id"])
            gui.dismiss_completion()
            before_runs = set(current_api.project_run_ids(client, project))
            try:
                submitted = _call(session, "jiejian_check_run", {"project_id": project, "idempotency_key": RUN_KEY, "change_id": change_id})
            except Exception:
                # 只回读新增 Run 供外层失败清理；不以 SDK 或 HTTP 重发检查。
                _recover_run(client, project, before_runs, state)
                raise
            run_id, job_id = submitted.get("run_id"), (submitted.get("job") or {}).get("job_id")
            if submitted.get("project_id") != project or not run_id or not job_id or run_id in before_runs:
                _recover_run(client, project, before_runs, state)
                _error("MCP_RUN_RECEIPT_MISMATCH")
            # 已取得同项目回执即保留清理身份；后续只读失败不能丢掉已创建的活动任务。
            state.active_run_id, state.active_run_job_id = run_id, job_id
            observed = client.call("GET", f"/api/runs/{run_id}")
            if observed.get("run", {}).get("project_id") != project or (observed.get("job") or {}).get("job_id") != job_id:
                state.active_run_id = state.active_run_job_id = None
                _recover_run(client, project, before_runs, state)
                _error("MCP_RUN_JOB_MISMATCH")
            current_api.wait_published(client, state.active_run_id, state.active_run_job_id)
            result = current_api.read_result(client, state.active_run_id)
            current_api.assert_current_result(result, expected="PASS")
            if len({item["action_id"] for item in result["story"]["actions"]}) != 2:
                _error("MCP_FULL_RESULT_SCOPE_MISMATCH")
            if (result["story"].get("repair_verification") or {}).get("status") == "VERIFIED":
                _error("MCP_ORDINARY_RUN_MARKED_VERIFIED")
            if (result["story"].get("change_context") or {}).get("change_id") != change_id:
                _error("MCP_RUN_CHANGE_MISMATCH")
            if set(current_api.project_run_ids(client, project)) != before_runs | {state.active_run_id} or len(before_runs) != 3:
                _error("MCP_FOUR_RUNS_MISMATCH")
            for original in runs:
                if current_api.read_result(client, original["run_id"]) != original:
                    _error("MCP_ORIGINAL_RESULT_CHANGED")
            state.active_run_id = state.active_run_job_id = None
            gui.mcp_completion(result, runs[0]["run_id"])
            gui._mark("mcp-responsibility")
        cleanup(client, gui, state)
        return dict(client_name=CLIENT_NAME, project_id=project, change_id=change_id, run_id=result["run_id"],
            verdict="PASS", scope="ordinary-full-check", actual_changed_path_count=0, total_run_count=4,
            pairing="created-and-removed" if state.mcp_created_pairing else "existing-preserved")
    except Exception as exc:
        from .official import SampleTestError
        if isinstance(exc, SampleTestError):
            raise
        _error("MCP_SCENARIO_FAILED:" + type(exc).__name__)
    finally:
        credential = token = None
