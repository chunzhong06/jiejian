# 确定性生成双发行归档，并比较产品文件身份。
from __future__ import annotations

import hashlib
import os
import zipfile
from collections.abc import Iterable
from pathlib import Path
from scripts.build.common import RELEASE_NAME, FORBIDDEN_PARTS


def iter_files(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        if not path.is_file():
            continue
        if any(part.casefold() in FORBIDDEN_PARTS for part in path.parts) or path.suffix.lower() in {".pyc", ".pyo"}:
            continue
        yield path


def write_zip(destination: Path, base: Path, samples: Path | None) -> None:
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.unlink(missing_ok=True)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            entries: list[tuple[Path, Path]] = [
                (path, Path(RELEASE_NAME) / path.relative_to(base)) for path in iter_files(base)
            ]
            if samples is not None:
                entries.extend(
                    (path, Path(RELEASE_NAME) / "samples" / path.relative_to(samples))
                    for path in iter_files(samples)
                )
            for source, relative in sorted(entries, key=lambda pair: pair[1].as_posix()):
                info = zipfile.ZipInfo(relative.as_posix(), date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                archive.writestr(info, source.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def archive_content(path: Path, *, without_samples: bool) -> dict[str, str]:
    with zipfile.ZipFile(path) as archive:
        content: dict[str, str] = {}
        for info in archive.infolist():
            relative = Path(info.filename)
            if relative.parts[0] != RELEASE_NAME or relative.is_absolute():
                raise RuntimeError(f"Portable ZIP 根目录无效: {info.filename}")
            if len(relative.parts) > 1 and relative.parts[1] == "samples":
                if without_samples:
                    raise RuntimeError("nosamples ZIP 意外包含 samples")
                continue
            content[relative.as_posix()] = hashlib.sha256(archive.read(info)).hexdigest()
        return content
