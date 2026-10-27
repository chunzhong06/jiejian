# 从正式迁移图发现当前修订，不维护重复的版本清单。
import sqlite3
from pathlib import Path
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory


def migration_history():
    root=Path(__file__).resolve().parents[3]
    config=Config(str(root/'product/backend/alembic.ini'))
    config.set_main_option('script_location',str(root/'product/backend/migrations'))
    return ScriptDirectory.from_config(config)


def migration_head():
    heads=migration_history().get_heads()
    if len(heads)!=1:
        raise AssertionError(f'数据库必须存在唯一可升级终点，实际为 {heads}')
    return heads[0]


