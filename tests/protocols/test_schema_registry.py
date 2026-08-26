# 验证公共 Schema 注册表完整覆盖仓库文件并保持确定性输出。

from __future__ import annotations

from pathlib import Path

from product.protocols.schema import SCHEMA_REGISTRY, render_schema, synchronize_schemas


def test_schema_registry_is_sorted_unique_and_complete() -> None:
    paths = tuple(entry.path for entry in SCHEMA_REGISTRY)
    checked_in = {
        path.relative_to(Path("product/protocols/schemas")).as_posix()
        for path in Path("product/protocols/schemas").rglob("*.schema.json")
    }

    assert paths == tuple(sorted(paths))
    assert len(paths) == len(set(paths))
    assert set(paths) == checked_in


def test_schema_registry_renders_stable_utf8_json() -> None:
    for entry in SCHEMA_REGISTRY:
        first = render_schema(entry)
        assert first == render_schema(entry)
        assert not first.startswith(b"\xef\xbb\xbf")
        assert first.endswith(b"\n")


def test_schema_registry_matches_checked_in_documents() -> None:
    assert synchronize_schemas() == ()
