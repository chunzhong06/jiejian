# 单规则只读投影：按精确修订连接业务约定、当前材料和已发布结果，不把动作或整轮结论代替该规则。
from product.backend.core.errors import ErrorCode,JiejianError


class BusinessRuleDetails:
    def __init__(self,*,uow_factory,boundaries,preparation,results,source_inspector,runtime_reader):
        self._uow,self._boundaries,self._preparation = uow_factory,boundaries,preparation
        self._results,self._source,self._runtime = results,source_inspector,runtime_reader

    def read(self,project_id,intent_id,*,revision=None):
        with self._uow() as work:
            revisions = [item for item in work.permission_intents.list_history(project_id) if item.intent_id==intent_id]
            rule = next((item for item in revisions if item.revision==revision),None) if revision is not None else max(revisions,key=lambda item:item.revision,default=None)
            if rule is None:
                raise JiejianError(ErrorCode.RECORD_NOT_FOUND,'这条权限规则的指定修订不存在')
            current = next((item for item in self._boundaries.view(project_id,work=work).permission_intents
                if item.intent_id==intent_id and item.revision==rule.revision and item.intent_hash==rule.intent_hash),None)
            action = work.business_boundaries.action_revision(rule.business_action_id,rule.action_revision)
            subject = work.business_boundaries.actor_revision(rule.subject_actor_id,rule.subject_actor_revision)
            owner = work.business_boundaries.actor_revision(rule.resource_owner_actor_id,rule.resource_owner_actor_revision)
            if action is None or subject is None or owner is None:
                raise JiejianError(ErrorCode.STORAGE_STATE,'权限规则的业务引用无法核对')
            runs = work.runs.page_for_project(project_id,limit=25)
            has_more = bool(runs) and work.runs.has_after_for_project(project_id,runs[-1].created_at_us,runs[-1].run_id)
        materials = []
        prepared = None
        if current is not None:
            prepared = next((item for item in self._preparation.get(project_id).actions if
                (item.action_id,item.action_revision)==(action.action_id,action.revision)),None)
            if prepared is not None:
                items = [('identity','测试账号',prepared.identity_requirements),('execution','业务操作',prepared.execution),
                    *[(f'resource-{index}','测试资源',item) for index,item in enumerate(prepared.resources)],
                    *[(item.effect_id,next(effect.business_label for effect in action.effect_catalog if effect.effect_id==item.effect_id),item)
                        for item in prepared.effect_evidence if item.effect_id in rule.protected_effect_ids],('recovery','恢复材料',prepared.recovery)]
                materials = [dict(key=key,label=label,status=item.status.value,reason_codes=item.reason_codes) for key,label,item in items]
        latest,unreadable = None,False
        try:
            source = self._source(project_id)
            runtime = self._runtime(project_id)
        except JiejianError:
            source,runtime = None,None
        for run in runs:
            if run.verdict is None:
                continue
            try:
                package = self._results.package(run.run_id,project_id=project_id)
            except JiejianError:
                unreadable = True
                continue
            cases = [case for candidate in package.request.actions for case in candidate.cases
                if (case.permission.intent_id,case.permission.revision,case.permission.intent_hash)==(intent_id,rule.revision,rule.intent_hash)]
            if not cases:
                continue
            ids = {case.case_id for case in cases}
            latest = dict(run_id=run.run_id,created_at_us=run.created_at_us,
                applies_to_current_implementation=source is not None and source==package.bundle.source_fingerprint
                    and runtime is not None and runtime==getattr(package.bundle,'runtime_reference',None),
                cases=[dict(case_id=item.case_id,verdict=item.verdict.value,reason_codes=item.reason_codes)
                    for item in package.result.case_results if item.case_id in ids])
            break
        resource_owner = '自己' if rule.relation.value=='OWNS' else f'另一个{owner.display_name}账号' if rule.relation.value=='SAME_ROLE_OTHER_ACCOUNT' else owner.display_name
        return dict(project_id=project_id,intent_id=intent_id,revision=rule.revision,current=current is not None,
            expectation=rule.expectation.value,action_id=action.action_id,action_revision=action.revision,action_label=action.display_name,
            sentence=f'{subject.display_name}对{resource_owner}拥有的资源，'+('可以' if rule.expectation.value=='ALLOW' else '不得')+action.display_name+'。',
            effects=[dict(effect_id=item.effect_id,label=item.business_label,description=item.description) for item in action.effect_catalog if item.effect_id in rule.protected_effect_ids],
            approval=rule.approval.model_dump(mode='json'),materials=materials,
            preparation_complete=prepared is not None and prepared.preparation_complete,latest_result=latest,
            history_has_more=has_more,unreadable_history=unreadable,
            preparation_url=f'/tests?materials=1&project_id={project_id}&action_id={action.action_id}',
            check_url=f'/tests?project_id={project_id}',history_url=f'/history?project_id={project_id}')
