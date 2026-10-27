# 监督测试创建的控制面进程，初始化失败或断言失败后仍回收本实例。
from contextlib import contextmanager
from dataclasses import dataclass
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import httpx
from tests.support.official import until

ROOT=Path(__file__).resolve().parents[2]

@dataclass
class RuntimeServer:
    client: httpx.Client
    origin: str
    output: Path

@contextmanager
def launch(output,frontend,*,workspace=None):
    output.mkdir(parents=True,exist_ok=False)
    assert (frontend/'index.html').is_file()
    with socket.socket() as available:
        available.bind(('127.0.0.1',0))
        port=available.getsockname()[1]
    origin=f'http://127.0.0.1:{port}'
    instance=output/'instance' if workspace is None else workspace.resolve()
    process=client=None
    exit_state={'schema_version':'1','graceful':False,'returncode':None}
    with (output/'service.log').open('w',encoding='utf-8') as log:
        try:
            command=[sys.executable,'-B','-m','product.backend.interfaces.cli','--var-dir',str(instance),'serve','--port',str(port),'--no-open','--frontend-dir',str(frontend),'--official-sample-root',str(ROOT/'samples/web/digital_gallery')]
            environment=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',JIEJIAN_VAR_DIR=str(instance))
            process=subprocess.Popen(command,cwd=ROOT,env=environment,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            client=httpx.Client(base_url=origin,headers={'origin':origin},timeout=30,trust_env=False)
            def ready():
                assert process.poll() is None,'独立控制面启动进程已退出'
                try:
                    response=client.get('/ready')
                    return response.status_code==200 and response.json().get('status')=='ready'
                except httpx.TransportError:return False
            until(ready,bool,seconds=60)
            assert client.get('/').status_code==200
            yield RuntimeServer(client,origin,output)
        finally:
            try:
                if process is not None:
                    if process.poll() is None:
                        try:
                            if client is not None:client.post('/api/system/shutdown')
                        except httpx.HTTPError:pass
                        try:process.wait(30)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait(10)
                            raise AssertionError('独立控制面未完成正常退出，已终止测试创建的进程')
                    exit_state.update(graceful=process.returncode==0,returncode=process.returncode)
                    assert process.returncode==0,'独立控制面异常退出'
            finally:
                if client is not None:client.close()
                (output/'shutdown.json').write_text(json.dumps(exit_state),encoding='utf-8')
