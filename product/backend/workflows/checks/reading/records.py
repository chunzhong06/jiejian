# 单条证据的有限阅读投影：只消费已验证包，精确定位原文，不访问目标、不重算安全结论。
from __future__ import annotations
import hashlib
from typing import Literal,Any
from pydantic import Field
from product.backend.core.errors import ErrorCode,JiejianError
from product.protocols.checks.execution_request import WireModel,content_hash
from product.protocols.checks.check_result import canonical_check_document
from product.backend.workflows.checks.reading.record_text import METHODS,REASONS,PHASES,TRACE_LABELS,JUDGEMENTS


class RecordLink(WireModel):
    record_id:str
    kind:Literal['FACT','OUTCOME','OBSERVATION','TRACE']
    label:str
    proof_fingerprint:str|None=None
    observer_id:str|None=None
    phase:str|None=None
    event_id:str|None=None


class EvidenceRecordIndex(WireModel):
    project_id:str
    run_id:str
    case_id:str
    action_id:str
    evidence_id:str
    records:tuple[RecordLink,...]=Field(max_length=817)


class VerificationSection(WireModel):
    key:Literal['rule','experiment','method','association','reason','boundary']
    title:str
    status:Literal['CONFIRMED','LIMITED','UNKNOWN']
    text:str
    record_refs:tuple[str,...]=Field(default=(),max_length=817)
    source:dict[str,str]=Field(default_factory=dict)
    fragment:dict[str,Any]=Field(default_factory=dict)


class EvidenceRecordView(WireModel):
    project_id:str
    run_id:str
    case_id:str
    action_id:str
    evidence_id:str
    record:RecordLink
    summary:str
    published_judgement:str
    role:Literal['PROOF','SUPPORTING']
    verification:tuple[VerificationSection,...]=Field(min_length=6,max_length=6)
    values:tuple[dict[str,Any],...]=Field(max_length=20)
    location:dict[str,str]
    fragment:dict[str,Any]
    related_records:tuple[RecordLink,...]=Field(max_length=817)
    limitations:tuple[str,...]


def _record_id(document,kind,value):
    return 'rd_'+content_hash('EvidenceRecord',dict(evidence_id=document.evidence_id,kind=kind,value=value))


def _entries(document):
    entries=[]
    def add(kind,value,pointer,label,**fields):
        key=value.fact_id if kind=='FACT' else _record_id(document,kind,value.model_dump(mode='json'))
        entries.append((RecordLink(record_id=key,kind=kind,label=label,**fields),value,pointer))
    add('OUTCOME',document.outcome,'/outcome','本题的实际执行核对')
    for index,fact in enumerate(getattr(document,'business_facts',())):
        labels={'COMMITTED_STATE':'独立业务提交','IDENTITY_CHECK':'实际账号核对','FIELD_DISCLOSURE':'受保护字段比较',
            'REFERENCE_ARTIFACT':'已采用的文件参照','FILE_RECEIPT':'实际接收的文件内容'}
        label=f'第 {fact.data.scope_ordinal+1} 次独立提交' if fact.data.kind=='COMMITTED_STATE' else labels[fact.data.kind]
        add('FACT',fact,f'/business_facts/{index}',label)
    for index,item in enumerate(document.observations):
        add('OBSERVATION',item,f'/observations/{index}',PHASES[item.phase]+'的结果观察',
            proof_fingerprint=item.proof_fingerprint,observer_id=item.observer_id,phase=item.phase)
    if document.trace is not None:
        for index,event in enumerate(document.trace.events):
            label='准备返回业务响应' if event.kind=='MESSAGE' and event.semantic_key=='response_prepared' else TRACE_LABELS[event.kind]
            add('TRACE',event,f'/trace/events/{index}',label,event_id=event.event_id)
    return entries


def _select(package,evidence_id,case_id):
    document=next((value for value in package.evidence if value.evidence_id==evidence_id and value.case.case_id==case_id),None)
    result=next((value for value in package.result.case_results if value.case_id==case_id and evidence_id in value.evidence_ids),None)
    if document is None or result is None:raise JiejianError(ErrorCode.RECORD_NOT_FOUND,'这条记录不属于指定检查项')
    return document,result


