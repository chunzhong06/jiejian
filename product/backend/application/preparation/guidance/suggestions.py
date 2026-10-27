# 在原准备事实之上保存有界建议；建议与真实账号、绑定、授权、预检查和采用保持独立。
from __future__ import annotations

import time
from urllib.parse import urlencode
from uuid import uuid4

from product.backend.domain.boundaries.entities import boundary_sha256
from product.backend.domain.errors import ErrorCode, JiejianError
from product.backend.domain.preparation.suggestions import PreparationSuggestionRevisionV2, SuggestionItemBasis, SavePreparationSuggestion
from product.backend.application.preparation.guidance.suggestion_targets import resolve_target, validate_existing_references


class PreparationSuggestionService:
    def __init__(self, *, uow_factory, proofs, boundaries, candidates, preparation, clock_us=None):
        self._uow, self._proofs, self._boundaries = uow_factory, proofs, boundaries
        self._candidates, self._preparation = candidates, preparation
        self._clock = clock_us or (lambda:time.time_ns()//1000)

    def _snapshot(self, work, project_id):
        facts = self._proofs._facts(work, project_id)
        bindings = []
        for action in facts.boundary.actions:
            values = [work.action_preparation.execution(action.action_id, action.revision),
                work.action_preparation.recovery(action.action_id, action.revision),
                *[work.action_preparation.evidence(action.action_id, action.revision, effect.effect_id) for effect in action.effect_catalog]]
            bindings.extend(value.binding_fingerprint for value in values if value is not None)
        source_refs = work.proof_sources.preparation_references(project_id)
        recordings = work.recordings.preparation_references(project_id)
        candidate_refs = work.rule_candidates.head_references(project_id)
        understanding = facts.understanding
        source_current = bool(understanding and understanding.source_analysis_authorized and understanding.source_fingerprint
            and facts.observed_source == understanding.source_fingerprint)
        known_code = {} if not source_current else {item.candidate_id:item for item in (*understanding.role_candidates,*understanding.action_candidates)
            if not item.stale and item.decision.value != 'REJECTED' and item.evidence}
        basis = 'psb_' + boundary_sha256({'proof_basis':facts.basis_id,'bindings':sorted(bindings),
            'proof_contracts':['TRANSACTION_HISTORY_V2','RESOURCE_FIELDS_V1','OBJECT_CREATION_V1'],
            'source_revision':None if understanding is None else understanding.revision,
            'source_authorized':bool(understanding and understanding.source_analysis_authorized),
            'recordings':recordings,'candidate_references':candidate_refs,'sources':source_refs,
            'read_scopes':[value.model_dump(mode='json') for value in work.proof_sources.scopes(project_id)]})
        return {'facts':facts,'basis_id':basis,'recordings':recordings,'known_code':known_code,
            'source_current':source_current,'candidate_references':candidate_refs}

    def context(self, project_id):
        with self._uow() as work:
            snapshot = self._snapshot(work, project_id)
            heads = work.preparation_suggestions.list(project_id, limit=50)
            latest = None if not heads else work.preparation_suggestions.get(project_id, heads[0]['suggestion_id'], heads[0]['revision'])
            facts = snapshot['facts']
            return {'project_id':project_id,'basis_id':snapshot['basis_id'],'input_schema':SavePreparationSuggestion.model_json_schema(),
                'source_current':snapshot['source_current'],
                'source_hints':[{'candidate_id':item.candidate_id,'label':item.display_name,
                    'locations':[{'relative_path':e.relative_path,'line_start':e.line_start,'line_end':e.line_end,'symbol':e.symbol} for e in item.evidence[:2]]}
                    for item in tuple(snapshot['known_code'].values())[:32]],
                'actors':[{'actor_id':item.actor_id,'revision':item.revision,'label':item.display_name} for item in facts.boundary.actors],
                'candidate_references':snapshot['candidate_references'],
                'available_recordings':snapshot['recordings'][-50:],
                'supported_evidence_capabilities':['MANAGED_TRANSACTION_RECORDS'],
                'evidence_capability_note':'material.capability 是能力标识，请使用 supported_evidence_capabilities。RESOURCE_FIELDS_V1 与 TRANSACTION_HISTORY_V2 是来源合同 source_contract_id，不是能力标识；合同不应填入 capability，也不表示对应读取能力缺失。',
                'latest':None if latest is None else self._view(work,latest,snapshot),
                'suggestion_references':heads,
                'limits':{'max_items':50,'max_unresolved_questions':10,'max_bytes':262144},
                'note':'可以先整理尚未生成的账号、数据和结果怎样准备；建议不会把材料改成已齐备。'}

    def basis(self, project_id):
        with self._uow() as work:
            return self._snapshot(work,project_id)['basis_id']

    def _validate(self, work, project_id, item, snapshot):
        target = resolve_target(work, project_id, item.target, self._candidates, self._boundaries)
        if target['state'] in {'STALE','ASSOCIATION_UNAVAILABLE'}:
            raise JiejianError(ErrorCode.STATE_PRECONDITION, '材料建议对应的规则引用需要重新核对')
        known_code = snapshot['known_code']
        refs = set(item.source.candidate_ids)
        entry = getattr(item.material,'entry_candidate_id',None)
        if entry is not None:
            refs.add(entry)
        if not refs <= set(known_code):
            raise JiejianError(ErrorCode.STATE_PRECONDITION, '源码定位未核实或已经变化；请重新分析，或明确保留为假设')
        if item.material.kind == 'evidence' and item.material.capability not in {None,'MANAGED_TRANSACTION_RECORDS'}:
            raise JiejianError(ErrorCode.INPUT_INVALID, 'material.capability 不是已注册能力。当前支持 MANAGED_TRANSACTION_RECORDS，请核对 supported_evidence_capabilities；RESOURCE_FIELDS_V1 等是来源合同 source_contract_id，不能填入 capability。保留原业务结果要求，不要据此判定读取能力缺失。')
        facts = snapshot['facts']
        if target['state'] == 'APPROVED' and item.material.kind in {'identity','resource'}:
            rules = [rule for rule in facts.boundary.permission_intents if (rule.business_action_id,rule.action_revision)==(target['action_id'],target['action_revision'])]
            roles = {(rule.resource_owner_actor_id,rule.resource_owner_actor_revision) for rule in rules}
            if item.material.kind == 'identity':
                roles.update((rule.subject_actor_id,rule.subject_actor_revision) for rule in rules)
            if (target['actor_id'],target['actor_revision']) not in roles:
                raise JiejianError(ErrorCode.STATE_PRECONDITION, '建议角色不属于该动作当前规则要求的账号或所有者')
        if item.material.kind == 'identity' and item.material.slot_id is not None:
            prepared = self._preparation.get(project_id)
            slots = [slot for action in prepared.actions if (action.action_id,action.action_revision)==(target['action_id'],target['action_revision'])
                for slot in action.identity_requirements.slots]
            if not any(slot.requirement.slot_id == item.material.slot_id
                and (slot.requirement.actor_id,slot.requirement.actor_revision)==(target['actor_id'],target['actor_revision']) for slot in slots):
                raise JiejianError(ErrorCode.STATE_PRECONDITION, '账号槽位不属于当前准备要求')
        validate_existing_references(work, project_id, item, target, facts, snapshot['recordings'])
        return target

    def save(self, project_id, command: SavePreparationSuggestion, *, submitted_via='LOCAL_GUI'):
        if submitted_via not in {'LOCAL_GUI','MCP'}:
            raise JiejianError(ErrorCode.INPUT_INVALID,'材料建议来源无效')
        fingerprint = boundary_sha256({'command':command.model_dump(mode='json'),'submitted_via':submitted_via})
        with self._uow() as work:
            work.acquire_write_lock()
            receipt = work.preparation_suggestions.receipt(project_id,command.operation_id)
            if receipt:
                if receipt[0] != fingerprint:
                    raise JiejianError(ErrorCode.STATE_PRECONDITION,'操作标识已用于另一份材料建议')
                return self._view(work,self._required(work,project_id,receipt[1],receipt[2]),self._snapshot(work,project_id))
            snapshot = self._snapshot(work,project_id)
            if command.expected_basis_id != snapshot['basis_id']:
                raise JiejianError(ErrorCode.STATE_PRECONDITION,'规则、源码或材料已经变化，请重新读取准备依据')
            if command.suggestion_id:
                current = self._required(work,project_id,command.suggestion_id)
                if current.revision != command.expected_revision:
                    raise JiejianError(ErrorCode.STATE_PRECONDITION,'材料建议已有新修订，请重新读取')
            elif len(work.preparation_suggestions.list(project_id,limit=201)) >= 200:
                raise JiejianError(ErrorCode.STATE_PRECONDITION,'材料建议数量已达上限，请更新已有建议')
            for item in command.content.items:
                self._validate(work,project_id,item,snapshot)
            value = PreparationSuggestionRevisionV2(project_id=project_id,suggestion_id=command.suggestion_id or 'psg_'+uuid4().hex,
                revision=(command.expected_revision or 0)+1,basis_id=snapshot['basis_id'],content=command.content,
                item_bases=tuple(SuggestionItemBasis(item_id=item.item_id, fingerprint=self._item_basis(work, project_id, item, snapshot)) for item in command.content.items),
                submitted_via=submitted_via,created_at_us=self._clock())
            # 源码属于数据库外部；提交前再核验，不能在文件变化后接受混合依据。
            if self._snapshot(work,project_id)['basis_id'] != snapshot['basis_id']:
                raise JiejianError(ErrorCode.STATE_PRECONDITION,'整理期间应用条件已经变化，请重新读取')
            work.preparation_suggestions.append(value,expected_revision=command.expected_revision)
            work.preparation_suggestions.add_receipt(project_id,command.operation_id,fingerprint,value)
            result = self._view(work,value,snapshot)
            work.commit()
            return result

    @staticmethod
    def _item_basis(work, project_id, item, snapshot):
        # 建立办法依赖源码和明确引用的配置，不依赖其他材料的登录、录制、预检查进度。
        facts = snapshot['facts']
        refs = set(item.source.candidate_ids)
        entry = getattr(item.material, 'entry_candidate_id', None)
        if entry:
            refs.add(entry)
        code = {ref: [entry.model_dump(mode='json') for entry in snapshot['known_code'][ref].evidence]
            for ref in sorted(refs) if ref in snapshot['known_code']}
        sources = []
        for source_id in getattr(item.material, 'existing_source_ids', ()):
            source = work.proof_sources.source(project_id, source_id)
            sources.append([source_id, None if source is None else source.config.model_dump(mode='json')])
        rules = [] if item.target.kind != 'APPROVED' else sorted(
            (rule.intent_id, rule.revision, rule.intent_hash) for rule in facts.boundary.permission_intents
            if rule.business_action_id == item.target.action_id)
        return boundary_sha256({'source': facts.observed_source, 'source_current': snapshot['source_current'],
            'code': code, 'sources': sources, 'rules': rules})

    def _view(self, work, value, snapshot):
        head = self._required(work,value.project_id,value.suggestion_id)
        matches_basis = value.basis_id == snapshot['basis_id']
        latest = head.revision == value.revision
        bases = {item.item_id:item.fingerprint for item in getattr(value, 'item_bases', ())}
        items = []
        for item in value.content.items:
            reasons = []
            try:
                target = resolve_target(work,value.project_id,item.target,self._candidates,self._boundaries)
                if target['state'] in {'STALE','ASSOCIATION_UNAVAILABLE'}:
                    reasons.append('RULE_REFERENCE_CHANGED')
            except JiejianError:
                target = {'state':'STALE','action_label':'原规则引用需要核对','action_id':None,'action_revision':None}
                reasons.append('RULE_REFERENCE_CHANGED')
            if not latest:
                reasons.append('NEWER_REVISION')
            if value.schema_version == '2':
                if bases[item.item_id] != self._item_basis(work, value.project_id, item, snapshot):
                    reasons.append('ITEM_DEPENDENCY_CHANGED')
            elif not matches_basis:
                # 旧根没有逐项摘要；不能从今天的源码倒推出当时的依赖。
                reasons.append('LEGACY_BASIS_UNVERIFIED')
            if not reasons:
                try:
                    self._validate(work, value.project_id, item, snapshot)
                except JiejianError:
                    reasons.append('MATERIAL_REFERENCE_CHANGED')
            query = {'project_id':value.project_id,'materials':'1','suggestion_id':value.suggestion_id,
                'suggestion_revision':value.revision,'material_kind':item.material.kind}
            if target.get('action_id'):
                query['action_id'] = target['action_id']
            locations = [dict(candidate_id=ref,relative_path=e.relative_path,line_start=e.line_start,line_end=e.line_end,symbol=e.symbol)
                for ref in item.source.candidate_ids if ref in snapshot['known_code'] for e in snapshot['known_code'][ref].evidence[:2]]
            items.append({'item_id':item.item_id,'resolved_target':target,'current':not reasons, 'reason_codes':reasons,
                'source_locations':locations if not reasons else [],'return_url':'#/tests?'+urlencode(query)})
        by_id = {item['item_id']:item for item in items}
        def resolve_dependencies(item_id):
            row = by_id[item_id]
            if item_id in resolved:
                return row['current']
            item = definitions[item_id]
            dependency_states = [resolve_dependencies(ref) for ref in item.depends_on]
            if not all(dependency_states):
                row['current'] = False
                row['source_locations'] = []
                row['reason_codes'].append('DEPENDENCY_NEEDS_REVIEW')
            resolved.add(item_id)
            return row['current']
        definitions = {item.item_id:item for item in value.content.items}
        resolved = set()
        for item in items:
            resolve_dependencies(item['item_id'])
        count = sum(item['current'] for item in items)
        state = 'SUPERSEDED' if not latest else ('CURRENT' if count == len(items) and (items or matches_basis) else 'PARTIAL' if count else 'STALE')
        return {'suggestion':value.model_dump(mode='json'),'current_basis_id':snapshot['basis_id'],
            'state':state,'latest_revision':head.revision,'items':items,
            'current_count':count,'review_count':len(items)-count,
            'review_url':'#/tests?'+urlencode({'project_id':value.project_id,'materials':'1',
                'suggestion_id':value.suggestion_id,'suggestion_revision':value.revision})}

    def show(self, project_id, suggestion_id, revision=None):
        if revision is not None and (type(revision) is not int or revision < 1):
            raise JiejianError(ErrorCode.INPUT_INVALID,'建议修订必须是正整数')
        with self._uow() as work:
            return self._view(work,self._required(work,project_id,suggestion_id,revision),self._snapshot(work,project_id))

    def receipt(self, project_id, operation_id):
        with self._uow() as work:
            receipt = work.preparation_suggestions.receipt(project_id,operation_id)
            if receipt is None:
                return {'status':'UNKNOWN','operation_id':operation_id}
            return {'status':'FOUND','operation_id':operation_id,
                'suggestion':self._view(work,self._required(work,project_id,receipt[1],receipt[2]),self._snapshot(work,project_id))}

    @staticmethod
    def _required(work, project_id, suggestion_id, revision=None):
        value = work.preparation_suggestions.get(project_id,suggestion_id,revision)
        if value is None:
            raise JiejianError(ErrorCode.RECORD_NOT_FOUND,'指定的材料建议修订不存在')
        return value
