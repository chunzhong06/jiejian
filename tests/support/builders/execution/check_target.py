# 所属业务域的共享测试构造器；不导入测试用例。
import hashlib
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import pytest
from product.protocols.checks.check_result import CheckAssetReference, CheckRunnerInput
from product.protocols.checks.execution_request import canonical_execution_request_bytes
from tests.support.builders.checks.check_execution import execution_pair

@pytest.fixture
def check_target():
    state = dict(value="original", deny_status=403, deny_effect=False, allow_effect=True,
        recovery_fail=False, identity_mismatch=False, cases={}, target_calls=[], recovery_calls=[], caller_pids=[])
    class Handler(BaseHTTPRequestHandler):
        def reply(self, status, payload):
            raw = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        def do_GET(self):
            if self.path.startswith("/tasks/"):
                marker = self.path.rsplit("/", 1)[-1]
                task_state = state.get("task_state", "SUCCESS")
                return self.reply(200, dict(schema_version="1", case_tag=marker,
                    resource_id="resource-1", task_id=None if task_state == "NOT_CREATED" else "task-" + marker,
                    state=task_state, final_result=None))
            if self.path == "/identity":
                token = self.headers.get("Authorization", "").removeprefix("Bearer ")
                subject = "subject-" + token.removeprefix("credential-")
                case = state["cases"].get(self.headers.get("X-Jiejian-Case-ID"))
                if state["identity_mismatch"] and case is not None and case.permission.expectation == "DENY" and token == state.get("deny_token"):
                    subject = "unmapped-subject"
                return self.reply(200, {"subject_id": subject})
            resource=self.path.rsplit('/',1)[-1] if 'values' in state else 'resource-1'
            return self.reply(200, dict(resource_id=resource, workflow_state="DRAFT", value=state.get('values',{}).get(resource,state['value'])))
        def do_POST(self):
            case_id = self.headers.get("X-Jiejian-Case-ID")
            if self.path=='/bulk' and 'batch_strategy' in state:
                data=json.loads(self.rfile.read(min(int(self.headers.get('Content-Length','0')),8192)))
                subject=self.headers.get('Authorization','').removeprefix('Bearer credential-')
                resources=[item['id'] for item in data['items']]
                allowed=[subject=='3' or key=='resource-'+subject for key in resources]
                mixed=not all(allowed)
                for key,permitted in zip(resources,allowed,strict=True):
                    execute=permitted or state.get('batch_fault')=='UNAUTHORIZED'
                    if state['batch_strategy']=='ATOMIC' and mixed and state.get('batch_fault')!='PARTIAL_ATOMIC':execute=False
                    if execute:state['values'][key]='changed'
                state.setdefault('batch_payloads',[]).append(data)
                state['target_calls'].append((case_id,self.headers.get('X-Jiejian-Request-ID')))
                # 单项回归有独立拒绝状态；多项逐条策略只返回整次请求的接收状态。
                return self.reply(403 if mixed and (len(resources)==1 or state['batch_strategy']=='ATOMIC') else 200,{})
            if self.path=='/bulk' and 'batch_response_rows' in state:
                raw=self.rfile.read(min(int(self.headers.get('Content-Length','0')),8192))
                state.setdefault('batch_payloads',[]).append(json.loads(raw))
                state['target_calls'].append((case_id,self.headers.get('X-Jiejian-Request-ID')))
                return self.reply(200,dict(items=state['batch_response_rows']))
            if self.path.startswith("/restore/"):
                state["recovery_calls"].append(case_id)
                if state["recovery_fail"] and state["cases"][case_id].permission.expectation == "DENY":
                    return self.reply(500, {})
                state["value"] = "original"
                if 'values' in state:state['values'][self.path.rsplit('/',1)[-1]]='original'
                return self.reply(200, {})
            case = state["cases"][case_id]
            deny = case.permission.expectation == "DENY"
            state["target_calls"].append((case_id, self.headers.get("X-Jiejian-Request-ID")))
            state["caller_pids"].append(int(self.headers.get("X-Jiejian-Runner-PID", "0")))
            if 'pipeline' in state:
                stage=state['pipeline'][case_id]
                permitted=(not deny or state['deny_effect']) and state['value']==('original' if stage=='reviewed' else 'reviewed')
                if permitted:state['value']=stage
                state.setdefault('pipeline_events',[]).append((stage,permitted))
                return self.reply(200 if permitted else 403,{})
            if state["deny_effect"] if deny else state["allow_effect"]:
                state["value"] = "changed-by-" + case_id
            # 发布链测试在真实 TARGET 完成时落审计事件，保持请求标记与副作用同源。
            if state.get("after_target") is not None:
                state["after_target"](case, self.headers.get("X-Jiejian-Request-ID"))
            return self.reply(state["deny_status"] if deny else state.get("allow_status", 200), {})
        def log_message(self, *_args):
            pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_port, state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        assert not thread.is_alive()

def execution_configuration(check_target, *, configure=None, **changes):
    port, state = check_target
    state.update(changes)
    request, bundle = execution_pair(port=port, state_changing=True, configure=configure)
    state["cases"] = {case.case_id: case for action in request.actions for case in action.cases}
    environment = {identity.binding.secret_ref.removeprefix("env:"): f"credential-{index}"
        for index, identity in enumerate(bundle.identities, 1)}
    deny = next(case for case in state["cases"].values() if case.permission.expectation == "DENY")
    deny_identity = next(identity for identity in bundle.identities if identity.identity_id == deny.subject_test_identity_id)
    state["deny_token"] = environment[deny_identity.binding.secret_ref.removeprefix("env:")]
    request_hash = hashlib.sha256(canonical_execution_request_bytes(request)).hexdigest()
    input = CheckRunnerInput(run_id="run_" + "1" * 32, job_id="job_" + "2" * 32,
        attempt=1, lease_owner="check-worker", fencing_token=1, created_at_us=1,
        request_hash=request_hash, config_hash=request.config_fingerprint,
        assets=(CheckAssetReference(logical_id="request", sha256=request_hash),
            CheckAssetReference(logical_id="runtime", sha256=request.config_fingerprint)))
    return request, bundle, input, environment
