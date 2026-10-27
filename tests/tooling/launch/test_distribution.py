# 验证 Windows x64 Portable 的单一 Base Tree、离线相对启动、双包组成与仓库外真实烟测。
from __future__ import annotations

import zipfile
from pathlib import Path
import pytest
from product.backend import __version__
from scripts.build.archive import write_zip, archive_content
from scripts.build.runtime import prune_installed_runtime, runtime_environment
from scripts.build.validation import validate_tree_content
from scripts.build.resources import write_runtime_files

ROOT = Path(__file__).parents[3]
RELEASE_NAME = f"JieJian-WebV1-{__version__}-Windows-x64"

def test_full_and_nosamples_archives_share_exact_product_tree(tmp_path: Path) -> None:
    base = tmp_path / "base"
    samples = tmp_path / "samples"
    (base / "runtime").mkdir(parents=True)
    (base / "界鉴.exe").write_bytes(b'MZ')
    (base / "app").mkdir()
    (base / "app" / "release.json").write_text("{}", encoding="ascii")
    (samples / "digital_gallery").mkdir(parents=True)
    (samples / "digital_gallery" / "sample.json").write_text("{}", encoding="ascii")
    full = tmp_path / "full.zip"
    nosamples = tmp_path / "nosamples.zip"

    write_zip(full, base, samples)
    write_zip(nosamples, base, None)

    assert archive_content(full, without_samples=False) == archive_content(
        nosamples, without_samples=True
    )
    with zipfile.ZipFile(full) as archive:
        assert f"{RELEASE_NAME}/samples/digital_gallery/sample.json" in archive.namelist()
    with zipfile.ZipFile(nosamples) as archive:
        assert all("/samples/" not in name for name in archive.namelist())

def test_portable_tree_rejects_repository_paths_and_local_wheel_metadata(tmp_path: Path) -> None:
    base = tmp_path / "base"
    site_packages = base / "runtime" / "python" / "Lib" / "site-packages"
    site_packages.mkdir(parents=True)
    leaked = base / "runtime" / "leak.txt"
    leaked.write_text(str(ROOT.resolve()), encoding="utf-8")

    with pytest.raises(RuntimeError, match="泄漏构建仓库绝对路径"):
        validate_tree_content(base, ROOT)

    leaked.unlink()
    direct_url = site_packages / "jiejian-1.0.16.dist-info" / "direct_url.json"
    direct_url.parent.mkdir()
    direct_url.write_text("{}", encoding="ascii")
    with pytest.raises(RuntimeError, match="direct_url"):
        validate_tree_content(base, ROOT)

def test_portable_runtime_prunes_dependency_tests_and_generated_python_artifacts(
    tmp_path: Path,
) -> None:
    python = tmp_path / "runtime" / "python" / "python.exe"
    site_packages = python.parent / "Lib" / "site-packages"
    dependency_tests = site_packages / "dependency" / "tests"
    dependency_tests.mkdir(parents=True)
    (dependency_tests / "test_runtime.py").write_text("raise AssertionError", encoding="utf-8")
    metadata = site_packages / "jiejian-1.0.16.dist-info"
    metadata.mkdir()
    (metadata / "direct_url.json").write_text("{}", encoding="ascii")
    cache = site_packages / "dependency" / "__pycache__"
    cache.mkdir()
    (cache / "runtime.pyc").write_bytes(b"cache")
    runtime_module = site_packages / "dependency" / "runtime.py"
    runtime_module.write_text("VALUE = 1", encoding="ascii")

    prune_installed_runtime(python)

    assert not dependency_tests.exists()
    assert not (metadata / "direct_url.json").exists()
    assert not cache.exists()
    assert runtime_module.is_file()

def test_portable_build_owns_its_temporary_directory(
    tmp_path: Path,
) -> None:
    temporary = tmp_path / "release" / "build" / "temp"

    environment = runtime_environment(tmp_path / "uv-cache", temporary)

    assert environment["TEMP"] == str(temporary.resolve())
    assert environment["TMP"] == str(temporary.resolve())
    assert temporary.is_dir()


def test_release_resources_use_product_launcher_and_single_guide(tmp_path):
    project = tmp_path / 'project'
    launcher = project / 'product/launcher/windows'
    (launcher / 'licenses').mkdir(parents=True)
    startup = '# 固定发行启动入口。\nWrite-Output ready\n'
    (launcher / 'start.ps1').write_text(startup, encoding='utf-8-sig')
    (launcher / 'licenses/NOTICE.txt').write_text('license fixture', encoding='utf-8')
    guide = project / 'docs/产品/便携版使用.md'
    guide.parent.mkdir(parents=True)
    guide.write_text('# 使用说明\n\n## 退出\n\n使用左侧退出入口。\n', encoding='utf-8')
    base = tmp_path / 'release'
    base.mkdir()
    metadata = dict(wheel_version=__version__, python_version='3.13.13',
        playwright_version='1.61.0', chromium_revision='1234',
        node_version='24.19.0', node_sha256='a' * 64)

    write_runtime_files(base, metadata, project)

    readme = (base / 'README.txt').read_text('utf-8-sig')
    assert readme == (base / 'docs/使用说明.txt').read_text('utf-8-sig')
    assert '使用左侧退出入口。' in readme
    assert (base / 'app/start.ps1').read_text('utf-8-sig') == startup
    assert (base / 'docs/NOTICE.txt').read_text('utf-8') == 'license fixture'
    guide.write_text('# 使用说明\n\n更新后的操作指引。\n', encoding='utf-8')
    write_runtime_files(base, metadata, project)
    assert '更新后的操作指引。' in (base / 'README.txt').read_text('utf-8-sig')

pytestmark = [pytest.mark.level3]
