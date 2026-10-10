# 唯一检查历史的规则索引维护；耗时读包在锁外，有界批次和原操作回执在同事务提交。
from __future__ import annotations
import hashlib
import time
from pydantic import Field
from product.protocols.checks.execution_request import WireModel,content_hash
from product.protocols.checks.check_result import canonical_check_document
from product.backend.core.errors import ErrorCode,JiejianError


class MaintainHistory(WireModel):
    operation_id:str=Field(pattern=r'^[0-9a-f]{32}$')
    expected_checkpoint:int=Field(ge=0)
    limit:int=Field(default=25,ge=1,le=100)


class CheckHistoryService:
    def __init__(self,reader,uow_factory,*,monotonic=time.monotonic):self.reader,self._uow,self.clock=reader,uow_factory,monotonic

    def status(self,project_id):
        with self._uow() as work:
            self._project(work,project_id);state=work.rule_history.coverage(project_id)
            missing=work.rule_history.missing(project_id);bad=work.rule_history.unreadable(project_id)
            return dict(project_id=project_id,checkpoint=state['checkpoint'],generation=state['generation'],processed=state['processed'],failed=bad,
                missing=missing,status='IN_PROGRESS' if not state['complete'] else 'NEEDS_SCAN' if missing else 'INCOMPLETE' if bad else 'COMPLETE')

    def receipt(self,project_id,operation_id):
        with self._uow() as work:
            self._project(work,project_id);value=work.rule_history.receipt(project_id,operation_id)
            return dict(status='NOT_FOUND') if value is None else dict(status='FOUND',receipt={key:item for key,item in value.items() if key!='request_hash'})

    @staticmethod
    def _project(work,project_id):
        if work.projects.get(project_id) is None:raise JiejianError(ErrorCode.PROJECT_NOT_FOUND,'应用不存在')

    @staticmethod
    def _replay(work,project_id,command,digest):
        receipt=work.rule_history.receipt(project_id,command.operation_id)
        if receipt is None:return None
        if receipt['request_hash']!=digest:raise JiejianError(ErrorCode.STATE_PRECONDITION,'原操作对应不同的整理范围')
        return {key:value for key,value in receipt.items() if key!='request_hash'}

    def maintain(self,project_id,command):
        digest=content_hash('MaintainRuleHistory',dict(project_id=project_id,**command.model_dump(mode='json')))
        with self._uow() as work:
            self._project(work,project_id)
            replay=self._replay(work,project_id,command,digest)
            if replay is not None:return replay
            state=work.rule_history.coverage(project_id)
            if state['checkpoint']!=command.expected_checkpoint:raise JiejianError(ErrorCode.STATE_PRECONDITION,'历史整理位置已经变化，请刷新进度')
            if state['complete']:
                upper=work.rule_history.upper(project_id)
                state.update(generation=state['generation']+1,upper_time=upper[0],upper_run=upper[1],cursor_time=0,cursor_run='',processed=0,failed=0,complete=False)
            candidates=work.rule_history.scan(project_id,cursor=(state['cursor_time'],state['cursor_run']),upper=(state['upper_time'],state['upper_run']),limit=command.limit+1)
        started=self.clock();consumed=0;checked=[]
        for item in candidates[:command.limit]:
            if checked and (self.clock()-started>=5 or consumed>=64*1024*1024):break
            try:
                package=self.reader.package(item['run_id'],project_id=project_id)
                if hashlib.sha256(canonical_check_document(package.manifest)).hexdigest()!=item['manifest_hash']:
                    raise JiejianError(ErrorCode.ARTIFACT_MANIFEST,'发布引用不一致')
                consumed+=sum(file.byte_count for file in package.files)
                permissions=tuple((case.case_id,case.permission) for action in package.request.actions for case in action.cases)
                checked.append((item,permissions,None))
            except JiejianError as error:
                if not error.code.startswith(('ARTIFACT_','RECORD_NOT_FOUND')):raise
                consumed+=256*1024*1024;checked.append((item,(),'ARTIFACT_UNREADABLE'))
        with self._uow() as work:
            work.acquire_write_lock();self._project(work,project_id)
            replay=self._replay(work,project_id,command,digest)
            if replay is not None:return replay
            if work.rule_history.coverage(project_id)['checkpoint']!=command.expected_checkpoint:
                raise JiejianError(ErrorCode.STATE_PRECONDITION,'另一批整理已推进，当前批次未写入')
            for item,permissions,error in checked:
                receipt=work.check_publications.get(item['run_id'])
                if receipt is None or receipt.manifest_hash!=item['manifest_hash']:
                    raise JiejianError(ErrorCode.STATE_PRECONDITION,'发布引用已经变化，当前批次未写入')
                work.rule_history.index(project_id=project_id,run_id=item['run_id'],manifest_hash=item['manifest_hash'],created_at_us=item['created_at_us'],permissions=permissions,error_code=error)
            if checked:
                last=checked[-1][0];state.update(cursor_time=last['published_at_us'],cursor_run=last['run_id'])
            state['processed']+=len(checked);state['failed']+=sum(error is not None for _,_,error in checked)
            state['complete']=not work.rule_history.scan(project_id,cursor=(state['cursor_time'],state['cursor_run']),upper=(state['upper_time'],state['upper_run']),limit=1)
            state['checkpoint']=command.expected_checkpoint+1
            work.rule_history.save_coverage(state)
            answer=dict(project_id=project_id,operation_id=command.operation_id,checkpoint=state['checkpoint'],processed=len(checked),failed=sum(error is not None for _,_,error in checked),complete=state['complete'])
            work.rule_history.save_receipt(dict(answer,request_hash=digest));work.commit()
            return answer

    def rules(self,project_id,*,limit=25,after=None,include_archived=False):
        if not 1<=limit<=50 or after is not None and len(after)>64:raise JiejianError(ErrorCode.INPUT_INVALID,'规则分页参数无效')
        with self._uow() as work:
            self._project(work,project_id);rows=work.rule_history.rules(project_id,limit=limit+1,after=after,include_archived=include_archived)
            page=list(rows[:limit]);snapshots={}
            # 相同Run中的多条规则只读包一次，所有摘要均从准确Case复制，不存第二份Verdict。
            for run_id in dict.fromkeys(row['latest_run_id'] for row in page if row['latest_run_id']):
                run=work.runs.get(run_id)
                if run is not None and run.project_id==project_id:snapshots[run_id]=self.reader._status_and_package(work,run)
        for row in page:
            status,package=snapshots.get(row['latest_run_id'],(None,None));matches=[]
            if package is not None:
                results={item.case_id:item for item in package.result.case_results}
                matches=[results[case.case_id] for action in package.request.actions for case in action.cases
                    if (case.permission.intent_id,case.permission.revision,case.permission.intent_hash)==(row['intent_id'],row['revision'],row['intent_hash'])]
            row['case_results']=[dict(case_id=item.case_id,verdict=item.verdict.value) for item in matches]
            row['result_integrity']='NOT_PUBLISHED' if status is None else status.result_integrity
            row['index_matches']=bool(matches) if row['latest_run_id'] else True
        last=page[-1] if page else None
        return dict(project_id=project_id,items=page,next_cursor=None if len(rows)<=limit or last is None else last['intent_id']+':'+str(last['revision']).zfill(12),coverage=self.status(project_id))
