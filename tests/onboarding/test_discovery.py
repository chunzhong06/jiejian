from __future__ import annotations

from pathlib import Path

import pytest

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.workflows.onboarding import discovery
from product.backend.workflows.onboarding.discovery import discover_folder
from product.backend.workflows.onboarding.models import DiscoveryLimits


def test_discovery_returns_stack_candidates_hints_and_stable_missing_items(
    tmp_path: Path,
) -> None:
    (tmp_path / "package.json").write_text(
        '{"scripts":{"dev":"node -e \\"process.exit(1)\\"","build":"echo build"},'
        '"dependencies":{"next-auth":"1.0.0","react":"19"}}',
        encoding="utf-8",
    )
    (tmp_path / "pnpm-lock.yaml").write_text(
        "lockfileVersion: '9'", encoding="utf-8"
    )
    (tmp_path / ".env").write_text(
        "SECRET_TOKEN=must-not-appear", encoding="utf-8"
    )
    (tmp_path / "openapi.json").write_text(
        '{"openapi":"3.0.0","paths":{}}', encoding="utf-8"
    )

    result = discover_folder(tmp_path.resolve())

    assert result.detected_types == ("Next.js", "Node.js", "OpenAPI")
    assert {item.command for item in result.start_candidates} == {
        "pnpm run build",
        "pnpm run dev",
    }
    assert all(
        item.confirmation_required and not item.executed
        for item in result.start_candidates
    )
    assert any("环境配置文件存在" in item.detail for item in result.config_hints)
    assert result.auth_hints
    assert result.interface_hints
    assert tuple(item.key for item in result.missing_items) == (
        "startup",
        "target_address",
        "test_accounts",
        "authorized_scope",
        "recovery",
    )
    dumped = result.model_dump_json()
    assert "SECRET_TOKEN" not in dumped
    assert "node -e" not in dumped
    assert "process.exit" not in dumped


def test_discovery_never_reads_scripts_or_source_and_reports_env_only(
    tmp_path: Path,
) -> None:
    (tmp_path / "package.json").write_text(
        '{"scripts":{"start":"echo SECRET_SCRIPT_BODY"}}', encoding="utf-8"
    )
    (tmp_path / "main.py").write_text("SECRET_SOURCE_BODY", encoding="utf-8")
    (tmp_path / ".env.production").write_text(
        "PASSWORD=secret", encoding="utf-8"
    )

    result = discover_folder(tmp_path.resolve())

    text = result.model_dump_json()
    assert "SECRET_SCRIPT_BODY" not in text
    assert "SECRET_SOURCE_BODY" not in text
    assert "PASSWORD" not in text
    assert "secret" not in text
    assert result.start_candidates[0].command == "npm run start"


def test_discovery_prunes_large_dependency_and_cache_directories(
    tmp_path: Path,
) -> None:
    (tmp_path / "package.json").write_text(
        '{"name":"fixture","scripts":{"dev":"vite"}}', encoding="utf-8"
    )
    node_modules = tmp_path / "Node_Modules"
    node_modules.mkdir()
    for index in range(300):
        (node_modules / f"unrelated-{index:03d}.txt").write_text("x", encoding="utf-8")
    cache_dir = tmp_path / ".CACHE"
    cache_dir.mkdir()
    for index in range(3):
        (cache_dir / f"cache-{index}").write_text("x", encoding="utf-8")

    result = discover_folder(tmp_path.resolve())

    assert "Node.js" in result.detected_types
    assert any(item.command == "npm run dev" for item in result.start_candidates)


def test_discovery_requires_absolute_existing_directory(tmp_path: Path) -> None:
    with pytest.raises(JiejianError) as relative:
        discover_folder("relative-folder")
    assert relative.value.code == ErrorCode.ONBOARDING_INPUT_INVALID.value

    with pytest.raises(JiejianError) as missing:
        discover_folder(str(tmp_path / "missing"))
    assert missing.value.code == ErrorCode.ONBOARDING_INPUT_INVALID.value

    file_path = tmp_path / "file.txt"
    file_path.write_text("x", encoding="utf-8")
    with pytest.raises(JiejianError) as not_dir:
        discover_folder(str(file_path.resolve()))
    assert not_dir.value.code == ErrorCode.ONBOARDING_PATH_UNSAFE.value