def record_index(package,evidence_id,case_id):
    document,_=_select(package,evidence_id,case_id)
    return EvidenceRecordIndex(project_id=package.request.project_id,run_id=document.run_id,case_id=case_id,
        action_id=document.action_id,evidence_id=evidence_id,records=tuple(item[0] for item in _entries(document)))


def _summary(link,value):
    if link.kind=='TRACE':return f'执行路径记录了“{link.label}”。它说明过程，不单独证明业务后果。'
    if link.kind=='OUTCOME':
        return f'请求返回HTTP {value.http_status}。下面同时核对实际身份、资源归属和恢复情况。' if value.http_status is not None else '本题未保存HTTP状态；保留已取得的执行核对。'
    if link.kind=='OBSERVATION':
        if value.level!='VERDICT_REQUIRED':return '这条记录用于理解执行或恢复过程，不替代必要的业务结果证明。'
        if value.phase in {'BASELINE','BEFORE','RECOVERY'}:return PHASES[value.phase]+'的对照记录；最终业务后果还需结合操作后的观察。'
        return {'CONFIRMED':'这项业务后果已被观察到。','ABSENT':'在这条记录的观察范围内没有发现该后果。','UNKNOWN':'这条记录不足以确认业务后果。'}[value.state]
    data=value.data
    if data.kind=='COMMITTED_STATE':return '这次独立提交改变了受保护字段。下方保留提交前后的值，可核对变化到底发生在哪里。'
    if data.kind=='IDENTITY_CHECK':return '独立身份读取的结果：账号'+{'MATCH':'一致','MISMATCH':'不一致','UNKNOWN':'尚未确认'}[data.subject_match]+'，角色'+{'MATCH':'一致','MISMATCH':'不一致','UNKNOWN':'尚未确认'}[data.role_match]+'。'
    if data.kind=='FIELD_DISCLOSURE':return '对实际返回的受保护字段逐项比较；摘要用于核对内容，不展示原始敏感正文。'
    if data.kind=='REFERENCE_ARTIFACT':return '这是用户采用的测试参照，只定义要比较的内容，本身不能证明本次已经收到文件。'
    return {'MATCH':'实际完整收到的内容与已采用参照一致。','DIFFERENT':'实际收到的内容与参照不同，不能把它当作原完整文件。','INCOMPLETE':'本次没有形成完整文件接收证明。'}[data.comparison]


