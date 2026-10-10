# Node官方体验编排安装、普通加载与显式材料准备；目标进程和检查结论由现有通用服务拥有。
from __future__ import annotations
import hashlib
import socket
import time
from pathlib import Path
from threading import RLock
from uuid import uuid4
from product.backend.core.errors import ErrorCode,JiejianError
from product.backend.infra.runtime.process.tree import kernel_tree_has_exited
from product.backend.workflows.examples.environment import OfficialExperienceView,OfficialScenarioVersion
from product.backend.workflows.examples.journey import OfficialDevelopmentJourney
from product.backend.workflows.preparation.supplemental.contract import request_uuid
from product.backend.workflows.examples.gallery_recipe import gallery_recipe,BASELINE,VULNERABLE,EXPOSE_REVOKE,PREVIEW_CHANGED


class NodeOfficialSampleExperience:
    def __init__(self,manager,*,runtime,understanding,boundaries,identities,identity_preparations,preparation,proofs,artifacts,installer,changes,reader,repairs,
                 uow_factory,archive_project,cancel_check,clock_us=None):
        self.manager,self.runtime,self.understanding,self.boundaries=manager,runtime,understanding,boundaries
        self.identities,self.preparation,self.proofs,self.installer=identities,preparation,proofs,installer
        self.identity_preparations=identity_preparations
        self.artifacts=artifacts
        self.changes,self.reader,self.repairs=changes,reader,repairs
        self._uow,self.archive,self.cancel_check=uow_factory,archive_project,cancel_check
        self.clock=clock_us or (lambda:time.time_ns()//1000)
        self._lock=RLock();self._operation=None

    def _workspace(self):
        with self._uow() as work:return work.sample_workspaces.latest()

    def _load(self,workspace):
        if not workspace or not workspace['project_id']:return None
        with self._uow() as work:return work.runtime_loads.latest(workspace['project_id'])

    def _exited(self,workspace):
        if workspace is None:return True
        if workspace['runtime_kind']!='NODE_ESM':
            from product.backend.workflows.examples.recovery import SampleRecovery
            _,instance,observation,_=SampleRecovery(self._uow,self.manager,self.clock).read()
            return instance is not None and observation is not None and observation['outcome']=='EXITED'
        load=self._load(workspace)
        if load is None:return True
        with self._uow() as work:job=work.jobs.get_by_runtime_load(load.load_id)
        if job is None or job.state.value not in {'SUCCEEDED','FAILED','CANCELLED'}:return False
        return kernel_tree_has_exited({'kind':'windows-job','name':'jiejian-node-'+load.instance_id})

    def status(self):
        workspace=self._workspace();installation=self.manager.installation
        with self._uow() as work:history,_=work.environment_operations.list(1)
        operation=history[0] if history else None
        project=None if workspace is None else workspace['project_id']
        state=None
        if project and workspace['runtime_kind']=='NODE_ESM':
            try:state=self.runtime.state(project)
            except JiejianError:pass
        active=bool(state and state['running']);exited=self._exited(workspace)
        lifecycle='RUNNING' if active else 'NOT_STARTED' if workspace is None else 'STOPPED' if exited else 'UNKNOWN'
        if operation and operation['state']=='PENDING':lifecycle=('STOPPING' if operation['operation']=='stop' else 'STARTING') if self._operation==operation['operation_id'] else 'UNKNOWN'
        pending=();prepared=False
        if active:
            materials=self.preparation.get(project);prepared=materials.preparation_complete
            pending=() if prepared else ('PREPARATION_REQUIRED',)
        return OfficialExperienceView(available=installation.available,display_name=installation.display_name,runtime_kind='NODE_ESM',
            unavailable_reason=installation.reason,active=active,project_id=project,experience_id=None if workspace is None else 'exp_'+workspace['workspace_id'][4:],
            origin=f"http://127.0.0.1:{state['configuration']['port']}" if active and state['configuration'] else None,
            scenario_prepared=prepared,scenario_version=None if workspace is None else OfficialScenarioVersion(workspace['scenario_version']),
            scenario_changed_at_us=None if workspace is None else workspace['created_at_us'],pending_tasks=pending,lifecycle=lifecycle,
            history_project_id=project,workspace_retained=workspace is not None,recovery_state='OWNED_RUNNING' if active else 'EXITED' if exited else 'OWNERSHIP_UNCONFIRMED',
            operation_id=None if operation is None else operation['operation_id'],operation_state=None if operation is None else ('UNKNOWN' if operation['state']=='PENDING' and self._operation!=operation['operation_id'] else operation['state']),
            last_error_code=None if operation is None else operation['error_code'],
            vulnerable_change_id=self._change_id(project,('VULNERABLE','EXPOSE_REVOKE')) if project else None,
            repair_change_id=self._change_id(project,('FIXED',)) if project else None,
            current_change_id=self._change_id(project,(workspace['scenario_version'],)) if project else None)

    def _change_id(self,project,stages):
        workspace=self._workspace()
        for stage in stages:
            value=self.changes.receipt(project,'DELIVER',self._key(workspace['workspace_id'],stage))
            if value is not None:return value.change_id
        return None

    @staticmethod
    def _key(workspace,stage):return hashlib.sha256(('gallery:'+workspace+':'+stage).encode()).hexdigest()[:32]

    def start(self,*,consent,operation_id=None):
        if consent is not True:raise JiejianError(ErrorCode.STATE_OPERATOR_REQUIRED,'启动示例需要明确同意')
        return self._operate('start',operation_id,lambda:self._start(False))

    def reset(self,*,consent,operation_id=None):
        if consent is not True:raise JiejianError(ErrorCode.STATE_OPERATOR_REQUIRED,'重置示例需要明确同意')
        return self._operate('reset',operation_id,lambda:self._start(True))

    def _start(self,reset):
        old=self._workspace()
        if old and old['runtime_kind']=='NODE_ESM':
            try:
                running=self.runtime.state(old['project_id'])['running']
            except JiejianError:running=False
            if running and not reset:return
            if running:self._stop()
        if not self._exited(old):raise JiejianError(ErrorCode.STATE_PRECONDITION,'旧示例退出尚未确认，请先核对原实例')
        if old and old['project_id']:self.archive(old['project_id'])
        workspace_id='wsp_'+uuid4().hex
        source=self.manager.copy_node_source(workspace_id)
        connection=self.understanding.connect(source,project_name=self.manager.installation.display_name)
        project=connection.project.project_id
        workspace=dict(workspace_id=workspace_id,project_id=project,source_root=str(source),scenario_version='BASELINE',runtime_kind='NODE_ESM',created_at_us=self.clock())
        with self._uow() as work:work.sample_workspaces.save(workspace);work.commit()
        self._progress(project_id=project,experience_id='exp_'+workspace_id[4:])
        with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        self._launch(workspace,port,self._key(workspace_id,'start'))

    def _launch(self,workspace,port,operation):
        project=workspace['project_id'];value=self.understanding.get(project)
        preview=self.runtime.preview(project,entry=self.manager.installation.entry,port=port,revision=value.revision,consent_source_read=True)
        self.runtime.start(project,entry=preview.entry,port=port,revision=preview.revision,preview_fingerprint=preview.preview_fingerprint,operation_id=operation,consent_execute=True)
        self.runtime.supervisor.start()
        deadline=time.monotonic()+25
        while time.monotonic()<deadline:
            receipt=self.runtime.operation(project,operation)
            if receipt['state']=='SUCCEEDED':break
            if receipt['state'] in {'FAILED','CANCELLED'}:raise JiejianError(ErrorCode.OFFICIAL_SAMPLE_START_FAILED,'受控示例启动未完成，请查看本次加载状态')
            time.sleep(.1)
        else:raise JiejianError(ErrorCode.STATE_PRECONDITION,'启动结果尚未确认，请查询原操作')
        # 示例会话保存在目标进程内；新实例不能继续把旧 Cookie 标成已准备。
        for identity in self.identities.list(project):
            if identity.auth_method is not None:self.identities.reset(identity.identity_id)
        self._finish_connection(workspace,port)

    def _finish_connection(self,workspace,port):
        project=workspace['project_id'];value=self.understanding.get(project)
        value=self.understanding.confirm_endpoint(project,endpoint=f'http://127.0.0.1:{port}',revision=value.revision)
        self.understanding.analyze_source_for_change(project,revision=value.revision)

    def reconcile(self):
        with self._lock:
            workspace=self._workspace()
            with self._uow() as work:history,_=work.environment_operations.list(1)
            operation=history[0] if history else None
            if (workspace and workspace['runtime_kind']=='NODE_ESM' and workspace['project_id'] and operation
                and operation['project_id']==workspace['project_id'] and operation['state'] in {'PENDING','UNKNOWN'}):
                state=self.runtime.state(workspace['project_id'])
                update=None
                if state['running'] and operation['operation'] in {'start','reset'}:
                    self._idle(workspace['project_id'])
                    self._finish_connection(workspace,state['configuration']['port'])
                    update=dict(state='SUCCEEDED',finished_at_us=self.clock(),error_code=None)
                elif self._exited(workspace):
                    update=dict(state='SUCCEEDED' if operation['operation']=='stop' else 'FAILED',finished_at_us=self.clock(),cleanup_confirmed=True)
                if update:
                    with self._uow() as work:
                        # 回读原键，不重放启动或停止；成功操作的普通刷新不重新分析源码。
                        current=work.environment_operations.get(operation['operation_id'])
                        if current['state'] in {'PENDING','UNKNOWN'}:
                            current.update(update);work.environment_operations.save(current);work.commit()
            return self.status()

    def boundary_proposal(self,*,exhibition_download=None):
        current=self._active()
        if type(exhibition_download) is not bool:raise JiejianError(ErrorCode.STATE_OPERATOR_REQUIRED,'请先选择评审能否下载公开展示版')
        command=gallery_recipe(exhibition_download,self.understanding.get(current.project_id))
        return self.boundaries.create_initial_proposal(current.project_id,command)

    def prepare(self):
        with self._lock:
            current=self._active();self._idle(current.project_id)
            from product.backend.workflows.examples.gallery_materials import prepare_gallery_materials
            prepare_gallery_materials(self,current.project_id)
            return self.status()

    def _active(self):
        value=self.status()
        if not value.active:raise JiejianError(ErrorCode.STATE_PRECONDITION,'当前没有正在运行的官方示例')
        return value

    def _idle(self,project):
        with self._uow() as work:
            if any(item.state.value in {'PENDING','RUNNING','RETRY_WAIT'} for item in work.jobs.list_for_project(project)):
                raise JiejianError(ErrorCode.STATE_PRECONDITION,'当前仍有任务，请等待或停止后再修改示例')

    def switch_version(self,*,version,repair_reference=None):
        with self._lock:
            current=self._active();workspace=self._workspace();self._idle(current.project_id)
            version=OfficialScenarioVersion(version)
            if version is OfficialScenarioVersion.EVIDENCE_LIMITED:return self.set_observation(available=False)
            saved=self.changes.receipt(current.project_id,'DELIVER',self._key(workspace['workspace_id'],version.value))
            if saved is not None:return self.status()
            journey=self.development_journey()
            if journey.implementation=='CUSTOM':raise JiejianError(ErrorCode.STATE_PRECONDITION,'源码已由外部修改，不能覆盖为预设实现')
            if version is OfficialScenarioVersion.VULNERABLE and not journey.can_optimize:raise JiejianError(ErrorCode.STATE_PRECONDITION,'先完成起始实现的真实检查')
            if version is OfficialScenarioVersion.EXPOSE_REVOKE and not (workspace['scenario_version']=='VULNERABLE' and journey.verdict=='BLOCK'):raise JiejianError(ErrorCode.STATE_PRECONDITION,'先核对错误交付这次修改的实际结果')
            if version is OfficialScenarioVersion.FIXED and repair_reference is None:raise JiejianError(ErrorCode.STATE_PRECONDITION,'修复必须携带准确原题')
            if version is OfficialScenarioVersion.PREVIEW_CHANGED and not journey.repair_verified:raise JiejianError(ErrorCode.STATE_PRECONDITION,'先完成原题复验，再继续后续修改')
            if version not in {OfficialScenarioVersion.VULNERABLE,OfficialScenarioVersion.EXPOSE_REVOKE,OfficialScenarioVersion.FIXED,OfficialScenarioVersion.PREVIEW_CHANGED}:raise JiejianError(ErrorCode.INPUT_INVALID,'不支持该预设修改')
            source=Path(workspace['source_root']);name='preview.mjs' if version is OfficialScenarioVersion.PREVIEW_CHANGED else 'delivery.mjs'
            content={OfficialScenarioVersion.VULNERABLE:VULNERABLE,OfficialScenarioVersion.EXPOSE_REVOKE:EXPOSE_REVOKE,OfficialScenarioVersion.FIXED:BASELINE,OfficialScenarioVersion.PREVIEW_CHANGED:PREVIEW_CHANGED}[version]
            (source/name).write_text(content,encoding='utf-8')
            preview=self.changes.registration_preview(current.project_id)
            self.changes.register_change(current.project_id,operation_id=self._key(workspace['workspace_id'],version.value),expected_registration_fingerprint=preview['fingerprint'],reason='预设演示：'+version.value,claimed_paths=(name,),repair_reference=repair_reference,submitted_by='预设演示 · 本机用户')
            workspace['scenario_version']=version.value
            with self._uow() as work:work.sample_workspaces.save(workspace);work.commit()
            state=self.runtime.state(current.project_id)
            self._launch(workspace,state['configuration']['port'],self._key(workspace['workspace_id'],'load:'+version.value))
            return self.status()

    def development_journey(self):
        current=self._active();workspace=self._workspace();project=current.project_id
        fingerprint=self.understanding.inspect_source_fingerprint(project)
        with self._uow() as work:
            if workspace['scenario_version']=='BASELINE':
                initial=work.runtime_loads.operation(project,self._key(workspace['workspace_id'],'start'))
                expected=None if initial is None else initial.source_fingerprint
            else:
                saved=work.development.receipt(project,'DELIVER',self._key(workspace['workspace_id'],workspace['scenario_version']))
                delivery=None if saved is None else work.development.delivery(project,saved.delivery_id)
                snapshot=None if delivery is None else work.source_changes.snapshot(delivery.current_snapshot_id)
                expected=None if snapshot is None else snapshot.source_fingerprint
        external=fingerprint!=expected
        state=self.repairs.evaluate(project)
        verified=bool(state.tasks) and all(item.status=='VERIFIED' for item in state.tasks)
        verdict=None;run_id=None
        records=self.reader.list_for_project(project)
        if current.current_change_id:
            detail=self.changes.delivery_details(project,current.current_change_id)
            verification=detail['verification']
            records=[] if verification is None or verification['run_id'] is None else [self.reader.status(verification['run_id'],project_id=project)]
        for item in records:
            if item.result_integrity!='VALID':continue
            package=self.reader.package(item.run.run_id,project_id=project)
            if package.request.source_fingerprint==fingerprint and package.request.policy_epoch==self.boundaries.view(project).policy_epoch:
                run_id=item.run.run_id;verdict=item.run.verdict.value;break
        return OfficialDevelopmentJourney(project_id=project,implementation='CUSTOM' if external else workspace['scenario_version'],delivery_source='EXTERNAL_CODE' if external else 'PRESET_DEMONSTRATION',
            run_id=run_id,verdict=verdict,repair_verified=verified,can_optimize=not external and workspace['scenario_version']=='BASELINE' and verdict=='PASS',
            evidence_limited=False,reason='按原要求核对内部资料限制、公开预览与负责人导出，结论以本次真实证据为准。')

    def set_observation(self,*,available):
        raise JiejianError(ErrorCode.STATE_PRECONDITION,'此示例的来源在检查材料中管理；来源缺失会明确显示证据不足，不切换伪造观察条件')

    def stop(self,*,operation_id=None):return self._operate('stop',operation_id,self._stop)

    def _stop(self):
        workspace=self._workspace()
        if not workspace:return
        project=workspace['project_id'];load=self._load(workspace)
        with self._uow() as work:active=tuple(item for item in work.jobs.list_for_project(project) if item.state.value in {'PENDING','RUNNING','RETRY_WAIT'})
        for job in active:
            if job.operation_type=='CHECK':self.cancel_check(project,job.run_id)
            elif job.operation_type=='RUNTIME_LOAD' and load:self.runtime.cancel(project,load.operation_id)
            else:raise JiejianError(ErrorCode.STATE_PRECONDITION,'请先停止当前材料准备操作，再退出示例')
        deadline=time.monotonic()+15
        while time.monotonic()<deadline:
            try:self._idle(project);break
            except JiejianError:time.sleep(.1)
        else:raise JiejianError(ErrorCode.STATE_PRECONDITION,'活动任务尚未完成回收，未停止目标')
        if load:self.runtime.stop(project,instance_id=load.instance_id)
        if not self._exited(workspace):raise JiejianError(ErrorCode.STATE_PRECONDITION,'受控实例退出尚未确认')
        # 示例退出后撤销本项目的短期登录状态，历史证据只保留原引用。
        for identity in self.identities.list(project):
            if identity.auth_method is not None:self.identities.reset(identity.identity_id)

    def stop_project(self,project_id):
        workspace=self._workspace()
        if workspace is None or workspace['project_id']!=project_id:return False
        if not self._exited(workspace):self.stop()
        return True

    def close(self):
        workspace=self._workspace()
        if workspace and workspace['runtime_kind']=='NODE_ESM' and workspace['project_id']:
            with self._uow() as work:project=work.projects.get(workspace['project_id'])
            if project is not None and project.status.value!='ARCHIVED':
                # 已显式停止的实例只清理残留会话，不为关闭控制面追加第二条停止操作。
                if self._exited(workspace):self._stop()
                else:self.stop()

    def _progress(self,**updates):
        if not self._operation:return
        with self._uow() as work:
            value=work.environment_operations.get(self._operation);value.update(updates);work.environment_operations.save(value);work.commit()

    def _operate(self,operation,operation_id,action):
        operation_id=request_uuid(operation_id or str(uuid4()))
        with self._lock:
            with self._uow() as work:
                previous=work.environment_operations.get(operation_id)
                if previous is not None:
                    if previous['operation']!=operation:raise JiejianError(ErrorCode.STATE_PRECONDITION,'原操作键用于另一项操作')
                    # 重放只能给出原操作的所属项目；后来的新实例不能冒充旧操作成功。
                    view=self.status()
                    same=view.project_id==previous['project_id']
                    return view.model_copy(update=dict(project_id=previous['project_id'],experience_id=previous['experience_id'],
                        operation_id=previous['operation_id'],operation_state=previous['state'],active=view.active and same,
                        origin=view.origin if same else None,scenario_prepared=view.scenario_prepared and same,
                        scenario_version=view.scenario_version if same else None,scenario_changed_at_us=view.scenario_changed_at_us if same else None,
                        vulnerable_change_id=view.vulnerable_change_id if same else None,repair_change_id=view.repair_change_id if same else None,current_change_id=view.current_change_id if same else None,
                        pending_tasks=view.pending_tasks if same else (),lifecycle=view.lifecycle if same else 'STOPPED'))
                history,_=work.environment_operations.list(1)
                if history and history[0]['state']=='PENDING':raise JiejianError(ErrorCode.STATE_PRECONDITION,'请先核对原环境操作')
                workspace=work.sample_workspaces.latest();project=None if workspace is None else workspace['project_id']
                work.environment_operations.save(dict(operation_id=operation_id,operation=operation,state='PENDING',started_at_us=self.clock(),finished_at_us=None,
                    experience_id=None if workspace is None else 'exp_'+workspace['workspace_id'][4:],project_id=project,error_code=None,cleanup_confirmed=False));work.commit()
            self._operation=operation_id
            try:action()
            except Exception as error:
                code=error.code if isinstance(error,JiejianError) else ErrorCode.OFFICIAL_SAMPLE_START_FAILED.value
                self._progress(state='UNKNOWN',finished_at_us=self.clock(),error_code=code)
                if isinstance(error,JiejianError):raise
                raise JiejianError(ErrorCode.OFFICIAL_SAMPLE_START_FAILED,'官方示例操作未完成，请核对原状态') from error
            else:self._progress(state='SUCCEEDED',finished_at_us=self.clock(),cleanup_confirmed=operation=='stop')
            finally:self._operation=None
            return self.status()

    def history(self,*,limit=25):
        if not 1<=limit<=100:raise JiejianError(ErrorCode.INPUT_INVALID,'历史上限为100')
        with self._uow() as work:items,more=work.environment_operations.list(limit)
        for item in items:item.pop('cleanup_confirmed',None)
        return dict(items=items,has_more=more)
