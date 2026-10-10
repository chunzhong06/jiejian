# 比较旧运行与当前的通用来源能力；录制请求与已确认实现绑定另行核对，不改写原材料。
from product.backend.infra.observers.records.source_contracts import audit_source_contract
from contextlib import contextmanager
from contextvars import ContextVar

_reuse_read = ContextVar('material_reuse_read', default=None)


@contextmanager
def material_reuse_read(work):
    """只在同一动作的一次材料投影内复用来源能力，不跨事务或请求。"""
    token = _reuse_read.set((work, {}))
    try:
        yield
    finally:
        _reuse_read.reset(token)


def recorded_material_reusable(work, binding, understanding, var_dir):
    """没有历史副本、已批准实现或来源合同即返回False，不猜测hash或改写旧录制。"""
    scope = _reuse_read.get()
    key = (str(var_dir),binding.project_id,binding.business_action_id,binding.action_revision,
        binding.source_fingerprint,binding.implementation_fingerprint,understanding.source_fingerprint)
    if scope is None or scope[0] is not work:
        return _recorded_material_reusable(work,binding,understanding,var_dir)
    if key not in scope[1]:
        scope[1][key] = _recorded_material_reusable(work,binding,understanding,var_dir)
    return scope[1][key]


def _recorded_material_reusable(work, binding, understanding, var_dir):
    if binding.source_fingerprint is None or understanding.source_fingerprint is None:
        return False
    current = work.runtime_loads.successful_for_source(binding.project_id,understanding.source_fingerprint)
    previous = work.runtime_loads.successful_for_source(binding.project_id,binding.source_fingerprint)
    if current is None or previous is None:
        return False
    implementation = work.business_boundaries.action_binding(binding.business_action_id,binding.action_revision)
    if implementation is None or implementation.basis_version != 2 or implementation.binding_fingerprint != binding.implementation_fingerprint:
        return False
    for source in work.proof_sources.list(binding.project_id,limit=256):
        if (source.config.action_id,source.config.action_revision) != (binding.business_action_id,binding.action_revision):
            continue
        # 旧实例只用于比对冻结组件，不能再取数；当前实例仍须满足存活和来源核验。
        before = audit_source_contract(var_dir,previous.reference,source.config,require_live=False)
        after = audit_source_contract(var_dir,current.reference,source.config)
        if before is not None and before == after:
            return True
    return False
