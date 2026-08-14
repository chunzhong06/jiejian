# 定位：首次使用目录选择与只读识别的应用边界。
# 职责：注入系统选择器、保留取消/不可用状态并调用受限 discovery；不执行目标命令。

from __future__ import annotations

import os
import hashlib
import re
import secrets
import time
from pathlib import Path
from typing import Protocol
from urllib.parse import urlsplit

import yaml

from ..errors import ErrorCode, JiejianError
from ..execution.request_store import required_secret_names
from ..execution.submission import SubmitExecutionV1
from ..verification.inputs import load_project_bundle
from .discovery import canonical_folder, discover_folder
from .models import (
    DiscoveryLimits,
    DiscoveryResult,
    FolderSelectionResult,
    OnboardingConfirmations,
    OnboardingCredentialStatus,
    OnboardingQuickCheckResult,
    OnboardingSession,
    OnboardingSessionUpdate,
    OnboardingSessionView,
)
from .secrets import RuntimeSecretVault
from .session import OnboardingSessionStore


class FolderSelector(Protocol):
    def select_folder(self) -> FolderSelectionResult:
        """打开系统目录选择器，返回 selected/cancelled/unavailable。"""


class SystemFolderSelector:
    def select_folder(self) -> FolderSelectionResult:
        if os.name != "nt":
            return FolderSelectionResult(
                status="unavailable",
                message="当前平台没有可用的系统目录选择器，请改用手工绝对路径",
            )
        try:
            import tkinter as tk
            from tkinter import filedialog

            root = tk.Tk()
            root.withdraw()
            try:
                selected = filedialog.askdirectory(
                    title="选择要检查的应用文件夹",
                    mustexist=True,
                )
            finally:
                root.destroy()
        except Exception as exc:
            raise JiejianError(
                ErrorCode.ONBOARDING_SELECTOR_UNAVAILABLE,
                "系统目录选择器当前不可用，请改用手工绝对路径",
            ) from exc
        if not selected:
            return FolderSelectionResult(status="cancelled")
        return FolderSelectionResult(status="selected", path=str(Path(selected)))


