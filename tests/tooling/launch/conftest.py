# 为启动脚本行为测试执行有界、无网络的 PowerShell 探针。
import json
import os
import shutil
import subprocess
import pytest


@pytest.fixture
def powershell_record():
    def run(command):
        executable=shutil.which('pwsh') or shutil.which('powershell')
        assert executable,'需要 Windows PowerShell 或 PowerShell 7'
        completed=subprocess.run([executable,'-NoLogo','-NoProfile','-Command',command],
            env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'},text=True,capture_output=True,timeout=30,check=False)
        assert completed.returncode==0,completed.stdout+completed.stderr
        return json.loads(completed.stdout.strip().splitlines()[-1])
    return run
