# 合并同一真实提交的多个字段/阶段引用，应用Evidence预算；完整肯定事实优先保留。
from product.protocols.checks.business_facts import CommittedStateFact,IdentityCheckFact,seal_business_fact


def finalize_facts(observations,collected):
    """同一提交只封存一次；超出条数预算的观察降为未知，不截断后宣称未发生。"""
    groups,aliases={},{}
    references=[]
    for observation in observations:
        entry=collected.get(observation.model_dump_json())
        if entry is None:continue
        facts,reference=entry
        references.append((observation,reference))
        for fact in facts:
            data=fact.data
            key=(fact.case_id,fact.request_ref,data.kind,
                (data.generation,data.operation_id) if isinstance(data,CommittedStateFact) else
                (data.identity_id,data.subject_match,data.role_match) if isinstance(data,IdentityCheckFact) else data.model_dump_json())
            groups.setdefault(key,{})[fact.fact_id]=fact
    merged={}
    for key,items in groups.items():
        values=list(items.values())
        first=min(values,key=lambda fact:fact.observed_at_us)
        proof_refs={ref.proof_fingerprint:ref for fact in values for ref in fact.proofs}
        data=first.data
        if isinstance(data,CommittedStateFact):
            changes={}
            for fact in values:
                if fact.data.model_dump(exclude={'changes'})!=data.model_dump(exclude={'changes'}):
                    raise ValueError('conflicting committed fact')
                for change in fact.data.changes:
                    change_key=(change.proof_fingerprint,change.path)
                    if change_key in changes and changes[change_key]!=change:raise ValueError('conflicting field projection')
                    changes[change_key]=change
            data=data.model_copy(update={'changes':tuple(changes[item] for item in sorted(changes))})
        # 合并后仍必须通过2KiB和字段数量限制；无法合法封存时中止发布，不能隐瞒已形成的事实。
        combined=seal_business_fact(**first.model_dump(exclude={'fact_id','proofs','data'}),
            proofs=tuple(proof_refs[item] for item in sorted(proof_refs)),data=data)
        merged[combined.fact_id]=combined
        aliases.update({old:combined.fact_id for old in items})
    remapped=[(observation,reference.model_copy(update={'fact_ids':tuple(dict.fromkeys(aliases[item] for item in reference.fact_ids))}))
        for observation,reference in references]
    ordered=[]
    for observation,reference in sorted(remapped,key=lambda pair:pair[0].state!='CONFIRMED'):
        ordered.extend(item for item in reference.fact_ids if item not in ordered)
    retained=set(ordered[:64])
    updated,final_refs={},[]
    for observation,reference in remapped:
        if not set(reference.fact_ids)<=retained:
            reference=reference.model_copy(update={'fact_ids':tuple(item for item in reference.fact_ids if item in retained),
                'complete':False,'reason_codes':('FACT_BUDGET_EXCEEDED',)})
            observation_update=observation.model_copy(update={'state':'UNKNOWN','closure':'OPEN','complete':False,
                'reliable':False,'correlated':False,'authoritative':False,'reason_codes':('FACT_BUDGET_EXCEEDED',)})
            updated[observation.model_dump_json()]=observation_update
        final_refs.append(reference)
    return (tuple(updated.get(item.model_dump_json(),item) for item in observations),
        tuple(merged[item] for item in ordered[:64]),tuple(final_refs))
