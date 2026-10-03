# 验证文档生成器的 AST 隔离、稳定输出、阅读路由与当前事实检查。

import re
from pathlib import Path

import pytest

from scripts.docs.generate import generate


_HIGH_VALUE_GUIDES = (
    '能力/控制面/修改API与装配.md',
    '能力/账号与材料/修改录制.md',
    '能力/账号与材料/修改材料与恢复.md',
    '能力/检查执行/修改权限判断.md',
    '能力/账号与材料/修改测试账号.md',
    '能力/控制面/修改模型服务.md',
    '工程/运行与交付/修改发布与便携版.md',
    '能力/应用接入/修改官方示例.md',
    '工程/运行与交付/环境与脚本.md',
    '工程/前端/修改前端.md',
    '工程/数据与协议/修改数据库.md',
    '能力/结果与变化/修改变化登记与交付.md',
    '能力/检查执行/修改Observer.md',
    '能力/检查执行/修改Worker与Runner.md',
    '能力/检查执行/修改Web执行.md',
    '能力/结果与变化/修改结果与修复.md',
)
_ROOT_GUIDE_PATHS = frozenset(
    {
        "environment.yml",
        "jiejian.code-workspace",
        "pnpm-lock.yaml",
        "pyproject.toml",
        "uv.lock",
    }
)
_REPOSITORY_PATH = re.compile(
    r"`((?:(?:product|samples|scripts|tests)/[^`]+)|(?:src/[^`]+)|"
    r"(?:environment\.yml|jiejian\.code-workspace|pnpm-lock\.yaml|pyproject\.toml|uv\.lock))`"
)


def _declared_repository_paths(root: Path, text: str) -> list[tuple[str, Path]]:
    """把文档中的确定性仓库路径解析成可做存在性检查的真实位置。"""

    declared: list[tuple[str, Path]] = []
    for value in _REPOSITORY_PATH.findall(text):
        value = value.split("::", 1)[0]
        # 通配符和动态运行路径不是可确定验证的仓库位置，不进入存在性门禁。
        if any(character in value for character in "*?[]{}"):
            continue
        if value.startswith("src/"):
            resolved = root / "product/frontend" / value
        elif value in _ROOT_GUIDE_PATHS or value.startswith(
            ("product/", "samples/", "scripts/", "tests/")
        ):
            resolved = root / value
        else:
            continue
        declared.append((value, resolved))
    return declared


def _fixture_root(tmp_path: Path) -> Path:
    (tmp_path / "product/backend/core").mkdir(parents=True)
    (tmp_path / "product/protocols/schemas").mkdir(parents=True)
    (tmp_path / "docs/参考/生成").mkdir(parents=True)
    (tmp_path / "docs/工程/数据与协议").mkdir(parents=True)
    (tmp_path / "docs/llms.txt").write_text("→ docs/工程/数据与协议/公共数据与Schema版本.md\n", encoding="utf-8")
    (tmp_path / "docs/工程/数据与协议/公共数据与Schema版本.md").write_text("# 协议版本\n", encoding="utf-8")
    return tmp_path


