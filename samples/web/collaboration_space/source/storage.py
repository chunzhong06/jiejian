# 协作空间 Sample 的运行数据存储与受控工件生成。

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import threading
import time
import zipfile
from pathlib import Path
from typing import Any


PROJECT_ID = "campus-digital-museum"
PROJECT_NAME = "校园数字展馆"
RESOURCE_ID = "campus-digital-museum-package"


def _now_us() -> int:
    return time.time_ns() // 1_000


def _safe_marker(value: str) -> bool:
    return 1 <= len(value) <= 128 and value[0].isalpha() and all(
        char.isalnum() or char in "_.:-" for char in value
    )


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    os.replace(temporary, path)


class CollaborationStorage:
    """保存 Sample 运行事实；秘密、答案和界鉴结果不进入这些记录。"""

    def __init__(self, runtime_root: str | Path) -> None:
        self.root = Path(runtime_root).resolve()
        self.database_dir = self.root / "database"
        self.audit_dir = self.root / "audit"
        self.queue_dir = self.root / "queue"
        self.tasks_dir = self.root / "tasks"
        self.blob_dir = self.root / "blob"
        for directory in (
            self.database_dir,
            self.audit_dir,
            self.queue_dir,
            self.tasks_dir,
            self.blob_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)
        self.database_path = self.database_dir / "collaboration-space.sqlite3"
        self.lock = threading.RLock()
        self._initialize_database()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=5)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize_database(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                f"""
                CREATE TABLE IF NOT EXISTS projects (
                    project_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    owner_id TEXT NOT NULL,
                    export_state TEXT NOT NULL,
                    latest_task_id TEXT,
                    latest_artifact_id TEXT,
                    updated_at_us INTEGER NOT NULL,
                    case_id TEXT
                );
                CREATE TABLE IF NOT EXISTS members (
                    project_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    PRIMARY KEY (project_id, user_id)
                );
                CREATE TABLE IF NOT EXISTS export_jobs (
                    task_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    actor_id TEXT NOT NULL,
                    state TEXT NOT NULL,
                    artifact_id TEXT,
                    case_id TEXT NOT NULL,
                    created_at_us INTEGER NOT NULL,
                    finished_at_us INTEGER
                );
                DROP VIEW IF EXISTS resource_state;
                CREATE VIEW resource_state AS
                    SELECT
                        '{RESOURCE_ID}' AS resource_id,
                        CASE WHEN export_state = 'READY' THEN 'READY' ELSE 'ABSENT' END AS workflow_state,
                        COALESCE(latest_artifact_id, '') AS value
                    FROM projects
                    WHERE project_id = '{PROJECT_ID}';
                """,
            )
            connection.execute(
                "INSERT OR IGNORE INTO projects(project_id, name, owner_id, export_state, updated_at_us) VALUES (?, ?, ?, ?, ?)",
                (PROJECT_ID, PROJECT_NAME, "alice", "NOT_CREATED", _now_us()),
            )
            connection.executemany(
                "INSERT OR IGNORE INTO members(project_id, user_id, role) VALUES (?, ?, ?)",
                (
                    (PROJECT_ID, "alice", "PROJECT_OWNER"),
                    (PROJECT_ID, "bob", "MEMBER"),
                ),
            )

    def member_role(self, user_id: str) -> str | None:
        with self.lock, self._connect() as connection:
            row = connection.execute(
                "SELECT role FROM members WHERE project_id = ? AND user_id = ?",
                (PROJECT_ID, user_id),
            ).fetchone()
            return None if row is None else str(row["role"])

    def project_summary(self) -> dict[str, Any]:
        with self.lock, self._connect() as connection:
            row = connection.execute(
                "SELECT project_id, name, owner_id, export_state, latest_task_id, latest_artifact_id, updated_at_us FROM projects WHERE project_id = ?",
                (PROJECT_ID,),
            ).fetchone()
            assert row is not None
            return dict(row)

    def project_catalog_entry(self) -> dict[str, str]:
        """返回登录用户均可见的项目目录信息，不泄露成员态和导出态。"""

        summary = self.project_summary()
        return {
            "project_id": str(summary["project_id"]),
            "name": str(summary["name"]),
            "summary": "校园历史、科研成果与师生记忆数字展馆",
        }

    def project_detail(self) -> dict[str, Any]:
        with self.lock, self._connect() as connection:
            row = connection.execute(
                "SELECT projects.project_id, projects.name, projects.owner_id, projects.export_state, "
                "projects.latest_task_id, projects.latest_artifact_id, projects.updated_at_us, "
                "jobs.case_id AS active_request_marker, jobs.task_id AS active_task_id "
                "FROM projects LEFT JOIN export_jobs AS jobs "
                "ON jobs.task_id = projects.latest_task_id AND jobs.state = 'SUCCESS' "
                "WHERE projects.project_id = ?",
                (PROJECT_ID,),
            ).fetchone()
            assert row is not None
            summary = {
                key: row[key]
                for key in (
                    "project_id",
                    "name",
                    "owner_id",
                    "export_state",
                    "latest_task_id",
                    "latest_artifact_id",
                    "updated_at_us",
                )
            }
            members = [
                dict(row)
                for row in connection.execute(
                    "SELECT user_id, role FROM members WHERE project_id = ? ORDER BY user_id",
                    (PROJECT_ID,),
                )
            ]
            active_export = (
                {
                    "request_marker": str(row["active_request_marker"]),
                    "task_id": str(row["active_task_id"]),
                }
                if row["export_state"] == "READY"
                and row["active_request_marker"] is not None
                and row["active_task_id"] is not None
                else None
            )
        return {
            **summary,
            "active_export": active_export,
            "members": members,
            "materials": [
                {"name": "展馆项目说明", "kind": "PROJECT_NOTE"},
                {"name": "展陈设计占位稿", "kind": "DESIGN_PLACEHOLDER"},
                {"name": "项目预算摘要", "kind": "BUDGET_SUMMARY"},
            ],
            "export_action": "导出完整项目资料包",
        }

    def resource_state(self) -> dict[str, str]:
        """读取与 SQLite Observer 相同的单资源业务投影。"""

        with self.lock, self._connect() as connection:
            row = connection.execute(
                "SELECT resource_id, workflow_state, value FROM resource_state WHERE resource_id = ?",
                (RESOURCE_ID,),
            ).fetchone()
            assert row is not None
            return {key: str(row[key]) for key in ("resource_id", "workflow_state", "value")}

    def find_job(self, marker: str) -> dict[str, Any] | None:
        with self.lock, self._connect() as connection:
            row = connection.execute(
                "SELECT task_id, project_id, actor_id, state, artifact_id, case_id, created_at_us, finished_at_us FROM export_jobs WHERE case_id = ?",
                (marker,),
            ).fetchone()
            return None if row is None else dict(row)

    def create_job(self, marker: str, actor_id: str) -> dict[str, Any]:
        if not _safe_marker(marker):
            raise ValueError("invalid request marker")
        task_id = "task-" + hashlib.sha256(marker.encode("utf-8")).hexdigest()[:24]
        with self.lock, self._connect() as connection:
            existing = connection.execute(
                "SELECT task_id, project_id, actor_id, state, artifact_id, case_id, created_at_us, finished_at_us FROM export_jobs WHERE case_id = ?",
                (marker,),
            ).fetchone()
            if existing is not None:
                return {**dict(existing), "_created": False}
            now = _now_us()
            connection.execute(
                "INSERT INTO export_jobs(task_id, project_id, actor_id, state, case_id, created_at_us) VALUES (?, ?, ?, ?, ?, ?)",
                (task_id, PROJECT_ID, actor_id, "QUEUED", marker, now),
            )
            connection.execute(
                "UPDATE projects SET export_state = 'PROCESSING', latest_task_id = ?, latest_artifact_id = NULL, updated_at_us = ?, case_id = ? WHERE project_id = ?",
                (task_id, now, marker, PROJECT_ID),
            )
            row = connection.execute(
                "SELECT task_id, project_id, actor_id, state, artifact_id, case_id, created_at_us, finished_at_us FROM export_jobs WHERE task_id = ?",
                (task_id,),
            ).fetchone()
            assert row is not None
            return {**dict(row), "_created": True}

    def update_job(self, task_id: str, state: str, *, artifact_id: str | None = None) -> dict[str, Any]:
        with self.lock, self._connect() as connection:
            finished_at = _now_us() if state in {"SUCCESS", "FAILED"} else None
            connection.execute(
                "UPDATE export_jobs SET state = ?, artifact_id = COALESCE(?, artifact_id), finished_at_us = ? WHERE task_id = ?",
                (state, artifact_id, finished_at, task_id),
            )
            row = connection.execute(
                "SELECT task_id, project_id, actor_id, state, artifact_id, case_id, created_at_us, finished_at_us FROM export_jobs WHERE task_id = ?",
                (task_id,),
            ).fetchone()
            if row is None:
                raise KeyError(task_id)
            if state == "SUCCESS":
                connection.execute(
                    "UPDATE projects SET export_state = 'READY', latest_task_id = ?, latest_artifact_id = ?, updated_at_us = ? WHERE project_id = ?",
                    (task_id, artifact_id, _now_us(), PROJECT_ID),
                )
            elif state == "FAILED":
                connection.execute(
                    "UPDATE projects SET export_state = 'FAILED', updated_at_us = ? WHERE project_id = ?",
                    (_now_us(), PROJECT_ID),
                )
            return dict(row)

    def write_task(self, job: dict[str, Any], *, final_result: dict[str, Any] | None = None) -> None:
        payload = {
            "schema_version": "1",
            "case_tag": job["case_id"],
            "resource_id": RESOURCE_ID,
            "task_id": job["task_id"],
            "state": job["state"],
            "final_result": final_result,
            "actor_id": job["actor_id"],
            "project_id": PROJECT_ID,
            "artifact_id": job.get("artifact_id"),
        }
        with self.lock:
            _write_json(self.tasks_dir / f"{job['case_id']}.json", payload)

    def task_for_marker(self, marker: str) -> dict[str, Any] | None:
        path = self.tasks_dir / f"{marker}.json"
        if not _safe_marker(marker):
            return None
        # Windows 不允许在无共享删除的读取句柄存在时替换目标文件；读取和写入
        # 必须共用同一把锁，才能保持任务快照的原子发布语义。
        with self.lock:
            if not path.is_file():
                return None
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                return None
        if not isinstance(payload, dict):
            return None
        return {
            key: payload.get(key)
            for key in ("schema_version", "case_tag", "resource_id", "task_id", "state", "final_result")
        }

    def append_audit(
        self,
        *,
        marker: str,
        task_id: str,
        event_type: str,
        sequence: int,
        result: str,
        effect: str,
    ) -> None:
        record = {
            "event_id": hashlib.sha256(f"{marker}:{event_type}:{sequence}".encode("utf-8")).hexdigest()[:24],
            "case_tag": marker,
            "task_id": task_id,
            "event_type": event_type,
            "sequence": sequence,
            "resource_id": RESOURCE_ID,
            "result": result,
            "effect": effect,
        }
        self._append_record_once(self.audit_dir / "events.jsonl", record)

    def append_queue_message(
        self,
        *,
        marker: str,
        task_id: str,
        event_type: str,
        sequence: int,
        result: str,
        effect: str,
    ) -> None:
        record = {
            "event_id": hashlib.sha256(f"queue:{marker}:{event_type}:{sequence}".encode("utf-8")).hexdigest()[:24],
            "case_tag": marker,
            "resource_id": RESOURCE_ID,
            "sequence": sequence,
            "event_type": event_type,
            "task_id": task_id,
            "result": result,
            "effect": effect,
        }
        self._append_record_once(self.queue_dir / "messages.jsonl", record)

    def _append_record_once(self, path: Path, record: dict[str, Any]) -> None:
        """按稳定事件身份幂等追加，避免重复请求制造第二份业务历史。"""

        encoded = json.dumps(record, separators=(",", ":"), sort_keys=True)
        with self.lock:
            if path.is_file():
                for line in path.read_text(encoding="utf-8").splitlines():
                    try:
                        current = json.loads(line)
                    except ValueError:
                        continue
                    if isinstance(current, dict) and current.get("event_id") == record["event_id"]:
                        return
            with path.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(encoded + "\n")

    def queue_records(self) -> list[dict[str, Any]]:
        path = self.queue_dir / "messages.jsonl"
        if not path.is_file():
            return []
        records: list[dict[str, Any]] = []
        with self.lock:
            for line in path.read_text(encoding="utf-8").splitlines()[:256]:
                try:
                    item = json.loads(line)
                except ValueError:
                    continue
                if isinstance(item, dict):
                    records.append(item)
        return records

    def create_archive(self, marker: str) -> tuple[str, Path]:
        artifact_id = "artifact-" + hashlib.sha256(marker.encode("utf-8")).hexdigest()[:24]
        directory = self.blob_dir / marker
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / "campus-digital-museum-package.zip"
        temporary = directory / ".campus-digital-museum-package.zip.tmp"
        files = {
            "project.json": json.dumps(
                {"project_id": PROJECT_ID, "name": PROJECT_NAME, "description": "校园数字展馆项目资料"},
                ensure_ascii=False,
                sort_keys=True,
            ),
            "members.json": json.dumps(
                [
                    {"name": "Alice", "role": "项目负责人"},
                    {"name": "Bob", "role": "普通成员"},
                ],
                ensure_ascii=False,
                sort_keys=True,
            ),
            "design/placeholder.txt": "虚构设计占位内容\n",
            "history.json": json.dumps({"entries": ["项目创建", "展陈资料整理"]}, ensure_ascii=False, sort_keys=True),
        }
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, content in files.items():
                info = zipfile.ZipInfo(name, date_time=(2024, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, content.encode("utf-8"))
        os.replace(temporary, target)
        return artifact_id, target

    def blob_objects(self) -> list[dict[str, Any]]:
        """只暴露当前仍有效的交付物；磁盘历史文件不等于当前 Blob 对象。"""

        objects: list[dict[str, Any]] = []
        with self.lock:
            with self._connect() as connection:
                active_rows = connection.execute(
                    "SELECT jobs.case_id FROM export_jobs AS jobs "
                    "JOIN projects AS projects ON projects.latest_task_id = jobs.task_id "
                    "WHERE projects.project_id = ? AND projects.export_state = 'READY' "
                    "AND jobs.state = 'SUCCESS'",
                    (PROJECT_ID,),
                ).fetchall()
            for row in active_rows:
                marker = str(row["case_id"])
                archive = self.blob_dir / marker / "campus-digital-museum-package.zip"
                if not archive.is_file():
                    continue
                body = archive.read_bytes()
                objects.append(
                    {
                        "name": f"{marker}/campus-digital-museum-package.zip",
                        "path": archive,
                        "length": len(body),
                        "etag": hashlib.sha256(body).hexdigest(),
                        "case_tag": marker,
                        "resource_id": RESOURCE_ID,
                    }
                )
        return objects

    def revoke_export(self, marker: str) -> dict[str, Any]:
        """逻辑撤销当前有效导出，同时保留任务、工件和过程历史。"""

        if not _safe_marker(marker):
            raise ValueError("invalid request marker")
        with self.lock, self._connect() as connection:
            row = connection.execute(
                "SELECT task_id, project_id, actor_id, state, artifact_id, case_id, "
                "created_at_us, finished_at_us FROM export_jobs WHERE case_id = ?",
                (marker,),
            ).fetchone()
            if row is None:
                return {"code": "EXPORT_NOT_ACTIVE", "request_marker": marker, "revoked": False}
            job = dict(row)
            if job["state"] == "REVOKED":
                return {
                    "code": "EXPORT_ALREADY_REVOKED",
                    "request_marker": marker,
                    "revoked": True,
                }
            if job["state"] != "SUCCESS":
                return {
                    "code": "EXPORT_NOT_READY_FOR_REVOKE",
                    "request_marker": marker,
                    "revoked": False,
                }
            project = connection.execute(
                "SELECT export_state, latest_task_id, case_id FROM projects WHERE project_id = ?",
                (PROJECT_ID,),
            ).fetchone()
            if (
                project is None
                or project["export_state"] != "READY"
                or project["latest_task_id"] != job["task_id"]
                or project["case_id"] != marker
            ):
                return {"code": "EXPORT_NOT_ACTIVE", "request_marker": marker, "revoked": False}
            connection.execute(
                "UPDATE export_jobs SET state = 'REVOKED' WHERE task_id = ? AND state = 'SUCCESS'",
                (job["task_id"],),
            )
            connection.execute(
                "UPDATE projects SET export_state = 'REVOKED', latest_task_id = NULL, "
                "latest_artifact_id = NULL, updated_at_us = ?, case_id = NULL "
                "WHERE project_id = ? AND latest_task_id = ?",
                (_now_us(), PROJECT_ID, job["task_id"]),
            )
            revoked = {**job, "state": "REVOKED"}
            self.write_task(
                revoked,
                final_result={"artifact_id": job["artifact_id"], "state": "REVOKED"},
            )
            self.append_audit(
                marker=marker,
                task_id=str(job["task_id"]),
                event_type="EXPORT_REVOKED",
                sequence=4,
                result="revoked",
                effect="REVOKED",
            )
            self.append_queue_message(
                marker=marker,
                task_id=str(job["task_id"]),
                event_type="EXPORT_REVOKED",
                sequence=4,
                result="revoked",
                effect="REVOKED",
            )
            return {
                "code": "EXPORT_REVOKED",
                "request_marker": marker,
                "revoked": True,
            }

    def reset(self) -> None:
        with self.lock:
            for directory in (self.audit_dir, self.queue_dir, self.tasks_dir, self.blob_dir):
                shutil.rmtree(directory, ignore_errors=True)
                directory.mkdir(parents=True, exist_ok=True)
            with self._connect() as connection:
                connection.execute("DELETE FROM export_jobs")
                connection.execute(
                    "UPDATE projects SET export_state = 'NOT_CREATED', latest_task_id = NULL, latest_artifact_id = NULL, updated_at_us = ?, case_id = NULL WHERE project_id = ?",
                    (_now_us(), PROJECT_ID),
                )
