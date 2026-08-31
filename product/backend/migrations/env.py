# =============================================================================
# Alembic 迁移运行环境
#
# 定位
#   为界鉴 SQLite 数据库装配 Alembic 的离线 SQL 与在线迁移入口
#
# 职责
#   绑定当前 ORM metadata｜复用 SQLite 连接约束｜限定迁移事务和连接生命周期
#
# 边界
#   不定义具体表变更，不绕过版本迁移，也不持有在线连接。
#
# 调用链
#   Alembic → 本环境 → SQLite Engine / 版本迁移
# =============================================================================

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from product.backend.infra.storage.base import Base
from product.backend.infra.storage.db import configure_sqlite_engine
from product.backend.infra.storage.orm_registry import load_storage_orm_mappings

config = context.config
if config.config_file_name is not None and config.attributes.get(
    "configure_logger", True
):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

load_storage_orm_mappings()
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """在不建立数据库连接时生成绑定当前 metadata 的迁移 SQL。"""

    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """建立受配置约束的 SQLite 连接并在单个 Alembic 事务中迁移。"""

    engine = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    configure_sqlite_engine(engine)
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
