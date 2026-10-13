# 执行GUI确认的有限材料批次；目标访问仍交由原Worker，关页可续查，未知写入不重放。
import hashlib
import json
import time
from threading import Lock, Event
from typing import Literal

from pydantic import Field
from product.protocols.runtime.runtime_identity import RuntimeModel
from product.protocols.preparation.proof_sources import SourceId
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.workflows.preparation.proofs.commands import GrantProofScope, StartProofPreflight, AdoptProofSource, CancelProofPreflight


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


class BatchSource(RuntimeModel):
    source_id: SourceId
    revision: int = Field(ge=1)
    config_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    label: str = Field(max_length=256)
    scope_id: str | None = Field(default=None, pattern=r'^prs_[0-9a-f]{32}$')


class PreparationBatchPlan(RuntimeModel):
    schema_version: Literal['1'] = '1'
    project_id: str = Field(min_length=1, max_length=64)
    mode: Literal['OFFICIAL', 'REVIEWED']
    basis_id: str = Field(pattern=r'^pb_[0-9a-f]{64}$')
    runtime_origin: str = Field(max_length=2048)
    guard: str = Field(pattern=r'^[0-9a-f]{64}$')
    sources: tuple[BatchSource, ...] = Field(max_length=64)


class StartPreparationBatch(RuntimeModel):
    operation_id: str = Field(pattern=r'^[0-9a-f]{32}$')
    plan: PreparationBatchPlan
    confirmed: Literal[True]


