# =============================================================================
# 应用接入工作流
#
# 定位
# 系统目录选择、受限识别、短期会话与首次检查提交之间的应用边界。
#
# 职责
# 保留选择状态｜管理非秘密会话｜隔离运行时凭据｜冻结并提交首次检查
#
# 边界
# 选择动作不扫描；识别不执行命令、不联网、不读取源码正文；入口不直接执行目标。
#
# 调用链
# Onboarding API → OnboardingWorkflow → Discovery / Project / Contract / Execution services
# =============================================================================

from __future__ import annotations

import json
import os
import re
import secrets
import subprocess
import threading
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Protocol
from urllib.parse import urlsplit

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.verification.permissions import PermissionContract, parse_permission_contract
from product.backend.infra.runtime.process_environment import ProcessEnvironmentRole, confirmed_python_executable, minimal_process_environment, run_python_module
from product.backend.infra.runtime.paths import RuntimePaths
from product.backend.workflows.onboarding.discovery import canonical_folder, discover_folder
from product.backend.workflows.onboarding.models import DiscoveryLimits, DiscoveryResult, FolderSelectionResult, OnboardingConfirmations, OnboardingCredentialStatus, OnboardingQuickCheckResult, OnboardingSession, OnboardingSessionUpdate, OnboardingSessionView
from product.backend.workflows.onboarding.secrets import RuntimeSecretVault
from product.backend.workflows.onboarding.session import OnboardingSessionStore

class FolderSelector(Protocol):
    def select_folder(self) -> FolderSelectionResult:
        """打开系统目录选择器，返回 selected/cancelled/unavailable。"""


