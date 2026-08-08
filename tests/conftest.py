from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PROJECT_ROOT / "backend" / "src"
sys.path.insert(0, str(SOURCE_ROOT))


@pytest.fixture
def isolated_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    for key in tuple(os.environ):
        if key.startswith("JIEJIAN_"):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.chdir(tmp_path)
    return tmp_path
