# 测试身份准备进程协议
# 冻结端点与账号引用、返回 Cookie/Bearer 元数据和 SecretStore 引用、限制消息大小。
# 不承载密码、Cookie 值、Token 正文、浏览器历史或完整 storage_state。

from __future__ import annotations

from product.protocols.codec import decode_json
import json
from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from product.backend.domain.identifiers import (
    PROJECT_ID_PATTERN,
    TEST_IDENTITY_ID_PATTERN,
)
from product.backend.domain.identities.models import TestIdentityAuthMethod
from product.protocols.runner.execution import ProtocolModel
from product.protocols.web.target import WebTargetScope


IDENTITY_PREPARATION_REQUEST_MAX_BYTES = 16_384
IDENTITY_PREPARATION_RESULT_MAX_BYTES = 65_536
_PREPARATION_ID_PATTERN = r"^prep_[0-9a-f]{32}$"
_SECRET_REF_PATTERN = (
    r"^cred:jiejian/test-identity/"
    r"[a-z][a-z0-9_-]{0,63}/tid_[0-9a-f]{32}/"
    r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$"
)


class IdentityPreparationResultType(StrEnum):
    PREPARED = "PREPARED"
    UNSUPPORTED = "UNSUPPORTED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


class IdentityPreparationRequest(ProtocolModel):
    schema_version: Literal["1"]
    preparation_id: str = Field(pattern=_PREPARATION_ID_PATTERN)
    project_id: str = Field(pattern=PROJECT_ID_PATTERN)
    identity_id: str = Field(pattern=TEST_IDENTITY_ID_PATTERN)
    target_scope: WebTargetScope
    timeout_us: int = Field(default=900_000_000, ge=1_000_000, le=3_600_000_000)


class PreparedCookieRef(ProtocolModel):
    name: str = Field(min_length=1, max_length=256)
    domain: str = Field(min_length=1, max_length=253)
    path: str = Field(min_length=1, max_length=2048)
    secure: bool
    http_only: bool
    same_site: str = Field(pattern=r"^(STRICT|LAX|NONE)$")
    expires_at_us: int | None = Field(default=None, ge=0)
    value_secret_ref: str = Field(pattern=_SECRET_REF_PATTERN, max_length=512)


class IdentityPreparationResult(ProtocolModel):
    # PREPARED 仅说明采集进程形成了受控引用；应用层仍须核对账号、来源和执行权后采用。
    schema_version: Literal["1"]
    preparation_id: str = Field(pattern=_PREPARATION_ID_PATTERN)
    project_id: str = Field(pattern=PROJECT_ID_PATTERN)
    identity_id: str = Field(pattern=TEST_IDENTITY_ID_PATTERN)
    result_type: IdentityPreparationResultType
    auth_method: TestIdentityAuthMethod | None = None
    cookies: tuple[PreparedCookieRef, ...] = Field(default=(), max_length=32)
    bearer_secret_ref: str | None = Field(
        default=None,
        pattern=_SECRET_REF_PATTERN,
        max_length=512,
    )
    prepared_at_us: int | None = Field(default=None, ge=0)
    error_code: str | None = Field(default=None, min_length=1, max_length=64)

    @model_validator(mode="after")
    def validate_result_matrix(self) -> IdentityPreparationResult:
        # 成功结果只能选择 Cookie 或 Bearer 一种表示，失败结果不允许夹带可采用的认证状态。
        if self.result_type is IdentityPreparationResultType.PREPARED:
            if self.auth_method is None or self.prepared_at_us is None or self.error_code:
                raise ValueError("prepared result is incomplete")
            if self.auth_method is TestIdentityAuthMethod.COOKIE_SESSION:
                if not self.cookies or self.bearer_secret_ref is not None:
                    raise ValueError("prepared cookie result is invalid")
            elif self.cookies or self.bearer_secret_ref is None:
                raise ValueError("prepared bearer result is invalid")
            refs = tuple(cookie.value_secret_ref for cookie in self.cookies)
            if self.bearer_secret_ref:
                refs += (self.bearer_secret_ref,)
            expected_prefix = (
                f"cred:jiejian/test-identity/{self.project_id}/{self.identity_id}/"
            )
            if (
                any(not item.startswith(expected_prefix) for item in refs)
                or len(set(refs)) != len(refs)
            ):
                raise ValueError("prepared result secret refs do not match identity")
        elif (
            self.auth_method is not None
            or self.cookies
            or self.bearer_secret_ref is not None
            or self.prepared_at_us is not None
        ):
            raise ValueError("non-prepared result contains login state")
        if self.result_type is IdentityPreparationResultType.FAILED:
            if self.error_code is None:
                raise ValueError("failed result requires an error code")
        elif self.error_code is not None:
            raise ValueError("only failed result may contain an error code")
        return self


def canonical_identity_preparation_json_bytes(
    document: IdentityPreparationRequest | IdentityPreparationResult,
) -> bytes:
    payload = document.model_dump(mode="json")
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    limit = (
        IDENTITY_PREPARATION_REQUEST_MAX_BYTES
        if isinstance(document, IdentityPreparationRequest)
        else IDENTITY_PREPARATION_RESULT_MAX_BYTES
    )
    if len(encoded) > limit:
        raise ValueError("identity preparation document exceeds byte budget")
    return encoded


def parse_identity_preparation_request(raw: bytes) -> IdentityPreparationRequest:
    decode_json(raw, limit=IDENTITY_PREPARATION_REQUEST_MAX_BYTES)
    return IdentityPreparationRequest.model_validate_json(raw, strict=True)


def parse_identity_preparation_result(raw: bytes) -> IdentityPreparationResult:
    decode_json(raw, limit=IDENTITY_PREPARATION_RESULT_MAX_BYTES)
    return IdentityPreparationResult.model_validate_json(raw, strict=True)
