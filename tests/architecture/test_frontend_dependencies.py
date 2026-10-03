# 防止页面和共同能力反向依赖应用壳；所有前端消费者共同遵守同一依赖方向。
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "product/frontend/src"
MODULE_SPECIFIER = re.compile(
    r"(?:\bfrom\s+|\bimport\s*\(\s*|\bimport\s+)[\"']([^\"']+)[\"']"
)


def test_features_and_shared_do_not_import_application_shell() -> None:
    violations = []
    for area in ("features", "shared", "api"):
        for path in (SOURCE / area).rglob("*"):
            if path.suffix not in {".ts", ".tsx"} or ".test." in path.name:
                continue
            for imported in MODULE_SPECIFIER.findall(path.read_text(encoding="utf-8")):
                if not imported.startswith("."):
                    continue
                target = (path.parent / imported).resolve()
                if target.is_relative_to(SOURCE / "app"):
                    violations.append((path.relative_to(ROOT).as_posix(), imported))
    assert violations == []
