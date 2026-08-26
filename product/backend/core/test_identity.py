# =============================================================================
# 测试身份领域模型
#
# 定位
#   已确认角色、受限登录状态元数据与后续安全配置编译之间的项目级事实。
#
# 职责
#   表达测试账号归属｜约束 Cookie/Bearer 非秘密元数据｜维护准备时间与秘密引用。
#
# 边界
#   不等同 Contract Subject、WebExecutionIdentity 或运行时 Cookie Jar；不包含秘密正文。
#
# 调用链
#   TestIdentityService ↔ TestIdentity ↔ storage / SecretStore
# =============================================================================

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from product.backend.core.identifiers import (
    PROJECT_ID_PATTERN,
    SHA256_PATTERN,
    TEST_IDENTITY_ID_PATTERN,
)


_ROLE_CANDIDATE_ID_PATTERN = r"^role_[0-9a-f]{32}$"
_SECRET_REF_PATTERN = (
    r"^cred:jiejian/test-identity/"
    r"[a-z][a-z0-9_-]{0,63}/tid_[0-9a-f]{32}/"
    r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$"
)


class TestIdentityModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
    )


class TestIdentityAuthMethod(StrEnum):
    COOKIE_SESSION = "COOKIE_SESSION"
    BEARER = "BEARER"


class TestIdentityCookie(TestIdentityModel):
    name: str = Field(min_length=1, max_length=256)
    domain: str = Field(min_length=1, max_length=253)
    path: str = Field(min_length=1, max_length=2048)
    secure: bool
    http_only: bool
    same_site: str = Field(pattern=r"^(STRICT|LAX|NONE)$")
    expires_at_us: int | None = Field(default=None, ge=0)
    value_secret_ref: str = Field(pattern=_SECRET_REF_PATTERN, max_length=512)

    @model_validator(mode="after")
    def validate_cookie_metadata(self) -> TestIdentityCookie:
        if self.name != self.name.strip() or any(ord(char) < 33 for char in self.name):
            raise ValueError("cookie name must be trimmed and printable")
        if not self.path.startswith("/"):
            raise ValueError("cookie path must be absolute")
        return self


class TestIdentity(TestIdentityModel):
    identity_id: str = Field(pattern=TEST_IDENTITY_ID_PATTERN)
    project_id: str = Field(pattern=PROJECT_ID_PATTERN)
    role_candidate_id: str = Field(pattern=_ROLE_CANDIDATE_ID_PATTERN)
    role_canonical_key: str = Field(min_length=1, max_length=128)
    role_display_name: str = Field(min_length=1, max_length=128)
    label: str = Field(min_length=1, max_length=128)
    confirmed_endpoint: str = Field(min_length=1, max_length=2048)
    endpoint_source_fingerprint: str = Field(pattern=SHA256_PATTERN)
    understanding_revision: int = Field(ge=0, le=1_000_000)
    auth_method: TestIdentityAuthMethod | None = None
    cookies: tuple[TestIdentityCookie, ...] = Field(default=(), max_length=32)
    bearer_secret_ref: str | None = Field(
        default=None,
        pattern=_SECRET_REF_PATTERN,
        max_length=512,
    )
    prepared_at_us: int | None = Field(default=None, ge=0)
    refreshed_at_us: int | None = Field(default=None, ge=0)
    created_at_us: int = Field(ge=0)
    updated_at_us: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_login_state(self) -> TestIdentity:
        if self.updated_at_us < self.created_at_us:
            raise ValueError("test identity update time precedes creation")
        prepared = self.prepared_at_us is not None and self.refreshed_at_us is not None
        if self.auth_method is None:
            if prepared or self.cookies or self.bearer_secret_ref is not None:
                raise ValueError("unprepared test identity contains login state")
            return self
        if not prepared:
            raise ValueError("prepared test identity requires preparation timestamps")
        assert self.prepared_at_us is not None
        assert self.refreshed_at_us is not None
        if not self.created_at_us <= self.prepared_at_us <= self.refreshed_at_us:
            raise ValueError("test identity preparation timestamps are invalid")
        if self.updated_at_us < self.refreshed_at_us:
            raise ValueError("test identity update precedes refresh")
        if self.auth_method is TestIdentityAuthMethod.COOKIE_SESSION:
            if not self.cookies or self.bearer_secret_ref is not None:
                raise ValueError("cookie session login state is invalid")
            cookie_keys = {(item.name, item.domain, item.path) for item in self.cookies}
            if len(cookie_keys) != len(self.cookies):
                raise ValueError("cookie session contains duplicate cookie metadata")
        elif self.cookies or self.bearer_secret_ref is None:
            raise ValueError("bearer login state is invalid")
        expected_prefix = (
            f"cred:jiejian/test-identity/{self.project_id}/{self.identity_id}/"
        )
        if (
            any(not ref.startswith(expected_prefix) for ref in self.secret_refs)
            or len(set(self.secret_refs)) != len(self.secret_refs)
        ):
            raise ValueError("test identity secret_ref crosses identity namespace")
        return self

    @property
    def secret_refs(self) -> tuple[str, ...]:
        refs = tuple(cookie.value_secret_ref for cookie in self.cookies)
        return refs + ((self.bearer_secret_ref,) if self.bearer_secret_ref else ())
