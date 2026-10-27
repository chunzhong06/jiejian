# 通用来源预检查只确认当前字段、归属和组件能力；不产生权限结论。
from product.backend.infrastructure.observers.records.record_facts import record_value
from product.backend.infrastructure.observers.adapters.json_source import SourceReadError
from product.protocols.preparation.proof_sources import ProofCheckItem


def managed_source_checks(view, config, *, resource_id, owner_subject_id, contract):
    if config.source_kind == 'CREATED_OBJECT_RECORDS':
        valid = view.collection == config.collection and contract is not None and contract.implementation_profile == 'CONTROLLED_CREATION_V1'
        return (ProofCheckItem(code='CREATION_COLLECTION_VERIFIED' if valid else 'CREATION_SOURCE_UNAVAILABLE',
            status='CONFIRMED' if valid else 'UNSUPPORTED'),)
    if view.schema_version!='2' or (contract is not None and contract.implementation_profile not in {'CONTROLLED_TRANSACTION_RECORDS_V2','CONTROLLED_FILE_RECEIPT_V1'}):
        return (ProofCheckItem(code='SOURCE_REQUIRES_MIGRATION',status='UNSUPPORTED'),)
    checks = []
    snapshot = view.snapshot
    payload = snapshot.model_dump(mode='json')
    for key, path in config.mappings.items():
        try:
            value = record_value(payload, path)
            valid = isinstance(value,str) and bool(value) and value not in {'[REDACTED]','<redacted>'}
            checks.append(ProofCheckItem(code='MAPPING_READABLE' if valid else 'MAPPING_TYPE_INVALID',
                status='CONFIRMED' if valid else 'MISSING',mapping_key=key))
        except SourceReadError:
            checks.append(ProofCheckItem(code='MAPPING_MISSING',status='MISSING',mapping_key=key))
    for path in config.protected_projection:
        try:
            value = record_value(snapshot.data, path.split('.'))
            valid = value is not None and value not in ('[REDACTED]','<redacted>')
        except SourceReadError:
            valid = False
        checks.append(ProofCheckItem(code='PROTECTED_FIELD_READABLE' if valid else 'PROTECTED_FIELD_MISSING',
            status='CONFIRMED' if valid else 'MISSING'))
    matching = snapshot.collection == config.collection and snapshot.resource_id == resource_id and snapshot.owner_id == owner_subject_id
    checks.append(ProofCheckItem(code='RESOURCE_OWNER_MATCH' if matching else 'RESOURCE_OWNER_MISMATCH',status='CONFIRMED' if matching else 'MISSING'))
    checks.append(ProofCheckItem(code='SOURCE_CONTRACT_VERIFIED' if contract is not None else 'CONTRACT_UNVERIFIED',status='CONFIRMED' if contract is not None else 'UNSUPPORTED'))
    return tuple(checks)
