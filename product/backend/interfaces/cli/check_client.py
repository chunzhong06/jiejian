"""自动化只连接显式本机控制面；会话驻留内存，业务写入不自动重试。"""
from __future__ import annotations

import json
import time
from urllib.parse import quote

import httpx

from product.backend.domain.errors import ErrorCode, JiejianError
from product.backend.interfaces.http.local_control import LocalControlGuard


class CheckClient:
    def __init__(self, endpoint: str, *, transport=None):
        try:
            origin, _ = LocalControlGuard._normalize_origin(endpoint)
        except ValueError as exc:
            raise JiejianError(ErrorCode.INPUT_INVALID, '服务地址必须为显式的 http://127.0.0.1:端口') from exc
        self.origin = origin
        self.http = httpx.Client(base_url=origin, headers={'Origin': origin}, timeout=30,
            trust_env=False, follow_redirects=False, transport=transport)

    def __enter__(self):
        try:
            with self.http.stream('GET', '/') as response:
                if response.status_code != 200 or LocalControlGuard.cookie_name not in self.http.cookies:
                    raise JiejianError(ErrorCode.API_CONTROL_REJECTED, '无法取得当前本机界鉴服务的控制会话')
        except httpx.HTTPError as exc:
            self.close()
            raise JiejianError(ErrorCode.SERVE_FAILED, '本机服务不可达，请先启动界鉴服务') from exc
        except BaseException:
            self.close()
            raise
        return self

    def __exit__(self, *_):
        self.close()

    def close(self):
        self.http.cookies.clear()
        self.http.close()

    def request(self, method, path, *, body=None, params=None):
        try:
            with self.http.stream(method, path, json=body, params=params) as response:
                payload = bytearray()
                for part in response.iter_bytes():
                    payload.extend(part)
                    if len(payload) > 4 * 1024 * 1024:
                        raise JiejianError(ErrorCode.REQUEST_TOO_LARGE, '本机服务响应超过读取上限')
                try:
                    envelope = json.loads(payload)
                except (ValueError, UnicodeError) as exc:
                    raise JiejianError(ErrorCode.EXEC_REQUEST, '本机服务返回了无法读取的响应') from exc
                if not isinstance(envelope, dict) or envelope.get('schema_version') != '1':
                    raise JiejianError(ErrorCode.EXEC_REQUEST, '本机服务响应格式不兼容')
                if response.is_error:
                    error = envelope.get('error', {})
                    if not isinstance(error, dict):
                        raise JiejianError(ErrorCode.EXEC_REQUEST, '本机服务未返回可识别的错误回执')
                    try:
                        code = ErrorCode(error.get('code'))
                    except (ValueError, AttributeError):
                        code = ErrorCode.EXEC_REQUEST
                    message = error.get('message')
                    raise JiejianError(code, message if isinstance(message, str) else '本机服务拒绝了请求',
                        details=error.get('details') if isinstance(error.get('details'), dict) else {})
                if not 200 <= response.status_code < 300 or 'data' not in envelope:
                    raise JiejianError(ErrorCode.EXEC_REQUEST, '本机服务未返回业务回执')
                return envelope['data']
        except httpx.HTTPError as exc:
            # HTTP 中断不能证明写入失败；原请求标识由调用者保存，再用只读 request 查询。
            raise JiejianError(ErrorCode.SERVE_FAILED, '服务连接中断；写请求结果未知，请先查询原请求回执',
                details={'receipt_unknown': method != 'GET'}) from exc

    @staticmethod
    def project_path(project):
        return '/api/projects/' + quote(project, safe='')

    def preview(self, project, reference):
        return self.request('POST', self.project_path(project)+'/check-preview', body={'routine':reference.model_dump(mode='json')})

    def run(self, project, reference, fingerprint, request_id):
        return self.request('POST', self.project_path(project)+'/runs', body={
            'schema_version':'2', 'routine':reference.model_dump(mode='json'),
            'expected_plan_fingerprint':fingerprint, 'idempotency_key':request_id})

    def receipt(self, project, reference, fingerprint, request_id):
        return self.request('GET', self.project_path(project)+'/check-routines/'+reference.routine_id+
            '/requests/'+quote(request_id, safe=''), params={'revision':reference.revision,
            'binding_id':reference.binding_id, 'fingerprint':fingerprint})

    def status(self, project, run_id):
        status = self.request('GET', '/api/runs/'+quote(run_id, safe=''))
        if status['run']['project_id'] != project:
            raise JiejianError(ErrorCode.RECORD_NOT_FOUND, '本应用没有这条运行记录')
        return status

    def cancel(self, project, run_id):
        status = self.status(project, run_id)
        if status['run']['lifecycle'] in {'QUEUED', 'RUNNING'} and status['job'] is not None:
            self.request('POST', '/api/jobs/'+quote(status['job']['job_id'], safe='')+'/cancel')
        return self.status(project, run_id)

    def wait(self, project, run_id, *, timeout, interval=1, clock=time.monotonic, sleep=time.sleep):
        deadline = clock()+timeout
        while True:
            status = self.status(project, run_id)
            if status['run']['lifecycle'] not in {'QUEUED', 'RUNNING'}:
                return status, False
            remaining = deadline-clock()
            if remaining <= 0:
                return status, True
            sleep(min(interval, remaining))


def execution_exit(status):
    """检查命令单独映射事实；未发布或失败不能因为没有 BLOCK 而返回成功。"""
    run = status['run']
    if run['lifecycle'] in {'QUEUED', 'RUNNING'}:
        return 6
    if run['lifecycle'] == 'CANCELLED':
        return 130
    if run['lifecycle'] != 'COMPLETED' or status['result_integrity'] != 'VALID':
        return 4
    return {'PASS':0, 'BLOCK':10, 'INCONCLUSIVE':11}.get(run['verdict'], 4)
