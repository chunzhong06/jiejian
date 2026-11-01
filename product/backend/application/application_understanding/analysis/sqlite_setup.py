from __future__ import annotations

import re
from pathlib import PurePosixPath

from .models import SqliteSetupSuggestions, SqliteTableSuggestion

_PATH = re.compile(r'''(["'])([A-Za-z0-9_./-]{1,240}\.(?:sqlite3?|db))\1''', re.IGNORECASE)
_TABLE = re.compile(r'''\bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?["`\[]?([A-Za-z_][A-Za-z0-9_]{0,63})["`\]]?\s*\(''', re.IGNORECASE)
_COLUMN = re.compile(r'''^\s*["`\[]?([A-Za-z_][A-Za-z0-9_]{0,63})["`\]]?\s+(.+)$''', re.DOTALL)


def _parts(text, start):
    depth, quote, part_start = 1, None, start
    parts = []
    index = start
    while index < len(text):
        char = text[index]
        if quote is not None:
            if char == quote:
                if index + 1 < len(text) and text[index + 1] == quote:
                    index += 2
                    continue
                quote = None
        elif char in "'\"`[":
            quote = ']' if char == '[' else char
        elif char == '(':
            depth += 1
        elif char == ')':
            depth -= 1
            if depth == 0:
                parts.append(text[part_start:index])
                return parts
        elif char == ',' and depth == 1:
            parts.append(text[part_start:index])
            part_start = index + 1
        index += 1
    return []


def sqlite_setup_suggestions(files: tuple[tuple[str, bytes], ...]) -> SqliteSetupSuggestions:
    """从本次已授权读取的源码提取配置候选，不打开数据库，也不推断所有者。"""
    paths = set()
    tables = {}
    conflicts = set()
    for relative, raw in files:
        text = raw.decode('utf-8')
        for match in _PATH.finditer(text):
            candidate = PurePosixPath(match[2])
            if not candidate.is_absolute() and '..' not in candidate.parts:
                paths.add(candidate.as_posix())
        for match in _TABLE.finditer(text):
            columns, primary = [], []
            for part in _parts(text, match.end()):
                column = _COLUMN.match(part)
                if column is None:
                    continue
                name, declaration = column.groups()
                if name.upper() in {'CONSTRAINT', 'PRIMARY', 'UNIQUE', 'CHECK', 'FOREIGN'}:
                    continue
                columns.append(name)
                if re.search(r'\bPRIMARY\s+KEY\b', declaration, re.IGNORECASE):
                    primary.append(name)
            if not columns or len(columns) > 128:
                continue
            name = match[1]
            value = SqliteTableSuggestion(name=name,columns=tuple(columns),primary_key=primary[0] if len(primary)==1 else None,source=relative)
            previous = tables.get(name)
            if previous is not None and (previous.columns,previous.primary_key)!=(value.columns,value.primary_key):
                conflicts.add(name)
            tables[name] = value
    return SqliteSetupSuggestions(paths=tuple(sorted(paths))[:32],tables=tuple(tables[key] for key in sorted(tables) if key not in conflicts)[:64])
