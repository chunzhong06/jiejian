# 范围决定与覆盖关联共用候选CAS和回执；不授予MCP批准能力，不执行目标。
import json
from product.backend.domain.boundaries.entities import boundary_sha256
from product.backend.domain.boundaries.candidate_scope import ScopeDecision, ScopeReference, CoverageLink, scope_items, scope_decision_fingerprint
from product.backend.domain.boundaries.candidate_reviews import boundary_review_items
from product.backend.domain.boundaries.candidate_reviews import CoverageDependency, coverage_dependency_fingerprint
from product.backend.domain.boundaries.rule_candidates import revised_candidate, ScopedCandidateContentInput
from product.backend.domain.errors import ErrorCode, JiejianError


def merge_content(current, incoming):
    if current is None:
        raise JiejianError(ErrorCode.INPUT_INVALID, "分批整理需要已有候选和最新修订")
    if incoming.original_text != current.content.original_text:
        raise JiejianError(ErrorCode.STATE_PRECONDITION, "分批补充时保留原文；修改原文请提交完整修订")
    data = current.content.model_dump(mode="json")
    for field, key in (("actors", "item_id"), ("actions", "item_id"), ("permissions", "item_id"),
                       ("scenarios", "scenario_id"), ("requirement_sources", "requirement_id"), ('coverage_suggestions', 'issue_id')):
        items = {item[key]: item for item in data.get(field, [])}
        items.update({getattr(item, key): item.model_dump(mode="json") for item in getattr(incoming, field)})
        data[field] = list(items.values())
    examples = {item.get("permission_item_id") or item["description"]: item for item in data["examples"]}
    examples.update({item.permission_item_id or item.description: item.model_dump(mode="json") for item in incoming.examples})
    data["examples"] = list(examples.values())
    for field in ("unresolved_questions", "unsupported_constraints"):
        data[field] = list(dict.fromkeys([*data[field], *getattr(incoming, field)]))
    for scene in data['scenarios']:
        scene.pop('scenario_fingerprint', None)
    return ScopedCandidateContentInput.model_validate_json(json.dumps(data))


