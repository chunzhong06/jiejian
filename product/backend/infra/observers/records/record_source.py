# 读取由 Runtime Worker 拥有的通用记录来源；路径/进程/组件身份先核对，秘密只在 Runner 内注入。
from __future__ import annotations

import os
import json
from pathlib import Path
from urllib.parse import quote

from product.backend.core.errors import JiejianError
from product.backend.infra.execution.web.adapter import HttpExecutionAdapter
from product.backend.infra.execution.web.identity import HttpIdentityRuntime
from product.backend.infra.runtime.process.controlled.artifact import _read_bounded, _regular_file, verify_runtime_artifact
from product.backend.infra.runtime.process.controlled.node_owned import node_artifact_store
from product.backend.infra.runtime.process.records.record_server import record_provider_fingerprint
from product.backend.infra.runtime.process.records.record_capabilities import read_record_capability
from product.backend.infra.runtime.process.listeners import ipv4_listeners
from product.backend.infra.runtime.process.tree import kernel_process_created_at
from product.protocols.runtime.node_runtime import NodeRuntimeManifest, node_document_fingerprint
from product.protocols.runtime.transaction_records import RecordProviderReference, RecordProofView
from product.protocols.web.identity import BearerIdentityBinding
from product.protocols.web.request import HttpRequestTemplate
from product.protocols.web.target import WebTargetScope
from product.backend.infra.observers.adapters.json_source import strict_json, SourceReadError


def record_provider(var_dir: Path, runtime_reference, *, require_live=True) -> RecordProviderReference | None:
    """API 可读取宿主事实，但不访问应用或来源接口；旧实例与未知拥有者不构成可信来源。"""
    try:
        root = node_artifact_store(var_dir) / runtime_reference.instance_id
        if root.resolve() != root:
            return None
        manifest = NodeRuntimeManifest.model_validate_json(_read_bounded(_regular_file(root,'launch.json'),262144))
        if (manifest.project_id, manifest.instance_id, manifest.source_fingerprint, node_document_fingerprint(manifest)) != (
                runtime_reference.project_id, runtime_reference.instance_id, runtime_reference.source_fingerprint, runtime_reference.manifest_fingerprint):
            return None
        verify_runtime_artifact(root/'source', manifest)
        provider = RecordProviderReference.model_validate_json(_read_bounded(_regular_file(root,'record-provider.json'),4096))
        identity = {'kind':'windows-job','name':provider.owner_tree_name}
        if (provider.project_id != runtime_reference.project_id or provider.instance_id != runtime_reference.instance_id
                or provider.implementation_fingerprint != record_provider_fingerprint()):
            return None
        if require_live and (kernel_process_created_at(identity,provider.owner_process_id) != provider.owner_process_created_at
                or ipv4_listeners(provider.port) != (('127.0.0.1',provider.owner_process_id),)):
            return None
        return provider
    except (OSError, ValueError, JiejianError):
        return None


def read_record_source(var_dir, runtime_reference, config, resource_id, *, request_nonce=None, cancelled=lambda:False):
    """仅由预检查/正式检查 Runner 调用；每次读取前后都核对同一来源拥有者，响应不进入公共日志。"""
    provider = record_provider(var_dir, runtime_reference)
    if provider is None or cancelled():
        raise SourceReadError('RECORD_PROVIDER_UNAVAILABLE')
    try:
        capability = read_record_capability(var_dir, provider.instance_id)
    except (ValueError, OSError):
        raise SourceReadError('RECORD_PROVIDER_UNAVAILABLE') from None
    origin = f'http://127.0.0.1:{provider.port}'
    scope = WebTargetScope(base_url=origin,allowed_origins=(origin,),allowed_hosts=('127.0.0.1',),
        allowed_ports=(provider.port,),allow_private_network=True,max_requests=1,
        timeout_seconds=config.timeout_us/1_000_000,max_response_bytes=config.max_response_bytes)
    identity = HttpIdentityRuntime(BearerIdentityBinding(secret_ref='env:JIEJIAN_RECORD_READ'),
        resolve_secret=lambda _ref:capability, business_origin=origin)
    adapter = HttpExecutionAdapter(scope, known_secrets=(capability,), cancellation_requested=cancelled, executor_process_id=os.getpid())
    try:
        identity.bootstrap(lambda *_a, **_k:None)
        path = '/proof/read/'+quote(config.collection,safe='')+'/'+quote(resource_id,safe='')
        if request_nonce is not None:
            path += '/'+quote(request_nonce,safe='')
        _, response = adapter.execute_detailed(HttpRequestTemplate(method='GET',path=path),
            case_id='record-read',action_id='record-proof',identity_runtime=identity)
        if response.status_code != 200:
            raise SourceReadError('RECORD_SOURCE_UNAVAILABLE')
        body = strict_json(response.body, config.max_response_bytes)
        try:
            value = RecordProofView.model_validate_json(json.dumps(body.get('data'),allow_nan=False))
        except (ValueError, TypeError):
            raise SourceReadError('RECORD_SOURCE_INVALID') from None
        if value.snapshot.collection != config.collection or value.snapshot.resource_id != resource_id:
            raise SourceReadError('OPERATION_CORRELATION_INVALID')
        if record_provider(var_dir,runtime_reference) != provider or cancelled():
            raise SourceReadError('RECORD_PROVIDER_UNAVAILABLE')
        return value
    finally:
        identity.close()
        adapter.close()
