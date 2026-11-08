"""在两个准确发布包之间投影变化；比较结果不修改原结论或修复状态。"""
from collections import Counter
from typing import Literal

from product.backend.domain.errors import ErrorCode, JiejianError
from product.backend.application.reading import projection_read
from product.protocols.checks.execution_request import WireModel
from product.protocols.codec import content_hash
from product.protocols.web.environment import FrozenEnvironment


ChangeKind = Literal['NEW','PERSISTING','FIXED','NO_LONGER_OBSERVED','RECURRED','UNCHANGED','INSUFFICIENT','INCOMPARABLE']


class ComparisonRun(WireModel):
    run_id: str
    created_at_us: int
    lifecycle: str
    integrity: str
    environment: FrozenEnvironment | None
    source_fingerprint: str | None
    deployment: Literal['MATCHED','UNCONFIRMED','UNKNOWN']


class ComparisonObservation(WireModel):
    case_id: str
    verdict: str | None
    expectation: str
    resource_id: str
    identity_status: str | None
    execution_outcome: str | None
    control_verdict: str | None
    evidence_ids: tuple[str, ...]


class ComparisonItem(WireModel):
    key: str
    action_label: str
    subject_label: str
    state: ChangeKind
    reasons: tuple[str, ...]
    before: ComparisonObservation | None
    after: ComparisonObservation | None


class RunComparison(WireModel):
    project_id: str
    baseline: ComparisonRun
    current: ComparisonRun
    earlier: ComparisonRun | None = None
    limitations: tuple[str, ...]
    counts: dict[str, int]
    items: tuple[ComparisonItem, ...]
    next_cursor: str | None = None


def _deployment(package):
    if package is None:
        return 'UNKNOWN'
    correspondence = package.result.runtime_correspondence
    if correspondence is None:
        return 'UNKNOWN'
    return 'MATCHED' if correspondence.before == correspondence.after == 'MATCHED' else 'UNCONFIRMED'


def _header(status, package):
    request = None if package is None else package.request
    return ComparisonRun(run_id=status.run.run_id, created_at_us=status.run.created_at_us,
        lifecycle=status.run.lifecycle.value, integrity=status.result_integrity,
        environment=status.environment, source_fingerprint=None if request is None else request.source_fingerprint,
        deployment=_deployment(package))


def _index(package):
    if package is None:
        return {}
    result = {item.case_id:item for item in package.result.case_results}
    names = {item.action_id:item.display_name for item in package.bundle.actions}
    identities = {item.identity_id:item.label for item in package.bundle.identities}
    rows = {}
    for action in package.request.actions:
        controls = {item.deny_case_id:item.allow_case_id for item in action.twins}
        for case in action.cases:
            # 没有人工确认的跨环境对应时保留准确主体和资源，不能仅凭同名角色配成同一道题。
            key = content_hash('ComparisonCase', dict(intent_id=case.permission.intent_id,
                subject_actor_id=case.subject_actor_id, owner_actor_id=case.resource_owner_actor_id,
                relation=case.permission.relation, occurrence_id=case.occurrence_id,
                subject_identity_id=case.subject_test_identity_id, owner_identity_id=case.resource_owner_test_identity_id,
                resource_id=case.resource_id))
            if key in rows:
                raise JiejianError(ErrorCode.STORAGE_STATE, '本轮存在无法唯一对应的逻辑检查项')
            observed = result.get(case.case_id)
            control = result.get(controls.get(case.case_id))
            proof_methods = sorted((item.effect_id,item.rule,item.level,_proof_method(item.reference))
                for item in case.proof_requirements)
            signature = content_hash('ComparisonContract', dict(permission=case.permission.model_dump(mode='json'),
                action_semantic_fingerprint=action.action_semantic_fingerprint,
                proof_methods=proof_methods, protected_effect_ids=case.protected_effect_ids,
                scenario=None if package.request.scenario is None else package.request.scenario.model_dump(mode='json')))
            rows[key] = dict(case=case, result=observed, control=control, signature=signature,
                action_label=names[action.action_id], subject_label=identities.get(case.subject_test_identity_id,'匿名主体'))
    return rows


def _proof_method(reference):
    if reference.kind == 'RECORDED_OBSERVATION':
        return reference.kind+':'+reference.request_template_fingerprint
    if reference.kind == 'REGISTERED_OBSERVER':
        return reference.kind+':'+reference.descriptor_fingerprint
    return reference.kind+':'+reference.query_fingerprint


def _observation(row):
    if row is None:
        return None
    case, result, control = row['case'], row['result'], row['control']
    return ComparisonObservation(case_id=case.case_id, verdict=None if result is None else result.verdict.value,
        expectation=case.permission.expectation, resource_id=case.resource_id,
        identity_status=None if result is None else result.outcome.actual_identity_status,
        execution_outcome=None if result is None else result.outcome.execution_outcome,
        control_verdict=None if control is None else control.verdict.value,
        evidence_ids=() if result is None else result.evidence_ids)


