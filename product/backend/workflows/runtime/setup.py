# 普通应用受控运行的预览、显式提交与只读回执；执行只交给Runtime Worker。
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import time
from urllib.parse import urlsplit
from uuid import uuid4

from pydantic import Field

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.lifecycle import ProjectStatus
from product.backend.infra.runtime.process.controlled.artifact import create_node_runtime_artifact, inspect_runtime_files
from product.backend.infra.runtime.process.controlled.node_owned import node_execution_identity, node_artifact_store, node_reference_matches, read_node_manifest
from product.backend.workflows.runtime.load_jobs import RuntimeLoadJobs
from product.backend.infra.runtime.jobs.queue import JobQueue
from product.backend.infra.runtime.jobs.models import RequestCancellation
from product.backend.infra.runtime.jobs.target_handlers.runtime_load import runtime_load_targets
from product.protocols.runtime.node_runtime import NodeRuntimeManifest, NodeRuntimeLoadRequest, ProjectId, node_document_fingerprint
from product.protocols.runtime.runtime_identity import RuntimeFile, RuntimeModel, runtime_source_fingerprint, Digest


class NodeStartPreview(RuntimeModel):
    project_id: ProjectId
    revision: int = Field(ge=0)
    entry: str
    port: int
    source_fingerprint: Digest
    interpreter_fingerprint: Digest
    executor_fingerprint: Digest
    files: tuple[RuntimeFile, ...]
    preview_fingerprint: Digest


