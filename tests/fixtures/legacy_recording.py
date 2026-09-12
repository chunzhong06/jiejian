# 构造冻结0003格式的非空业务、录制与绑定数据，供迁移和隔离启动验收共用。
import sqlite3
import hashlib
import json
from pathlib import Path
from alembic import command
from alembic.config import Config

ROOT = Path(__file__).resolve().parents[2]

def _canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()


def _preserved_rows(connection):
    changed = {"alembic_version", "recordings", "action_execution_bindings", "action_resource_bindings",
               "action_evidence_bindings", "action_recovery_bindings", "action_allow_control_bindings",
               "runs", "check_publications"}
    tables = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
              if row[0] not in changed]
    result = {}
    for table in tables:
        columns = [row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')]
        order = ",".join(f'"{column}"' for column in columns)
        result[table] = (columns, connection.execute(f'SELECT * FROM "{table}" ORDER BY {order}').fetchall())
    return result


def _nonempty_0003(tmp_path):
    from tests.fixtures.action_preparation import build_preparation_harness, add_recording
    from product.backend.core.recording import RecordingPurpose
    harness = build_preparation_harness(tmp_path)
    target = add_recording(harness)
    final = harness.core.recording_lifecycle.finalize(target.recording_id, var_dir=harness.var_dir, now_us=100)
    for purpose in (RecordingPurpose.OBSERVATION, RecordingPurpose.RECOVERY):
        record = add_recording(harness, purpose=purpose, parent_recording_id=target.recording_id,
            effect_id=harness.effect_id if purpose is RecordingPurpose.OBSERVATION else None)
        harness.core.recording_lifecycle.finalize(record.recording_id, var_dir=harness.var_dir, now_us=100)
    current = harness.var_dir / "data/jiejian.db"
    harness.close()
    database = tmp_path / "nonempty-0003.db"
    config = Config(str(ROOT / "product/backend/alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database.as_posix()}")
    command.upgrade(config, "0003_action_assurance_recording")
    # 旧结构只由冻结 migration 建立；测试按旧 wire 形成原始历史材料。
    flow = final.flow.model_dump(mode="json")
    flow["schema_version"] = "2"
    flow["test_identity_id"] = flow.pop("subject_test_identity_id")
    flow.pop("resource_owner_test_identity_id")
    flow_bytes = _canonical(flow)
    flow_path = tmp_path / "historical-flow.json"
    flow_path.write_bytes(flow_bytes)
    binding_tables = {"action_execution_bindings": "ActionExecutionBinding", "action_resource_bindings": "ActionResourceBinding",
        "action_evidence_bindings": "ActionEvidenceBinding", "action_recovery_bindings": "ActionRecoveryBinding"}
    with sqlite3.connect(current) as source, sqlite3.connect(database) as destination:
        source.row_factory = sqlite3.Row
        tables = [row[0] for row in destination.execute("SELECT name FROM sqlite_master WHERE type='table'") if row[0] != "alembic_version"]
        rows = {table: [dict(row) for row in source.execute(f'SELECT * FROM "{table}"')] for table in tables}
        draft_hashes = {}
        for row in rows["flow_draft_revisions"]:
            payload = json.loads(row["draft_json"])
            payload["schema_version"] = "2"
            payload["test_identity_id"] = payload.pop("subject_test_identity_id")
            payload.pop("resource_owner_test_identity_id")
            row["draft_json"] = _canonical(payload).decode()
            row["draft_sha256"] = hashlib.sha256(row["draft_json"].encode()).hexdigest()
            draft_hashes[(row["recording_id"], row["revision"])] = row["draft_sha256"]
        for table in ("recordings", *binding_tables):
            for row in rows[table]:
                row["test_identity_id"] = row.pop("subject_test_identity_id")
                row.pop("resource_owner_test_identity_id")
                if table == "recordings":
                    continue
                row["identity_fingerprint"] = row.pop("subject_identity_fingerprint")
                row.pop("owner_identity_fingerprint")
                if table == "action_resource_bindings":
                    row["owner_test_identity_id"] = row["test_identity_id"]
                row["source_draft_sha256"] = draft_hashes[(row["source_recording_id"], row["source_draft_revision"])]
                if "flow_sha256" in row:
                    row["flow_sha256"] = hashlib.sha256(flow_bytes).hexdigest()
                facts = {key[:-5] if key.endswith("_json") else key:
                    json.loads(value) if key.endswith("_json") and value is not None else value
                    for key, value in row.items() if key not in {"confirmed_at_us", "binding_fingerprint"}}
                row["binding_fingerprint"] = hashlib.sha256(_canonical({"kind": binding_tables[table], "facts": facts})).hexdigest()
        for table in tables:
            for row in rows[table]:
                columns = tuple(row)
                destination.execute(f'INSERT INTO "{table}" ('+",".join(f'"{c}"' for c in columns)+") VALUES ("+",".join("?" for _ in columns)+")", tuple(row.values()))
        assert destination.execute("PRAGMA foreign_key_check").fetchall() == []
    return database, flow_path
