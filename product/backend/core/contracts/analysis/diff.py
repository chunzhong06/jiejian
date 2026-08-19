# =============================================================================
# Contract Version 差异
#
# 定位
#   两个不可变治理版本之间的纯结构差异算法
#
# 职责
#   比较规则增删改｜比较 provenance｜生成稳定差异视图
#
# 调用链
#   ContractAnalysis → diff_contract_versions → ContractVersionDiff
# =============================================================================

from __future__ import annotations

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.contracts.models import ContractVersion
from product.backend.core.contracts.analysis.canonical import canonical_sha256
from product.backend.core.contracts.analysis.models import ContractVersionDiff, ProvenanceDelta, RuleDiff


def diff_contract_versions(
    before: ContractVersion,
    after: ContractVersion,
) -> ContractVersionDiff:
    if (before.project_id, before.contract_id) != (after.project_id, after.contract_id):
        raise JiejianError(ErrorCode.CONTRACT_REFERENCE_INVALID, "契约版本差分必须属于同一项目和契约")
    before_rules = {rule.rule_id: rule for rule in before.snapshot.rules}
    after_rules = {rule.rule_id: rule for rule in after.snapshot.rules}
    changed = tuple(
        RuleDiff(rule_id=rule_id, before=before_rules[rule_id], after=after_rules[rule_id])
        for rule_id in sorted(set(before_rules) & set(after_rules))
        if before_rules[rule_id] != after_rules[rule_id]
    )
    added = tuple(after_rules[rule_id] for rule_id in sorted(set(after_rules) - set(before_rules)))
    removed = tuple(before_rules[rule_id] for rule_id in sorted(set(before_rules) - set(after_rules)))
    provenance_added = ProvenanceDelta(
        requirement_ids=tuple(sorted(set(after.provenance.requirement_ids) - set(before.provenance.requirement_ids))),
        candidate_ids=tuple(sorted(set(after.provenance.candidate_ids) - set(before.provenance.candidate_ids))),
        sources=tuple(source for source in after.provenance.sources if source not in before.provenance.sources),
    )
    provenance_removed = ProvenanceDelta(
        requirement_ids=tuple(sorted(set(before.provenance.requirement_ids) - set(after.provenance.requirement_ids))),
        candidate_ids=tuple(sorted(set(before.provenance.candidate_ids) - set(after.provenance.candidate_ids))),
        sources=tuple(source for source in before.provenance.sources if source not in after.provenance.sources),
    )
    body = {
        "project_id": before.project_id,
        "contract_id": before.contract_id,
        "from_version": before.version,
        "to_version": after.version,
        "from_status": before.status,
        "to_status": after.status,
        "added": added,
        "removed": removed,
        "changed": changed,
        "provenance_added": provenance_added,
        "provenance_removed": provenance_removed,
    }
    return ContractVersionDiff(
        project_id=before.project_id,
        contract_id=before.contract_id,
        from_version=before.version,
        to_version=after.version,
        from_status=before.status,
        to_status=after.status,
        added=added,
        removed=removed,
        changed=changed,
        provenance_added=provenance_added,
        provenance_removed=provenance_removed,
        canonical_sha256=canonical_sha256(body),
    )
