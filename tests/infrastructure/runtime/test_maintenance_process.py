# 用隔离的本地进程验证运行临时目录：活跃树保留，确认退出后才能回收。
import os
import subprocess
from threading import Event

import pytest

from product.backend.infrastructure.maintenance.service import LocalMaintenanceService
from product.backend.infrastructure.runtime.process.environment import spawn_python_module, ProcessEnvironmentRole
from product.backend.infrastructure.runtime.process.tree import terminate_process_tree
from tests.support.builders.runtime.runtime_environment import runtime_identity_environment


@pytest.mark.process
@pytest.mark.skipif(os.name!='nt',reason='Windows process ownership')
def test_child_temp_is_preserved_until_real_process_tree_exits(tmp_path):
    var=tmp_path/'var'
    service=LocalMaintenanceService(var)
    data=service.paths.data/'retained.txt';data.write_text('keep')
    process=spawn_python_module(runtime_identity_environment(var),'http.server','0','--bind','127.0.0.1',
        role=ProcessEnvironmentRole.ARTIFACT_SCAN,cwd=tmp_path,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        Event().wait(.2)
        assert process.poll() is None
        directories=[path for path in service.paths.temp.glob('process-*') if (path/'.runtime-process.json').is_file()]
        assert len(directories)==1
        assert service.preview('clear-temporary')['targets']==[]
    finally:
        terminate_process_tree(process,2)
    plan=service.preview('clear-temporary')
    assert len(plan['targets'])==1
    assert service.execute(plan['plan_id'])['counts']['DELETED']==1
    assert not directories[0].exists()
    assert data.read_text()=='keep'

pytestmark = [pytest.mark.level3]
