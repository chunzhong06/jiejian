# 一次真实代码变化声明的规则与原问题关联；声明不产生修复结论。
from __future__ import annotations

from product.backend.domain.checks.repair import CurrentRepairReference
from product.protocols.checks.execution_request import PermissionReference, WireModel, content_hash


class RuleChangeTarget(WireModel):
    permission: PermissionReference
    repair: CurrentRepairReference | None = None

    def key(self):
        return content_hash('RuleChangeTarget', self.model_dump(mode='json'))

