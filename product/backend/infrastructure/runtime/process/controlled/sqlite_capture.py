from __future__ import annotations

from contextlib import closing
import json
from pathlib import Path
import sqlite3
from uuid import uuid4
from tempfile import TemporaryDirectory

from product.backend.infrastructure.runtime.process.controlled.artifact import _regular_file


def prepare_sqlite_copies(root: Path, data: Path, manifest):
    """一致性复制只发生在新测试数据建立时；加载修复代码沿用所属测试数据。"""
    if not manifest.sqlite:
        return
    directory = data / 'sqlite'
    directory.mkdir(parents=True, exist_ok=True)
    for index, specification in enumerate(manifest.sqlite):
        path = directory / f'{index}.sqlite'
        config = json.dumps(specification.model_dump(mode='json'), sort_keys=True, separators=(',', ':'))
        if path.exists():
            with closing(sqlite3.connect(path)) as database:
                existing = database.execute('SELECT config FROM _jj_meta').fetchone()
                if existing is None or existing[0] != config:
                    raise ValueError('SQLite capture configuration changed; explicitly establish new test data')
            continue
        original = _regular_file(root, specification.relative_path)
        if original.stat().st_size > 128 * 1024 * 1024:
            raise ValueError('SQLite test source exceeds size budget')
        # 只有声明与结构均通过后才发布测试库，失败不会留下无法再次准备的半成品。
        with TemporaryDirectory(prefix='.initializing-', dir=directory) as temporary:
            staged = Path(temporary) / 'database.sqlite'
            with closing(sqlite3.connect(original.as_uri() + '?mode=ro', uri=True)) as source, closing(sqlite3.connect(staged)) as database:
                source.backup(database)
                if database.execute("SELECT 1 FROM sqlite_schema WHERE name LIKE '_jj_%'").fetchone():
                    raise ValueError('source contains reserved capture tables')
                for table in specification.tables:
                    definition = database.execute('SELECT sql FROM sqlite_schema WHERE type=? AND name=?', ('table', table.table)).fetchone()
                    if definition is None or 'VIRTUAL' in definition[0].upper():
                        raise ValueError('capture requires an ordinary declared table')
                    columns = {row[1] for row in database.execute('PRAGMA table_info("' + table.table + '")')}
                    if not {table.resource_column, table.owner_column, *table.fields}.issubset(columns):
                        raise ValueError('capture fields missing')
                    primary=[row[1] for row in database.execute('PRAGMA table_info("'+table.table+'")') if row[5]]
                    unique=[row[1] for row in database.execute('PRAGMA index_list("'+table.table+'")') if row[2]]
                    keys=[primary]+[[row[2] for row in database.execute('PRAGMA index_info("'+name.replace('"','""')+'")')] for name in unique]
                    if [table.resource_column] not in keys:
                        raise ValueError('capture requires a stable unique resource key')
                    invalid=database.execute('SELECT 1 FROM "'+table.table+'" WHERE "'+table.resource_column+'" IS NULL OR "'+table.owner_column+'" IS NULL LIMIT 1').fetchone()
                    collision=database.execute('SELECT 1 FROM "'+table.table+'" GROUP BY CAST("'+table.resource_column+'" AS TEXT) HAVING count(*)>1 LIMIT 1').fetchone()
                    if invalid or collision:raise ValueError('capture requires non-null identities and an unambiguous text resource key')
                database.executescript('''CREATE TABLE _jj_meta(generation TEXT NOT NULL,config TEXT NOT NULL);
                    CREATE TABLE _jj_rows(seq INTEGER PRIMARY KEY AUTOINCREMENT,table_name TEXT NOT NULL,
                    resource_id TEXT NOT NULL,owner_id TEXT NOT NULL,kind TEXT NOT NULL,request_nonce TEXT,
                    transaction_id TEXT NOT NULL,before_data TEXT,after_data TEXT,identity_changed INTEGER NOT NULL);''')
                database.execute('INSERT INTO _jj_meta VALUES(?,?)', ('sql_' + uuid4().hex, config))
                database.commit()
            staged.rename(path)
