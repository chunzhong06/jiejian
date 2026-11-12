# 普通应用受控运行的预览、显式提交与只读回执；执行只交给Runtime Worker。
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import time
from urllib.parse import urlsplit
from uuid import uuid4

from pydantic import Field

from product.backend.domain.errors import ErrorCode, JiejianError
from product.backend.domain.lifecycle import JobState, ProjectStatus
from product.backend.infrastructure.runtime.process.controlled.artifact import create_node_runtime_artifact, inspect_runtime_files
from product.backend.infrastructure.runtime.process.controlled.node_owned import node_execution_identity, node_artifact_store, node_reference_matches, read_node_manifest
from product.backend.application.runtime.load_jobs import RuntimeLoadJobs
from product.backend.infrastructure.runtime.jobs.queue import JobQueue
from product.backend.infrastructure.runtime.jobs.models import RequestCancellation
from product.backend.infrastructure.runtime.jobs.registration import runtime_load_targets
from product.protocols.runtime.node_runtime import NodeRuntimeManifest, NodeRuntimeLoadRequest, NodePackagePlan, SqliteDatabaseCapture, ProjectId, node_document_fingerprint
from product.protocols.runtime.runtime_identity import RuntimeFile, RuntimeModel, runtime_source_fingerprint, Digest
from product.protocols.runtime.database_capture import DatabaseCapture,database_secret_name


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
    package: NodePackagePlan | None = None
    sqlite: tuple[SqliteDatabaseCapture, ...] = ()
    databases:tuple[DatabaseCapture,...]=()


