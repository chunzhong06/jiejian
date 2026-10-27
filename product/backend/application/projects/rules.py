# 按权限规则聚合已发布检查、原问题和真实修改；不执行目标或改写历史结论。
from __future__ import annotations


class RuleWorkspaceService:
    def __init__(self, *, uow_factory, boundaries, reader, repairs):
        self._uow, self._boundaries, self._reader, self._repairs = uow_factory, boundaries, reader, repairs

    def read(self, project_id):
        boundary = self._boundaries.view(project_id)
        readings = self._reader.project_readings(project_id)
        repair = self._repairs.evaluate(project_id, readings=readings)
        with self._uow() as work:
            understanding = work.application_understanding.get(project_id)
            saved = work.source_changes.current_changes(project_id, limit=100)
            changes = [(item, work.source_changes.rule_targets(project_id, item[0].change_id)) for item in saved]
        actors = {item.actor_id: item.display_name for item in boundary.actors}
        actions = {item.action_id: item.display_name for item in boundary.actions}
        packages = sorted(((status, package) for status, package in readings if package is not None
            and status.result_integrity == 'VALID'), key=lambda item: (item[0].run.created_at_us, item[0].run.run_id), reverse=True)
        rules = []
        for rule in boundary.permission_intents:
            if rule.effective_state != 'ACTIVE':
                continue
            reference = (rule.intent_id, rule.revision, rule.intent_hash)
            def matches(permission):
                return (permission.intent_id, permission.revision, permission.intent_hash) == reference
            history = []
            for status, package in packages:
                results = {item.case_id: item for item in package.result.case_results}
                cases = [results[case.case_id] for action in package.request.actions for case in action.cases
                    if matches(case.permission)]
                if not cases:
                    continue
                verdicts = {item.verdict.value for item in cases}
                judgement = 'VULNERABLE' if 'VULNERABLE' in verdicts else 'INCONCLUSIVE' if 'INCONCLUSIVE' in verdicts else 'SAFE'
                current = (understanding is not None and package.request.source_fingerprint == understanding.source_fingerprint
                    and package.request.policy_epoch == boundary.policy_epoch)
                runtime = getattr(package.result, 'runtime_correspondence', None)
                runtime_confirmed = runtime is not None and runtime.before == runtime.after == 'MATCHED'
                history.append(dict(run_id=status.run.run_id, created_at_us=status.run.created_at_us,
                    case_ids=[item.case_id for item in cases], verdict=judgement, case_count=len(cases), current=current, runtime_confirmed=runtime_confirmed,
                    change_id=None if package.request.change_context is None else package.request.change_context.change_id))
            issues = [item for item in repair.tasks if matches(item.contract.deny.identity.permission)]
            linked = []
            for (manifest, change, assessment), targets in changes:
                declared = tuple(item for item in targets if matches(item.permission))
                legacy = manifest.repair_reference is not None and any(item.contract.reference() == manifest.repair_reference for item in issues)
                if not declared and not legacy:
                    continue
                linked.append(dict(change_id=manifest.change_id, reason=manifest.reason, created_at_us=manifest.created_at_us,
                    file_count=len(change.changed_paths), targets=[item.model_dump(mode='json') for item in declared]))
            latest = history[0] if history else None
            current_issues = [item for item in issues if item.status not in {'VERIFIED', 'STALE'}]
            state = 'UNTESTED' if latest is None else 'STALE' if not latest['current'] else latest['verdict']
            if state == 'SAFE' and not latest['runtime_confirmed']:
                state = 'UNCONFIRMED'
            if state == 'SAFE' and current_issues:
                state = 'REPAIR_PENDING'
            subject = actors.get(rule.subject_actor_id, '未命名角色')
            action = actions.get(rule.business_action_id, '未命名操作')
            owner = actors.get(rule.resource_owner_actor_id, '资源所有者')
            relation = '自己的资源' if rule.relation == 'OWNS' else f'其他{owner}账号的资源' if rule.relation == 'SAME_ROLE_OTHER_ACCOUNT' else f'{owner}的资源'
            rules.append(dict(permission=dict(intent_id=rule.intent_id, revision=rule.revision, intent_hash=rule.intent_hash),
                title=f'{subject}{"可以" if rule.expectation == "ALLOW" else "不得"}{action}',
                expectation=rule.expectation, subject=subject, action=action, resource_scope=relation,
                state=state, latest=latest, issues=[item.model_dump(mode='json') for item in issues],
                changes=linked, history=history[:20], history_has_more=len(history)>20))
        ranking = {'VULNERABLE':0, 'REPAIR_PENDING':1, 'INCONCLUSIVE':2, 'STALE':3, 'UNCONFIRMED':3, 'UNTESTED':4, 'SAFE':5}
        rules.sort(key=lambda item:(ranking[item['state']], item['title'], item['permission']['intent_id']))
        return dict(schema_version='1', project_id=project_id, policy_epoch=boundary.policy_epoch, rules=rules,
            scope='REGISTERED_SOURCE', change_history_limited=len(saved)==100)
