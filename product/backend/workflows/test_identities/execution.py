# =============================================================================
# 测试身份执行时凭据投影
#
# 定位
#   TestIdentity 长期 secret_ref 与 Generated WebExecutionProfile 环境引用之间的桥接。
#
# 职责
#   生成稳定无秘密身份绑定｜按提交所需名称读取最小秘密集合｜拒绝失效身份。
#
# 边界
#   明文只作为一次环境映射返回；不写 Profile、数据库、日志或 API 响应。
#
# 调用链
#   SecuritySetupCompiler / ExecutionWorkflow → provider → TestIdentity / SecretStore
# =============================================================================

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.test_identity import TestIdentity, TestIdentityAuthMethod
from product.backend.infra.secrets import SecretStore
from product.backend.workflows.test_identities.service import (
    TestIdentityService,
    TestIdentityStatus,
)
from product.protocols import (
    BearerIdentityBinding,
    PreparedCookieCredential,
    PreparedCookieSessionIdentityBinding,
    WebExecutionIdentity,
)


_ENVIRONMENT_NAME = re.compile(
    r"^JIEJIAN_TEST_IDENTITY_([0-9A-F]{32})_(BEARER|COOKIE_([0-9]{2}))$"
)


class TestIdentityExecutionCredentials:
    """只为当前有效 TestIdentity 解析编译器声明的固定环境名。"""

    def __init__(
        self,
        identities: TestIdentityService,
        secret_store: SecretStore,
    ) -> None:
        self._identities = identities
        self._secret_store = secret_store

    def profile_identity(self, record: TestIdentity) -> WebExecutionIdentity:
        view = self._identities.get(record.identity_id)
        if view.status is not TestIdentityStatus.PREPARED or record.auth_method is None:
            raise JiejianError(
                ErrorCode.TEST_IDENTITY_NOT_READY,
                "测试账号尚未准备完成，或绑定的角色和运行地址已经变化",
            )
        if record.auth_method is TestIdentityAuthMethod.BEARER:
            binding = BearerIdentityBinding(
                secret_ref=f"env:{self._name(record.identity_id, 'BEARER')}"
            )
        else:
            binding = PreparedCookieSessionIdentityBinding(
                cookies=tuple(
                    PreparedCookieCredential(
                        name=cookie.name,
                        domain=cookie.domain,
                        path=cookie.path,
                        secure=cookie.secure,
                        value_ref=(
                            f"env:{self._name(record.identity_id, f'COOKIE_{index:02d}')}"
                        ),
                    )
                    for index, cookie in enumerate(record.cookies)
                )
            )
        role_id = f"role-{record.role_candidate_id.removeprefix('role_')[:24]}"
        return WebExecutionIdentity(
            identity_id=record.identity_id,
            role=role_id,
            label=record.label,
            binding=binding,
        )

    def resolve(self, names: Sequence[str]) -> Mapping[str, str]:
        values: dict[str, str] = {}
        records: dict[str, TestIdentity] = {}
        for name in names:
            match = _ENVIRONMENT_NAME.fullmatch(name)
            if match is None:
                continue
            identity_id = f"tid_{match.group(1).lower()}"
            record = records.get(identity_id)
            if record is None:
                view = self._identities.get(identity_id)
                if view.status is not TestIdentityStatus.PREPARED:
                    raise JiejianError(
                        ErrorCode.TEST_IDENTITY_NOT_READY,
                        "执行所需测试账号已经失效，请重新准备",
                    )
                record = self._identities.get_record(identity_id)
                records[identity_id] = record
            suffix = match.group(2)
            if suffix == "BEARER":
                secret_ref = record.bearer_secret_ref
            else:
                index = int(match.group(3) or "-1")
                secret_ref = (
                    record.cookies[index].value_secret_ref
                    if 0 <= index < len(record.cookies)
                    else None
                )
            if secret_ref is None:
                raise JiejianError(
                    ErrorCode.TEST_IDENTITY_NOT_READY,
                    "执行身份与所需凭据类型不一致，请重新生成检查配置",
                )
            try:
                value = self._secret_store.read(secret_ref)
            except (JiejianError, OSError, RuntimeError, ValueError):
                raise JiejianError(
                    ErrorCode.TEST_IDENTITY_NOT_READY,
                    "无法读取测试账号登录状态，请重新准备",
                ) from None
            if not value:
                raise JiejianError(
                    ErrorCode.TEST_IDENTITY_NOT_READY,
                    "测试账号登录状态不完整，请重新准备",
                )
            values[name] = value
        return values

    @staticmethod
    def _name(identity_id: str, suffix: str) -> str:
        token = identity_id.removeprefix("tid_").upper()
        return f"JIEJIAN_TEST_IDENTITY_{token}_{suffix}"


__all__ = ["TestIdentityExecutionCredentials"]
