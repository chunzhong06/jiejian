# 比较当前 SQLite 表、约束和索引，忽略仅记录修订身份的 Alembic 表。
from __future__ import annotations

import json
import re
import sqlite3
from product.backend.domain.errors import ErrorCode, JiejianError

def sqlite_schema_signature(
    connection: sqlite3.Connection,
) -> tuple[tuple[str, str, str, str], ...]:
    return tuple(
        sorted(
            (
                str(row[0]),
                str(row[1]),
                str(row[2]),
                normalize_table_sql(str(row[3])) if row[0] == "table" else normalize_sql(str(row[3])),
            )
            for row in connection.execute(
                "SELECT type, name, tbl_name, sql FROM sqlite_master "
                "WHERE type IN ('table', 'index', 'trigger', 'view') "
                "AND name NOT LIKE 'sqlite_%' AND name != 'alembic_version' AND sql IS NOT NULL"
            )
        )
    )


def normalize_table_sql(statement: str) -> str:
    """只消除具名表约束排列差异；列序、约束正文及表选项仍逐项比较。"""

    start = statement.find("(")
    if start < 0:
        return normalize_sql(statement)
    clauses = []
    segment = start + 1
    depth = 1
    quote = None
    index = segment
    while index < len(statement):
        char = statement[index]
        if quote is not None:
            if char == quote:
                if quote != "]" and index + 1 < len(statement) and statement[index + 1] == quote:
                    index += 2
                    continue
                quote = None
        elif char in "'\"`[":
            quote = "]" if char == "[" else char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                clauses.append(normalize_sql(statement[segment:index]))
                break
        elif char == "," and depth == 1:
            clauses.append(normalize_sql(statement[segment:index]))
            segment = index + 1
        index += 1
    if depth or quote is not None:
        raise JiejianError(ErrorCode.STORAGE_MIGRATION, "数据库结构无法识别；数据库未修改")
    # 约束来自集合，比较时仅消除无语义的排列差异。
    constraints = sorted(clause for clause in clauses if clause.startswith("CONSTRAINT "))
    columns = [clause for clause in clauses if not clause.startswith("CONSTRAINT ")]
    return json.dumps(
        (normalize_sql(statement[:start]), columns, constraints, normalize_sql(statement[index + 1:])),
        ensure_ascii=False, separators=(",", ":"),
    )


def normalize_sql(statement: str) -> str:
    """折叠 SQLite 保存 SQL 的无意义空白，保留结构比较语义。"""

    tokens = re.findall(r"'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"|`(?:``|[^`])*`|\[[^\]]*\]|\s+|[^\s'\"`\[]+", statement)
    return "".join(" " if token.isspace() else token for token in tokens).strip()
