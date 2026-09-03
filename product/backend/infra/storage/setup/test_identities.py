# =============================================================================
# 测试准备：测试身份持久化
#
# 定位
#   TestIdentity 非秘密元数据与 SQLite 关系记录之间的 Repository 边界。
#
# 职责
#   持久化账号与稳定 Actor revision 关联｜保存 Cookie 元数据与秘密引用｜精确替换和删除。
#
# 边界
#   绝不保存 Cookie/Token 正文；秘密删除由应用服务先行完成，Repository 不访问 SecretStore。
#
# 调用链
#   TestIdentityService → TestIdentityRepository → SQLite
# =============================================================================

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    delete,
    select,
)
from sqlalchemy.orm import Mapped, Session, mapped_column

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.test_identity import (
    TestIdentity,
    TestIdentityAuthMethod,
    TestIdentityCookie,
)
from product.backend.infra.storage.base import (
    Base,
    _flush,
    _scalar,
    _scalars,
    ensure_storage_payload_safe,
)


class TestIdentityRow(Base):
    __tablename__ = "test_identities"
    __table_args__ = (
        ForeignKeyConstraint(
            ["actor_id", "actor_revision"],
            ["business_actor_revisions.actor_id", "business_actor_revisions.revision"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "length(identity_id) = 36 AND identity_id GLOB 'tid_[0-9a-f]*'",
            name="test_identity_id_format",
        ),
        CheckConstraint(
            "auth_method IS NULL OR auth_method IN ('COOKIE_SESSION', 'BEARER')",
            name="test_identity_auth_method_value",
        ),
        CheckConstraint(
            "created_at_us >= 0 AND updated_at_us >= created_at_us",
            name="test_identity_time_order",
        ),
        Index("ix_test_identities_project_updated", "project_id", "updated_at_us"),
    )

    identity_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("projects.project_id"), nullable=False
    )
    actor_id: Mapped[str] = mapped_column(String(36), nullable=False)
    actor_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str] = mapped_column(String(128), nullable=False)
    auth_method: Mapped[str | None] = mapped_column(String(32), nullable=True)
    bearer_secret_ref: Mapped[str | None] = mapped_column(String(512), nullable=True)
    prepared_at_us: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    refreshed_at_us: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at_us: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_at_us: Mapped[int] = mapped_column(BigInteger, nullable=False)


class TestIdentityCookieRow(Base):
    __tablename__ = "test_identity_cookies"
    __table_args__ = (
        UniqueConstraint(
            "identity_id", "name", "domain", "path", name="uq_test_identity_cookie"
        ),
        CheckConstraint("ordinal BETWEEN 0 AND 31", name="test_identity_cookie_ordinal"),
    )

    identity_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("test_identities.identity_id", ondelete="CASCADE"),
        primary_key=True,
    )
    ordinal: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    domain: Mapped[str] = mapped_column(String(253), nullable=False)
    path: Mapped[str] = mapped_column(String(2048), nullable=False)
    secure: Mapped[bool] = mapped_column(Boolean, nullable=False)
    http_only: Mapped[bool] = mapped_column(Boolean, nullable=False)
    same_site: Mapped[str] = mapped_column(String(8), nullable=False)
    expires_at_us: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    value_secret_ref: Mapped[str] = mapped_column(String(512), nullable=False)


