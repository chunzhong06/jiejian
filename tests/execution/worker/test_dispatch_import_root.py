from __future__ import annotations

import sys
from pathlib import Path

from product.backend.infra.runtime.jobs.dispatch import WorkerDispatcher, _worker_import_root


def test_worker_dispatch_uses_import_root_for_child_cwd(tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def fake_popen(command: list[str], **kwargs: object) -> object:
        captured["command"] = command
        captured.update(kwargs)
        return object()

    var_dir = tmp_path / "var"
    dispatcher = WorkerDispatcher(
        var_dir=var_dir,
        uow_factory=lambda: None,
        environ={},
        popen=fake_popen,
    )

    dispatcher.start(
        job_id="job_12345678901234567890123456789012",
        lease_owner="worker-test",
        secret_names=(),
    )

    command = captured["command"]
    assert isinstance(command, list)
    assert command[0] == sys.executable
    assert command[1:4] == ["-B", "-m", "product.backend.infra.runtime.worker_process"]
    assert captured["cwd"] == str(_worker_import_root())
    assert captured["cwd"] != str(var_dir.resolve())
    assert command[command.index("--var-dir") + 1] == str(var_dir.resolve())
