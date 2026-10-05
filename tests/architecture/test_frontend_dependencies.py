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


def test_feature_components_are_reachable_from_product_entry() -> None:
    """组件自己的测试不算产品接线；退役页面应连同专属样式和测试一起收口。"""
    modules = {path.resolve() for path in SOURCE.rglob("*")
               if path.suffix in {".ts", ".tsx"} and ".test." not in path.name}
    reachable = set()
    pending = [(SOURCE / "main.tsx").resolve()]
    while pending:
        path = pending.pop()
        if path in reachable:
            continue
        reachable.add(path)
        for imported in MODULE_SPECIFIER.findall(path.read_text(encoding="utf-8")):
            if not imported.startswith("."):
                continue
            target = (path.parent / imported).resolve()
            choices = [target, Path(str(target) + ".ts"), Path(str(target) + ".tsx"),
                       target / "index.ts", target / "index.tsx"]
            pending.extend(candidate for candidate in choices if candidate in modules)
    components = {path.resolve() for path in (SOURCE / "features").rglob("*.tsx")
                  if ".test." not in path.name}
    assert sorted(path.relative_to(ROOT).as_posix() for path in components - reachable) == []