class OnboardingService:
    def __init__(
        self,
        folder_selector: FolderSelector | None = None,
        *,
        limits: DiscoveryLimits | None = None,
        var_dir: Path | None = None,
        vault: RuntimeSecretVault | None = None,
        projects=None,
        execution_requests=None,
        execution_submission=None,
        environment_provider=None,
    ) -> None:
        self.folder_selector = folder_selector or SystemFolderSelector()
        self.limits = limits or DiscoveryLimits()
        self._store = OnboardingSessionStore(var_dir) if var_dir is not None else None
        self._vault = vault or RuntimeSecretVault()
        self._projects = projects
        self._execution_requests = execution_requests
        self._execution_submission = execution_submission
        self._environment_provider = environment_provider

    def select_folder(self) -> FolderSelectionResult:
        return self.folder_selector.select_folder()

    def inspect(self, path: str) -> DiscoveryResult:
        return discover_folder(path, limits=self.limits)

    def create_session(self, path: str, project_name: str) -> OnboardingSessionView:
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
        bundle_path = self._write_bundle(session)
        registered = False
        try:
            record, bundle = self._projects.register(bundle_path / "project.yaml", revalidate=True)
            registered = True
            request = self._execution_requests.execution_request(record.project_id)
            names = required_secret_names(request)
            known = tuple(self._environment_provider(names).get(name, "") for name in names)
            now_us = time.time_ns() // 1_000
            result = self._execution_submission.submit(
                SubmitExecutionV1(
                    schema_version="1", request=request,
                    idempotency_key=f"onboarding:{session.session_id}:quick-check",
                    now_us=now_us, available_at_us=now_us,
                    run_id=f"run_{hashlib.sha256(session.session_id.encode()).hexdigest()[:32]}",
                    job_id=f"job_{hashlib.sha256((session.session_id + ":job").encode()).hexdigest()[:32]}",
                ),
                known_secrets=known,
            )
        except Exception:
            if not registered and not session.submitted_run_id:
                self._remove_bundle_if_safe(bundle_path)
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
        if self._store is None or self._projects is None:
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

    def _expected_documents(self, session: OnboardingSession) -> tuple[dict[str, dict], dict]:
        target, port = self._parse_loopback(session.target_address or "")
        owner_ref = session.primary_secret_ref
        comparison_ref = session.comparison_secret_ref
        documents = {
            "project.yaml": {"schema_version": "1", "project": {"id": session.project_id, "name": session.project_name}, "target": {"base_url": target, "allowed_origins": [target], "allowed_hosts": ["127.0.0.1"], "allowed_ports": [port], "allow_private_network": True, "follow_redirects": False, "timeout_seconds": 5, "max_requests": 8, "max_response_bytes": 262144}, "identities": [{"id": "primary", "role": session.primary_display_name, "secret_ref": owner_ref}, {"id": "comparison", "role": session.comparison_display_name, "secret_ref": comparison_ref}], "resources": [{"id": session.primary_resource_id, "owner_identity_id": "primary"}, {"id": session.comparison_resource_id, "owner_identity_id": "comparison"}], "flow": "flow.yaml", "contract": "contract.yaml", "observers": {"owner_api": False}, "mutation_seed": 7},
            "flow.yaml": {"schema_version": "1", "flow": {"id": f"{session.project_id}-flow", "owner_observer_path": "/owner/resources/{resource_id}", "reset_path": session.recovery_path, "steps": [{"id": "quick-read", "method": "GET", "path": session.read_only_path_template, "identity_id": "primary", "resource_id": session.primary_resource_id, "alternate_identity_id": "comparison", "alternate_resource_id": session.comparison_resource_id, "expected_statuses": [200]}]}},
            "contract.yaml": {"schema_version": "1", "contract": {"id": f"{session.project_id}-contract", "version": 1, "status": "ACTIVE", "rules": [{"id": "foreign-read", "kind": "foreign_read", "required_observers": ["http"], "severity": "high"}]}},
        }
        expected = {
            "project": (session.project_id, session.project_name),
            "target": (target, (target,), ("127.0.0.1",), (port,), True, False, 5, 8, 262144),
            "identities": (("primary", session.primary_display_name, owner_ref), ("comparison", session.comparison_display_name, comparison_ref)),
            "resources": ((session.primary_resource_id, "primary"), (session.comparison_resource_id, "comparison")),
            "observers": False,
            "mutation_seed": 7,
            "flow": (f"{session.project_id}-flow", "/owner/resources/{resource_id}", session.recovery_path, (("quick-read", "GET", session.read_only_path_template, "primary", session.primary_resource_id, "comparison", session.comparison_resource_id, (200,)),)),
            "contract": (f"{session.project_id}-contract", 1, "ACTIVE", (("foreign-read", "foreign_read", ("http",), "high"),)),
        }
        return documents, expected

    @staticmethod
    def _bundle_signature(bundle) -> dict:
        target = bundle.project.target
        return {
            "project": (bundle.project.id, bundle.project.name),
            "target": (target.base_url, target.allowed_origins, target.allowed_hosts, target.allowed_ports, target.allow_private_network, target.follow_redirects, target.timeout_seconds, target.max_requests, target.max_response_bytes),
            "identities": tuple((item.id, item.role, item.secret_ref) for item in bundle.project.identities),
            "resources": tuple((item.id, item.owner_identity_id) for item in bundle.project.resources),
            "observers": bundle.project.owner_observer_enabled,
            "mutation_seed": bundle.project.mutation_seed,
            "flow": (bundle.flow.id, bundle.flow.owner_observer_path, bundle.flow.reset_path, tuple((step.id, step.method, step.path, step.identity_id, step.resource_id, step.alternate_identity_id, step.alternate_resource_id, step.expected_statuses) for step in bundle.flow.steps)),
            "contract": (bundle.contract.id, bundle.contract.version, bundle.contract.status.value, tuple((rule.id, rule.kind.value, rule.required_observers, rule.severity) for rule in bundle.contract.rules)),
        }

    def _write_bundle(self, session: OnboardingSession) -> Path:
        documents, expected = self._expected_documents(session)
        root = (self._store.root.parent / session.session_id).resolve()
        if not root.is_relative_to(self._store.root.parent):
            raise JiejianError(ErrorCode.ONBOARDING_PATH_UNSAFE, "新手 bundle 路径不安全")
        bundle = root / "bundle"
        if bundle.is_dir():
            try:
                loaded = load_project_bundle(bundle / "project.yaml")
            except JiejianError:
                raise JiejianError(ErrorCode.ONBOARDING_BUNDLE_FAILED, "已有快速检查准备文件无效") from None
            if self._bundle_signature(loaded) != expected:
                raise JiejianError(ErrorCode.ONBOARDING_SESSION_CONFLICT, "快速检查准备文件与当前会话不一致，请新建会话")
            return bundle
        temp = root / f".bundle-{secrets.token_hex(8)}"
        temp.mkdir(parents=True, exist_ok=False)
        try:
            for name, document in documents.items():
                (temp / name).write_text(yaml.safe_dump(document, allow_unicode=True, sort_keys=False), encoding="utf-8")
            if self._bundle_signature(load_project_bundle(temp / "project.yaml")) != expected:
                raise JiejianError(ErrorCode.ONBOARDING_BUNDLE_FAILED, "快速检查准备内容与当前会话不一致")
            os.replace(temp, bundle)
            try:
                loaded = load_project_bundle(bundle / "project.yaml")
                if self._bundle_signature(loaded) != expected:
                    raise JiejianError(ErrorCode.ONBOARDING_BUNDLE_FAILED, "快速检查准备内容与当前会话不一致")
            except Exception:
                import shutil
                shutil.rmtree(bundle, ignore_errors=True)
                raise
            return bundle
        except JiejianError:
            self._remove_bundle_if_safe(temp)
            raise
        except Exception as exc:
            self._remove_bundle_if_safe(temp)
            raise JiejianError(ErrorCode.ONBOARDING_BUNDLE_FAILED, "快速检查准备失败") from exc

    @staticmethod
    def _remove_bundle_if_safe(path: Path) -> None:
        if path.name.startswith(".bundle-") or path.name == "bundle":
            import shutil
            shutil.rmtree(path, ignore_errors=True)

    def _view(self, session: OnboardingSession) -> OnboardingSessionView:
        credentials = self._credential_status(session)
        return OnboardingSessionView(
            **session.model_dump(exclude={"primary_secret_ref", "comparison_secret_ref", "project_id", "submitted_run_id", "submitted_job_id"}),
            primary_configured=credentials.primary_configured,
            comparison_configured=credentials.comparison_configured,
            missing_items=self._missing(session) + (("测试凭据",) if not all((credentials.primary_configured, credentials.comparison_configured)) else ()),
        )
