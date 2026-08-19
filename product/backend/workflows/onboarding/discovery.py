# =============================================================================
# 受限目录识别
#
# 定位
# 用户选择目录进入项目识别结果前的只读文件系统安全边界。
#
# 职责
# 规范根路径｜执行 allowlist 与预算检查｜提取技术提示、启动候选和缺项
#
# 边界
# 不执行命令、不联网、不读取源码正文或秘密，并拒绝重解析点逃逸与超预算遍历。
#
# 调用链
# OnboardingWorkflow.inspect → discover_folder → DiscoveryResult
# =============================================================================

from __future__ import annotations

import json
import os
import re
import stat
import tomllib
from pathlib import Path
from typing import Any

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.workflows.onboarding.models import DiscoveryCandidate, DiscoveryHint, DiscoveryLimits, DiscoveryMissingItem, DiscoveryResult, DiscoveryWarning


_ALLOWED_NAMES = {
    "angular.json",
    "astro.config.js",
    "astro.config.mjs",
    "astro.config.ts",
    "docker-compose.yml",
    "docker-compose.yaml",
    "environment.yml",
    "environment.yaml",
    "manage.py",
    "next.config.js",
    "next.config.mjs",
    "next.config.ts",
    "nuxt.config.js",
    "nuxt.config.ts",
    "npm-shrinkwrap.json",
    "openapi.json",
    "openapi.yaml",
    "openapi.yml",
    "package-lock.json",
    "package.json",
    "pipfile",
    "pipfile.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
    "pyproject.toml",
    "requirements-dev.txt",
    "requirements.txt",
    "swagger.json",
    "swagger.yaml",
    "swagger.yml",
    "uv.lock",
    "vite.config.js",
    "vite.config.mjs",
    "vite.config.ts",
    "yarn.lock",
}
_AUTH_DEPENDENCY_MARKERS = (
    "auth",
    "bcrypt",
    "django-allauth",
    "fastapi-users",
    "flask-login",
    "jsonwebtoken",
    "next-auth",
    "passport",
    "session",
    "argon2",
)
_SCRIPT_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9:_-]{0,63}$")
_IGNORED_DIRECTORY_NAMES = frozenset(
    {
        "node_modules",
        ".git",
        ".venv",
        "venv",
        "dist",
        "build",
        ".next",
        ".nuxt",
        ".cache",
        "coverage",
        "__pycache__",
        ".pnpm-store",
        ".hg",
        ".svn",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".tox",
        "htmlcov",
    }
)
_READ_BUDGET_MESSAGE = "应用目录内容过多，自动识别已达到安全扫描上限。请确认选择的是项目根目录，或改为手工填写必要信息。"


def _is_reparse_point(path: Path) -> bool:
    if path.is_symlink():
        return True
    is_junction = getattr(os.path, "isjunction", None)
    if is_junction is not None and is_junction(path):
        return True
    attributes = getattr(os.lstat(path), "st_file_attributes", 0)
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def _invalid_path(message: str = "应用文件夹路径无效") -> JiejianError:
    return JiejianError(ErrorCode.ONBOARDING_INPUT_INVALID, message)


def _safe_source(name: str) -> str:
    return name[:128]


def _read_budget_error() -> JiejianError:
    return JiejianError(ErrorCode.ONBOARDING_READ_BUDGET, _READ_BUDGET_MESSAGE)


def _hint(detail: str, source: str) -> DiscoveryHint:
    return DiscoveryHint(detail=detail, source=_safe_source(source))


def _missing_items(has_start_candidate: bool) -> tuple[DiscoveryMissingItem, ...]:
    startup_state = "待确认" if has_start_candidate else "缺少"
    return (
        DiscoveryMissingItem(
            key="startup",
            label="应用启动方式",
            state=startup_state,
            reason="识别结果只提供候选，启动命令必须由你确认",
        ),
        DiscoveryMissingItem(
            key="target_address",
            label="允许检查哪些地址",
            state="缺少",
            reason="未自动确认目标地址或公网范围",
        ),
        DiscoveryMissingItem(
            key="test_accounts",
            label="测试账号有哪些",
            state="缺少",
            reason="不会从文件读取账号、令牌或秘密",
        ),
        DiscoveryMissingItem(
            key="authorized_scope",
            label="授权范围",
            state="缺少",
            reason="需要你明确允许检查的地址和边界",
        ),
        DiscoveryMissingItem(
            key="recovery",
            label="检查后怎样恢复数据",
            state="缺少",
            reason="不会自动推断或执行重置、删除和回滚操作",
        ),
    )


def _parse_json(path: Path, content: str) -> dict[str, Any] | None:
    try:
        value = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _parse_pyproject(content: str) -> dict[str, Any] | None:
    try:
        value = tomllib.loads(content)
    except (UnicodeDecodeError, tomllib.TOMLDecodeError):
        return None
    return value if isinstance(value, dict) else None


