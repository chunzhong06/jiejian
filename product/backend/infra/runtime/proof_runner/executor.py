# 预检查只读固定身份和单资源接口；每次请求前核对授权、租约和受控实例，响应只留有限状态。
import time

from product.backend.core.errors import JiejianError
from product.backend.core.lifecycle import JobState, ProjectStatus
from product.backend.infra.execution.web.adapter import HttpExecutionAdapter
from product.backend.infra.execution.web.identity import HttpIdentityRuntime
from product.backend.infra.execution.web.check_runtime import check_secret_names
from product.backend.infra.observers.json_source import strict_json, SourceReadError
from product.backend.infra.observers.source_contracts import audit_source_contract
from product.backend.infra.observers.record_source import read_record_source
from product.backend.infra.observers.record_preflight import managed_source_checks
from product.backend.infra.observers.record_facts import record_value
from product.backend.infra.runtime.process.node_owned import node_corresponds
from product.backend.infra.runtime.process.node_locator import controlled_node_executable
from product.protocols.proof_sources import ProofCheckItem, ProofPreflightReport, proof_fingerprint, ManagedProofSourceConfig
from product.protocols.web.request import HttpRequestTemplate


def execute_preflight(input, *, var_dir, uow_factory, environ, cancellation_requested):
    request = input.request
    started = time.time_ns() // 1000
    checks = []
    names = check_secret_names(request)
    known = tuple(environ[name] for name in names if environ.get(name))
    node = controlled_node_executable(environ)

    def active():
        if cancellation_requested() or time.time_ns() // 1000 - started > 30_000_000:
            return False
        with uow_factory() as work:
            job = work.jobs.get(input.job_id)
            scope = work.proof_sources.scope(request.project_id, request.scope.scope_id)
            project = work.projects.get(request.project_id)
            valid = (job is not None and job.state is JobState.RUNNING
                and (job.attempt, job.fencing_token, job.lease_owner, job.request_hash) ==
                    (input.attempt, input.fencing_token, input.lease_owner, input.request_fingerprint)
                and job.cancel_requested_at_us is None and job.lease_expires_at_us > time.time_ns() // 1000
                and scope == request.scope and project is not None and project.status is not ProjectStatus.ARCHIVED)
        return valid and node_corresponds(var_dir, request.runtime_reference, node)

    adapter = HttpExecutionAdapter(request.target, known_secrets=known,
        cancellation_requested=lambda: not active(), executor_process_id=__import__('os').getpid())
    try:
        if not isinstance(request.config,ManagedProofSourceConfig):
            checks.append(ProofCheckItem(code='SOURCE_REQUIRES_MIGRATION',status='UNSUPPORTED'))
        elif any(not environ.get(name) for name in names):
            checks.append(ProofCheckItem(code='IDENTITY_SESSION_MISSING', status='MISSING'))
        elif not active():
            checks.append(ProofCheckItem(code='READ_AUTHORITY_UNAVAILABLE', status='UNAVAILABLE'))
        else:
            claims = {item.identity_id: item for item in request.config.identity_claims}
            for identity in request.identities:
                runtime = HttpIdentityRuntime(identity.binding,
                    resolve_secret=lambda reference: environ.get(reference.removeprefix('env:')),
                    business_origin=request.target.base_url)
                try:
                    runtime.bootstrap(lambda *_args, **_kwargs: None)
                    claim = claims[identity.identity_id]
                    _, response = adapter.execute_detailed(HttpRequestTemplate(method='GET', path=claim.request_path),
                        case_id=request.preflight_id, action_id='proof-identity', identity_runtime=runtime)
                    data = strict_json(response.body, request.config.max_response_bytes)
                    matching = (response.status_code == 200 and record_value(data,claim.subject_path) == claim.application_subject_id
                        and record_value(data,claim.role_path) == request.identity_roles[identity.identity_id])
                    checks.append(ProofCheckItem(code='ACTUAL_IDENTITY_MATCH' if matching else 'ACTUAL_IDENTITY_MISMATCH',
                        status='CONFIRMED' if matching else 'MISSING'))
                    if matching and identity.identity_id == request.config.observation_identity_id:
                        contract = audit_source_contract(var_dir, request.runtime_reference, request.config)
                        if contract != request.contract:
                            contract = None
                        view = read_record_source(var_dir,request.runtime_reference,request.config,request.resource_id,cancelled=lambda:not active())
                        checks.extend(managed_source_checks(view, request.config, resource_id=request.resource_id,
                            owner_subject_id=request.owner_subject_id, contract=contract))
                finally:
                    runtime.close()
            if not active():
                checks.append(ProofCheckItem(code='READ_AUTHORITY_UNAVAILABLE', status='UNAVAILABLE'))
    except SourceReadError as error:
        checks.append(ProofCheckItem(code=error.code, status='MISSING', mapping_key=error.mapping_key))
    except JiejianError:
        checks.append(ProofCheckItem(code='SOURCE_READ_UNAVAILABLE', status='UNAVAILABLE'))
    finally:
        adapter.close()
    usable = bool(checks) and all(item.status == 'CONFIRMED' for item in checks)
    assessment = 'USABLE' if usable else 'UNSUPPORTED' if any(item.status == 'UNSUPPORTED' for item in checks) else 'NEEDS_CHANGES'
    return ProofPreflightReport(preflight_id=request.preflight_id, job_id=input.job_id,
        request_fingerprint=proof_fingerprint(request), source_fingerprint=request.source_fingerprint,
        attempt=input.attempt, fencing_token=input.fencing_token, lease_owner=input.lease_owner,
        assessment=assessment, checks=tuple(checks), started_at_us=started, completed_at_us=time.time_ns() // 1000)
