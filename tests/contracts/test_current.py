# 快速发现当前合同与夹具过期，避免等到 Worker 或数据库整链结束才发现。
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

from product.backend.infra.storage import JobRecord
from tests.contracts.current import DATABASE_HEAD, JOB_TARGET_FIELDS, WORKER_CAPABILITIES

ROOT = Path(__file__).resolve().parents[2]


def test_migration_has_one_accepted_head():
    config = Config(str(ROOT / "product/backend/alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "product/backend/migrations"))
    assert ScriptDirectory.from_config(config).get_heads() == [DATABASE_HEAD]
    from product.backend.infra.storage.db import _CURRENT_MIGRATION_REVISION
    assert _CURRENT_MIGRATION_REVISION == DATABASE_HEAD


def test_job_fixture_contract_contains_every_target():
    assert JOB_TARGET_FIELDS <= set(JobRecord.model_fields)


def test_current_worker_registry_is_explicit():
    from product.backend.infra.runtime.jobs.targets import current_check_and_recording_targets
    targets = current_check_and_recording_targets().target_types
    assert tuple(item.value for item in targets) == ("PROOF_PREFLIGHT", "RECORDING", "RUN")


def test_test_catalog_covers_all_python_and_frontend_tests():
    from tests.support.verification.catalog import inventory
    result = inventory(ROOT)
    assert result["files"]
    assert {row["engine"] for row in result["files"]} == {"pytest", "vitest"}
