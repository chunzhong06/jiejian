# 验证文档生成器的 AST 隔离、稳定输出和生成区收敛。

import re
from pathlib import Path

import pytest

from scripts.docs.generate import generate


_HIGH_VALUE_GUIDES = (
    "修改API与控制面.md",
    "修改Recording.md",
    "修改安全准备.md",
    "修改权限判断.md",
    "修改测试账号.md",
    "修改模型服务.md",
    "修改发布与便携版.md",
    "修改官方示例与整链验收.md",
    "修改开发环境.md",
    "修改前端.md",
    "修改Observer.md",
    "修改Worker与Runner.md",
    "修改Web执行.md",
    "修改结果与报告.md",
)
_MODULE_GUIDES = (
    "backend.md",
    "frontend.md",
    "protocols.md",
    "recording.md",
    "runtime.md",
    "scripts.md",
    "storage.md",
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
    (tmp_path / "docs/03_参考手册/代码").mkdir(parents=True)
    (tmp_path / "docs/03_参考手册/协议").mkdir(parents=True)
    (tmp_path / "docs/llms.txt").write_text("→ docs/03_参考手册/协议/公共数据与Schema版本.md\n", encoding="utf-8")
    (tmp_path / "docs/03_参考手册/协议/公共数据与Schema版本.md").write_text("# 协议版本\n", encoding="utf-8")
    return tmp_path


def test_generator_parses_source_without_importing_production(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    source = root / "product/backend/core/evil.py"
    source.write_text(
        "from pathlib import Path\nPath('imported-marker').write_text('bad')\n\nclass PublicThing: ...\n\ndef public_function(value: str) -> int: return 1\n",
        encoding="utf-8",
    )

    generate(root, update=True)

    reference = (root / "docs/03_参考手册/代码/backend-core.md").read_text(encoding="utf-8")
    assert "PublicThing" in reference
    assert "public_function(value) -> int" in reference
    assert not (root / "imported-marker").exists()


def test_generator_update_is_byte_stable(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    (root / "product/backend/core/sample.py").write_text("PUBLIC_VALUE = 1\n", encoding="utf-8")

    generate(root, update=True)
    first = {
        path: path.read_bytes()
        for path in (root / "docs/03_参考手册").rglob("*.md")
    }
    assert generate(root, update=False) == []
    generate(root, update=True)
    second = {
        path: path.read_bytes()
        for path in (root / "docs/03_参考手册").rglob("*.md")
    }
    assert first == second


def test_generator_rejects_and_repairs_duplicate_code_reference_header(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    (root / "product/backend/core/sample.py").write_text("PUBLIC_VALUE = 1\n", encoding="utf-8")
    generate(root, update=True)
    reference = root / "docs/03_参考手册/代码/backend-core.md"
    header = "# 自动代码参考：后端 Core\n\n> 生成区域只描述当前代码结构；职责与安全理由由模块参考和任务指南维护。\n\n"
    reference.write_text(header * 2 + reference.read_text(encoding="utf-8"), encoding="utf-8")

    with pytest.raises(SystemExit, match="代码参考漂移"):
        generate(root, update=False)

    generate(root, update=True)
    assert reference.read_text(encoding="utf-8").count("# 自动代码参考：后端 Core") == 1
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
    reference = (root / "docs/03_参考手册/代码/scripts.md").read_text(encoding="utf-8")
    assert "function Invoke-Sample" in reference
    assert "param $Mode" in reference
    assert "param $Force" in reference
    assert "./shared.ps1" in reference
    assert "$PSScriptRoot/dev/common.ps1" in reference
    assert "(Join-Path" not in reference
    assert "startup/$module" not in reference


def test_generator_aggregates_api_and_cli_sources(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    api = root / "product/backend/api"
    cli = root / "product/backend/cli"
    api.mkdir(parents=True)
    cli.mkdir(parents=True)
    (api / "routes.py").write_text("def public_api(): ...\n", encoding="utf-8")
    (cli / "commands.py").write_text("def public_cli(): ...\n", encoding="utf-8")

    generate(root, update=True)
    reference = (root / "docs/03_参考手册/代码/backend-api-cli.md").read_text(encoding="utf-8")
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
    guide = root / "docs/02_开发指南/任务" / guide_name
    text = guide.read_text(encoding="utf-8")
    marker = "## 快速找到修改位置"
    assert marker in text, f"{guide_name} 缺少快速修改地图"
    section = text.split(marker, 1)[1].split("\n## ", 1)[0]
    declared = _declared_repository_paths(root, section)

    assert declared, f"{guide_name} 没有声明可检查的静态仓库位置"
    missing = [value for value, path in declared if not path.exists()]
    assert missing == [], f"{guide_name} 包含不存在的仓库位置：{missing}"


@pytest.mark.parametrize("guide_name", _MODULE_GUIDES)
def test_module_guides_keep_scripts_guide_navigation_quality(guide_name: str) -> None:
    """模块 Guide 必须保持 scripts.md 级别的职责、修改路由和验证密度。"""

    root = Path(__file__).parents[2]
    guide = root / "docs/02_开发指南/模块" / guide_name
    text = guide.read_text(encoding="utf-8")
    required_markers = (
        "> 状态：CURRENT。",
        "## 职责",
        "## 非职责",
        "## 稳定入口",
        "## 我想修改什么",
        "## 必须保持的边界",
        "## 直接验证",
    )
    missing_markers = [marker for marker in required_markers if marker not in text]
    assert missing_markers == [], f"{guide_name} 缺少模块导航结构：{missing_markers}"
    assert text.count("| ---") >= 2, f"{guide_name} 缺少边界表或修改路由表"
    route_section = text.split("## 我想修改什么", 1)[1].split("\n## ", 1)[0]
    route_rows = [
        line
        for line in route_section.splitlines()
        if line.startswith("| ") and not line.startswith(("| ---", "| 任务"))
    ]
    assert len(route_rows) >= 5, f"{guide_name} 修改路由不足"
    assert text.count("\n- ") >= 5, f"{guide_name} 硬边界不足"
    assert "dev.ps1" in text, f"{guide_name} 没有给出受控验证入口"

    declared = _declared_repository_paths(root, text)
    assert declared, f"{guide_name} 没有声明可检查的静态仓库位置"
    missing = sorted({value for value, path in declared if not path.exists()})
    assert missing == [], f"{guide_name} 包含不存在的仓库位置：{missing}"


def test_observer_sqlite_knowledge_route_reaches_current_owner() -> None:
    """SQLite Observer 必须能从最小路由追到当前 Guide、Reference、实现和测试。"""

    root = Path(__file__).parents[2]
    routes = (root / "docs/llms.txt").read_text(encoding="utf-8")
    guide = (root / "docs/02_开发指南/任务/修改Observer.md").read_text(encoding="utf-8")
    reference = (root / "docs/03_参考手册/协议/Observer观察协议.md").read_text(encoding="utf-8")
    assert "docs/02_开发指南/任务/修改Observer.md" in routes
    assert "docs/03_参考手册/协议/Observer观察协议.md" in routes
    for value in (
        "product/backend/infra/observers/sqlite.py",
        "tests/backend/infra/observers/",
    ):
        assert value in guide or value in reference
        assert (root / value).exists()


def test_observer_reference_exposes_corroborating_channels_owner() -> None:
    """Reference 必须把佐证角色字段追到当前公共协议与装配实现。"""

    root = Path(__file__).parents[2]
    reference = (root / "docs/03_参考手册/协议/Observer观察协议.md").read_text(encoding="utf-8")
    assert "corroborating_channels" in reference
    for value in (
        "product/protocols/execution.py",
        "product/backend/workflows/security_setup/local_observer_wiring.py",
    ):
        assert value in reference
        assert (root / value).exists()


def test_observer_reference_exposes_failure_to_inconclusive_trace() -> None:
    """Reference 必须把观察失败到三态判断的实现和测试链路说清。"""

    root = Path(__file__).parents[2]
    reference = (root / "docs/03_参考手册/协议/Observer观察协议.md").read_text(encoding="utf-8")
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
    guide = (root / "docs/02_开发指南/任务/修改发布与便携版.md").read_text(encoding="utf-8")
    reference = (root / "docs/03_参考手册/协议/Portable运行身份与发行结构.md").read_text(encoding="utf-8")
    assert "docs/03_参考手册/协议/Portable运行身份与发行结构.md" in routes
    for fact in ("start.cmd", "runtime/start.ps1", "runtime/python", "JIEJIAN_RUNTIME_MODE=portable"):
        assert fact in guide
        assert fact in reference
    for value in (
        "scripts/build/portable.py",
        "product/backend/infra/runtime/process/identity.py",
        "product/backend/infra/runtime/process/environment.py",
        "tests/scripts/test_portable.py",
    ):
        assert value in guide or value in reference
        assert (root / value).exists()