class TestIdentityRepository:
    def __init__(self, session: Session, known_secrets: Sequence[str]) -> None:
        self._session = session
        self._known_secrets = known_secrets

    def add(self, record: TestIdentity) -> None:
        values = self._row_values(record)
        ensure_storage_payload_safe(values, self._known_secrets)
        self._session.add(TestIdentityRow(**values))
        self._replace_cookies(record)
        _flush(self._session)

    def get(self, identity_id: str) -> TestIdentity | None:
        row = _scalar(
            self._session,
            select(TestIdentityRow).where(TestIdentityRow.identity_id == identity_id),
        )
        return None if row is None else self._record(row)

    def list_for_project(self, project_id: str) -> tuple[TestIdentity, ...]:
        rows = _scalars(
            self._session,
            select(TestIdentityRow)
            .where(TestIdentityRow.project_id == project_id)
            .order_by(TestIdentityRow.created_at_us, TestIdentityRow.identity_id),
        )
        return tuple(self._record(row) for row in rows)

    def replace(self, record: TestIdentity) -> None:
        row = _scalar(
            self._session,
            select(TestIdentityRow).where(
                TestIdentityRow.identity_id == record.identity_id
            ),
        )
        if row is None:
            raise JiejianError(ErrorCode.TEST_IDENTITY_NOT_FOUND, "测试账号不存在")
        if row.project_id != record.project_id:
            raise JiejianError(ErrorCode.TEST_IDENTITY_CONFLICT, "测试账号与项目不匹配")
        values = self._row_values(record)
        ensure_storage_payload_safe(values, self._known_secrets)
        for key, value in values.items():
            setattr(row, key, value)
        self._session.execute(
            delete(TestIdentityCookieRow).where(
                TestIdentityCookieRow.identity_id == record.identity_id
            )
        )
        self._replace_cookies(record)
        _flush(self._session)

    def delete(self, identity_id: str) -> None:
        row = _scalar(
            self._session,
            select(TestIdentityRow).where(TestIdentityRow.identity_id == identity_id),
        )
        if row is None:
            raise JiejianError(ErrorCode.TEST_IDENTITY_NOT_FOUND, "测试账号不存在")
        self._session.delete(row)
        _flush(self._session)

    @staticmethod
    def _row_values(record: TestIdentity) -> dict[str, object]:
        return {
            "identity_id": record.identity_id,
            "project_id": record.project_id,
            "actor_id": record.actor_id,
            "actor_revision": record.actor_revision,
            "label": record.label,
            "auth_method": record.auth_method.value if record.auth_method else None,
            "bearer_secret_ref": record.bearer_secret_ref,
            "prepared_at_us": record.prepared_at_us,
            "refreshed_at_us": record.refreshed_at_us,
            "created_at_us": record.created_at_us,
            "updated_at_us": record.updated_at_us,
        }

    def _replace_cookies(self, record: TestIdentity) -> None:
        for ordinal, cookie in enumerate(record.cookies):
            values = cookie.model_dump(mode="json")
            ensure_storage_payload_safe(values, self._known_secrets)
            self._session.add(
                TestIdentityCookieRow(
                    identity_id=record.identity_id,
                    ordinal=ordinal,
                    **values,
                )
            )

    def _record(self, row: TestIdentityRow) -> TestIdentity:
        cookie_rows = _scalars(
            self._session,
            select(TestIdentityCookieRow)
            .where(TestIdentityCookieRow.identity_id == row.identity_id)
            .order_by(TestIdentityCookieRow.ordinal),
        )
        return TestIdentity.model_validate(
            {
                "identity_id": row.identity_id,
                "project_id": row.project_id,
                "actor_id": row.actor_id,
                "actor_revision": row.actor_revision,
                "label": row.label,
                "auth_method": (
                    TestIdentityAuthMethod(row.auth_method)
                    if row.auth_method is not None
                    else None
                ),
                "cookies": tuple(
                    TestIdentityCookie(
                        name=item.name,
                        domain=item.domain,
                        path=item.path,
                        secure=item.secure,
                        http_only=item.http_only,
                        same_site=item.same_site,
                        expires_at_us=item.expires_at_us,
                        value_secret_ref=item.value_secret_ref,
                    )
                    for item in cookie_rows
                ),
                "bearer_secret_ref": row.bearer_secret_ref,
                "prepared_at_us": row.prepared_at_us,
                "refreshed_at_us": row.refreshed_at_us,
                "created_at_us": row.created_at_us,
                "updated_at_us": row.updated_at_us,
            }
        )
