# =============================================================================
# 脱敏 SQL Trace 辅助适配
#
# 定位
#   把灰盒 SQL 语句投影为不含参数值的效果、漂移和 Observer 配置建议。
#
# 职责
#   有界解析语句类型与表名｜删除 literal｜生成稳定 Advisory
#
# 边界
#   不发布 ObservationFact/SecurityEffectFact，不参与 BLOCK/PASS，也不保存原 SQL。
# =============================================================================

from __future__ import annotations

import re
from collections.abc import Sequence

from product.backend.core.verification.permissions import (
    SecurityEffectKind,
    canonical_sha256,
)
from product.backend.core.verification.sql_trace import (
    SqlStatementKind,
    SqlTraceAdvisory,
    SqlTraceEvent,
)


_STRING_LITERAL = re.compile(r"'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"")
_NUMBER_LITERAL = re.compile(r"(?<![A-Za-z0-9_])[-+]?\d+(?:\.\d+)?(?![A-Za-z0-9_])")
_SPACE = re.compile(r"\s+")
_RELATION = {
    SqlStatementKind.SELECT: re.compile(r"\bFROM\s+([A-Za-z_][A-Za-z0-9_.]*)", re.I),
    SqlStatementKind.INSERT: re.compile(r"\bINTO\s+([A-Za-z_][A-Za-z0-9_.]*)", re.I),
    SqlStatementKind.UPDATE: re.compile(r"\bUPDATE\s+([A-Za-z_][A-Za-z0-9_.]*)", re.I),
    SqlStatementKind.DELETE: re.compile(r"\bFROM\s+([A-Za-z_][A-Za-z0-9_.]*)", re.I),
}


def build_sql_trace_advisory(
    statements: Sequence[str],
    *,
    max_statements: int = 4096,
    max_statement_length: int = 65_536,
) -> SqlTraceAdvisory:
    """只保留规范形状 hash 与安全表名，不让 SQL 实现事实直接成为结论。"""

    if len(statements) > max_statements:
        raise ValueError("SQL trace exceeds its statement budget")
    events: list[SqlTraceEvent] = []
    for sequence, statement in enumerate(statements, start=1):
        if not isinstance(statement, str) or len(statement) > max_statement_length:
            raise ValueError("SQL trace statement is invalid or oversized")
        normalized = _normalize_statement(statement)
        keyword = normalized.split(" ", 1)[0].upper() if normalized else ""
        kind = SqlStatementKind(keyword) if keyword in {item.value for item in SqlStatementKind if item is not SqlStatementKind.OTHER} else SqlStatementKind.OTHER
        relation_match = _RELATION.get(kind).search(normalized) if kind in _RELATION else None
        events.append(
            SqlTraceEvent(
                sequence=sequence,
                statement_kind=kind,
                relation_name=relation_match.group(1) if relation_match is not None else None,
                normalized_statement_fingerprint=canonical_sha256(normalized),
            )
        )
    relations = tuple(sorted({item.relation_name for item in events if item.relation_name is not None}))
    effect_suggestions: list[SecurityEffectKind] = []
    if any(item.statement_kind is SqlStatementKind.INSERT for item in events):
        effect_suggestions.append(SecurityEffectKind.OBJECT_CREATION)
    if any(item.statement_kind in {SqlStatementKind.UPDATE, SqlStatementKind.DELETE} for item in events):
        effect_suggestions.append(SecurityEffectKind.STATE_MUTATION)
    observer_suggestions = ("read_only_database",) if relations else ()
    payload = {
        "schema_version": "1",
        "events": tuple(events),
        "effect_suggestions": tuple(effect_suggestions),
        "contract_drift_subjects": relations,
        "observer_suggestions": observer_suggestions,
        "verdict_authority": False,
    }
    return SqlTraceAdvisory(
        **payload,
        trace_fingerprint=canonical_sha256(payload),
    )


def _normalize_statement(statement: str) -> str:
    without_strings = _STRING_LITERAL.sub("?", statement)
    without_numbers = _NUMBER_LITERAL.sub("?", without_strings)
    return _SPACE.sub(" ", without_numbers).strip().rstrip(";")
