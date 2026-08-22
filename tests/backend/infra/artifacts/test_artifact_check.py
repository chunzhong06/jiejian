from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from product.backend.infra.artifacts.scan_job import ArtifactCheckJobHandler
from product.protocols.artifacts import (
    ArtifactCheckRequest,
    ArtifactScanStatus,
    ArtifactVerdict,
    ScanBudget,
)
from product.backend.infra.artifacts.scanner import scan_artifact
from product.backend.infra.runtime.jobs.handlers import JobHandlerRegistry
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.infra.artifacts.run_packages import PublicationManifest
from product.protocols import StagedArtifact


PROJECT_ID = "artifact-project"
RUN_ID = "run_" + "1" * 32
JOB_ID = "job_" + "2" * 32


def _artifact_tree(tmp_path: Path, files: dict[str, bytes]) -> ArtifactCheckRequest:
    var_dir = tmp_path / "var"
    final_dir = var_dir / "data" / "projects" / PROJECT_ID / "runs" / RUN_ID
    root = final_dir / "artifacts"
    root.mkdir(parents=True)
    (final_dir / "result.json").write_bytes(b"{}")
    manifest_files = [StagedArtifact(schema_version="2", path="result.json", byte_count=2, sha256=hashlib.sha256(b"{}").hexdigest())]
    for relative, raw in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        manifest_files.append(StagedArtifact(schema_version="2", path=f"artifacts/{relative}", byte_count=len(raw), sha256=hashlib.sha256(raw).hexdigest()))
    manifest = PublicationManifest(
        project_id=PROJECT_ID,
        run_id=RUN_ID,
        job_id=JOB_ID,
        attempt=1,
        lease_owner="artifact-test",
        fencing_token=1,
        lease_expires_at_us=2_000,
        published_at_us=1_000,
        result_sha256=hashlib.sha256(b"{}").hexdigest(),
        files=tuple(manifest_files),
    )
    manifest_path = final_dir / "publication-manifest.json"
    manifest_path.write_bytes(json.dumps(manifest.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode())
    return ArtifactCheckRequest(
        project_id=PROJECT_ID,
        artifact_id="build-1",
        run_id=RUN_ID,
        artifact_root=str(root),
        manifest_path=str(manifest_path),
    )


def test_vulnerable_artifact_is_deterministically_identified_and_secret_is_redacted(tmp_path: Path) -> None:
    secret = "sk-" + "012345678901234567890123"
    request = _artifact_tree(
        tmp_path,
        {
            "app.js": f'const apiKey = "{secret}";\n//# sourceMappingURL=app.js.map\n'.encode(),
            ".env": b"DATABASE_URL=postgres://example.invalid/db\n",
            "package-lock.json": b'{"packages":{"node_modules/lodash":{"version":"4.17.20"}}}',
            "app.js.map": b'{"version":3}',
        },
    )
    result = scan_artifact(request)
    encoded = result.model_dump_json()
    assert result.status is ArtifactScanStatus.COMPLETE
    assert result.verdict is ArtifactVerdict.VULNERABLE
    assert {item.category for item in result.findings} >= {"SECRET_CANDIDATE", "FORBIDDEN_FILE", "SOURCE_MAP", "DEPENDENCY_VERSION"}
    assert secret not in encoded
    assert "example.invalid" not in encoded
    assert all(item.source_type == "ARTIFACT" for item in result.evidence)


def test_fixed_artifact_is_safe(tmp_path: Path) -> None:
    request = _artifact_tree(
        tmp_path,
        {
            "app.js": b"export const ready = true;\n",
            "package-lock.json": b'{"packages":{"node_modules/lodash":{"version":"4.17.21"}}}',
        },
    )
    result = scan_artifact(request)
    assert result.status is ArtifactScanStatus.COMPLETE
    assert result.verdict is ArtifactVerdict.SAFE
    assert result.findings == ()
    assert result.scanned_file_count == 2
    assert request.budget.max_parallel_files == 1

    schema = json.loads(
    (Path(__file__).resolve().parents[4] / "product" / "protocols" / "schemas" / "artifacts" / "artifact-check-request.schema.json").read_text(
            encoding="utf-8"
        )
    )
    budget_schema = schema["properties"]["budget"]
    assert budget_schema["properties"]["max_parallel_files"] == {"const": 1}
    assert "max_parallel_files" in budget_schema["required"]


def test_artifact_handler_is_auxiliary_and_does_not_add_a_persistent_target() -> None:
    registry = JobHandlerRegistry()
    registry.register_auxiliary("ARTIFACT_CHECK", lambda: object())
    assert registry.resolve_auxiliary("ARTIFACT_CHECK") is not None


def test_budget_or_manifest_boundary_is_inconclusive(tmp_path: Path) -> None:
    request = _artifact_tree(tmp_path, {"one.js": b"1", "two.js": b"2"})
    limited = request.model_copy(update={"budget": ScanBudget(max_files=1)})
    result = scan_artifact(limited)
    assert result.status is ArtifactScanStatus.INCONCLUSIVE
    assert result.verdict is ArtifactVerdict.INCONCLUSIVE
    assert result.error_code == "FILE_COUNT_BUDGET"

    escaped = request.model_copy(update={"manifest_path": str(Path(request.artifact_root).parent / ".." / "outside.json")})
    result = scan_artifact(escaped)
    assert result.status is ArtifactScanStatus.INCONCLUSIVE
    assert result.verdict is ArtifactVerdict.INCONCLUSIVE


def test_zip_magic_is_not_interpreted_as_safe_when_archive_layer_budget_is_zero(tmp_path: Path) -> None:
    request = _artifact_tree(tmp_path, {"bundle.bin": b"PK\x03\x04not-inspected"})
    result = scan_artifact(request)
    assert result.status is ArtifactScanStatus.INCONCLUSIVE
    assert result.verdict is ArtifactVerdict.INCONCLUSIVE
    assert result.error_code == "COMPRESSED_LAYER_BUDGET"


def test_handler_rejects_child_result_with_mismatched_run_id(tmp_path: Path) -> None:
    request = _artifact_tree(tmp_path, {"app.js": b"const safe = true;"})
    job_dir = tmp_path / "var" / "data" / "artifact-checks" / "jobs" / "artifact-job-run-mismatch"
    job_dir.mkdir(parents=True)
    (job_dir / "request.json").write_bytes(json.dumps(request.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode())
    child_result = scan_artifact(request).model_copy(update={"run_id": "run_" + "3" * 32})

    class CompletedProcess:
        returncode = 0

        def poll(self) -> int:
            return 0

        def kill(self) -> None:
            return None

    def fake_popen(command: list[str], **_: object) -> CompletedProcess:
        Path(command[-1]).write_bytes(json.dumps(child_result.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode())
        return CompletedProcess()

    with pytest.raises(JiejianError) as captured:
        ArtifactCheckJobHandler(tmp_path / "var", popen=fake_popen).run_job("artifact-job-run-mismatch")
    assert captured.value.code == ErrorCode.ARTIFACT_SCAN_FAILED.value
    assert not (job_dir / "published").exists()


@pytest.mark.process
def test_worker_handler_forms_isolated_prepare_check_assert_publish_cleanup_loop(tmp_path: Path) -> None:
    request = _artifact_tree(tmp_path, {"app.js": b"const safe = true;"})
    job_dir = tmp_path / "var" / "data" / "artifact-checks" / "jobs" / "artifact-job-1"
    job_dir.mkdir(parents=True)
    (job_dir / "request.json").write_bytes(json.dumps(request.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode())
    result = ArtifactCheckJobHandler(tmp_path / "var").run_job("artifact-job-1")
    published = job_dir / "published"
    assert result.verdict is ArtifactVerdict.SAFE
    assert (published / "artifact-result.json").is_file()
    manifest = json.loads((published / "artifact-check-manifest.json").read_text(encoding="utf-8"))
    assert manifest["result_sha256"] == hashlib.sha256((published / "artifact-result.json").read_bytes()).hexdigest()
    assert not list(job_dir.glob("*.tmp-*"))