def classify_change(before, after, *, deployment, earlier=None):
    """只归约已发布的逐项结论；未执行、不同题和未确认部署各保留自己的含义。"""
    if before is None or after is None:
        return 'INSUFFICIENT', ('BASELINE_NOT_COVERED' if before is None else 'CURRENT_NOT_COVERED',)
    if before['signature'] != after['signature']:
        return 'INCOMPARABLE', ('CHECK_CONTRACT_CHANGED',)
    left, right = before['result'], after['result']
    if left is None or right is None or left.verdict.value not in {'SAFE','VULNERABLE'} or right.verdict.value not in {'SAFE','VULNERABLE'}:
        return 'INSUFFICIENT', ('PUBLISHED_FACTS_INCOMPLETE',)
    if right.verdict.value == 'VULNERABLE':
        if left.verdict.value == 'VULNERABLE':
            return 'PERSISTING', ()
        if earlier is not None and earlier['signature'] == after['signature'] and earlier['result'] is not None and earlier['result'].verdict.value == 'VULNERABLE':
            return 'RECURRED', ()
        return 'NEW', ('RELATIVE_TO_BASELINE',)
    if left.verdict.value == 'SAFE':
        return 'UNCHANGED', ()
    control = after['control']
    if control is None or control.verdict.value != 'SAFE':
        return 'INSUFFICIENT', ('NORMAL_CONTROL_NOT_RETAINED',)
    if deployment != 'MATCHED':
        return 'NO_LONGER_OBSERVED', ('DEPLOYMENT_UNCONFIRMED',)
    return 'FIXED', ()


class CheckComparisonService:
    def __init__(self, reader, stories):
        self.reader, self.stories = reader, stories

    def _runs(self, project, baseline, current, earlier):
        if baseline == current or earlier is not None and earlier in {baseline,current}:
            raise JiejianError(ErrorCode.INPUT_INVALID, '请选择不同的准确检查记录')
        left = self.reader.inspect(baseline, project_id=project)
        right = self.reader.inspect(current, project_id=project)
        old = None if earlier is None else self.reader.inspect(earlier, project_id=project)
        if left[0].run.created_at_us >= right[0].run.created_at_us or old is not None and old[0].run.created_at_us >= left[0].run.created_at_us:
            raise JiejianError(ErrorCode.INPUT_INVALID, '更早问题记录、基线和本轮需要按时间递增')
        return left, right, old

    @projection_read
    def compare(self, project, baseline, current, *, earlier=None, after=None, limit=25):
        if not 1 <= limit <= 50 or after is not None and (len(after)!=64 or any(c not in '0123456789abcdef' for c in after)):
            raise JiejianError(ErrorCode.INPUT_INVALID, '比较分页参数无效')
        left, right, old = self._runs(project, baseline, current, earlier)
        headers = _header(*left), _header(*right), None if old is None else _header(*old)
        limitations = []
        if any(item[1] is None for item in (left,right)):
            limitations.append('UNPUBLISHED_OR_INVALID_RUN')
        if any(header.deployment != 'MATCHED' for header in headers[:2]):
            limitations.append('DEPLOYMENT_VERSION_UNCONFIRMED')
        if old is not None and old[1] is None:
            limitations.append('EARLIER_RUN_UNAVAILABLE')
        before, current_rows = _index(left[1]), _index(right[1])
        before_intents = {item['case'].permission.intent_id for item in before.values()}
        current_intents = {item['case'].permission.intent_id for item in current_rows.values()}
        older = {} if old is None else _index(old[1])
        items = []
        for key in sorted(set(before)|set(current_rows)):
            a, b = before.get(key), current_rows.get(key)
            deployment = 'MATCHED' if all(header.deployment=='MATCHED' for header in headers[:2]) else 'UNKNOWN'
            state, reasons = classify_change(a,b,deployment=deployment,earlier=older.get(key))
            missing = b or a
            opposite = current_intents if b is None else before_intents
            if a is None or b is None:
                if missing['case'].permission.intent_id in opposite:
                    state, reasons = 'INCOMPARABLE', ('SUBJECT_OR_RESOURCE_BINDING_CHANGED',)
            row = b or a
            items.append(ComparisonItem(key=key,action_label=row['action_label'],subject_label=row['subject_label'],
                state=state,reasons=reasons,before=_observation(a),after=_observation(b)))
        counts = dict(Counter(item.state for item in items))
        page = [item for item in items if after is None or item.key>after][:limit+1]
        return RunComparison(project_id=project,baseline=headers[0],current=headers[1],earlier=headers[2],
            limitations=tuple(limitations),counts=counts,items=tuple(page[:limit]),
            next_cursor=page[limit-1].key if len(page)>limit else None)

    @projection_read
    def detail(self, project, baseline, current, key):
        """详情只投影准确对应项；效应和证据沿用原结果故事，不重新裁决。"""
        if len(key)!=64 or any(c not in '0123456789abcdef' for c in key):
            raise JiejianError(ErrorCode.INPUT_INVALID, '比较事项引用无效')
        left, right, _ = self._runs(project,baseline,current,None)
        values = []
        for _, package in (left,right):
            row = _index(package).get(key)
            if row is None:
                values.append(None)
                continue
            story = self.stories._from_verified_package(package,include_repair=False)
            values.append(next((item for item in story.actions if item.case_id==row['case'].case_id),None))
        if all(item is None for item in values):
            raise JiejianError(ErrorCode.RECORD_NOT_FOUND, '比较事项不存在')
        return dict(project_id=project,before=values[0],after=values[1])