def decide_scope(service, project_id, candidate_id, command, *, coverage=False):
    kind = "COVERAGE_LINK" if coverage else "SCOPE_DECISION"
    fingerprint = boundary_sha256({"kind": kind, "candidate_id": candidate_id, "command": command.model_dump(mode="json")})
    with service._uow_factory() as work:
        work.acquire_write_lock()
        receipt = work.rule_candidates.receipt(project_id, "DECIDE", command.operation_id)
        if receipt:
            service._same_request(receipt, fingerprint)
            return service._view(work, service._required(work, project_id, receipt[1], receipt[2]))
        current = service._required(work, project_id, candidate_id)
        draft = service._boundaries.maintenance_draft(project_id, work=work, allow_empty=True)
        service._current_basis(command.expected_basis_id, draft)
        if current.revision != command.expected_revision or current.basis_id != command.expected_basis_id:
            raise JiejianError(ErrorCode.STATE_PRECONDITION, "内容已变化，请读取最新修订", details={"reason": "CONFLICT"})
        if work.rule_candidates.visibility(candidate_id)["archived"]:
            raise JiejianError(ErrorCode.STATE_PRECONDITION, "请先恢复候选")
        if work.rule_candidates.proposal_id(candidate_id, current.revision):
            raise JiejianError(ErrorCode.STATE_PRECONDITION, "本修订已有提案，请返回修改形成新修订")
        if coverage:
            item = next((item for item in boundary_review_items(current) if item['issue_id'] == command.issue_id), None)
            if item is None or item['issue_fingerprint'] != command.issue_fingerprint or item['status'] != 'OPEN' or item['decision'].output_revision != command.review_revision or item['decision'].outcome not in {'PREPARATION_DEPENDENCY', 'EVIDENCE_GAP', 'COVERAGE_GAP'}:
                raise JiejianError(ErrorCode.STATE_PRECONDITION, "请先确认这是准备、证据或覆盖缺口，并读取最新依据")
            ids = {item.item_id for item in current.content.permissions if item.effective_state.value == 'ACTIVE'}
            if not {target.permission_item_id for target in command.targets} <= ids:
                raise JiejianError(ErrorCode.INPUT_INVALID, "覆盖只能关联当前候选中的有效权限")
            record = CoverageLink(**command.model_dump(), output_revision=current.revision+1, created_at_us=service._clock_us())
            updates = {"coverage_links": tuple(v for v in getattr(current, 'coverage_links', ()) if v.issue_id != command.issue_id)+(record,)}
            dependency = CoverageDependency(issue_id=command.issue_id, output_revision=record.output_revision,
                fingerprint=coverage_dependency_fingerprint(current, command.targets))
            updates['coverage_dependencies'] = tuple(v for v in getattr(current, 'coverage_dependencies', ()) if v.issue_id != command.issue_id)+(dependency,)
        else:
            item = next((item for item in scope_items(current) if item['source'].requirement_id == command.requirement_id), None)
            if item is None or item['fingerprint'] != command.requirement_fingerprint:
                raise JiejianError(ErrorCode.STATE_PRECONDITION, "要求来源或解释已变化，请重新读取")
            record = ScopeDecision(**command.model_dump(), output_revision=current.revision+1, created_at_us=service._clock_us())
            updates = {"scope_decisions": tuple(v for v in getattr(current, 'scope_decisions', ()) if v.requirement_id != command.requirement_id)+(record,)}
            updates['scope_references'] = tuple(v for v in current.scope_references if v.requirement_id != command.requirement_id)
        value = revised_candidate(current, revision=current.revision+1, submitted_via='LOCAL_GUI', created_at_us=service._clock_us(), **updates)
        work.rule_candidates.append(value, expected_revision=current.revision)
        work.rule_candidates.add_receipt(project_id, 'DECIDE', command.operation_id, fingerprint, value)
        result = service._view(work, value)
        work.commit()
        return result


