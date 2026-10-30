# 人工参照输入沿原准备依据和操作回执保存；已被来源引用的字节不可替换或清除。
from typing import Literal
from pydantic import Field
from product.backend.domain.errors import ErrorCode,JiejianError
from product.backend.infrastructure.artifacts.proof_artifacts import ProofArtifactStore
from product.backend.application.preparation.proofs.commands import ProofOperation
from product.protocols.preparation.proof_artifacts import ProofArtifactInput,ArtifactId
from product.protocols.checks.business_facts import ArtifactManifestReference


class UploadProofArtifact(ProofOperation):
    action_id:str=Field(pattern=r'^bac_[0-9a-f]{32}$')
    action_revision:int=Field(ge=1)
    resource_binding_id:str=Field(pattern=r'^res_[0-9a-f]{32}$')
    size:int=Field(gt=0,le=4194304)
    sha256:str=Field(pattern=r'^[0-9a-f]{64}$')
    confirmed:Literal[True]


class CancelProofArtifact(ProofOperation):
    asset_id:ArtifactId
    confirmed:Literal[True]


class ProofArtifactPreparation:
    def __init__(self,proofs,inspector):
        self.proofs,self.inspector=proofs,inspector
        self.store=ProofArtifactStore(proofs.var_dir)

    def _known(self,project_id,action_id,action_revision,owner_id=None):
        from product.backend.infrastructure.execution.web.check_runtime import check_secret_names
        with self.proofs._uow() as work:
            ids={owner_id} if owner_id is not None else set()
            for binding in (work.action_preparation.execution(action_id,action_revision),work.action_preparation.recovery(action_id,action_revision)):
                if binding is not None:ids.update((binding.subject_test_identity_id,binding.resource_owner_test_identity_id))
            identities=tuple(item for item in work.test_identities.list_for_project(project_id) if item.identity_id in ids)
        names=set()
        for identity in identities:
            if identity.prepared_at_us is not None:
                names.update(check_secret_names(self.proofs._credentials.profile_identity(identity)))
        return tuple(self.proofs._credentials.resolve(tuple(sorted(names))).values())

    def upload(self,project_id,command,content):
        known=self._known(project_id,command.action_id,command.action_revision)
        content=self.store.accept(content,known)
        if (len(content.raw),content.sha256)!=(command.size,command.sha256):
            raise JiejianError(ErrorCode.STATE_PRECONDITION,'上传内容与本次操作不一致')
        def execute(work):
            facts=self.proofs._current(work,project_id,command)
            action=next((item for item in facts.boundary.actions if (item.action_id,item.revision)==(command.action_id,command.action_revision)),None)
            resource=next((item for item in facts.resources if self.proofs._resource_id(item)==command.resource_binding_id
                and (item.business_action_id,item.action_revision)==(command.action_id,command.action_revision)),None)
            if action is None or resource is None or self.inspector.reasons(work,resource,action,facts.understanding):
                raise JiejianError(ErrorCode.STATE_PRECONDITION,'请先确认本动作的真实测试资源及所有者')
            asset_id='pai_'+command.operation_id
            manifest=ArtifactManifestReference(asset_id=asset_id,size=command.size,sha256=command.sha256)
            value=ProofArtifactInput(asset_id=asset_id,project_id=project_id,operation_id=command.operation_id,
                action_id=command.action_id,action_revision=command.action_revision,resource_binding_id=command.resource_binding_id,
                resource_id=resource.actual_resource_id,owner_identity_id=resource.resource_owner_test_identity_id,
                origin='UPLOAD',state='COMPLETE',manifest=manifest,created_at_us=self.proofs._clock(),basis_id=facts.basis_id)
            work.proof_artifacts.add_input(value)
            self.store.save(project_id,asset_id,content)
            return dict(asset_id=asset_id,state='COMPLETE',manifest=manifest.model_dump(mode='json'))
        return self.proofs._operation(project_id,'UPLOAD_REFERENCE',command,execute)

    def read(self,project_id,asset_id):
        with self.proofs._uow() as work:
            self.proofs._facts(work,project_id)
            value=work.proof_artifacts.input(project_id,asset_id)
            if value is None or value.state!='COMPLETE':raise JiejianError(ErrorCode.RECORD_NOT_FOUND,'参照文件尚不可读取')
            known=self._known(project_id,value.action_id,value.action_revision,value.owner_identity_id)
            return self.store.read(project_id,value.manifest,known_secrets=known)

    def cancel(self,project_id,command):
        def execute(work):
            self.proofs._current(work,project_id,command)
            value=work.proof_artifacts.input(project_id,command.asset_id)
            if value is None:raise JiejianError(ErrorCode.RECORD_NOT_FOUND,'参照输入不存在')
            if work.proof_artifacts.referenced(value.asset_id):raise JiejianError(ErrorCode.STATE_PRECONDITION,'这份参照仍被来源或检查使用，不能清除')
            if value.reference_capture_id is not None:
                job=work.jobs.get_by_capture(value.reference_capture_id)
                if job is None or job.state.value not in {'SUCCEEDED','FAILED','CANCELLED'}:
                    raise JiejianError(ErrorCode.STATE_PRECONDITION,'请先结束这次取样任务')
            if value.state!='CANCELLED':
                work.proof_artifacts.update_input(value.model_copy(update={'state':'CANCELLED','manifest':None}),expected_state=value.state)
            return dict(asset_id=value.asset_id,state='CANCELLED')
        receipt=self.proofs._operation(project_id,'CANCEL_REFERENCE',command,execute)
        # 先提交不可采用状态，再清理无引用原文；清理中断可由同一回执重试，不能反向留下可采用的缺失文件。
        with self.proofs._uow() as work:
            work.acquire_write_lock()
            value=work.proof_artifacts.input(project_id,command.asset_id)
            if value is not None and value.state=='CANCELLED' and not work.proof_artifacts.referenced(value.asset_id):
                self.store.remove_unreferenced(project_id,value.asset_id)
        return receipt
