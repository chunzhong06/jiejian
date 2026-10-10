# 共享真实页面会话与回执核对，不创建第二份业务状态。
import re
import time


class GuiSession:
    def __init__(self, page, client, audit_dir):
        self.page, self.client, self.audit_dir = page, client, audit_dir
        self.records = []

    def _mark(self, event):
        self.records.append({"event": event, "status": "PASSED"})

    def _goto(self, path):
        self.page.goto(self.client.origin + "/#" + path, wait_until="domcontentloaded")

    def _response(self, path, action, *, accepted=(200, 201, 202), method="POST"):
        from tests.acceptance.sample_test.harness.state import SampleTestError
        with self.page.expect_response(lambda response: response.request.method == method
                and response.url.split("?", 1)[0] == self.client.origin + path, timeout=120_000) as response:
            action()
        actual = response.value
        if actual.status not in accepted:
            # 真实便携失败需要稳定错误码定位；不保存请求、响应正文或凭据字段。
            try:
                code = actual.json().get('error', {}).get('code', '')
            except (ValueError, AttributeError):
                code = ''
            safe_code = code if isinstance(code, str) and re.fullmatch(r'[A-Z][A-Z0-9_]{0,80}', code) else 'UNKNOWN'
            raise SampleTestError(f"GUI_ACTION_REJECTED: path={path} status={actual.status} code={safe_code}")
        envelope = actual.json()
        if not isinstance(envelope, dict) or "data" not in envelope:
            raise SampleTestError("GUI_ACTION_RECEIPT_INVALID")
        return envelope["data"], actual.request.post_data_json

    def capture(self, name):
        """只截取当前真实页面；文件名有界，不注入占位运行状态。"""
        from tests.acceptance.sample_test.harness.state import SampleTestError
        if not re.fullmatch(r"[a-z][a-z0-9-]{0,63}", name):
            raise SampleTestError("GUI_CAPTURE_NAME_INVALID")
        self.page.screenshot(path=str(self.audit_dir / (name + ".png")), full_page=True)

    def _environment_completed(self, receipt):
        """受理不代表实例就绪；查询原键，不重放页面写操作。"""
        from tests.acceptance.sample_test.harness.state import SampleTestError
        deadline=time.monotonic()+40
        while receipt.get('operation_state')=='PENDING' and time.monotonic()<deadline:
            self.page.wait_for_timeout(150)
            receipt=self.client.call('GET','/api/experience/official-sample?operation_id='+receipt['operation_id'])
        if receipt.get('operation_state')!='SUCCEEDED':raise SampleTestError('GUI_ENVIRONMENT_NOT_COMPLETED')
        return receipt
