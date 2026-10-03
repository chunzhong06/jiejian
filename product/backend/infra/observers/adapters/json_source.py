# 普通JSON来源的严格有界读取与事实投影；不接受原始响应自报可靠性，不计算Verdict。
from __future__ import annotations
from dataclasses import dataclass
import json
import re
import math

from product.protocols.preparation.proof_sources import ProofCheckItem

HISTORY_FIELDS=frozenset({'resource_id','owner_id','state','version','effect_count','history_generation',
    'operation_id','operation_resource_id','operation_subject_id','operation_before_version','operation_after_version',
    'operation_state','unfinished_effects'})
INTEGER_FIELDS=frozenset({'version','effect_count','operation_before_version','operation_after_version','unfinished_effects'})
IDENTIFIER_FIELDS=frozenset({'resource_id','owner_id','operation_id','operation_resource_id','operation_subject_id','history_generation'})


class SourceReadError(ValueError):
    def __init__(self,code,mapping_key=None):
        self.code,self.mapping_key=code,mapping_key
        super().__init__(code)


def strict_json(raw:bytes,limit=262144):
    if not isinstance(raw,bytes) or len(raw)>limit:raise SourceReadError('RESPONSE_TOO_LARGE')
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result:raise SourceReadError('JSON_DUPLICATE_KEY')
            result[key]=value
        return result
    try:
        data=json.loads(raw.decode('utf-8'),object_pairs_hook=unique,
            parse_constant=lambda _:(_ for _ in ()).throw(SourceReadError('JSON_NONFINITE')))
    except (ValueError,UnicodeError,RecursionError) as error:
        if isinstance(error,SourceReadError):raise
        raise SourceReadError('JSON_INVALID') from None
    pending=[(data,0)];count=0
    while pending:
        value,depth=pending.pop();count+=1
        if depth>16 or count>4096:raise SourceReadError('JSON_STRUCTURE_LIMIT')
        if isinstance(value,float) and not math.isfinite(value):raise SourceReadError('JSON_NONFINITE')
        if isinstance(value,dict):pending.extend((item,depth+1) for item in value.values())
        elif isinstance(value,list):pending.extend((item,depth+1) for item in value)
    if not isinstance(data,dict):raise SourceReadError('JSON_OBJECT_REQUIRED')
    return data


def scalar(data,path,key=None):
    value=data
    for part in path:
        if not isinstance(value,dict) or part not in value:raise SourceReadError('MAPPING_MISSING',key)
        value=value[part]
    if key in INTEGER_FIELDS:
        if type(value) is not int or not 0<=value<=9_007_199_254_740_991:raise SourceReadError('MAPPING_TYPE_INVALID',key)
    elif not isinstance(value,str) or not value or len(value)>512:
        raise SourceReadError('MAPPING_TYPE_INVALID',key)
    elif key in IDENTIFIER_FIELDS and not re.fullmatch(r'[\w.:-]{1,256}',value):
        raise SourceReadError('MAPPING_TYPE_INVALID',key)
    if value in {'[REDACTED]','<redacted>'}:raise SourceReadError('MAPPING_REDACTED',key)
    return value


def mapped_values(raw,config):
    data=strict_json(raw,config.max_response_bytes)
    required=HISTORY_FIELDS if config.source_contract_id=='SYNC_RESOURCE_HISTORY_V1' else {'resource_id','owner_id'}
    missing=required-set(config.mappings)
    if missing:raise SourceReadError('MAPPING_REQUIRED',sorted(missing)[0])
    return {key:scalar(data,path,key) for key,path in config.mappings.items()},data


def preflight_source_checks(raw,config,*,resource_id,owner_subject_id,contract):
    try:
        values,_=mapped_values(raw,config)
        checks=[ProofCheckItem(code='MAPPING_READABLE',status='CONFIRMED',mapping_key=key) for key in config.mappings]
        matching=values['resource_id']==resource_id and values['owner_id']==owner_subject_id
        checks.append(ProofCheckItem(code='RESOURCE_OWNER_MATCH' if matching else 'RESOURCE_OWNER_MISMATCH',
            status='CONFIRMED' if matching else 'MISSING'))
        checks.append(ProofCheckItem(code='SOURCE_CONTRACT_VERIFIED' if contract is not None else 'CONTRACT_UNVERIFIED',
            status='CONFIRMED' if contract is not None else 'UNSUPPORTED'))
        if config.source_contract_id=='SYNC_RESOURCE_HISTORY_V1':
            completed=(values['operation_resource_id']==resource_id and values['operation_state']=='completed'
                and values['unfinished_effects']==0 and values['operation_after_version']==values['version']
                and values['operation_before_version']<=values['operation_after_version'])
            checks.append(ProofCheckItem(code='OPERATION_RECORD_COMPLETE' if completed else 'COMPLETION_UNCONFIRMED',
                status='CONFIRMED' if completed else 'MISSING'))
        return tuple(checks)
    except SourceReadError as error:
        return (ProofCheckItem(code=error.code,status='MISSING',mapping_key=error.mapping_key),)


@dataclass(frozen=True)
class JsonHistoryFact:
    state:str
    closure:str
    reason_codes:tuple[str,...]=()


def project_history(before,after,*,operation_id,subject_id,resource_id,owner_id):
    """只根据同一可信记录窗口投影发生/未发生；同步完成与真实响应ID缺一不可。"""
    if before is None or after is None:return JsonHistoryFact('UNKNOWN','OPEN',('HISTORY_BASELINE_MISSING',))
    correlated=(before['resource_id']==after['resource_id']==resource_id and before['owner_id']==after['owner_id']==owner_id
        and after['operation_id']==operation_id and after['operation_resource_id']==resource_id
        and after['operation_subject_id']==subject_id and after['operation_before_version']==before['version']
        and after['operation_after_version']==after['version']==before['version']+1)
    if not correlated:return JsonHistoryFact('UNKNOWN','OPEN',('OPERATION_CORRELATION_INVALID',))
    if (before['history_generation']!=after['history_generation'] or after['effect_count']<before['effect_count']):
        return JsonHistoryFact('UNKNOWN','OPEN',('HISTORY_GENERATION_CHANGED',))
    if after['effect_count']>before['effect_count']:
        return JsonHistoryFact('CONFIRMED','CLOSED',('BUSINESS_EFFECT_RECORDED',))
    if after['operation_state']!='completed' or after['unfinished_effects']!=0:
        return JsonHistoryFact('UNKNOWN','OPEN',('COMPLETION_UNCONFIRMED',))
    return JsonHistoryFact('ABSENT','CLOSED',('COMPLETE_HISTORY_UNCHANGED',))