class NodeRuntimeSetup:
    def __init__(self, var_dir, uow_factory, understanding, supervisor, *, node_executable_provider,
            control_origin=None, clock_us=None):
        self.var_dir=Path(var_dir).resolve()
        self._uow=uow_factory
        self.understanding=understanding
        self.supervisor=supervisor
        self.jobs=RuntimeLoadJobs(uow_factory)
        self._node=node_executable_provider
        self._control_port=urlsplit(control_origin).port if control_origin else None
        self._clock=clock_us or (lambda:time.time_ns()//1000)

    def preview(self, project_id, *, entry, port, revision, consent_source_read=False):
        """预览只读代码，授权后可先于地址确认；不安装依赖或执行目标。"""
        before=self._eligible(project_id)
        if before.revision != revision:
            raise JiejianError(ErrorCode.STATE_PRECONDITION,'应用设置已变化，请重新读取')
        if not before.source_analysis_authorized:
            if not consent_source_read:
                raise JiejianError(ErrorCode.STATE_PRECONDITION,'请先明确允许读取当前应用源码')
            before=self.understanding.authorize_source_analysis(project_id,revision=revision,for_controlled_start=True)
        if port==self._control_port:
            raise JiejianError(ErrorCode.SELF_TARGET_FORBIDDEN,'不能使用界鉴自身的服务端口')
        analysis=self.understanding.analyzer.analyze(project_id,before.source_root)
        try:
            files=inspect_runtime_files(Path(before.source_root),
                ((item.relative_path, item.content_sha256) for item in analysis.files))
            # 与正式源码身份使用同一份受控扫描范围，不能运行扫描范围外的模块。
            manifest=NodeRuntimeManifest(instance_id='rti_'+'0'*32,project_id=project_id,entry=entry,port=port,
                files=files,source_fingerprint=runtime_source_fingerprint(files),
                **node_execution_identity(self._node()))
            if manifest.source_fingerprint != analysis.source_fingerprint:
                raise ValueError('source identity mismatch')
        except (OSError,ValueError):
            raise JiejianError(ErrorCode.STATE_PRECONDITION,
                '当前目录不符合受控ESM范围：需要.mjs入口及静态相对模块，不支持外部包、CJS或其他源码类型') from None
        payload=dict(project_id=project_id,revision=before.revision,entry=entry,port=port,
            source_fingerprint=manifest.source_fingerprint,interpreter_fingerprint=manifest.interpreter_fingerprint,
            executor_fingerprint=manifest.executor_fingerprint,files=[item.model_dump(mode='json') for item in files])
        digest=hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
        return NodeStartPreview(**(payload|{'files':files,'preview_fingerprint':digest}))

    def start(self, project_id, *, entry, port, revision, preview_fingerprint, operation_id, consent_execute, work=None):
        """同操作键先查原记录；只有新操作才冻结已预览代码并排队。"""
        if not consent_execute:
            raise JiejianError(ErrorCode.STATE_PRECONDITION,'启动当前应用需要明确确认')
        self._eligible(project_id)
        previous=self.jobs.operation(project_id,operation_id)
        if previous is not None:
            if previous['request'].preview_fingerprint != preview_fingerprint:
                raise JiejianError(ErrorCode.STATE_PRECONDITION,'该操作已用于另一份启动预览')
            return self._public(previous)
        preview=self.preview(project_id,entry=entry,port=port,revision=revision)
        if preview.preview_fingerprint != preview_fingerprint:
            raise JiejianError(ErrorCode.STATE_PRECONDITION,'源码或运行设置已变化，请重新预览')
        before=self.understanding.get(project_id)
        manifest=NodeRuntimeManifest(instance_id='rti_'+uuid4().hex,project_id=project_id,entry=entry,port=port,
            files=preview.files,source_fingerprint=preview.source_fingerprint,
            interpreter_fingerprint=preview.interpreter_fingerprint,executor_fingerprint=preview.executor_fingerprint)
        request=NodeRuntimeLoadRequest(load_id='rld_'+uuid4().hex,project_id=project_id,operation_id=operation_id,
            control_session_id=self.supervisor.control_session_id,preview_fingerprint=preview_fingerprint,
            instance_id=manifest.instance_id,manifest_fingerprint=node_document_fingerprint(manifest),
            source_fingerprint=manifest.source_fingerprint,created_at_us=self._clock())
        try:
            create_node_runtime_artifact(Path(before.source_root),node_artifact_store(self.var_dir),manifest=manifest)
        except (OSError,ValueError):
            raise JiejianError(ErrorCode.STATE_PRECONDITION,'冻结源码时内容发生变化，请重新预览') from None
        def validate_current(work):
            current=work.application_understanding.get(project_id)
            if current is None or current.revision != preview.revision or current.source_root != before.source_root or not current.source_analysis_authorized:
                raise JiejianError(ErrorCode.STATE_PRECONDITION,'启动设置已变化，未提交运行任务')
            if work.sample_workspaces.for_project(project_id) is not None:
                raise JiejianError(ErrorCode.STATE_PRECONDITION,'官方示例应使用其独立启动入口')
        return self._public(self.jobs.submit(request,validate_current=validate_current,work=work))

    def state(self, project_id):
        self._eligible(project_id)
        with self._uow() as work:
            request=work.runtime_loads.latest(project_id)
        if request is None:
            return {'project_id':project_id,'operation':None,'running':False,'source_matches':False,'configuration':None}
        operation=self.jobs.operation(project_id,request.operation_id)
        configuration=None
        try:
            _,manifest=read_node_manifest(self.var_dir,request)
            configuration={'entry':manifest.entry,'port':manifest.port,'file_count':len(manifest.files)}
        except (OSError,ValueError,JiejianError):
            pass
        running=False
        source_matches=False
        if operation['receipt'] is not None:
            try:
                running=node_reference_matches(self.var_dir,request,operation['receipt'].reference,self._node())
                current=self.understanding.get(project_id)
                source_matches=current.source_analysis_authorized and self.understanding.analyzer.analyze(
                    project_id,current.source_root).source_fingerprint==request.source_fingerprint
            except (OSError,ValueError,JiejianError):
                pass
        return {'project_id':project_id,'operation':self._public(operation),'running':running,'source_matches':source_matches,'configuration':configuration}

    def operation(self, project_id, operation_id):
        self._eligible(project_id)
        value=self.jobs.operation(project_id,operation_id)
        return None if value is None else self._public(value)

    def cancel(self,project_id,operation_id):
        self._eligible(project_id)
        operation=self.jobs.operation(project_id,operation_id)
        if operation is None:
            raise JiejianError(ErrorCode.STATE_PRECONDITION,'本应用中未找到这次启动操作')
        JobQueue(self._uow,targets=runtime_load_targets()).request_cancellation(
            RequestCancellation(job_id=operation['job'].job_id,now_us=self._clock()))
        return self.operation(project_id,operation_id)

    def owns_project(self, project_id):
        with self._uow() as work:
            return work.runtime_loads.latest(project_id) is not None

    def reference(self, project_id):
        state=self.state(project_id)
        if not state['running']:
            raise JiejianError(ErrorCode.STATE_PRECONDITION,'当前应用的受控实例未得到确认',details={'reason':'RUNTIME_SOURCE_NOT_LOADED'})
        with self._uow() as work:
            request=work.runtime_loads.latest(project_id)
            receipt=work.runtime_loads.receipt(request.load_id)
        if receipt is None or request.instance_id!=state['operation']['instance_id']:
            raise JiejianError(ErrorCode.STATE_PRECONDITION,'运行实例已变化，请重新读取')
        return receipt.reference

    def require_loaded_delivery(self, project_id, source_fingerprint):
        reference=self.reference(project_id)
        if reference.source_fingerprint!=source_fingerprint:
            raise JiejianError(ErrorCode.STATE_PRECONDITION,'请先预览并启动这批源码',details={'reason':'RUNTIME_SOURCE_NOT_LOADED'})
        return reference

    def stop(self, project_id, *, instance_id):
        self._eligible(project_id)
        with self._uow() as work:
            work.acquire_write_lock()
            latest=work.runtime_loads.latest(project_id)
            active=any(job.state.value in {'PENDING','RUNNING','RETRY_WAIT'} for job in work.jobs.list_for_project(project_id))
            if latest is None or latest.instance_id != instance_id or active:
                raise JiejianError(ErrorCode.STATE_PRECONDITION,'实例已变化或仍有操作执行，请刷新后处理')
            # 保持写锁到拥有树退出，防止确认空闲后有新的检查或加载插入。
            self.supervisor.stop_project(project_id,expected_instance_id=instance_id)
        return self.state(project_id)

    def _eligible(self, project_id):
        with self._uow() as work:
            project=work.projects.get(project_id)
            if project is None or project.status is ProjectStatus.ARCHIVED:
                raise JiejianError(ErrorCode.STATE_PRECONDITION,'应用不存在或已归档')
            if work.sample_workspaces.for_project(project_id) is not None:
                raise JiejianError(ErrorCode.STATE_PRECONDITION,'官方示例应使用其独立启动入口')
        return self.understanding.get(project_id)

    @staticmethod
    def _public(value):
        # 不向页面暴露内部进程路径、会话或租约，仅返回加载生命周期和独立启动回执。
        return {'operation_id':value['request'].operation_id,'project_id':value['request'].project_id,
            'instance_id':value['request'].instance_id,'job_id':value['job'].job_id,
            'state':value['job'].state.value,'source_fingerprint':value['request'].source_fingerprint,
            'receipt':None if value['receipt'] is None else value['receipt'].model_dump(mode='json')}