class SystemFolderSelector:
    """用短生命周期主线程 UI 进程隔离 Tk，并保证超时和并发请求可收敛。"""

    _DESKTOP_ENVIRONMENT_KEYS = (
        "ALLUSERSPROFILE",
        "APPDATA",
        "HOMEDRIVE",
        "HOMEPATH",
        "PROGRAMDATA",
        "PUBLIC",
        "SYSTEMDRIVE",
    )

    def __init__(
        self,
        *,
        environment: Mapping[str, str] | None = None,
        timeout_seconds: float = 120.0,
        python_executable: str | None = None,
        var_dir: Path | None = None,
        platform_name: str | None = None,
        runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("folder selector timeout must be positive")
        self._environment = dict(environment if environment is not None else os.environ)
        self._timeout_seconds = timeout_seconds
        self._python_executable = python_executable
        selected_var = var_dir or Path(self._environment.get("JIEJIAN_VAR_DIR", "var"))
        self._runtime_paths = RuntimePaths(selected_var.resolve()).ensure_layout()
        self._platform_name = platform_name or os.name
        self._runner = runner
        self._selection_lock = threading.Lock()

    def select_folder(self) -> FolderSelectionResult:
        if self._platform_name != "nt":
            return FolderSelectionResult(
                status="unavailable",
                message="当前平台没有可用的系统目录选择器，请改用手工绝对路径",
            )
        if not self._selection_lock.acquire(blocking=False):
            return FolderSelectionResult(
                status="unavailable",
                message="目录选择器已经打开，请先完成或取消当前选择",
            )
        try:
            try:
                child_environment = minimal_process_environment(
                    self._environment,
                    role=ProcessEnvironmentRole.ONBOARDING_SELECTOR,
                )
                source_by_casefold = {
                    key.casefold(): value for key, value in self._environment.items()
                }
                for name in self._DESKTOP_ENVIRONMENT_KEYS:
                    value = source_by_casefold.get(name.casefold())
                    if value:
                        child_environment[name] = value
                confirmed_executable = confirmed_python_executable(child_environment)
                if self._python_executable is not None:
                    # 测试替身也必须声明同一解释器，避免目录选择器形成例外旁路。
                    requested_executable = Path(self._python_executable).resolve()
                    if requested_executable != Path(confirmed_executable):
                        raise JiejianError(
                            ErrorCode.ONBOARDING_SELECTOR_UNAVAILABLE,
                            "系统目录选择器不能替换界鉴已确认的 Python 解释器",
                        )
                if self._runner is not None:
                    completed = self._runner(
                        [
                            confirmed_executable,
                            "-B",
                            "-m",
                            "product.backend.workflows.onboarding.folder_picker_process",
                        ],
                        cwd=str(Path(__file__).resolve().parents[4]),
                        env=child_environment,
                        stdin=subprocess.DEVNULL,
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        timeout=self._timeout_seconds,
                        check=False,
                        shell=False,
                    )
                else:
                    source_environment = dict(self._environment)
                    source_environment.setdefault(
                        "JIEJIAN_VAR_DIR", str(self._runtime_paths.root)
                    )
                    desktop_environment = {
                        name: child_environment[name]
                        for name in self._DESKTOP_ENVIRONMENT_KEYS
                        if name in child_environment
                    }
                    completed = run_python_module(
                        source_environment,
                        "product.backend.workflows.onboarding.folder_picker_process",
                        role=ProcessEnvironmentRole.ONBOARDING_SELECTOR,
                        cwd=self._runtime_paths.temp,
                        timeout_seconds=self._timeout_seconds,
                        extra_environment=desktop_environment,
                        python_executable=confirmed_executable,
                    )
            except subprocess.TimeoutExpired:
                return FolderSelectionResult(
                    status="unavailable",
                    message="目录选择器等待超时，请重试或改用手工绝对路径",
                )
            except (OSError, ValueError) as exc:
                raise JiejianError(
                    ErrorCode.ONBOARDING_SELECTOR_UNAVAILABLE,
                    "系统目录选择器当前不可用，请改用手工绝对路径",
                ) from exc
            if completed.returncode != 0:
                raise JiejianError(
                    ErrorCode.ONBOARDING_SELECTOR_UNAVAILABLE,
                    "系统目录选择器当前不可用，请改用手工绝对路径",
                )
            try:
                payload = json.loads(completed.stdout.strip())
                if not isinstance(payload, dict) or payload.pop("schema_version", None) != "1":
                    raise ValueError("unsupported folder selector result version")
                result = FolderSelectionResult.model_validate(payload)
            except Exception as exc:
                raise JiejianError(
                    ErrorCode.ONBOARDING_SELECTOR_UNAVAILABLE,
                    "系统目录选择器返回无效，请改用手工绝对路径",
                ) from exc
            if (result.status == "selected") != (result.path is not None):
                raise JiejianError(
                    ErrorCode.ONBOARDING_SELECTOR_UNAVAILABLE,
                    "系统目录选择器返回无效，请改用手工绝对路径",
                )
            return result
        finally:
            self._selection_lock.release()


class OnboardingWorkflow:
    """编排受限目录识别、短期会话、运行时秘密和首次检查提交。"""

    def __init__(
        self,
        folder_selector: FolderSelector | None = None,
        *,
        limits: DiscoveryLimits | None = None,
        var_dir: Path | None = None,
        vault: RuntimeSecretVault | None = None,
        projects=None,
        contracts=None,
        execution=None,
        environment_provider=None,
    ) -> None:
        self.folder_selector = folder_selector or SystemFolderSelector()
        self.limits = limits or DiscoveryLimits()
        self._store = OnboardingSessionStore(var_dir) if var_dir is not None else None
        self._vault = vault or RuntimeSecretVault()
        self._projects = projects
        self._contracts = contracts
        self._execution = execution
        self._environment_provider = environment_provider

    def select_folder(self) -> FolderSelectionResult:
        return self.folder_selector.select_folder()

    def inspect(self, path: str) -> DiscoveryResult:
        """按冻结预算只读识别目录；不执行候选命令、不联网、不读取源码正文。"""

        return discover_folder(path, limits=self.limits)

    def create_session(self, path: str, project_name: str) -> OnboardingSessionView:
        """在再次受限识别后创建只含秘密引用的短期 onboarding 会话。"""

        store = self._require_store()
        source = canonical_folder(path)
        discover_folder(source, limits=self.limits)
        token = secrets.token_hex(16)
        session = OnboardingSession(
            session_id=f"onb_{token}",
            source_path=str(source),
            project_name=project_name,
            primary_secret_ref=f"env:JIEJIAN_ONB_{token.upper()}_PRIMARY",
            comparison_secret_ref=f"env:JIEJIAN_ONB_{token.upper()}_COMPARISON",
            project_id=f"onboarding_{token}",
        )
        store.create(session)
        return self._view(session)

    def get_session(self, session_id: str) -> OnboardingSessionView:
        return self._view(self._require_store().load(session_id))

    def update_session(self, session_id: str, update: OnboardingSessionUpdate) -> OnboardingSessionView:
        """以 revision 乐观锁更新非秘密字段，并重新计算 READY 状态。"""

        store = self._require_store()
        session = store.load(session_id)
        if session.status == "SUBMITTED":
            raise JiejianError(ErrorCode.ONBOARDING_SESSION_CONFLICT, "已提交的新手检查不能修改")
        if update.revision != session.revision:
            raise JiejianError(ErrorCode.ONBOARDING_SESSION_CONFLICT, "新手会话已更新，请刷新后重试")
        values = update.model_dump(exclude_unset=True, exclude={"revision"})
        if update.confirmations is not None:
            values["confirmations"] = update.confirmations
        next_session = session.model_copy(update={**values, "status": "DRAFT", "revision": session.revision + 1})
        self._validate_session_values(next_session)
        self._assert_no_secret_in_session(next_session)
        if not self._missing(next_session) and all(self._credential_status(next_session).model_dump().values()):
            next_session = next_session.model_copy(update={"status": "READY"})
        store.save(next_session)
        return self._view(next_session)

    def put_credentials(self, session_id: str, primary: str, comparison: str) -> OnboardingCredentialStatus:
        """把一次性凭据写入进程内 vault；持久会话始终只保留引用。"""

        session = self._require_store().load(session_id)
        if session.status == "SUBMITTED":
            raise JiejianError(ErrorCode.ONBOARDING_SESSION_CONFLICT, "已提交的新手检查不能修改凭据")
        if not primary or not comparison:
            raise JiejianError(ErrorCode.ONBOARDING_CREDENTIALS_INVALID, "需要同时提供两个测试凭据")
        self._vault.put(
            session_id,
            {session.primary_secret_ref.removeprefix("env:"): primary, session.comparison_secret_ref.removeprefix("env:"): comparison},
        )
        if not self._missing(session):
            self._require_store().save(session.model_copy(update={"status": "READY", "revision": session.revision + 1}))
        return self._credential_status(session)

    def quick_check(self, session_id: str) -> OnboardingQuickCheckResult:
        """把完整会话冻结为只读首检任务；重复调用返回已提交的同一 Run/Job。"""

        # --- 阶段：恢复幂等提交或验证当前会话 ---
        store = self._require_store()
        session = store.load(session_id)
        if session.status == "SUBMITTED" and session.submitted_run_id and session.submitted_job_id:
            with self._projects._uow_factory() as work:
                run = work.runs.get(session.submitted_run_id)
                job = work.jobs.get(session.submitted_job_id)
            if run is not None and job is not None:
                return OnboardingQuickCheckResult(
                    session=self._view(session), project_id=session.project_id,
                    run_id=run.run_id, job_id=job.job_id, created=False,
                )
        self._validate_session_values(session)
        missing = self._missing(session)
        credentials = self._credential_status(session)
        if not credentials.primary_configured or not credentials.comparison_configured:
            missing += ("测试凭据",)
        if missing:
            raise JiejianError(ErrorCode.ONBOARDING_SESSION_INCOMPLETE, "请先补充新手检查所需信息", details={"missing": missing})
        canonical_source = canonical_folder(session.source_path)
        if str(canonical_source) != session.source_path:
            raise JiejianError(ErrorCode.ONBOARDING_PATH_UNSAFE, "应用文件夹路径已变化，请重新选择")
        discover_folder(canonical_source, limits=self.limits)
        self._assert_no_secret_in_session(session)
        # --- 阶段：生成受控治理文件并登记项目、Contract 与 Profile ---
        profile_path = self._write_profile(session)
        registered = False
        try:
            self._projects.register(profile_path)
            contract = parse_permission_contract(self._contract_document(session))
            if self._contracts is None:
                raise JiejianError(ErrorCode.ONBOARDING_BUNDLE_FAILED, "Contract 治理服务尚未完成装配")
            with self._projects._uow_factory() as work:
                active = work.contract_versions.get_active(
                    session.project_id, contract.contract_id
                )
            if active is None:
                draft = self._contracts.create_draft(
                    session.project_id,
                    contract.contract_id,
                    snapshot=contract,
                    actor="onboarding",
                )
                reviewed = self._contracts.submit_review(
                    session.project_id, draft.contract_id, draft.version, actor="onboarding"
                )
                self._contracts.activate_review(
                    session.project_id, reviewed.contract_id, reviewed.version, actor="onboarding"
                )
            record = self._execution.register(profile_path, accept_source_changes=True)
            registered = True
            now_us = time.time_ns() // 1_000
            result, _request, _names = self._execution.submit(
                record.profile_id,
                project_id=record.project_id,
                idempotency_key=f"onboarding:{session.session_id}:quick-check",
                now_us=now_us,
                available_at_us=now_us,
                run_id=f"run_{secrets.token_hex(16)}",
                job_id=f"job_{secrets.token_hex(16)}",
            )
        except Exception:
            if not registered and not session.submitted_run_id:
                self._remove_profile_if_safe(profile_path)
            raise
        updated = session.model_copy(update={
            "status": "SUBMITTED", "revision": session.revision + 1,
            "submitted_run_id": result.run.run_id, "submitted_job_id": result.job.job_id,
        })
        store.save(updated)
        return OnboardingQuickCheckResult(
            session=self._view(updated), project_id=record.project_id,
            run_id=result.run.run_id, job_id=result.job.job_id, created=result.created,
        )

    def _require_store(self) -> OnboardingSessionStore:
        if self._store is None or self._projects is None or self._contracts is None or self._execution is None:
            raise JiejianError(ErrorCode.ONBOARDING_BUNDLE_FAILED, "新手检查服务尚未完成装配")
        return self._store

    def _credential_status(self, session: OnboardingSession) -> OnboardingCredentialStatus:
        configured = self._vault.configured(session.session_id, (
            session.primary_secret_ref.removeprefix("env:"),
            session.comparison_secret_ref.removeprefix("env:"),
        ))
        return OnboardingCredentialStatus(primary_configured=configured[0], comparison_configured=configured[1])

    def _assert_no_secret_in_session(self, session: OnboardingSession) -> None:
        names = (session.primary_secret_ref.removeprefix("env:"), session.comparison_secret_ref.removeprefix("env:"))
        values = tuple(value for value in self._vault.resolve(names).values() if value)
        if any(secret in session.model_dump_json() for secret in values):
            raise JiejianError(ErrorCode.ONBOARDING_CREDENTIALS_INVALID, "普通信息不能包含测试凭据")

    def _missing(self, session: OnboardingSession) -> tuple[str, ...]:
        missing: list[str] = []
        if not session.target_address: missing.append("目标地址")
        if not session.primary_display_name or not session.comparison_display_name: missing.append("测试账号显示名")
        if not session.primary_resource_id or not session.comparison_resource_id: missing.append("归属资源")
        if not session.read_only_path_template: missing.append("只读路径")
        if not session.recovery_path or not session.confirmations.recovery_confirmed: missing.append("恢复方式确认")
        if not session.confirmations.app_started: missing.append("应用已由用户启动确认")
        if not session.confirmations.target_authorized: missing.append("目标地址授权确认")
        if not session.confirmations.dangerous_inference_confirmed: missing.append("危险推断确认")
        return tuple(missing)

    def _validate_session_values(self, session: OnboardingSession) -> None:
        if session.target_address:
            self._parse_loopback(session.target_address)
        for value in (session.read_only_path_template, session.recovery_path):
            if value and (
                not value.startswith("/")
                or value.startswith("//")
                or ".." in value.split("/")
                or "?" in value
                or "#" in value
                or "\\" in value
                or any(ord(character) < 0x20 or ord(character) == 0x7F for character in value)
                or re.search(r"%(?:2e|2f|5c)", value, re.IGNORECASE)
            ):
                raise JiejianError(ErrorCode.ONBOARDING_INPUT_INVALID, "路径必须是当前应用内的安全相对路径")
        if session.read_only_path_template and session.read_only_path_template.count("{resource_id}") != 1:
            raise JiejianError(ErrorCode.ONBOARDING_INPUT_INVALID, "只读路径必须包含一个 resource_id 占位符")
        for value in (session.primary_resource_id, session.comparison_resource_id):
            if value and not re.fullmatch(r"[a-z][a-z0-9_-]{0,127}", value):
                raise JiejianError(ErrorCode.ONBOARDING_INPUT_INVALID, "资源标识格式无效")

    @staticmethod
    def _parse_loopback(value: str) -> tuple[str, int]:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {"", "/"} or parsed.hostname != "127.0.0.1":
            raise JiejianError(ErrorCode.ONBOARDING_TARGET_INVALID, "快速检查只支持带明确端口的 127.0.0.1 地址")
        try:
            port = parsed.port
        except ValueError:
            port = None
        if port is None or not 1 <= port <= 65535:
            raise JiejianError(ErrorCode.ONBOARDING_TARGET_INVALID, "快速检查必须填写明确端口")
        return f"{parsed.scheme}://127.0.0.1:{port}", port

    def _contract_document(self, session: OnboardingSession) -> bytes:
        target, _port = self._parse_loopback(session.target_address or "")
        return json.dumps(
            {
                "schema_version": "4",
                "contract_id": f"{session.project_id}-contract",
                "version": 1,
                "role_ids": ["owner", "user"],
                "workflow_states": ["DRAFT"],
                "subjects": [
                    {"subject_id": "primary", "roles": ["owner"], "tenant_id": "tenant", "department_id": "department"},
                    {"subject_id": "comparison", "roles": ["user"], "tenant_id": "tenant", "department_id": "department"},
                ],
                "effects": [{"effect_id": "resource-disclosed", "kind": "DATA_DISCLOSURE", "resource_type": "document", "protected_fields": ["value"]}],
                "actions": [{"action_id": "view", "effect_ids": ["resource-disclosed"]}],
                "resources": [
                    {"resource_id": session.primary_resource_id, "resource_type": "document", "owner_subject_id": "primary", "tenant_id": "tenant", "department_id": "department", "workflow_state": "DRAFT"},
                    {"resource_id": session.comparison_resource_id, "resource_type": "document", "owner_subject_id": "comparison", "tenant_id": "tenant", "department_id": "department", "workflow_state": "DRAFT"},
                ],
                "relations": [
                    {"relation_id": "same-tenant-owner", "relation": "SAME_TENANT", "source": {"endpoint_type": "subject", "endpoint_id": "comparison"}, "target": {"endpoint_type": "subject", "endpoint_id": "primary"}},
                    {"relation_id": "owns-primary", "relation": "OWNS", "source": {"endpoint_type": "subject", "endpoint_id": "primary"}, "target": {"endpoint_type": "resource", "endpoint_id": session.primary_resource_id}},
                ],
                "rules": [
                    {"rule_id": "owner-read", "subject_id": "primary", "action_id": "view", "resource_id": session.primary_resource_id, "relation_path": ["owns-primary"], "context": {"resource_ids": [session.primary_resource_id]}, "expectation": "ALLOW", "required_observations": ["resource_state"], "coverage_dimensions": ["ROLE"], "severity": "high"},
                    {"rule_id": "unauthorized-read", "subject_id": "comparison", "action_id": "view", "resource_id": session.primary_resource_id, "relation_path": ["same-tenant-owner", "owns-primary"], "context": {"resource_ids": [session.primary_resource_id]}, "expectation": "DENY", "required_observations": ["resource_state"], "coverage_dimensions": ["RELATION"], "severity": "high"},
                ],
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

    def _profile_document(self, session: OnboardingSession) -> dict:
        target, port = self._parse_loopback(session.target_address or "")
        return {
            "schema_version": "4",
            "profile_id": session.project_id,
            "project_id": session.project_id,
            "project_name": session.project_name,
            "target_type": "WEB",
            "contract_id": f"{session.project_id}-contract",
            "contract_version": 1,
            "target": {"scope": {"base_url": target, "allowed_origins": [target], "allowed_hosts": ["127.0.0.1"], "allowed_ports": [port], "allow_private_network": True, "follow_redirects": False, "timeout_seconds": 5, "max_requests": 10, "max_response_bytes": 262144}, "reset_path": session.recovery_path},
            "identities": [
                {"identity_id": "primary", "role": session.primary_display_name, "binding": {"kind": "BEARER", "secret_ref": session.primary_secret_ref}},
                {"identity_id": "comparison", "role": session.comparison_display_name, "binding": {"kind": "BEARER", "secret_ref": session.comparison_secret_ref}},
            ],
            "observers": [{"observer_id": "owner-observer", "observer_type": "OWNER_API", "target": {"target_id": "owner-target", "locator": {"locator_type": "OWNER_API", "relative_path_template": "/owner/resources/{resource_id}"}, "normalization_id": "owner-state", "normalization_version": "1"}, "phases": ["BASELINE", "BEFORE", "AFTER"], "required": True, "protocol_version": "2", "budget": {"timeout_us": 5000000, "max_rows": 1, "max_bytes": 262144}}],
            "subject_bindings": [
                {"subject_id": "primary", "identity_id": "primary"},
                {"subject_id": "comparison", "identity_id": "comparison"},
            ],
            "workflow_bindings": [{ "workflow_id": "view-workflow", "source_flow_id": "onboarding-flow", "action_id": "view", "steps": [{"id": "target-view", "purpose": "TARGET", "identity_id": "CASE_SUBJECT", "request_template": {"method": "GET", "path": session.read_only_path_template, "input_slots": [{"slot_id": "resource_id", "source": "CASE_RESOURCE_ID", "consumer": "PATH", "consumer_step_id": "target-view"}]}, "classifier": {"accepted": [{"kind": "STATUS_IN", "statuses": [200]}], "denied": [{"kind": "STATUS_IN", "statuses": [401, 403, 404]}]}}], "target_step_id": "target-view", "baseline_projections": [{"projection_id": "resource-state", "logical_resource_handle": "case-resource", "normalization_version": "1", "projection_version": "1", "integrity_mode": "EXACT_RESTORE"}], "reset_strategy": {"kind": "RESET_ENDPOINT", "path": session.recovery_path}}],
            "effect_bindings": [{"effect_id": "resource-disclosed", "required_channels": ["resource_state"], "corroborating_channels": [], "closure_policy": "IMMEDIATE", "projection_version": "v1"}],
            "observer_bindings": [{"requirement_id": "resource_state", "kind": "OBSERVER_SPEC", "observer_id": "owner-observer", "observer_type": "OWNER_API", "credential_ref": session.primary_secret_ref, "phases": ["BASELINE", "BEFORE", "AFTER"]}],
            "seed": 7,
            "case_budget": 8,
            "max_relation_depth": 8,
            "max_duration_us": 300_000_000,
        }

    def _write_profile(self, session: OnboardingSession) -> Path:
        return self._write_profile_document(session, self._profile_document(session))

    def _write_profile_document(self, session: OnboardingSession, document: dict) -> Path:
        root = (self._store.root.parent / session.session_id).resolve()
        if not root.is_relative_to(self._store.root.parent):
            raise JiejianError(ErrorCode.ONBOARDING_PATH_UNSAFE, "新手 Profile 路径不安全")
        profile_path = root / "profile.json"
        encoded = json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        if profile_path.is_file():
            try:
                if json.loads(profile_path.read_text(encoding="utf-8")) != document:
                    raise JiejianError(ErrorCode.ONBOARDING_SESSION_CONFLICT, "快速检查 Profile 与当前会话不一致，请新建会话")
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                raise JiejianError(ErrorCode.ONBOARDING_BUNDLE_FAILED, "已有快速检查 Profile 无效") from None
            return profile_path
        temp = root / f".profile-{secrets.token_hex(8)}.tmp"
        try:
            root.mkdir(parents=True, exist_ok=True)
            temp.write_bytes(encoded)
            os.replace(temp, profile_path)
            return profile_path
        except JiejianError:
            self._remove_profile_if_safe(temp)
            raise
        except Exception as exc:
            self._remove_profile_if_safe(temp)
            raise JiejianError(ErrorCode.ONBOARDING_BUNDLE_FAILED, "快速检查准备失败") from exc

    @staticmethod
    def _remove_profile_if_safe(path: Path) -> None:
        if path.name.startswith(".profile-") or path.name == "profile.json":
            path.unlink(missing_ok=True)

    def _view(self, session: OnboardingSession) -> OnboardingSessionView:
        credentials = self._credential_status(session)
        return OnboardingSessionView(
            **session.model_dump(exclude={"primary_secret_ref", "comparison_secret_ref", "project_id", "submitted_run_id", "submitted_job_id"}),
            primary_configured=credentials.primary_configured,
            comparison_configured=credentials.comparison_configured,
            missing_items=self._missing(session) + (("测试凭据",) if not all((credentials.primary_configured, credentials.comparison_configured)) else ()),
        )