class PreparationBatchService:
    def __init__(self, *, uow_factory, proofs, official_prepare, official_project, guard_reader, clock_us=None, official_step=None):
        self._uow, self._proofs = uow_factory, proofs
        self._official_prepare, self._official_project = official_prepare, official_project
        self._guard = guard_reader
        self._clock = clock_us or (lambda: time.time_ns() // 1000)
        self._advancing = Lock()
        self.wake = Event()
        self._official_step = official_step

    def preview(self, project, mode='REVIEWED'):
        """只读列出待确认的精确修订；不登录、不授权、不提交任务。"""
        if mode == 'OFFICIAL' and self._official_project() != project:
            raise JiejianError(ErrorCode.STATE_PRECONDITION, '这不是当前运行的官方示例')
        context = self._proofs.context(project)
        if not context['runtime_available']:
            raise JiejianError(ErrorCode.STATE_PRECONDITION, '请先启动当前应用并核对运行对应')
        return PreparationBatchPlan(project_id=project, mode=mode, basis_id=context['basis_id'],
            runtime_origin=context['runtime_origin'], guard=_digest(self._guard(project)),
            sources=self._selections(context))

    @staticmethod
    def _selections(context):
        return tuple(BatchSource(source_id=source['source_id'], revision=source['revision'],
            config_hash=_digest(source['config']), label=next((effect['label'] for action in context['actions']
                if action['action_id'] == source['config']['action_id'] for effect in action['effects']
                if effect['effect_id'] == source['config']['effect_id']), '检查材料'),
            scope_id=source['matching_read_scope_id']) for source in context['sources'])

    def start(self, project, command):
        """仅由GUI路由调用；批准计划和操作键一起持久化，重复同键只回读。"""
        plan = command.plan
        if plan.project_id != project:
            raise JiejianError(ErrorCode.STATE_PRECONDITION, '材料计划不属于当前应用')
        fingerprint = _digest(plan.model_dump(mode='json'))
        with self._uow() as work:
            prior = work.preparation_batches.get(project, command.operation_id)
        if prior is not None:
            if prior['plan_hash'] != fingerprint:
                raise JiejianError(ErrorCode.STATE_PRECONDITION, '操作标识已用于另一份材料计划')
            return self._public(prior)
        if self.preview(project, plan.mode) != plan:
            raise JiejianError(ErrorCode.STATE_PRECONDITION, '材料在确认期间发生变化，请重新核对')
        if plan.mode == 'REVIEWED' and not plan.sources:
            raise JiejianError(ErrorCode.STATE_PRECONDITION, '尚无可准备的来源，请先整理材料')
        now = self._clock()
        value = dict(operation_id=command.operation_id, project_id=project, plan_hash=fingerprint,
            control_session_id=self._proofs.control_session_id, state='RUNNING', cancel_requested=False,
            created_at_us=now, updated_at_us=now, payload=dict(schema_version='2',items=[],recipe={},cursor=0, approved_plan=plan.model_dump(mode='json'), plan=plan.model_dump(mode='json'),
                stage='RECIPE' if plan.mode == 'OFFICIAL' else 'NEXT', index=0, pending=None,
                message='已收到材料准备任务', preflight_id=None, owned_preflight=False, cancel_sent=False))
        with self._uow() as work:
            work.acquire_write_lock()
            if work.preparation_batches.active(project):
                raise JiejianError(ErrorCode.STATE_PRECONDITION, '本应用已有材料批次，请先查看其进度')
            previous = work.preparation_batches.latest(project)
            if previous is not None and previous['payload'].get('pending'):
                pending = previous['payload']['pending']
                if work.preparation_recovery.receipt(pending['command']['operation_id'],
                        project_id=project, operation_kind=pending['kind']) is None:
                    raise JiejianError(ErrorCode.STATE_PRECONDITION, '上次准备步骤的结果仍不明确，请先核对原操作')
            for item in previous['payload'].get('items',[]) if previous else ():
                pending=item.get('pending')
                if pending and work.preparation_recovery.receipt(pending['command']['operation_id'],project_id=project,operation_kind=pending['kind']) is None:
                    raise JiejianError(ErrorCode.STATE_PRECONDITION,'上次准备步骤回执仍不明确，请先核对原批次')
            work.preparation_batches.save(value)
            work.commit()
        self.wake.set()
        return self._public(value)

    def show(self, project, operation=None):
        with self._uow() as work:
            value = work.preparation_batches.latest(project) if operation is None else work.preparation_batches.get(project, operation)
        if operation is not None and value is None:
            raise JiejianError(ErrorCode.RECORD_NOT_FOUND, '未找到这次材料批次')
        return None if value is None else self._public(value)

    def cancel(self, project, operation):
        with self._uow() as work:
            work.acquire_write_lock()
            value = work.preparation_batches.get(project, operation)
            if value is None:
                raise JiejianError(ErrorCode.RECORD_NOT_FOUND, '未找到这次材料批次')
            if value['state'] in ('RUNNING', 'CANCELLING'):
                value.update(cancel_requested=True, state='CANCELLING', updated_at_us=self._clock())
                work.preparation_batches.save(value)
                work.commit()
        self.wake.set()
        return self._public(value)

    def advance(self):
        """短步骤完成即推进；等待子任务时让出，不占住其他项目的协调器。"""
        if not self._advancing.acquire(blocking=False):return
        self.wake.clear()
        try:
            with self._uow() as work:active=work.preparation_batches.active()
            for value in active:
                deadline=time.monotonic()+.1
                for _ in range(8):
                    before=json.dumps(value,sort_keys=True)
                    try:self._step(value)
                    except JiejianError as exc:self._finish(value,'BLOCKED',exc.to_dict()['message'])
                    except Exception:self._finish(value,'BLOCKED','准备未能继续，请查看已有材料与原操作回执后重新核对计划')
                    if value['state'] not in ('RUNNING','CANCELLING') or before==json.dumps(value,sort_keys=True):break
                    # 取消决定每次从存储读取，不能连续推进旧快照越过用户取消。
                    with self._uow() as work:value=work.preparation_batches.get(value['project_id'],value['operation_id'])
                    if time.monotonic()>=deadline:
                        self.wake.set();break
        finally:self._advancing.release()

    def wait_for_work(self):
        with self._uow() as work:active=work.preparation_batches.active()
        # 登录进程有独立监督，有限观察间隔不向界面伪造进度；预检查由Worker退出唤醒。
        recipe_wait=any(v['payload'].get('stage')=='RECIPE' for v in active)
        self.wake.wait(.2 if recipe_wait else 2)

    def _save(self, value):
        value['updated_at_us'] = self._clock()
        with self._uow() as work:
            work.acquire_write_lock()
            current=work.preparation_batches.get(value['project_id'],value['operation_id'])
            if current and current['cancel_requested']:
                value['cancel_requested']=True
                if value['state'] in ('RUNNING','SUCCEEDED'):value['state']='CANCELLING'
            work.preparation_batches.save(value)
            work.commit()
        self.wake.set()

    def _finish(self, value, state, message):
        value['state'], value['payload']['message'] = state, message
        self._save(value)

    def _step(self, value):
        project,data=value['project_id'],value['payload']
        if data.get('schema_version')!='2':
            return self._finish(value,'BLOCKED','旧材料批次已保留，请核对原回执后重新确认剩余计划')
        if value['control_session_id']!=self._proofs.control_session_id:
            return self._finish(value,'BLOCKED','界鉴已重启，已完成材料保留，请重新确认剩余计划')
        for index,item in enumerate(data['items']):
            if item.get('pending'):
                pending=item['pending']
                receipt=self._proofs.receipt(project,pending['kind'],pending['command']['operation_id'])
                if receipt is None:raise JiejianError(ErrorCode.STATE_PRECONDITION,'原准备步骤回执尚未确认')
                self._accept(value,index,receipt);return
        if value['cancel_requested']:
            if data['stage']=='RECIPE' and self._official_step:
                progress=self._official_step(project,data['recipe'],cancel=True)
                if progress!=data['recipe']:data['recipe']=progress;self._save(value)
                if progress['phase']!='CANCELLED':return
            waiting=False
            for index,item in enumerate(data['items']):
                if item.get('owned_preflight') and self._lifecycle(project,item['preflight_id']) in ('PENDING','RUNNING','RETRY_WAIT'):
                    waiting=True
                    if not item.get('cancel_sent'):self._write(value,index,'CANCEL_PREFLIGHT',dict(preflight_id=item['preflight_id']))
            if not waiting:self._finish(value,'CANCELLED','已停止后续准备，已经完成的材料保留')
            return
        plan=PreparationBatchPlan.model_validate_json(json.dumps(data['plan']))
        if _digest(self._guard(project))!=plan.guard:
            return self._finish(value,'BLOCKED','权限、源码或运行实例已变化，请重新核对计划')
        if data['stage']=='RECIPE':
            if not data['recipe'] and self.preview(project,'OFFICIAL')!=plan:
                return self._finish(value,'BLOCKED','示例准备依据已变化，请重新确认')
            if self._official_step:
                progress=self._official_step(project,data['recipe'])
                phase=progress['phase']
                if progress!=data['recipe']:
                    data['recipe']=progress
                    data['message']='正在登录示例账号' if phase=='LOGIN' else '正在准备操作和对照文件'
                    self._save(value)
                if phase!='COMPLETED':return
            else:
                # 旧提供方保持原回执边界；只在未开始的固定配方上调用一次。
                data['stage']='RECIPE_RUNNING';self._save(value);self._official_prepare()
            context=self._proofs.context(project);self._validate_recipe(context)
            if _digest(self._guard(project))!=plan.guard:
                return self._finish(value,'BLOCKED','示例运行或要求发生变化，材料保留供核对')
            plan=plan.model_copy(update=dict(basis_id=context['basis_id'],sources=self._selections(context)))
            data.update(plan=plan.model_dump(mode='json'),stage='NEXT')
            self._save(value);return
        if data['stage']=='RECIPE_RUNNING':
            return self._finish(value,'BLOCKED','上次示例准备结果尚未确认，请核对原操作')
        context=self._proofs.context(project)
        if context['basis_id']!=plan.basis_id or context['runtime_origin']!=plan.runtime_origin:
            return self._finish(value,'BLOCKED','账号、资源或读取依据已变化，请重新确认剩余材料')
        if not data['items']:
            current={s['source_id']:s for s in context['sources']}
            def already_ready(selected):
                source=current.get(selected.source_id)
                attempt=None if source is None else source['preflight']
                return bool(source and source['revision']==selected.revision and _digest(source['config'])==selected.config_hash
                    and source['read_scope_confirmed'] and source['adopted'] and attempt and attempt['current_basis']
                    and attempt['state']=='SUCCEEDED' and attempt['report'] and attempt['report']['assessment']=='USABLE')
            data['items']=[dict(source_id=s.source_id,label=s.label,state='READY' if already_ready(s) else 'WAITING',pending=None,preflight_id=None,
                owned_preflight=False,cancel_sent=False,scope_id=s.scope_id) for s in plan.sources]
            if data['items']:self._save(value)
        if all(item['state']=='READY' for item in data['items']):
            return self._finish(value,'SUCCEEDED','这批材料已准备好，可以开始正式检查')
        count=len(data['items'])
        active=sum(item['state']=='CHECKING' for item in data['items'])
        for offset in range(count):
            index=(data['cursor']+offset)%count
            item=data['items'][index];selected=plan.sources[index]
            if item['state'] in ('READY','BLOCKED'):continue
            source=next((s for s in context['sources'] if s['source_id']==selected.source_id),None)
            if source is None or source['revision']!=selected.revision or _digest(source['config'])!=selected.config_hash:
                return self._finish(value,'BLOCKED','材料配置已经变化，请重新核对')
            if item['scope_id'] is not None and source['matching_read_scope_id']!=item['scope_id']:
                return self._finish(value,'BLOCKED','读取授权已撤回或更换，请重新核对剩余材料')
            if not source['supported'] or source['config']['source_kind']=='REFERENCE_FILE' and not source['config'].get('reference_artifact'):
                item['state']='BLOCKED';self._save(value);return
            attempt=source['preflight']
            usable=bool(attempt and attempt['current_basis'] and attempt['state']=='SUCCEEDED' and attempt['report'] and attempt['report']['assessment']=='USABLE')
            common=dict(source_id=selected.source_id,revision=selected.revision,basis_id=plan.basis_id)
            if attempt and attempt['state'] in ('PENDING','RUNNING','RETRY_WAIT'):
                if item['preflight_id']!=attempt['preflight_id']:
                    item.update(state='CHECKING',preflight_id=attempt['preflight_id']);self._save(value)
                continue
            if not source['read_scope_confirmed']:
                self._write(value,index,'GRANT_SCOPE',dict(common,confirmed=True))
            elif not usable:
                if item['state']=='CHECKING':item['state']='BLOCKED';self._save(value)
                elif active<2:self._write(value,index,'START_PREFLIGHT',common)
                else:continue
            elif not source['adopted']:
                self._write(value,index,'ADOPT_SOURCE',dict(common,confirmed=True,preflight_id=attempt['preflight_id']))
            else:
                item['state']='READY';item['finished_at_us']=self._clock();self._save(value)
            data['cursor']=(index+1)%count
            self._save(value);return
        if all(item['state'] in ('READY','BLOCKED') for item in data['items']):
            self._finish(value,'BLOCKED','部分材料未通过核对，已经就绪的材料保留')

    def _lifecycle(self, project, preflight):
        with self._uow() as work:_,job,_=self._proofs.jobs.read(work,project,preflight)
        return job.state.value

    def _write(self,value,index,kind,body):
        item=value['payload']['items'][index]
        operation=_digest([value['operation_id'],index,kind])[:32]
        body=dict(body,operation_id=operation)
        item['pending']=dict(kind=kind,command=body)
        with self._uow() as work:
            work.acquire_write_lock()
            current=work.preparation_batches.get(value['project_id'],value['operation_id'])
            if current['cancel_requested'] and kind!='CANCEL_PREFLIGHT':
                item['pending']=None;value['cancel_requested']=True;return
            value['updated_at_us']=self._clock();work.preparation_batches.save(value);work.commit()
        model,method={'GRANT_SCOPE':(GrantProofScope,self._proofs.grant_scope),'START_PREFLIGHT':(StartProofPreflight,self._proofs.start),
            'ADOPT_SOURCE':(AdoptProofSource,self._proofs.adopt),'CANCEL_PREFLIGHT':(CancelProofPreflight,self._proofs.cancel)}[kind]
        try:receipt=method(value['project_id'],model.model_validate_json(json.dumps(body)))
        except JiejianError as exc:
            if exc.code in {ErrorCode.STATE_PRECONDITION.value,ErrorCode.INPUT_INVALID.value,ErrorCode.RECORD_NOT_FOUND.value}:
                item['pending']=None;self._save(value)
            raise
        self._accept(value,index,receipt)

    def _accept(self,value,index,receipt):
        item=value['payload']['items'][index];pending=item['pending']
        if (receipt['operation_id'],receipt['operation_kind'],receipt['project_id'])!=(pending['command']['operation_id'],pending['kind'],value['project_id']):
            raise JiejianError(ErrorCode.STATE_PRECONDITION,'材料步骤回执不属于本次操作')
        if pending['kind']=='START_PREFLIGHT':item.update(state='CHECKING',preflight_id=receipt['result']['preflight_id'],owned_preflight=True,started_at_us=self._clock())
        elif pending['kind']=='CANCEL_PREFLIGHT':item['cancel_sent']=True
        elif pending['kind']=='GRANT_SCOPE':item['scope_id']=receipt['result']['scope_id']
        item['pending']=None
        ready=sum(s['state']=='READY' for s in value['payload']['items'])
        value['payload']['message']=f"已准备 {ready}/{len(value['payload']['items'])} 项证明材料"
        self._save(value)

    @staticmethod
    def _validate_recipe(context):
        if not context['sources']:
            raise JiejianError(ErrorCode.STATE_PRECONDITION, '示例没有形成可核对的材料')
        for source in context['sources']:
            config = source['config']
            resource = next((item for item in context['resources'] if item['resource_binding_id'] == config['resource_binding_id']), None)
            action = next((item for item in context['actions'] if item['action_id'] == config['action_id']), None)
            claims = config['identity_claims']
            if (resource is None or resource['resource_id'] != 'campus' or action is None
                or action['label'] not in ('取得内部完整包','查看公开预览','下载公开展示版')
                or config.get('collection') != 'galleries' or config['relative_path_template'] != '/collections/galleries/{resource_id}'
                or config['source_kind'] in {'JSON_HTTP_RESOURCE','CREATED_OBJECT_RECORDS'} or not claims
                or any(item.get('request_path') != '/api/me' or item['application_subject_id'] not in ('curator','judge') for item in claims)
                or not any(item['identity_id'] == resource['owner_identity_id'] and item['application_subject_id'] == 'curator' for item in claims)
                or config['max_response_bytes'] > 4194304 or config['timeout_us'] > 5000000):
                raise JiejianError(ErrorCode.STATE_PRECONDITION, '材料包含固定示例范围以外的内容，请逐项核对')

    @staticmethod
    def _public(value):
        data=value['payload'];items=data.get('items',[])
        return dict(schema_version='1',project_id=value['project_id'],operation_id=value['operation_id'],state=value['state'],cancel_requested=value['cancel_requested'],
            message=data['message'],completed=sum(i['state']=='READY' for i in items) if data.get('schema_version')=='2' else data['index'],
            total=len(data['plan']['sources']),preflight_id=next((i['preflight_id'] for i in items if i['state']=='CHECKING'),data.get('preflight_id')),
            phase=data['stage'],items=[dict(label=i['label'],state=i['state']) for i in items],
            identities=[dict(account=i['account'],state=i['state']) for i in data.get('recipe',{}).get('identities',[])],
            created_at_us=value['created_at_us'],updated_at_us=value['updated_at_us'])
