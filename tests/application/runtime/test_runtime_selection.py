"""持久加载历史与显式检查环境分开；不启动目标，也不伪造受控进程存活。"""
from uuid import uuid4

import pytest
from sqlalchemy import update

from product.backend.bootstrap.application import ApplicationCore
from product.backend.domain.errors import ErrorCode, JiejianError
from product.backend.infrastructure.runtime.jobs.attempts import JobAttempts
from product.backend.infrastructure.runtime.jobs.models import ClaimJob, FatalFailure, FatalFailureCode, RequestCancellation
from product.backend.infrastructure.runtime.jobs.queue import JobQueue
from product.backend.infrastructure.runtime.jobs.registration import runtime_load_targets
from product.backend.infrastructure.storage.runtime.runtime_loads import RuntimeLoadRow
from product.protocols.runtime.node_runtime import NodeRuntimeLoadRequest, NodeRuntimeLoadReceipt, NodeRuntimeReference, node_document_fingerprint
from product.protocols.web.environment import FrozenEnvironment
from product.protocols.web.target import WebTargetScope
from tests.support.builders.runtime.runtime_environment import runtime_identity_environment
from tests.support.secrets import MemorySecrets

NOW = 1_790_000_000_000_000


@pytest.fixture
def application(tmp_path):
    var = tmp_path / 'instance'
    core = ApplicationCore(var, secret_store=MemorySecrets(), environ=runtime_identity_environment(var))
    project = core.application_environments.create_application(operation_id=uuid4().hex, name='外部运行选择').project_id
    try:
        yield core, project
    finally:
        core.close()


def _environment(core, project, port=8091):
    origin = f'http://127.0.0.1:{port}'
    environment = FrozenEnvironment(environment_id='env_' + uuid4().hex, revision=1, name='明确选择的环境',
        target=WebTargetScope(base_url=origin, allowed_origins=(origin,), allowed_hosts=('127.0.0.1',),
            allowed_ports=(port,), allow_private_network=True))
    core.application_environments.save(project, environment, expected_revision=0)
    core.application_environments.activate(project, environment.environment_id, revision=1, expected_revision=0)


def _load(core, project, state):
    request = NodeRuntimeLoadRequest(load_id='rld_' + uuid4().hex, project_id=project,
        operation_id=uuid4().hex, control_session_id='rcs_' + '4' * 32, preview_fingerprint='c' * 64,
        instance_id='rti_' + uuid4().hex, manifest_fingerprint='a' * 64,
        source_fingerprint='b' * 64, created_at_us=NOW)
    job = core.node_runtime.jobs.submit(request)['job']
    if state == 'PENDING':
        return request
    targets = runtime_load_targets()
    if state == 'CANCELLED':
        JobQueue(core.uow_factory, targets=targets).request_cancellation(RequestCancellation(job_id=job.job_id, now_us=NOW + 10))
        return request
    attempts = JobAttempts(core.uow_factory, targets=targets)
    claim = attempts.claim(ClaimJob(job_id=job.job_id, lease_owner='selection-test', now_us=NOW + 10, lease_duration_us=1000))
    if state == 'FAILED':
        attempts.record_fatal_failure(FatalFailure(job_id=job.job_id, lease_owner=claim.job.lease_owner,
            fencing_token=claim.job.fencing_token, now_us=NOW + 20, reason_code=FatalFailureCode.RUNNER_FATAL))
    elif state == 'SUCCEEDED':
        # 合法发布关联用于选择判断；没有真实进程，因此同地址仍必须拒绝受控引用。
        core.node_runtime.jobs.publish(job_id=job.job_id, attempt=1, lease_owner=claim.job.lease_owner,
            fencing_token=claim.job.fencing_token, receipt=NodeRuntimeLoadReceipt(load_id=request.load_id,
                request_fingerprint=node_document_fingerprint(request), started_at_us=NOW + 20,
                reference=NodeRuntimeReference(project_id=project, instance_id=request.instance_id,
                    manifest_fingerprint=request.manifest_fingerprint, source_fingerprint=request.source_fingerprint,
                    process_id=123, process_created_at=456, port=18091)))
    return request


@pytest.mark.parametrize('state', ['FAILED', 'CANCELLED'])
def test_terminal_load_does_not_claim_explicit_external_target(application, state):
    core, project = application
    _environment(core, project)
    _load(core, project, state)
    assert core.runtime_ports.selected_reference(project) is None
    assert core.node_runtime.owns_project(project)
    with pytest.raises(JiejianError):
        core.runtime_ports.reference(project)
    with pytest.raises(JiejianError):
        core.runtime_ports.load_delivery(project, 'b' * 64)


@pytest.mark.parametrize('state', ['PENDING', 'RUNNING'])
def test_unsettled_load_never_becomes_external(application, state):
    core, project = application
    _environment(core, project)
    _load(core, project, state)
    with pytest.raises(JiejianError):
        core.runtime_ports.selected_reference(project)


@pytest.mark.parametrize('port,external', [(8091, True), (18091, False)])
def test_selected_origin_keeps_same_instance_gate(application, port, external):
    core, project = application
    _environment(core, project, port)
    _load(core, project, 'SUCCEEDED')
    if external:
        assert core.runtime_ports.selected_reference(project) is None
    else:
        with pytest.raises(JiejianError):
            core.runtime_ports.selected_reference(project)
    with pytest.raises(JiejianError):
        core.runtime_ports.reference(project)


def test_failed_load_without_explicit_environment_still_requires_runtime(application):
    core, project = application
    _load(core, project, 'FAILED')
    with pytest.raises(JiejianError):
        core.runtime_ports.selected_reference(project)


def test_official_sample_cannot_switch_to_external_through_failed_history(application):
    core, project = application
    _environment(core, project)
    _load(core, project, 'FAILED')
    with core.uow_factory() as work:
        work.sample_workspaces.save(dict(workspace_id='sw_' + uuid4().hex, project_id=project,
            source_root=str(core.var_dir / 'sample'), runtime_kind='NODE_ESM', scenario_version='1', created_at_us=NOW))
        work.commit()
    with pytest.raises(JiejianError):
        core.runtime_ports.selected_reference(project)


def test_inconsistent_publication_is_not_treated_as_external(application):
    core, project = application
    _environment(core, project)
    request = _load(core, project, 'SUCCEEDED')
    # 只破坏此测试的隔离数据库，复现成功Job缺少回执；不能在产品数据上修补历史。
    with core.engine.begin() as connection:
        connection.execute(update(RuntimeLoadRow).where(RuntimeLoadRow.load_id == request.load_id).values(receipt_json=None))
    with pytest.raises(JiejianError) as failure:
        core.runtime_ports.selected_reference(project)
    assert failure.value.code == ErrorCode.STORAGE_STATE.value
