# 定位迁移资源、核验当前修订图，并为初始化登记和维护迁移提供配置。
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from importlib.resources import as_file, files
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


@contextmanager
def migration_resources() -> Iterator[Path]:
    """在资源使用期内提供成对配置和迁移目录，兼容已安装包。"""
    packaged = files("product.backend")
    config_exists = packaged.joinpath("alembic.ini").is_file()
    migrations_exist = packaged.joinpath("migrations").is_dir()
    if config_exists or migrations_exist:
        if not (config_exists and migrations_exist):
            raise FileNotFoundError("packaged Alembic resources are incomplete")
        with as_file(packaged) as root:
            yield root
        return
    root = Path(__file__).resolve().parents[1]
    if not (root / "alembic.ini").is_file() or not (root / "migrations").is_dir():
        raise FileNotFoundError("source Alembic resources are incomplete")
    yield root


def migration_config(root: Path, database: Path | None = None) -> Config:
    config = Config(str(root / "alembic.ini"))
    config.attributes["configure_logger"] = False
    if database is not None:
        url = f"sqlite+pysqlite:///{database.as_posix()}"
        config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return config


@dataclass(frozen=True)
class MigrationHistory:
    head: str
    revisions: frozenset[str]

    @classmethod
    def load(cls, root: Path) -> MigrationHistory:
        """只接受单一起点、唯一终点且可完整遍历的历史；不维护第二份修订清单。"""
        scripts = ScriptDirectory.from_config(migration_config(root))
        heads, bases = scripts.get_heads(), scripts.get_bases()
        if len(heads) != 1 or len(bases) != 1:
            raise ValueError("migration history must have one base and one head")
        revisions = frozenset(item.revision for item in scripts.walk_revisions())
        if not revisions or bases[0] not in revisions:
            raise ValueError("migration history is disconnected")
        return cls(head=heads[0], revisions=revisions)
