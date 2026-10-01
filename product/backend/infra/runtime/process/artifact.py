# 创建和复核受控启动副本；只复制明确清单，不读取环境秘密、不执行应用源码。
from __future__ import annotations

import hashlib
from pathlib import Path
from uuid import uuid4

from product.protocols.runtime_identity import (
    MAX_ARTIFACT_BYTES, MAX_MANIFEST_BYTES, RuntimeFile, RuntimeLaunchManifest,
    runtime_source_fingerprint,
)


def _regular_file(root: Path, relative: str) -> Path:
    current = root
    for part in relative.split("/"):
        current = current / part
        if current.is_symlink() or current.is_junction():
            raise ValueError("runtime artifact cannot contain links")
    if not current.is_file() or not current.resolve().is_relative_to(root.resolve()):
        raise ValueError("runtime artifact file missing or outside root")
    return current


def _read_bounded(path: Path, limit: int) -> bytes:
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError("runtime artifact file exceeds byte budget")
    return data


def create_runtime_artifact(
    source_root: Path, artifact_store: Path, *, files: tuple[RuntimeFile, ...],
    entry_module: str, interpreter_fingerprint: str, dependency_files: tuple[str, ...] = (),
) -> tuple[Path, RuntimeLaunchManifest]:
    """在运行目录创建唯一副本；调用方提供已批准源码清单，失败副本不形成可启动清单。"""
    if source_root.is_symlink() or source_root.is_junction() or not source_root.is_dir():
        raise ValueError("runtime source root must be a regular directory")
    manifest = RuntimeLaunchManifest(instance_id="rti_" + uuid4().hex, entry_module=entry_module,
        files=files, source_fingerprint=runtime_source_fingerprint(files),
        dependency_files=dependency_files, interpreter_fingerprint=interpreter_fingerprint)
    root = artifact_store / manifest.instance_id
    root.mkdir(parents=True, exist_ok=False)
    copied = root / "source"
    copied.mkdir()
    for item in manifest.files:
        original = _regular_file(source_root, item.relative_path)
        data = _read_bounded(original, item.size)
        if len(data) != item.size or hashlib.sha256(data).hexdigest() != item.sha256:
            raise ValueError("source changed while preparing runtime artifact")
        target = copied / item.relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(data)
    verify_runtime_artifact(copied, manifest)
    encoded = manifest.model_dump_json().encode("utf-8")
    if len(encoded) > MAX_MANIFEST_BYTES:
        raise ValueError("runtime manifest exceeds byte budget")
    # 清单最后创建；中途失败不能留下看似完整的启动输入。
    with (root / "launch.json").open("xb") as stream:
        stream.write(encoded)
    return root, manifest


def verify_runtime_artifact(source_root: Path, manifest: RuntimeLaunchManifest) -> None:
    """启动前及检查边界复核全部文件；多出文件同样意味着副本已漂移。"""
    if source_root.is_symlink() or source_root.is_junction() or not source_root.is_dir():
        raise ValueError("runtime artifact root unavailable")
    expected = {item.relative_path for item in manifest.files}
    actual: set[str] = set()
    # 不跟随链接，且遇到第一个额外文件即停止，避免遍历无界目录。
    pending = [source_root]
    seen = 0
    while pending:
        directory = pending.pop()
        for path in directory.iterdir():
            seen += 1
            if seen > 4096 or path.is_symlink() or path.is_junction():
                raise ValueError("runtime artifact tree is unsupported")
            if path.is_dir():
                pending.append(path)
            else:
                relative = path.relative_to(source_root).as_posix()
                if relative not in expected:
                    raise ValueError("runtime artifact contains an unexpected file")
                actual.add(relative)
    if actual != expected:
        raise ValueError("runtime artifact files missing")
    total = 0
    for item in manifest.files:
        data = _read_bounded(_regular_file(source_root, item.relative_path), item.size)
        total += len(data)
        if total > MAX_ARTIFACT_BYTES or len(data) != item.size or hashlib.sha256(data).hexdigest() != item.sha256:
            raise ValueError("runtime artifact content changed")


def read_runtime_manifest(path: Path) -> RuntimeLaunchManifest:
    if path.is_symlink() or not path.is_file():
        raise ValueError("runtime manifest unavailable")
    return RuntimeLaunchManifest.model_validate_json(_read_bounded(path, MAX_MANIFEST_BYTES))


def python_runtime_files(source_root: Path) -> tuple[RuntimeFile, ...]:
    """当前受支持目录仅复制 Python 与 OpenAPI；不带入秘密、Git 或开发环境目录。"""
    import os
    files, total, entries = [], 0, 0
    for directory, directories, names in os.walk(source_root, followlinks=False):
        entries += len(directories) + len(names)
        if entries > 4096:
            raise ValueError("runtime source exceeds entry budget")
        directories[:] = [name for name in directories if name not in {".git", ".venv", "venv", "__pycache__", "node_modules", "var", ".pytest_cache"}]
        for name in directories:
            child = Path(directory) / name
            if child.is_symlink() or child.is_junction():
                raise ValueError("runtime source directory is a link")
        for name in names:
            if not name.endswith(".py") and name.casefold() not in {"openapi.json", "swagger.json"}:
                continue
            if any(part in name.casefold() for part in ("secret", "credential", "password", "token")):
                continue
            relative = (Path(directory) / name).relative_to(source_root).as_posix()
            raw = _read_bounded(_regular_file(source_root, relative), MAX_ARTIFACT_BYTES - total)
            total += len(raw)
            files.append(RuntimeFile(relative_path=relative, sha256=hashlib.sha256(raw).hexdigest(), size=len(raw)))
            if len(files) > 512:
                raise ValueError("runtime source exceeds file budget")
    return tuple(sorted(files, key=lambda item: (item.relative_path.casefold(), item.relative_path)))