def record_view(package,evidence_id,case_id,record_id):
    document,result=_select(package,evidence_id,case_id);entries=_entries(document)
    entry=next((entry for entry in entries if entry[0].record_id==record_id),None)
    if entry is None:raise JiejianError(ErrorCode.RECORD_NOT_FOUND,'未找到这条封存记录，请核对原链接')
    link,value,pointer=entry;case=document.case;outcome=document.outcome
    configuration=next(action for action in package.bundle.actions if action.action_id==document.action_id)
    identities={item.identity_id:item for item in package.bundle.identities}
    subject=identities[case.subject_test_identity_id];owner=identities[case.resource_owner_test_identity_id]
    proof_refs=getattr(document,'fact_references',())
    refs=tuple(ref for ref in proof_refs if (link.kind=='FACT' and record_id in ref.fact_ids) or
        (link.kind=='OBSERVATION' and (ref.proof_fingerprint,ref.observer_id,ref.phase)==(value.proof_fingerprint,value.observer_id,value.phase)))
    related_ids={fact_id for ref in refs for fact_id in ref.fact_ids}
    related_ids.update(item.record_id for item,observation,_ in entries if item.kind=='OBSERVATION' and any(
        (ref.proof_fingerprint,ref.observer_id,ref.phase)==(observation.proof_fingerprint,observation.observer_id,observation.phase) for ref in refs))
    related=tuple(item for item,_,_ in entries if item.record_id in related_ids and item.record_id!=record_id)
    outcome_ref=entries[0][0].record_id
    supporting=link.kind in {'TRACE','OUTCOME'} or link.kind=='OBSERVATION' and value.level!='VERDICT_REQUIRED'
    limitations=['本次判断只覆盖当时冻结的规则、账号、资源和观察范围。']
    if document.schema_version=='1':limitations.append('这份旧证据未保存逐次提交或内容比较值，无法补回当时没有记录的细节。')
    if supporting:limitations.append('这条过程记录不能单独证明权限安全或业务后果。')
    method='；'.join(dict.fromkeys(METHODS[ref.method] for ref in refs))
    if refs:
        selected_proofs={ref.proof_fingerprint for ref in refs}
        bindings={proof.binding_fingerprint for proof in case.proof_requirements if proof.proof_fingerprint in selected_proofs}
        expected=[proof.expected_state for proof in configuration.proofs if proof.binding_fingerprint in bindings and proof.expected_state is not None]
        if expected:method+=' 本次要核对的目标状态为：'+'、'.join(dict.fromkeys(expected))+'。'
    if not method:
        method='读取同一封存证据中的实际执行核对。' if link.kind=='OUTCOME' else '读取本题显式执行事件及它记录的前序关系；不按时间相邻推断因果。' if link.kind=='TRACE' else '原观察只保存了来源、阶段和判断字段，没有封存更细的采集步骤。'
    reasons=[REASONS.get(code,f'已发布原因 {code} 尚无对应说明，请结合原记录核对。') for code in result.reason_codes]
    if not reasons:
        reasons=['已发布结果确认本题的身份、请求与资源关联、必要证明和恢复条件满足要求。'+('对应正常业务对照也已通过。' if case.permission.expectation=='DENY' else '')] if result.verdict.value=='SAFE' else ['本题未封存可读的原因说明，保留已发布结论和具体记录。']
    relevant_reasons=tuple(item.record_id for item,observation,_ in entries if item.kind=='OBSERVATION' and observation.level=='VERDICT_REQUIRED' and observation.phase in {'AFTER','EVENTUAL'})
    actual={'MATCH':'与计划一致','MISMATCH':'与计划不一致','UNKNOWN':'尚未独立确认'}[outcome.actual_identity_status]
    association=f'实际账号{actual}；记录与本次请求'+('对应' if outcome.run_correlated else '尚未确认对应')+'；记录与本题资源'+('对应。' if outcome.resource_correlated else '尚未确认对应。')
    sections=(
        VerificationSection(key='rule',title='本次要验证什么',status='CONFIRMED',text=f'{subject.label}对{owner.label}拥有的资源“{case.resource_id}”，'+('不得' if case.permission.expectation=='DENY' else '可以')+configuration.display_name+f'。采用权限修订 {case.permission.revision}。',record_refs=(outcome_ref,)),
        VerificationSection(key='experiment',title='这次怎样执行',status='CONFIRMED' if outcome.actual_identity_status=='MATCH' else 'LIMITED',
            text=f'计划使用{subject.label}执行“{configuration.display_name}”；实际账号{actual}。'+('未取得HTTP状态。' if outcome.http_status is None else f'请求返回HTTP {outcome.http_status}。')+'请求状态需要与实际业务后果一起阅读。',record_refs=(outcome_ref,)),
        VerificationSection(key='method',title='怎样取得这条证据',status='CONFIRMED' if refs or link.kind in {'TRACE','OUTCOME'} else 'UNKNOWN',text=method,record_refs=(record_id,)),
        VerificationSection(key='association',title='为什么属于本次检查',status='CONFIRMED' if outcome.actual_identity_status=='MATCH' and outcome.run_correlated and outcome.resource_correlated else 'LIMITED',text=association,record_refs=(outcome_ref,)),
        VerificationSection(key='reason',title='为什么得到这个判断',status='CONFIRMED' if all(code in REASONS for code in result.reason_codes) and (result.reason_codes or result.verdict.value=='SAFE') else 'UNKNOWN',text=' '.join(reasons),record_refs=relevant_reasons),
        VerificationSection(key='boundary',title='这条记录能说明到哪里',status='LIMITED',text=' '.join(limitations),record_refs=()),
    )
    digest=hashlib.sha256(canonical_check_document(document)).hexdigest()
    result_index=next(index for index,item in enumerate(package.result.case_results) if item.case_id==case_id)
    # 每段说明指向已封存字段；不把“来自某次检查”当作可以打开的具体出处。
    locations={'rule':('/case/permission',digest),'experiment':('/outcome',digest),
        'method':('/fact_references' if refs else pointer,digest),'association':('/outcome',digest),
        'reason':(f'/case_results/{result_index}/reason_codes',hashlib.sha256(canonical_check_document(package.result)).hexdigest()),
        'boundary':('/case',digest)}
    source_fragments={'rule':case.permission.model_dump(mode='json'),'experiment':outcome.model_dump(mode='json'),
        'method':dict(methods=[ref.model_dump(mode='json') for ref in refs]) if refs else dict(record_id=record_id),
        'association':dict(actual_identity_status=outcome.actual_identity_status,run_correlated=outcome.run_correlated,resource_correlated=outcome.resource_correlated),
        'reason':dict(reason_codes=list(result.reason_codes)),
        'boundary':dict(resource_id=case.resource_id,permission=case.permission.model_dump(mode='json'))}
    sections=tuple(section.model_copy(update={'source':dict(logical_file='result.json' if section.key=='reason' else 'evidence/'+evidence_id+'.json',
        pointer=locations[section.key][0],sha256=locations[section.key][1]),'fragment':source_fragments[section.key]}) for section in sections)
    values=[]
    if link.kind=='FACT':
        data=value.data;fragment=dict(fact_id=value.fact_id,observed_at_us=value.observed_at_us,collector_kind=value.collector_kind,
            collector_version=value.collector_version,complete=value.complete,reason_codes=value.reason_codes,data=data.model_dump(mode='json'))
        if data.kind=='COMMITTED_STATE':values=[dict(label='.'.join(change.path),before=change.before,after=change.after) for change in data.changes]
        elif data.kind=='FILE_RECEIPT':values=[dict(label='内容大小（字节）',before=data.expected.size,after=data.actual_size),dict(label='SHA-256',before=data.expected.sha256,after=data.actual_sha256),dict(label='完整接收',value=data.complete)]
        elif data.kind=='FIELD_DISCLOSURE':values=[dict(label=item.path,value='与参照一致' if item.matched else '未形成一致比较') for item in data.fields]
        elif data.kind=='REFERENCE_ARTIFACT':values=[dict(label='参照大小（字节）',value=data.manifest.size),dict(label='参照SHA-256',value=data.manifest.sha256)]
        else:values=[dict(label='账号一致',value=data.subject_match),dict(label='角色一致',value=data.role_match)]
    elif link.kind=='TRACE':
        names=('event_id','parent_event_ids','kind','semantic_key','authorization_decision','effect_id','dispatch_effect_ids','source_component','source_location','recorded_at_us')
        fragment={key:val for key,val in value.model_dump(mode='json').items() if key in names}
        values=[dict(label='记录位置',value=value.source_component+' · '+value.source_location)]
    else:
        fragment=value.model_dump(mode='json',exclude={'correlation_refs'})
        if refs:
            # 归约窗口也必须可见，才能解释闭合与未发生；不导出原请求nonce。
            fragment['collection']=tuple(ref.model_dump(mode='json') for ref in refs)
            window=refs[0].record_window
            if window is not None:values=[dict(label='.'.join(window.field_path),before=window.before_value,after=window.after_value),dict(label='独立提交数',value=window.operation_count),dict(label='请求已闭合',value=window.scope_state=='COMPLETE')]
            elif refs[0].file_window is not None:values=[dict(label='本次请求已闭合',value=refs[0].file_window.scope_state=='COMPLETE')]
    return EvidenceRecordView(project_id=package.request.project_id,run_id=document.run_id,case_id=case_id,action_id=document.action_id,
        evidence_id=evidence_id,record=link,summary=_summary(link,value),published_judgement=JUDGEMENTS[result.verdict.value],
        role='SUPPORTING' if supporting else 'PROOF',verification=sections,values=tuple(values),
        location=dict(logical_file='evidence/'+evidence_id+'.json',sha256=digest,pointer=pointer),
        fragment=fragment,related_records=related,limitations=tuple(limitations))