def canonical_folder(path: str | Path) -> Path:
    """解析现有绝对目录，并拒绝根路径本身是链接或重解析点。"""

    raw_path = Path(path)
    if not raw_path.is_absolute():
        raise _invalid_path("应用文件夹必须使用绝对路径")
    try:
        if _is_reparse_point(raw_path):
            raise JiejianError(ErrorCode.ONBOARDING_PATH_UNSAFE, "应用文件夹不能是链接或重解析点")
        root = raw_path.resolve(strict=True)
        if _is_reparse_point(root) or not root.is_dir():
            raise JiejianError(ErrorCode.ONBOARDING_PATH_UNSAFE, "应用文件夹路径不安全")
        return root
    except JiejianError:
        raise
    except (OSError, RuntimeError, ValueError) as exc:
        raise _invalid_path() from exc


def discover_folder(path: str | Path, *, limits: DiscoveryLimits | None = None) -> DiscoveryResult:
    """在 allowlist、深度、条目数和字节预算内识别项目元数据。"""

    limits = limits or DiscoveryLimits()
    root = canonical_folder(path)

    detected: set[str] = set()
    config_hints: list[DiscoveryHint] = []
    interface_hints: list[DiscoveryHint] = []
    auth_hints: list[DiscoveryHint] = []
    warnings: list[DiscoveryWarning] = []
    candidates: list[DiscoveryCandidate] = []
    package_data: dict[str, Any] | None = None
    dependency_names: set[str] = set()
    package_manager = "npm"
    total_bytes = 0
    entry_count = 0
    env_present = False

    def warning(code: str, message: str) -> None:
        item = DiscoveryWarning(code=code, message=message)
        if item not in warnings:
            warnings.append(item)

    def read_allowed(file_path: Path) -> str | None:
        nonlocal total_bytes
        try:
            if _is_reparse_point(file_path):
                warning("REPARSE_SKIPPED", "发现链接或重解析点，已跳过相关条目")
                return None
            canonical = file_path.resolve(strict=True)
            if canonical != root and root not in canonical.parents:
                raise JiejianError(ErrorCode.ONBOARDING_PATH_UNSAFE, "应用文件夹路径不安全")
            size = canonical.stat().st_size
        except JiejianError:
            raise
        except (OSError, RuntimeError, ValueError):
            warning("READ_SKIPPED", "有文件无法读取，已跳过，不影响其他识别结果")
            return None
        if size > limits.max_file_bytes or total_bytes + size > limits.max_total_bytes:
            raise _read_budget_error()
        total_bytes += size
        try:
            return canonical.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            warning("READ_SKIPPED", "有配置文件无法按 UTF-8 读取，已跳过")
            return None

    # --- 阶段：按预算遍历文件名并只读取允许的配置文件 ---
    stack: list[tuple[Path, int]] = [(root, 0)]
    while stack:
        directory, depth = stack.pop()
        try:
            entries: list[os.DirEntry[str]] = []
            with os.scandir(directory) as scanner:
                for entry in scanner:
                    entry_count += 1
                    if entry_count > limits.max_entries:
                        raise _read_budget_error()
                    entries.append(entry)
            entries.sort(key=lambda item: item.name.lower())
        except JiejianError:
            raise
        except OSError:
            warning("READ_SKIPPED", "有目录无法读取，已跳过")
            continue
        for entry in entries:
            entry_path = Path(entry.path)
            try:
                if _is_reparse_point(entry_path):
                    warning("REPARSE_SKIPPED", "发现链接或重解析点，已跳过相关条目")
                    continue
                if entry.is_dir(follow_symlinks=False):
                    if entry.name.casefold() in _IGNORED_DIRECTORY_NAMES:
                        continue
                    if depth >= limits.max_depth:
                        warning("DEPTH_LIMIT", "已达到目录识别深度上限")
                    else:
                        stack.append((entry_path, depth + 1))
                    continue
                if not entry.is_file(follow_symlinks=False):
                    continue
            except OSError:
                warning("READ_SKIPPED", "有文件系统条目无法读取，已跳过")
                continue

            filename = entry.name
            lower_name = filename.lower()
            if lower_name == ".env" or lower_name.startswith(".env."):
                env_present = True
                continue
            if lower_name not in _ALLOWED_NAMES:
                continue

            source = filename
            if lower_name == "package.json":
                content = read_allowed(entry_path)
                if content is not None:
                    package_data = _parse_json(entry_path, content)
                    if package_data is None:
                        warning("UNSUPPORTED_FORMAT", "package.json 格式无法识别")
            elif lower_name == "pyproject.toml":
                content = read_allowed(entry_path)
                if content is not None:
                    pyproject = _parse_pyproject(content)
                    if pyproject is None:
                        warning("UNSUPPORTED_FORMAT", "pyproject.toml 格式无法识别")
                    else:
                        project = pyproject.get("project")
                        if isinstance(project, dict):
                            dependency_names.update(str(item).lower() for item in project.get("dependencies", ()) if isinstance(item, str))
            elif lower_name in {"openapi.json", "swagger.json"}:
                content = read_allowed(entry_path)
                document = _parse_json(entry_path, content or "") if content is not None else None
                if document and ("openapi" in document or "swagger" in document):
                    interface_hints.append(_hint("发现公开接口描述文件，地址和接口范围仍需确认", source))
            elif lower_name in {"openapi.yaml", "openapi.yml", "swagger.yaml", "swagger.yml"}:
                content = read_allowed(entry_path)
                if content is not None and ("openapi:" in content or "swagger:" in content):
                    interface_hints.append(_hint("发现公开接口描述文件，地址和接口范围仍需确认", source))
            elif lower_name == "manage.py":
                detected.add("Django")
                candidates.append(
                    DiscoveryCandidate(
                        label="Django 开发服务候选",
                        command="python manage.py runserver",
                        source=source,
                        safety_note="命令只展示不执行，可能写入或启动目标应用，必须确认",
                    )
                )
            else:
                content = read_allowed(entry_path)
                if content is None:
                    continue

            if lower_name == "package.json" and package_data is not None:
                detected.add("Node.js")
                scripts = package_data.get("scripts")
                if isinstance(scripts, dict):
                    lock_names = {item.name.lower() for item in entries}
                    package_manager = "pnpm" if "pnpm-lock.yaml" in lock_names else "yarn" if "yarn.lock" in lock_names else "npm"
                    for script_name in sorted(scripts)[: limits.max_candidates]:
                        if not isinstance(script_name, str) or not _SCRIPT_NAME.fullmatch(script_name):
                            continue
                        candidates.append(
                            DiscoveryCandidate(
                                label=f"{package_manager} 启动脚本候选：{script_name}",
                                command=f"{package_manager} run {script_name}",
                                source=f"package.json:scripts.{script_name}",
                                safety_note="只读取脚本名称，不读取或执行脚本正文，必须确认",
                            )
                        )
                for section in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
                    values = package_data.get(section)
                    if isinstance(values, dict):
                        dependency_names.update(str(item).lower() for item in values)
            elif lower_name in {"requirements.txt", "requirements-dev.txt", "pipfile", "poetry.lock", "uv.lock", "environment.yml", "environment.yaml"}:
                detected.add("Python")

            if lower_name in {"package-lock.json", "npm-shrinkwrap.json"}:
                detected.add("Node.js")
            if lower_name in {"pnpm-lock.yaml", "yarn.lock"}:
                detected.add("Node.js")
            if lower_name in {"pyproject.toml", "requirements.txt", "requirements-dev.txt", "pipfile", "poetry.lock", "uv.lock", "environment.yml", "environment.yaml"}:
                detected.add("Python")
            if lower_name in {"vite.config.js", "vite.config.mjs", "vite.config.ts"}:
                detected.add("Vite")
            if lower_name.startswith("next.config"):
                detected.add("Next.js")
            if lower_name.startswith("nuxt.config"):
                detected.add("Nuxt")
            if lower_name in {"angular.json"}:
                detected.add("Angular")
            if lower_name.startswith("astro.config"):
                detected.add("Astro")
            if lower_name in {"openapi.json", "openapi.yaml", "openapi.yml", "swagger.json", "swagger.yaml", "swagger.yml"}:
                detected.add("OpenAPI")

    # --- 阶段：从配置元数据生成脱敏提示与待确认候选 ---
    if env_present:
        config_hints.append(_hint("发现环境配置文件存在，但不会读取变量名或内容", ".env"))
    if package_data is not None:
        config_hints.append(_hint("发现 Node.js 项目配置，启动脚本仅作为待确认候选", "package.json"))
        if "next" in dependency_names or "next-auth" in dependency_names:
            detected.add("Next.js")
    if "Python" in detected:
        config_hints.append(_hint("发现 Python 项目配置，启动方式仍需确认", "Python 配置文件"))
    if "Vite" in detected or "Next.js" in detected or "Nuxt" in detected or "Angular" in detected:
        config_hints.append(_hint("发现前端构建配置，目标地址和启动方式仍需确认", "前端配置文件"))
    if dependency_names and any(marker in dependency for dependency in dependency_names for marker in _AUTH_DEPENDENCY_MARKERS):
        auth_hints.append(_hint("依赖结构显示可能存在登录或认证组件，账号和权限仍需你确认", "依赖名称"))
    if interface_hints:
        config_hints.append(_hint("发现接口描述线索，未自动采用任何地址或接口范围", "公开接口描述"))

    if len(candidates) > limits.max_candidates:
        raise _read_budget_error()
    return DiscoveryResult(
        detected_types=tuple(sorted(detected)),
        start_candidates=tuple(candidates[: limits.max_candidates]),
        config_hints=tuple(config_hints),
        interface_hints=tuple(interface_hints),
        auth_hints=tuple(auth_hints),
        missing_items=_missing_items(bool(candidates)),
        warnings=tuple(warnings),
    )