def test_chapter_links_and_routes_ignore_fenced_headings(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    target = root / "docs/章节.md"
    target.write_text("# 章节\n## 4. 范围 × 程度\n## 重复\n## 重复\n```md\n## 不存在\n```\n", encoding="utf-8")
    (root / "docs/llms.txt").write_text("→ docs/章节.md#4-范围--程度\n", encoding="utf-8")
    link = root / "docs/入口.md"
    link.write_text("[重复](章节.md#重复-1)\n", encoding="utf-8")
    generate(root, update=True)
    assert generate(root, update=False) == []
    link.write_text("[错误](章节.md#不存在)\n", encoding="utf-8")
    before = {p: p.read_bytes() for p in (root / "docs").rglob("*") if p.is_file()}
    with pytest.raises(SystemExit, match="章节锚点不存在"):
        generate(root, update=False)
    assert before == {p: p.read_bytes() for p in before}


def test_source_directory_reference_requires_actual_files(tmp_path: Path) -> None:
    """迁移后残留的空目录不能继续为失效实现说明提供存在性证明。"""
    root = _fixture_root(tmp_path)
    empty = root / "product/backend/workflows/obsolete"
    empty.mkdir(parents=True)
    (root / "docs/入口.md").write_text("实现：`product/backend/workflows/obsolete/`\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="源码目录没有文件"):
        generate(root, update=False)
    (empty / "service.py").write_text("# 提供此夹具声明的实现。\n", encoding="utf-8")
    generate(root, update=True)
    assert generate(root, update=False) == []


@pytest.mark.parametrize("state", ["提议", "已取代", "已废弃", "已拒绝", "PROPOSED"])
def test_default_route_rejects_noncurrent_decisions(tmp_path: Path, state: str) -> None:
    root = _fixture_root(tmp_path)
    (root / "docs/提议.md").write_text(f"# 设计\n\n> 状态：{state}。\n", encoding="utf-8")
    (root / "docs/llms.txt").write_text("→ docs/提议.md\n", encoding="utf-8")
    generate(root, update=True)
    with pytest.raises(SystemExit, match="默认路由指向非当前内容"):
        generate(root, update=False)


def test_static_source_path_outside_quick_map_is_checked(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    guide = root / "docs/说明.md"
    guide.write_text("# 说明\n\n正文指向 `product/backend/core/missing.py`。\n", encoding="utf-8")
    generate(root, update=True)
    with pytest.raises(SystemExit, match="静态源码路径"):
        generate(root, update=False)
    (root / "product/backend/core/current.py").write_text("VALUE = 1\n", encoding="utf-8")
    generate(root, update=True)
    guide.write_text("# 说明\n\n来源 `product/backend/core/current.py::VALUE`。包内 `./product/frontend/dist`。\n\n示例 `tests/<case>.py` 和 `tests/test_*.py`。\n```text\n`product/missing.py`\n```\n", encoding="utf-8")
    assert generate(root, update=False) == []


def test_database_head_checked_without_executing_module(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    source = root / "product/backend/infra/storage/db.py"
    source.parent.mkdir(parents=True)
    source.write_text("raise RuntimeError('不得执行')\n_CURRENT_MIGRATION_REVISION = '0007_test'\n", encoding="utf-8")
    guide = root / "docs/工程/数据与协议/修改数据库.md"
    guide.parent.mkdir(parents=True, exist_ok=True)
    guide.write_text("当前数据库 head 为 `0006_old`。\n", encoding="utf-8")
    generate(root, update=True)
    with pytest.raises(SystemExit, match="数据库 head 与源码声明不一致"):
        generate(root, update=False)
    guide.write_text("当前数据库 head 为 `0007_test`。\n", encoding="utf-8")
    assert generate(root, update=False) == []


def test_generator_parses_source_without_importing_production(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    source = root / "product/backend/core/evil.py"
    source.write_text(
        "from pathlib import Path\nPath('imported-marker').write_text('bad')\n\nclass PublicThing: ...\n\ndef public_function(value: str) -> int: return 1\n",
        encoding="utf-8",
    )

    generate(root, update=True)

    reference = (root / "docs/参考/生成/代码/backend/core/_root.md").read_text(encoding="utf-8")
    assert "PublicThing" in reference
    assert "public_function(value) -> int" in reference
    assert not (root / "imported-marker").exists()


def test_generator_update_is_byte_stable(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    (root / "product/backend/core/sample.py").write_text("PUBLIC_VALUE = 1\n", encoding="utf-8")

    generate(root, update=True)
    first = {
        path: path.read_bytes()
        for path in (root / "docs/参考").rglob("*.md")
    }
    assert generate(root, update=False) == []
    generate(root, update=True)
    second = {
        path: path.read_bytes()
        for path in (root / "docs/参考").rglob("*.md")
    }
    assert first == second


def test_generator_rejects_and_repairs_duplicate_code_reference_header(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    (root / "product/backend/core/sample.py").write_text("PUBLIC_VALUE = 1\n", encoding="utf-8")
    generate(root, update=True)
    reference = root / "docs/参考/生成/代码/backend/core/_root.md"
    header = "# 自动代码参考：backend/core/_root\n\n> 生成区域只描述当前代码结构；职责与安全理由由能力映射和任务指南维护。\n\n"
    reference.write_text(header * 2 + reference.read_text(encoding="utf-8"), encoding="utf-8")

    with pytest.raises(SystemExit, match="代码参考漂移"):
        generate(root, update=False)

    generate(root, update=True)
    assert reference.read_text(encoding="utf-8").count("# 自动代码参考：backend/core/_root") == 1
    assert generate(root, update=False) == []


def test_generator_checks_root_agents_links(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    (root / "AGENTS.md").write_text("[失效入口](docs/missing.md)\n", encoding="utf-8")
    generate(root, update=True)

    with pytest.raises(SystemExit, match="AGENTS.md -> docs/missing.md"):
        generate(root, update=False)


def test_generator_extracts_powershell_functions_params_and_dot_sources(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    scripts = root / "scripts"
    scripts.mkdir()
    (scripts / "sample.ps1").write_text(
        "param(\n"
        "    [ValidateSet('a', 'b')]\n"
        "    [string]$Mode,\n"
        "    [switch]$Force\n"
        ")\n"
        ". './shared.ps1'\n"
        ". (Join-Path $PSScriptRoot \"dev\\common.ps1\")\n"
        ". (Join-Path $PSScriptRoot \"startup\\$module\")\n"
        "function Invoke-Sample {}\n",
        encoding="utf-8",
    )

    generate(root, update=True)
    reference = (root / "docs/参考/生成/代码/scripts/_root.md").read_text(encoding="utf-8")
    assert "function Invoke-Sample" in reference
    assert "param $Mode" in reference
    assert "param $Force" in reference
    assert "./shared.ps1" in reference
    assert "$PSScriptRoot/dev/common.ps1" in reference
    assert "(Join-Path" not in reference
    assert "startup/$module" not in reference


def test_generator_indexes_api_and_cli_in_separate_readable_parts(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    api = root / "product/backend/api"
    cli = root / "product/backend/cli"
    api.mkdir(parents=True)
    cli.mkdir(parents=True)
    (api / "routes.py").write_text("def public_api(): ...\n", encoding="utf-8")
    (cli / "commands.py").write_text("def public_cli(): ...\n", encoding="utf-8")

    generate(root, update=True)
    reference = (root / "docs/参考/生成/代码/backend/api/_root.md").read_text(encoding="utf-8") + (root / "docs/参考/生成/代码/backend/cli.md").read_text(encoding="utf-8")
    assert "product/backend/api/routes.py" in reference
    assert "public_api()" in reference
    assert "product/backend/cli/commands.py" in reference
    assert "public_cli()" in reference


def test_dev_script_exposes_read_only_and_update_docs_commands() -> None:
    script = Path(__file__).parents[2] / "scripts/dev.ps1"
    text = script.read_text(encoding="utf-8-sig")
    assert '"docs"' in text
    assert "Invoke-Docs" in text
    assert "-Update 只允许与 schema 或 docs 命令一起使用" in text


@pytest.mark.parametrize("guide_name", _HIGH_VALUE_GUIDES)
def test_high_value_guide_quick_map_repository_paths_exist(guide_name: str) -> None:
    """高价值 Guide 的快速修改地图不得把开发者指向不存在的静态仓库位置。"""

    root = Path(__file__).parents[2]
    guide = root / "docs" / guide_name
    text = guide.read_text(encoding="utf-8")
    marker = "## 快速找到修改位置"
    assert marker in text, f"{guide_name} 缺少快速修改地图"
    section = text.split(marker, 1)[1].split("\n## ", 1)[0]
    declared = _declared_repository_paths(root, section)

    assert declared, f"{guide_name} 没有声明可检查的静态仓库位置"
    missing = [value for value, path in declared if not path.exists()]
    assert missing == [], f"{guide_name} 包含不存在的仓库位置：{missing}"


def test_capability_map_points_to_real_owners_and_tests() -> None:
    """能力地图的静态实现与测试入口必须存在，不强制机械标题或条数。"""
    root = Path(__file__).parents[2]
    text = (root / "docs/总览/功能地图.md").read_text(encoding="utf-8")
    declared = _declared_repository_paths(root, text)
    assert declared
    assert [value for value, path in declared if not path.exists()] == []
    assert "tests/backend/core/" in text
    assert "tests/backend/workflows/" in text
    assert "tests/backend/infra/runtime/" in text


def test_observer_sqlite_knowledge_route_reaches_current_owner() -> None:
    """SQLite Observer 必须能从最小路由追到当前 Guide、Reference、实现和测试。"""

    root = Path(__file__).parents[2]
    routes = (root / "docs/llms.txt").read_text(encoding="utf-8")
    guide = (root / "docs/能力/检查执行/修改Observer.md").read_text(encoding="utf-8")
    reference = (root / "docs/能力/检查执行/协议/Observer观察协议.md").read_text(encoding="utf-8")
    assert "docs/能力/检查执行/修改Observer.md" in routes
    assert "docs/能力/检查执行/协议/Observer观察协议.md" in routes
    for value in (
        "product/backend/infra/observers/adapters/sqlite.py",
        "tests/backend/infra/observers/",
    ):
        assert value in guide or value in reference
        assert (root / value).exists()


def test_observer_reference_exposes_corroborating_channels_owner() -> None:
    """Reference 必须把佐证角色字段追到当前公共协议与装配实现。"""

    root = Path(__file__).parents[2]
    reference = (root / "docs/能力/检查执行/协议/Observer观察协议.md").read_text(encoding="utf-8")
    assert "corroborating_channels" in reference
    for value in (
        "product/protocols/runner/execution.py",
        "product/backend/workflows/checks/local_observer_wiring.py",
    ):
        assert value in reference
        assert (root / value).exists()


def test_observer_reference_exposes_failure_to_inconclusive_trace() -> None:
    """Reference 必须把观察失败到三态判断的实现和测试链路说清。"""

    root = Path(__file__).parents[2]
    reference = (root / "docs/能力/检查执行/协议/Observer观察协议.md").read_text(encoding="utf-8")
    assert "失败为什么只能 INCONCLUSIVE" in reference
    for value in (
        "product/protocols/observer/result.py",
        "product/backend/core/verification/permissions/evaluation.py",
        "tests/protocols/observer/test_observer_result.py",
        "tests/backend/core/verification/permissions/test_evaluation.py",
    ):
        assert value in reference
        assert (root / value).exists()


def test_portable_python_knowledge_route_reaches_builder_and_identity() -> None:
    """Portable Python 启动必须能从路由追到 Guide、Reference、builder 与身份校验。"""

    root = Path(__file__).parents[2]
    routes = (root / "docs/llms.txt").read_text(encoding="utf-8")
    guide = (root / "docs/工程/运行与交付/修改发布与便携版.md").read_text(encoding="utf-8")
    reference = (root / "docs/工程/运行与交付/Portable运行身份与发行结构.md").read_text(encoding="utf-8")
    assert "docs/工程/运行与交付/Portable运行身份与发行结构.md" in routes
    for fact in ("start.cmd", "runtime/start.ps1", "runtime/python", "JIEJIAN_RUNTIME_MODE=portable"):
        assert fact in guide
        assert fact in reference
    for value in (
        "scripts/build/portable.py",
        "product/backend/infra/runtime/process/controlled/identity.py",
        "product/backend/infra/runtime/process/environment.py",
        "tests/scripts/test_portable.py",
    ):
        assert value in guide or value in reference
        assert (root / value).exists()
