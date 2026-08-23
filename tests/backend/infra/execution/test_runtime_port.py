from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest

from product.backend.core.errors import JiejianError
from product.backend.infra.execution.port import TargetRuntimeContext
from product.backend.infra.execution.registry import TargetRuntimeRegistry


class _Runtime:
    def open_case(self, case, action):
        return SimpleNamespace()

    def close(self) -> None:
        return None


@dataclass(frozen=True)
class _Factory:
    kind: str = "TEST_FAKE"

    def create(self, snapshot, context):
        del snapshot, context
        return _Runtime()


def _context(tmp_path: Path) -> TargetRuntimeContext:
    return TargetRuntimeContext(
        environ={},
        staging=tmp_path,
        clock=lambda: 1,
        cancellation_requested=lambda: False,
    )


def test_registry_accepts_test_fake_without_changing_production_target_type(
    tmp_path: Path,
) -> None:
    registry = TargetRuntimeRegistry()
    registry.register(_Factory())
    runtime = registry.create("TEST_FAKE", SimpleNamespace(), _context(tmp_path))
    assert isinstance(runtime, _Runtime)


def test_registry_rejects_duplicate_unknown_and_invalid_runtime(tmp_path: Path) -> None:
    registry = TargetRuntimeRegistry()
    registry.register(_Factory())
    with pytest.raises(ValueError, match="already registered"):
        registry.register(_Factory())
    with pytest.raises(JiejianError, match="未注册"):
        registry.create("UNKNOWN", SimpleNamespace(), _context(tmp_path))

    class InvalidFactory:
        kind = "INVALID"

        def create(self, snapshot, context):
            del snapshot, context
            return object()

    registry.register(InvalidFactory())
    with pytest.raises(TypeError, match="invalid runtime"):
        registry.create("INVALID", SimpleNamespace(), _context(tmp_path))

