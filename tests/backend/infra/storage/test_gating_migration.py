# 验证持久化基础设施中的结果闸门迁移。

from __future__ import annotations

from pathlib import Path

from sqlalchemy import inspect

from product.backend.infra.storage import create_sqlite_engine, upgrade_database


def test_current_migration_adds_immutable_baseline_and_gate_tables(tmp_path: Path) -> None:
    database = tmp_path / "gating-baseline.db"
    upgrade_database(database)
    engine = create_sqlite_engine(database)
    try:
        inspector = inspect(engine)
        assert {"regression_baselines", "gate_results"} <= set(inspector.get_table_names())
        assert "baseline_id" in {item["name"] for item in inspector.get_columns("regression_baselines")}
        assert "input_hash" in {item["name"] for item in inspector.get_columns("gate_results")}
        with engine.connect() as connection:
            assert connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one() == "0006_repair_contract_reference"
    finally:
        engine.dispose()