def test_discovery_rejects_root_symlink_and_skips_child_symlink(
    tmp_path: Path,
) -> None:
    real = tmp_path / "real"
    real.mkdir()
    (real / "package.json").write_text(
        '{"scripts":{"dev":"unsafe"}}', encoding="utf-8"
    )
    root_link = tmp_path / "root-link"
    try:
        root_link.symlink_to(real, target_is_directory=True)
        child_link = real / "linked"
        child_link.symlink_to(tmp_path, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink unavailable: {exc}")

    with pytest.raises(JiejianError) as root_error:
        discover_folder(root_link)
    assert root_error.value.code == ErrorCode.ONBOARDING_PATH_UNSAFE.value
    result = discover_folder(real)
    assert any(item.code == "REPARSE_SKIPPED" for item in result.warnings)


def test_discovery_reparse_policy_is_testable_without_link_privilege(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    child = root / "linked"
    child.mkdir()

    monkeypatch.setattr(discovery, "_is_reparse_point", lambda path: path == root)
    with pytest.raises(JiejianError) as root_error:
        discover_folder(root)
    assert root_error.value.code == ErrorCode.ONBOARDING_PATH_UNSAFE.value

    monkeypatch.setattr(discovery, "_is_reparse_point", lambda path: path == child)
    result = discover_folder(root)
    assert any(item.code == "REPARSE_SKIPPED" for item in result.warnings)


def test_discovery_enforces_file_and_total_read_budgets(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    with pytest.raises(JiejianError) as file_error:
        discover_folder(tmp_path, limits=DiscoveryLimits(max_file_bytes=1))
    assert file_error.value.code == ErrorCode.ONBOARDING_READ_BUDGET.value
    assert file_error.value.to_dict()["message"] == "应用目录内容过多，自动识别已达到安全扫描上限。请确认选择的是项目根目录，或改为手工填写必要信息。"

    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    with pytest.raises(JiejianError) as total_error:
        discover_folder(tmp_path, limits=DiscoveryLimits(max_total_bytes=1))
    assert total_error.value.code == ErrorCode.ONBOARDING_READ_BUDGET.value
    assert total_error.value.to_dict()["message"] == "应用目录内容过多，自动识别已达到安全扫描上限。请确认选择的是项目根目录，或改为手工填写必要信息。"


def test_discovery_rejects_too_many_empty_directories_before_reading_configs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for index in range(257):
        (tmp_path / f"empty-{index:03d}").mkdir()

    def fail_read(*args, **kwargs):
        pytest.fail("配置读取不应在条目预算超限前发生")

    monkeypatch.setattr(discovery.Path, "read_text", fail_read)
    with pytest.raises(JiejianError) as error:
        discover_folder(tmp_path)
    assert error.value.code == ErrorCode.ONBOARDING_READ_BUDGET.value
    assert error.value.to_dict()["message"] == "应用目录内容过多，自动识别已达到安全扫描上限。请确认选择的是项目根目录，或改为手工填写必要信息。"


def test_discovery_counts_mixed_entries_once_at_boundary(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    (tmp_path / ".env.local").write_text("TOKEN=secret", encoding="utf-8")
    (tmp_path / "ignored.txt").write_text("ignored", encoding="utf-8")
    for index in range(253):
        (tmp_path / f"empty-{index:03d}").mkdir()

    assert discover_folder(tmp_path, limits=DiscoveryLimits(max_entries=256))
    with pytest.raises(JiejianError) as error:
        discover_folder(tmp_path, limits=DiscoveryLimits(max_entries=255))
    assert error.value.code == ErrorCode.ONBOARDING_READ_BUDGET.value
    assert error.value.to_dict()["message"] == "应用目录内容过多，自动识别已达到安全扫描上限。请确认选择的是项目根目录，或改为手工填写必要信息。"
