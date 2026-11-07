# 通用记录来源核验：只信任当前受控记录组件，不通过某个应用的文件白名单声明可靠性。
from __future__ import annotations

import hashlib
import json

from product.backend.infrastructure.observers.records.record_source import record_provider
from product.protocols.preparation.proof_sources import AtomicProofSourceConfig,FileProofSourceConfig,CreationProofSourceConfig,ProofContractAttestation


def audit_source_contract(var_dir, reference, config, *, require_live=True):
    """只签发内建通用组件的来源依据；旧应用自报 JSON 及历史专用依据不能重新激活。"""
    if not isinstance(config, AtomicProofSourceConfig):
        return None
    provider = record_provider(var_dir, reference, require_live=require_live)
    if provider is None:
        return None
    if config.source_kind=='DATABASE_AUDIT':
        from product.backend.infrastructure.observers.records.database_capture import read_installation
        from product.backend.infrastructure.runtime.process.controlled.node_owned import DATABASE_ADAPTER
        from product.backend.infrastructure.runtime.process.controlled.node_owned import node_artifact_store
        from product.protocols.runtime.node_runtime import NodeRuntimeManifest
        manifest=NodeRuntimeManifest.model_validate_json((node_artifact_store(var_dir)/reference.instance_id/'launch.json').read_bytes())
        if config.database_capture not in manifest.databases:return None
        installed=read_installation(var_dir,reference.project_id,config.database_capture)
        if installed is None:return None
        from pathlib import Path
        material=dict(provider=provider.implementation_fingerprint,adapter=hashlib.sha256(DATABASE_ADAPTER.read_bytes()).hexdigest(),
            observer=hashlib.sha256(Path(__file__).with_name('database_capture.py').read_bytes()+Path(__file__).with_name('database_sql.py').read_bytes()).hexdigest(),
            installation=installed.model_dump(mode='json'))
        return ProofContractAttestation(contract_id='TRANSACTION_HISTORY_V2',
            implementation_profile=config.database_capture.engine+'_ROW_HISTORY_V1',
            fingerprint=hashlib.sha256(json.dumps(material,sort_keys=True,separators=(',',':')).encode()).hexdigest(),approved_effect_kind='STATE_MUTATION')
    if config.source_kind in {'SQLITE_AUDIT','SQLITE_OBJECTS'}:
        from product.backend.infrastructure.observers.records.sqlite_source import sqlite_selection
        from product.backend.infrastructure.observers.adapters.json_source import SourceReadError
        from product.backend.infrastructure.runtime.process.controlled.node_owned import SQLITE_ADAPTER
        try:
            _, database, table = sqlite_selection(var_dir, reference, config)
        except (SourceReadError, OSError, ValueError):
            return None
        material = {'provider': provider.implementation_fingerprint, 'adapter': hashlib.sha256(SQLITE_ADAPTER.read_bytes()).hexdigest(),
            'project_id': reference.project_id, 'database': database.relative_path, 'table': table.model_dump(mode='json')}
        fingerprint = hashlib.sha256(json.dumps(material, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        creation=config.source_kind=='SQLITE_OBJECTS'
        return ProofContractAttestation(contract_id='OBJECT_CREATION_V1' if creation else 'TRANSACTION_HISTORY_V2',implementation_profile='SQLITE_CREATION_HISTORY_V1' if creation else 'SQLITE_ROW_HISTORY_V1',
            fingerprint=fingerprint,approved_effect_kind='OBJECT_CREATION' if creation else 'STATE_MUTATION')
    # 应用源码身份由 Runtime/采用基线另行冻结。来源能力只取决于独立组件与所选集合，
    # 因而可以跨业务应用使用，也不会把应用的角色名、入口文件或权限逻辑带进信任目录。
    material = {'provider': provider.implementation_fingerprint, 'project_id': reference.project_id,
        'collection': config.collection, 'contract_id': config.source_contract_id}
    if isinstance(config,FileProofSourceConfig) and config.async_export is not None:
        from pathlib import Path
        root=Path(__file__).parents[1]/'checks'
        material['async_export']=config.async_export.model_dump(mode='json')
        material['async_collector']=hashlib.sha256((root/'async_export.py').read_bytes()+(root/'file_evidence.py').read_bytes()).hexdigest()
    fingerprint = hashlib.sha256(json.dumps(material, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return ProofContractAttestation(contract_id=config.source_contract_id,
        implementation_profile='CONTROLLED_CREATION_V1' if isinstance(config,CreationProofSourceConfig) else 'CONTROLLED_FILE_RECEIPT_V1' if isinstance(config,FileProofSourceConfig) else 'CONTROLLED_TRANSACTION_RECORDS_V2',fingerprint=fingerprint,
        approved_effect_kind='OBJECT_CREATION' if isinstance(config,CreationProofSourceConfig) else 'FILE_CONTENT_DELIVERY' if isinstance(config,FileProofSourceConfig) else
            'STATE_MUTATION' if config.source_contract_id=='TRANSACTION_HISTORY_V2' else 'DATA_DISCLOSURE')
