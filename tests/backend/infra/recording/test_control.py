from __future__ import annotations

from pathlib import Path

import pytest

from product.backend.core.errors import JiejianError
from product.backend.infra.recording.control import (
    control_paths_for_attempt,
    valid_control_marker,
    write_control_marker,
)


def test_recording_control_markers_are_atomic_fixed_and_bounded(tmp_path: Path) -> None:
    attempt = tmp_path / "attempt-1-1"
    attempt.mkdir()
    paths = control_paths_for_attempt(attempt)

    assert write_control_marker(paths.ready_path, attempt_dir=attempt) is True
    assert write_control_marker(paths.ready_path, attempt_dir=attempt) is False
    assert valid_control_marker(paths.ready_path)
    assert paths.ready_path.read_bytes() == b"1"
    assert all(secret not in paths.ready_path.read_bytes() for secret in (b"cookie", b"token"))

    with pytest.raises(JiejianError):
        write_control_marker(tmp_path / "capture.start", attempt_dir=attempt)

    paths.start_path.write_bytes(b"corrupt")
    with pytest.raises(JiejianError):
        write_control_marker(paths.start_path, attempt_dir=attempt)
