# 构造冻结0003格式的非空业务、录制与绑定数据，供迁移和隔离启动验收共用。
import sqlite3
import hashlib
import json
from pathlib import Path
from alembic import command
from alembic.config import Config

ROOT = Path(__file__).resolve().parents[3]
# 有意固定历史输入；格式升级新增另一个夹具，不能随当前模型重生成。
FROZEN_0003_SHA256 = "107332ae1cf741c698d00c7ae4660f53d9662581a642234137a2f3794d903d0b"

def _canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()


def _preserved_rows(connection, expected=None):
    changed = {"alembic_version", "recordings", "action_execution_bindings", "action_resource_bindings",
               "action_evidence_bindings", "action_recovery_bindings", "action_allow_control_bindings",
               "runs", "check_publications"}
    tables = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
              if row[0] not in changed]
    result = {}
    for table in tables:
        columns = [row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')]
        columns = expected[table][0] if expected and table in expected else columns
        order = ",".join(f'"{column}"' for column in columns)
        result[table] = (columns, connection.execute(f'SELECT {order} FROM "{table}" ORDER BY {order}').fetchall())
    return result


def _nonempty_0003(tmp_path):
    """重放已冻结的旧 wire；不导入当前模型、应用核心或当前准备夹具。"""
    frozen = ROOT / "tests/fixtures/history/recording-0003.json"
    raw = frozen.read_bytes()
    if hashlib.sha256(raw).hexdigest() != FROZEN_0003_SHA256:
        raise ValueError("HISTORICAL_FIXTURE_CHANGED")
    snapshot = json.loads(raw)
    database = tmp_path / "nonempty-0003.db"
    config = Config(str(ROOT / "product/backend/alembic.ini"))
    config.attributes["configure_logger"] = False
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database.as_posix()}")
    command.upgrade(config, snapshot["revision"])
    with sqlite3.connect(database) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for table, rows in snapshot["tables"].items():
            if table not in tables:
                raise ValueError("HISTORICAL_TABLE_MISSING")
            columns = [row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')]
            names = ",".join(f'"{name}"' for name in columns)
            placeholders = ",".join("?" for _ in columns)
            for row in rows:
                if set(row) != set(columns):
                    raise ValueError("HISTORICAL_COLUMNS_CHANGED")
                connection.execute(f'INSERT INTO "{table}" ({names}) VALUES ({placeholders})', [row[name] for name in columns])
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    flow_path = tmp_path / "historical-flow.json"
    flow_path.write_bytes(_canonical(snapshot["flow"]))
    return database, flow_path
