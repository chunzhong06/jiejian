# 通过正式Alembic生成指定历史版本，再写入最小保留事实供非空升级验证。
import sqlite3
from pathlib import Path
from alembic import command
from alembic.config import Config


def prior_database(tmp_path,revision):
    root=Path(__file__).resolve().parents[2]
    path=tmp_path/'old.db'
    config=Config(str(root/'product/backend/alembic.ini'))
    config.attributes['configure_logger']=False
    config.set_main_option('sqlalchemy.url','sqlite+pysqlite:///'+path.as_posix())
    command.upgrade(config,revision)
    with sqlite3.connect(path) as connection:
        connection.execute("INSERT INTO projects VALUES ('project','保留的项目','READY','WEB',NULL,NULL,1,1)")
        connection.execute("INSERT INTO preparation_receipts VALUES ('receipt','project',?,1,'{}')",('a'*64,))
    return path
