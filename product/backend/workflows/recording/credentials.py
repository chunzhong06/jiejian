# =============================================================================
# 录制身份运行时投影
#
# 定位
#   TestIdentity 长期秘密引用与单次 Recording Runner 环境之间的最小桥接边界。
#
# 职责
#   校验测试身份可用性｜读取精确秘密引用｜生成短期环境引用和非秘密 Cookie 元数据。
#
# 边界
#   明文只进入进程内 RuntimeSecretVault；请求快照、数据库、日志和 API 均不得携带明文。
# =============================================================================

from __future__ import annotations

from collections.abc import Mapping, Sequence
from threading import RLock

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.test_identity import TestIdentityAuthMethod
from product.backend.infra.secrets import SecretStore
from product.backend.workflows.test_identities import TestIdentityService, TestIdentityStatus
from product.protocols import (
    RecordingAuthMethod,
    RecordingCookieRef,
    RecordingSessionRef,
)


class RuntimeSecretVault:
    """录制会话内的短期秘密容器；不序列化、不落盘且 repr 只暴露不透明标记。"""

    def __init__(self) -> None:
        self._values: dict[str, dict[str, str]] = {}
        self._lock = RLock()

    def put(self, session_id: str, values: Mapping[str, str]) -> None:
        with self._lock:
            self._values[session_id] = {
                name: value for name, value in values.items() if value
            }

    def configured(self, session_id: str, names: Sequence[str]) -> tuple[bool, ...]:
        with self._lock:
            values = self._values.get(session_id, {})
            return tuple(bool(values.get(name)) for name in names)

    def resolve(self, names: Sequence[str]) -> dict[str, str]:
        with self._lock:
            result: dict[str, str] = {}
            for values in self._values.values():
                for name in names:
                    if name in values:
                        result[name] = values[name]
            return result

    def clear_session(self, session_id: str) -> None:
        with self._lock:
            self._values.pop(session_id, None)

    def clear(self) -> None:
        with self._lock:
            self._values.clear()

    def model_dump(self) -> dict[str, int]:
        with self._lock:
            return {"session_count": len(self._values)}

    def __repr__(self) -> str:
        return "RuntimeSecretVault(<opaque>)"


class RecordingCredentialProvider:
    """把一个已准备测试身份投影为一次录制专用的短期环境。"""

    def __init__(
        self,
        identities: TestIdentityService,
        secret_store: SecretStore,
        vault: RuntimeSecretVault,
    ) -> None:
        self._identities = identities
        self._secret_store = secret_store
        self._vault = vault

    def prepare(
        self,
        *,
        project_id: str,
        test_identity_id: str,
        recording_id: str,
        session_ref: str,
        now_us: int,
        expires_at_us: int,
    ) -> RecordingSessionRef:
        view = self._identities.get(test_identity_id)
        record = self._identities.get_record(test_identity_id)
        if view.project_id != project_id or record.project_id != project_id:
            raise JiejianError(ErrorCode.TEST_IDENTITY_NOT_READY, "测试账号不属于当前项目")
        if view.status is not TestIdentityStatus.PREPARED or record.auth_method is None:
            raise JiejianError(
                ErrorCode.TEST_IDENTITY_NOT_READY,
                "测试账号尚未准备完成，或绑定的角色和运行地址已经变化",
            )
        values: dict[str, str] = {}
        cookies: list[RecordingCookieRef] = []
        bearer_ref: str | None = None
        try:
            if record.auth_method is TestIdentityAuthMethod.COOKIE_SESSION:
                for index, cookie in enumerate(record.cookies):
                    if cookie.expires_at_us is not None and cookie.expires_at_us <= now_us:
                        raise JiejianError(
                            ErrorCode.TEST_IDENTITY_NOT_READY,
                            "测试账号登录状态已经过期，请重新准备",
                        )
                    name = self._environment_name(recording_id, f"COOKIE_{index:02d}")
                    values[name] = self._read(cookie.value_secret_ref)
                    cookies.append(
                        RecordingCookieRef(
                            name=cookie.name,
                            domain=cookie.domain,
                            path=cookie.path,
                            secure=cookie.secure,
                            http_only=cookie.http_only,
                            same_site=cookie.same_site,
                            expires_at_us=cookie.expires_at_us,
                            value_ref=f"env:{name}",
                        )
                    )
                auth_method = RecordingAuthMethod.COOKIE_SESSION
            else:
                if record.bearer_secret_ref is None:
                    raise JiejianError(ErrorCode.TEST_IDENTITY_NOT_READY, "测试账号登录状态不完整")
                name = self._environment_name(recording_id, "BEARER")
                values[name] = self._read(record.bearer_secret_ref)
                bearer_ref = f"env:{name}"
                auth_method = RecordingAuthMethod.BEARER
            self._vault.put(recording_id, values)
            return RecordingSessionRef(
                test_identity_id=test_identity_id,
                session_ref=session_ref,
                auth_method=auth_method,
                cookies=tuple(cookies),
                bearer_ref=bearer_ref,
                expires_at_us=expires_at_us,
            )
        except Exception:
            self._vault.clear_session(recording_id)
            raise

    def clear(self, recording_id: str) -> None:
        self._vault.clear_session(recording_id)

    def _read(self, secret_ref: str) -> str:
        try:
            value = self._secret_store.read(secret_ref)
        except (JiejianError, OSError, RuntimeError, ValueError):
            raise JiejianError(
                ErrorCode.TEST_IDENTITY_NOT_READY,
                "无法读取测试账号登录状态，请重新准备",
            ) from None
        if not value:
            raise JiejianError(ErrorCode.TEST_IDENTITY_NOT_READY, "测试账号登录状态不完整")
        return value

    @staticmethod
    def _environment_name(recording_id: str, suffix: str) -> str:
        token = recording_id.removeprefix("rec_").upper()
        return f"JIEJIAN_RECORDING_{token}_{suffix}"
