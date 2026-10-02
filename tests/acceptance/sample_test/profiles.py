# 用同一 sample-test 入口调度真实普通应用和便携版；场景仍通过正式 pytest 入口运行。
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from .harness.state import SampleTestError

PROFILES = {
    "windows": {
        "selectors": ["tests/e2e/test_recording_action_windows_l5.py", "tests/backend/infra/identity/test_windows_l5.py",
                      "tests/scripts/test_sample_environment.py", "tests/scripts/test_sample_contracts.py",
                      "tests/scripts/test_sample_lifecycle.py"],
        "scope": "显式 Windows 交互能力探针：UIA、录制、临时凭据的写入与回收、真实启动；需交互桌面",
        "environment": {"JIEJIAN_RUN_WINDOWS_L5": "1", "JIEJIAN_RUN_RECORDING_WINDOWS_L5": "1"},
    },
    "ordinary": {
        "selectors": ["tests/backend/workflows/preparation/test_proof_check.py", "tests/backend/workflows/preparation/test_proof_fail_closed.py"],
        "scope": "普通协议驱动：ApplicationCore、受控 Node、预检查、采用、真实 CHECK Worker/Runner；不声称真人 GUI 接入",
        "environment": {},
    },
    "portable": {
        "selectors": ["tests/scripts/test_portable.py::test_real_full_and_nosamples_portables_start_outside_repository"],
        "scope": "已构建的完整包与无样例包在独立安装视图启动、真实运行与资源回收；不自动构建或下载",
        "environment": {"JIEJIAN_RUN_PORTABLE_PROBE": "1"},
    },
}


def run_profile(root: Path, var_dir: Path, profile: str) -> None:
    from tests.support.verification.reporting import write_report
    definition = PROFILES[profile]
    evidence = var_dir / "audit" / "pytest.json"
    environment = {**os.environ, **definition["environment"], "PYTHONDONTWRITEBYTECODE": "1", "JIEJIAN_TEST_REPORT": str(evidence)}
    completed = subprocess.run(["powershell.exe", "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                               str(root / "scripts/dev.ps1"), "test", *definition["selectors"], "-q"],
                              cwd=root, env=environment, check=False)
    detail = json.loads(evidence.read_text(encoding="utf-8")) if evidence.exists() else {}
    success = completed.returncode == 0 and detail.get("status") == "PASSED"
    write_report(var_dir / "audit" / "profile.json", {"schema_version": "1", "profile": profile,
                 "status": "PASSED" if success else "FAILED", "scope": definition["scope"], "evidence": "pytest.json"})
    if not success:
        raise SampleTestError("SAMPLE_PROFILE_NOT_VERIFIED")