def decide_scope_batch(service, project_id, candidate_id, command):
    """一次人工审阅形成一个修订和回执；任一来源过期或关联无效时整批不写入。"""
    fingerprint = boundary_sha256({'kind':'SCOPE_BATCH', 'candidate_id':candidate_id, 'command':command.model_dump(mode='json')})
    with service._uow_factory() as work:
        work.acquire_write_lock()
        receipt = work.rule_candidates.receipt(project_id, 'DECIDE', command.operation_id)
        if receipt:
            service._same_request(receipt, fingerprint)
            return service._view(work, service._required(work, project_id, receipt[1], receipt[2]))
        current = service._required(work, project_id, candidate_id)
        draft = service._boundaries.maintenance_draft(project_id, work=work, allow_empty=True)
        service._current_basis(command.expected_basis_id, draft)
        if current.revision != command.expected_revision or current.basis_id != command.expected_basis_id:
            raise JiejianError(ErrorCode.STATE_PRECONDITION, '内容已变化，整批决定尚未保存，请读取最新修订', details={'reason':'CONFLICT'})
        if work.rule_candidates.visibility(candidate_id)['archived'] or work.rule_candidates.proposal_id(candidate_id, current.revision):
            raise JiejianError(ErrorCode.STATE_PRECONDITION, '请先恢复候选，或返回修改已有提案')
        items = {item['source'].requirement_id:item for item in scope_items(current)}
        choices = {item.requirement_id:item for item in command.choices}
        for choice in command.choices:
            item = items.get(choice.requirement_id)
            if item is None or item['fingerprint'] != choice.requirement_fingerprint:
                raise JiejianError(ErrorCode.STATE_PRECONDITION, '要求来源或解释已变化，整批决定尚未保存')
        common = {'operation_id':command.operation_id, 'expected_revision':command.expected_revision,
            'expected_basis_id':command.expected_basis_id, 'output_revision':current.revision+1, 'created_at_us':service._clock_us()}
        decisions = [item for item in getattr(current, 'scope_decisions', ()) if item.requirement_id not in choices]
        references = [item for item in getattr(current, 'scope_references', ()) if item.requirement_id not in choices]
        for choice in command.choices:
            if choice.disposition != 'SUPPORTING':
                decisions.append(ScopeDecision(**choice.model_dump(exclude={'related_requirement_ids'}), **common))
        value = revised_candidate(current, revision=current.revision+1, submitted_via='LOCAL_GUI', created_at_us=common['created_at_us'],
            scope_decisions=tuple(decisions), scope_references=tuple(references))
        updated = {item['source'].requirement_id:item for item in scope_items(value)}
        for choice in command.choices:
            if choice.disposition != 'SUPPORTING':
                continue
            fingerprints, linked = [], set()
            for target_id in choice.related_requirement_ids:
                target = updated.get(target_id)
                if target is None or target['status'] != 'CONFIRMED' or target['decision'].disposition != 'IN_SCOPE':
                    raise JiejianError(ErrorCode.INPUT_INVALID, '补充依据只能关联已经明确纳入的业务要求，可与业务要求在同一批确认')
                fingerprints.append(scope_decision_fingerprint(target['decision']))
                linked.update(target['source'].permission_item_ids)
            if not set(items[choice.requirement_id]['source'].permission_item_ids) <= linked:
                raise JiejianError(ErrorCode.INPUT_INVALID, '这条来源关联的权限未被所选业务要求完整承接，请补齐关联或修正候选，不能直接排除')
            references.append(ScopeReference(**choice.model_dump(), **common, related_decision_fingerprints=tuple(fingerprints)))
        value = revised_candidate(value, scope_references=tuple(references))
        work.rule_candidates.append(value, expected_revision=current.revision)
        work.rule_candidates.add_receipt(project_id, 'DECIDE', command.operation_id, fingerprint, value)
        result = service._view(work, value)
        work.commit()
        return result


def protect_scope(current, content):
    old = {item.requirement_id for item in getattr(current.content, 'requirement_sources', ())}
    if not old <= {item.requirement_id for item in content.requirement_sources}:
        raise JiejianError(ErrorCode.STATE_PRECONDITION, "已记录要求不能静默删除；保留来源并由用户确认范围，历史决定继续保留")


def issue_tasks(issues, reviews):
    by_id = {item['issue_id']: item for item in reviews}
    tasks = []
    for issue in issues:
        code = issue['code']
        review = by_id.get(issue.get('issue_id'))
        # 未整理的旧问题先交Agent提供可核对的说明；不是要求用户替Agent填写技术诊断。
        human = code in {'SCOPE_DECISION_REQUIRED', 'NEEDS_DECISION'} or review is not None and review['status'] in {'NEEDS_DECISION', 'STALE'} and review.get('suggestion') is not None
        limitation = code == 'HISTORY_CAPABILITY_REQUIRED' or review is not None and review['status'] == 'OPEN' and review['decision'].outcome in {'PREPARATION_DEPENDENCY', 'EVIDENCE_GAP', 'COVERAGE_GAP'}
        tasks.append({**issue, 'handler': 'USER' if human else 'CAPABILITY' if limitation else 'AGENT',
            'stage': 'RULES', 'agent_can_revise_draft':True,
            'next_step': '核对实际要求；Agent仍可先修正草稿并提供建议' if human else '说明对应要求、缺失能力与恢复条件；补齐入口和证明后才能检查' if limitation else '先修正明确错误，保留旧问题并提交有依据的纠正建议；不代用户作决定'})
    return sorted(tasks, key=lambda item:{'AGENT':0,'USER':1,'CAPABILITY':2}[item['handler']])
