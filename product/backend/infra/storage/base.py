# Storage 的 SQLAlchemy typed declarative 基类。

from __future__ import annotations

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)

# 共享持久化记录与安全辅助边界。

# =============================================================================
# Repository 共享持久化边界
#
# 定位
#   具体聚合仓储共用的 payload 安全与 SQLAlchemy 错误适配层
#
# 职责
#   拒绝 secret 持久化｜生成规范 JSON｜统一 flush 与查询错误映射
#
# 调用链
#   Aggregate repositories → repository base helpers → SQLAlchemy Session
# =============================================================================

import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict
from sqlalchemy import Select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from product.backend.core.errors import ErrorCode, JiejianError

_METADATA_KEY = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_SENSITIVE_METADATA_KEY = re.compile(
    r"(?:authorization|cookie|credential|password|passwd|secret|token|api[_-]?key)",
    re.IGNORECASE,
)
_INLINE_SECRET = re.compile(
    r"(?:\bBearer\s+\S+|\b(?:authorization|cookie|credential|password|passwd|"
    r"secret|token|api[_-]?key)\s*[:=]\s*\S+)",
    re.IGNORECASE,
)

MetadataValue = str | int | bool | None

class StorageRecord(BaseModel):
    """不向调用方泄露 ORM 对象的冻结数据结构。"""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
    )

def ensure_storage_payload_safe(value: Any, known_secrets: Sequence[str]) -> None:
    """在进入数据库前拒绝内联凭据和本次尝试的已知秘密。"""
    normalized = tuple(secret for secret in known_secrets if secret)
    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, Mapping):
            pending.extend(item.keys())
            pending.extend(item.values())
        elif isinstance(item, (list, tuple)):
            pending.extend(item)
        elif isinstance(item, str) and (
            _INLINE_SECRET.search(item) is not None
            or any(secret in item for secret in normalized)
        ):
            raise JiejianError(ErrorCode.STORAGE_SECRET, "持久化数据包含敏感内容")


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,

            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError):
        raise JiejianError(ErrorCode.STORAGE_CONSTRAINT, "持久化 JSON 无效") from None


def _flush(session: Session) -> None:
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        raise JiejianError(
            ErrorCode.STORAGE_CONSTRAINT,
            "数据库约束拒绝写入",
        ) from None
    except SQLAlchemyError:
        session.rollback()
        raise JiejianError(ErrorCode.STORAGE_FAILURE, "数据库操作失败") from None
def _scalar(session: Session, statement: Select[Any]) -> Any | None:
    try:
        return session.execute(statement).scalar_one_or_none()
    except SQLAlchemyError:
        session.rollback()
        raise JiejianError(ErrorCode.STORAGE_FAILURE, "数据库操作失败") from None

def _scalars(session: Session, statement: Select[Any]) -> tuple[Any, ...]:
    try:
        return tuple(session.execute(statement).scalars())
    except SQLAlchemyError:
        session.rollback()
        raise JiejianError(ErrorCode.STORAGE_FAILURE, "数据库操作失败") from None