class NodeRuntimeSetup:
    def __init__(self, var_dir, uow_factory, understanding, supervisor, *, node_executable_provider,
            control_origin=None, clock_us=None, secret_store=None):
        self.var_dir=Path(var_dir).resolve()
        self._uow=uow_factory
        self.understanding=understanding
        self.supervisor=supervisor
        self.jobs=RuntimeLoadJobs(uow_factory)
        self._node=node_executable_provider
        self._control_port=urlsplit(control_origin).port if control_origin else None
        self._clock=clock_us or (lambda:time.time_ns()//1000)
        self._secrets=secret_store

    def configure_database_credential(self,project_id,connection_id,password):
        self._eligible(project_id)
        if self._secrets is None:
            raise JiejianError(ErrorCode.SECRET_STORE_UNAVAILABLE,'当前秘密存储不可用')
        from product.backend.infrastructure.secrets.refs import credential_ref
        self._secrets.write(credential_ref('database',project_id,connection_id),password)
        return dict(connection_id=connection_id,password_env=database_secret_name(project_id,connection_id),configured=True)

    def capabilities(self, project_id):
        current = self._eligible(project_id)
        if not current.source_analysis_authorized:
            return dict(project_id=project_id,source_read_authorized=False,entries=[],package=None,
                dependencies='NEEDS_AUTHORIZATION',build_scripts=[],database='NEEDS_CONFIGURATION')
        root = Path(current.source_root)
        analysis = self.understanding.analyzer.analyze(project_id,root)
        entries = [item.relative_path for item in analysis.files if item.relative_path.endswith(('.js','.mjs','.cjs'))]
        package, scripts, dependency_state = None, [], 'NOT_REQUIRED'
        if (root/'package.json').is_file():
            try:
                package = json.loads((root/'package.json').read_text(encoding='utf-8-sig'))
                from product.backend.infrastructure.runtime.process.controlled.npm import npm_plan
                npm_plan(root)
                dependency_state = 'LOCKED'
                scripts = list(package.get('scripts', {}))
            except (OSError,ValueError):
                dependency_state = 'NEEDS_CONFIGURATION'
        preferred = package.get('main') if isinstance(package,dict) else None
        if preferred in entries:
            entries.remove(preferred)
            entries.insert(0,preferred)
        return dict(project_id=project_id,source_read_authorized=True,entries=entries,
            package=package.get('name') if isinstance(package,dict) else None,dependencies=dependency_state,
            build_scripts=scripts,database='NEEDS_CONFIGURATION',sqlite_setup=analysis.sqlite_setup.model_dump(mode='json'),module_loader='NODE_STANDARD',
            supported_database_driver='better-sqlite3 13.0.3',node='24.19.0')

    def preview(self, project_id, *, entry, port, revision, consent_source_read=False,
            build_script=None, allow_install_scripts=False, sqlite=(),databases=()):
        """预览只读代码，授权后可先于地址确认；不安装依赖或执行目标。"""
        before=self._eligible(project_id)
        if any(item.password_env!=database_secret_name(project_id,item.connection_id) for item in databases):
            raise JiejianError(ErrorCode.INPUT_INVALID,'数据库秘密引用与应用和连接身份不一致')
        if before.revision != revision:
            raise JiejianError(ErrorCode.STATE_PRECONDITION,'应用设置已变化，请重新读取')
        if not before.source_analysis_authorized:
            if not consent_source_read:
                raise JiejianError(ErrorCode.STATE_PRECONDITION,'请先明确允许读取当前应用源码')
            before=self.understanding.authorize_source_analysis(project_id,revision=revision)
        if port==self._control_port:
            raise JiejianError(ErrorCode.SELF_TARGET_FORBIDDEN,'不能使用界鉴自身的服务端口')
        analysis=self.understanding.analyzer.analyze(project_id,before.source_root)
        try:
            from product.backend.infrastructure.runtime.process.controlled.npm import npm_plan
            package=npm_plan(Path(before.source_root),build_script=build_script,allow_install_scripts=allow_install_scripts)
            files=inspect_runtime_files(Path(before.source_root),
                ((item.relative_path, item.content_sha256) for item in analysis.files))
            if entry not in {item.relative_path for item in files} and (package is None or package.build_script is None):
                raise JiejianError(ErrorCode.STATE_PRECONDITION,
                    '入口文件不在当前目录的已授权文件清单中。入口应相对接入目录填写；例如文件位于 source 子目录时，填写 source/app.mjs。')
            # 与正式源码身份使用同一份受控扫描范围，不能运行扫描范围外的模块。
            manifest=NodeRuntimeManifest(instance_id='rti_'+'0'*32,project_id=project_id,entry=entry,port=port,
                files=files,source_fingerprint=runtime_source_fingerprint(files),
                **node_execution_identity(self._node()),module_loader='NODE_STANDARD',package=package,sqlite=tuple(sqlite),
                sqlite_source_root=before.source_root if sqlite else None,databases=tuple(databases))
            if manifest.source_fingerprint != analysis.source_fingerprint:
                raise ValueError('source identity mismatch')
        except (OSError,ValueError):
            raise JiejianError(ErrorCode.STATE_PRECONDITION,
                '请核对 JavaScript 入口、npm 锁文件、受支持的公开依赖及所选构建步骤') from None
        # 在安装依赖前指出缺失的业务数据；Worker 复制时仍须核对当时的文件和结构。
        from product.backend.infrastructure.runtime.process.controlled.artifact import _regular_file
        for database in sqlite:
            try:
                _regular_file(Path(before.source_root), database.relative_path)
            except (OSError, ValueError):
                raise JiejianError(ErrorCode.STATE_PRECONDITION,
                    '没有找到所选 SQLite 业务数据库。请先初始化应用数据，或选择已有数据库后继续。',
                    details={'reason': 'SQLITE_SOURCE_REQUIRED'}) from None
        payload=dict(project_id=project_id,revision=before.revision,entry=entry,port=port,
            source_fingerprint=manifest.source_fingerprint,interpreter_fingerprint=manifest.interpreter_fingerprint,
            executor_fingerprint=manifest.executor_fingerprint,files=[item.model_dump(mode='json') for item in files],
            package=None if package is None else package.model_dump(mode='json'),sqlite=[item.model_dump(mode='json') for item in sqlite],
            **({'databases':[item.model_dump(mode='json') for item in databases]} if databases else {}))
        digest=hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
        return NodeStartPreview(**(payload|{'files':files,'package':package,'sqlite':tuple(sqlite),'databases':tuple(databases),'preview_fingerprint':digest}))

    def start(self, project_id, *, entry, port, revision, preview_fingerprint, operation_id, consent_execute, work=None,
            build_script=None, allow_install_scripts=False, sqlite=(),databases=()):
        """同操作键先查原记录；只有新操作才冻结已预览代码并排队。"""
        if not consent_execute:
            raise JiejianError(ErrorCode.STATE_PRECONDITION,'启动当前应用需要明确确认')
        self._eligible(project_id)
        previous=self.jobs.operation(project_id,operation_id)
        if previous is not None:
            if previous['request'].preview_fingerprint != preview_fingerprint:
                raise JiejianError(ErrorCode.STATE_PRECONDITION,'该操作已用于另一份启动预览')
            return self._public(previous)
        preview=self.preview(project_id,entry=entry,port=port,revision=revision,build_script=build_script,
            allow_install_scripts=allow_install_scripts,sqlite=sqlite,databases=databases)
        if preview.preview_fingerprint != preview_fingerprint:
            raise JiejianError(ErrorCode.STATE_PRECONDITION,'源码或运行设置已变化，请重新预览')
        before=self.understanding.get(project_id)
        manifest=NodeRuntimeManifest(instance_id='rti_'+uuid4().hex,project_id=project_id,entry=entry,port=port,
            files=preview.files,source_fingerprint=preview.source_fingerprint,
            interpreter_fingerprint=preview.interpreter_fingerprint,executor_fingerprint=preview.executor_fingerprint,
            module_loader='NODE_STANDARD',package=preview.package,sqlite=preview.sqlite,
            sqlite_source_root=before.source_root if preview.sqlite else None,databases=preview.databases)
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
            sample=work.sample_workspaces.for_project(project_id)
            if sample is not None and sample['runtime_kind']!='NODE_ESM':
                raise JiejianError(ErrorCode.STATE_PRECONDITION,'官方示例应使用其独立启动入口')
        return self._public(self.jobs.submit(request,validate_current=validate_current,work=work))

    def state(self, project_id, *, verify_source=True, verify_artifacts=True):
        self._eligible(project_id)
        with self._uow() as work:
            request=work.runtime_loads.latest(project_id)
        if request is None:
            return {'project_id':project_id,'operation':None,'running':False,'source_matches':False,'configuration':None}
        operation=self.jobs.operation(project_id,request.operation_id)
        configuration=None
        try:
            _,manifest=read_node_manifest(self.var_dir,request,verify_files=verify_artifacts)
            configuration={'entry':manifest.entry,'port':manifest.port,'file_count':len(manifest.files),
                'package':None if manifest.package is None else manifest.package.model_dump(mode='json'),
                'sqlite':[item.model_dump(mode='json') for item in manifest.sqlite],
                'databases':[item.model_dump(mode='json') for item in manifest.databases]}
        except (OSError,ValueError,JiejianError):
            pass
        running=False
        source_matches=False
        if operation['receipt'] is not None:
            try:
                if verify_artifacts:
                    running=node_reference_matches(self.var_dir,request,operation['receipt'].reference,self._node())
                else:
                    from product.backend.infrastructure.runtime.process.controlled.node_owned import node_process_alive
                    running=node_process_alive(operation['receipt'].reference)
                if verify_source:
                    current=self.understanding.get(project_id)
                    source_matches=current.source_analysis_authorized and self.understanding.analyzer.analyze(
                        project_id,current.source_root).source_fingerprint==request.source_fingerprint
            except (OSError,ValueError,JiejianError):
                pass
        preparation = None
        stage_file = node_artifact_store(self.var_dir) / request.instance_id / 'dependency-state.json'
        if stage_file.is_file():
            value = json.loads(stage_file.read_text(encoding='utf-8'))
            if value.get('stage') in {'INSTALLING','BUILDING','READY'}:
                preparation = dict(stage=value['stage'],cache_reused=value.get('cache_reused') is True)
        return {'project_id':project_id,'operation':self._public(operation),'running':running,'source_matches':source_matches,'configuration':configuration,'preparation':preparation}

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

    def selected_reference(self, project_id):
        """显式外部环境不借用受控回执；相同实例、未收口加载及官方样例保留核验。"""
        with self._uow() as work:
            work.begin_read_snapshot()
            current=work.application_understanding.get(project_id)
            sample=work.sample_workspaces.for_project(project_id)
            request=work.runtime_loads.latest(project_id)
            operation=None if request is None else self.jobs.read_in_work(work,request)
            if sample is None and current is not None and current.environment is not None and operation is not None:
                receipt=operation['receipt']
                if receipt is None and operation['job'].state in {JobState.FAILED,JobState.CANCELLED}:
                    return None
                if receipt is not None:
                    target=urlsplit(current.environment.target.base_url)
                    origin=(target.scheme,target.hostname,target.port or (443 if target.scheme=='https' else 80))
                    if origin!=('http','127.0.0.1',receipt.reference.port):
                        return None
        # 未确认失败不授权降级；同地址继续核对真实进程、实例和受控文件。
        return self.reference(project_id)

    def reference(self, project_id):
        # reference核对已加载实例；调用者按本次源码事实比较，避免先运行一轮不会使用结果的源码分析。
        state=self.state(project_id, verify_source=False)
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
            sample=work.sample_workspaces.for_project(project_id)
            if sample is not None and sample['runtime_kind']!='NODE_ESM':
                raise JiejianError(ErrorCode.STATE_PRECONDITION,'官方示例应使用其独立启动入口')
        return self.understanding.get(project_id)

    @staticmethod
    def _public(value):
        # 不向页面暴露内部进程路径、会话或租约，仅返回加载生命周期和独立启动回执。
        return {'operation_id':value['request'].operation_id,'project_id':value['request'].project_id,
            'instance_id':value['request'].instance_id,'job_id':value['job'].job_id,
            'state':value['job'].state.value,'source_fingerprint':value['request'].source_fingerprint,
            'receipt':None if value['receipt'] is None else value['receipt'].model_dump(mode='json')}
