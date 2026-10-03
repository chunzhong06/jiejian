# 通用记录来源核验：只信任当前受控记录组件，不通过某个应用的文件白名单声明可靠性。
from __future__ import annotations

import hashlib
import json

from product.backend.infra.observers.records.record_source import record_provider
from product.protocols.preparation.proof_sources import ManagedProofSourceConfig, ProofContractAttestation


def audit_source_contract(var_dir, reference, config, *, require_live=True):
    """只签发内建通用组件的来源依据；旧应用自报 JSON 及历史专用依据不能重新激活。"""
    if not isinstance(config, ManagedProofSourceConfig):
        return None
    provider = record_provider(var_dir, reference, require_live=require_live)
    if provider is None:
        return None
    # 应用源码身份由 Runtime/采用基线另行冻结。来源能力只取决于独立组件与所选集合，
    # 因而可以跨业务应用使用，也不会把应用的角色名、入口文件或权限逻辑带进信任目录。
    material = {'provider': provider.implementation_fingerprint, 'project_id': reference.project_id,
        'collection': config.collection, 'contract_id': config.source_contract_id}
    fingerprint = hashlib.sha256(json.dumps(material, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return ProofContractAttestation(contract_id=config.source_contract_id,
        implementation_profile='CONTROLLED_TRANSACTION_RECORDS_V1', fingerprint=fingerprint,
        approved_effect_kind='STATE_MUTATION' if config.source_contract_id == 'TRANSACTION_HISTORY_V1' else 'DATA_DISCLOSURE')
