# 私有参照输入的独立根；只保存内容摘要、来源及业务归属，文件正文不进入公共协议。
from typing import Annotated,Literal
from pydantic import Field,model_validator
from product.protocols.runtime.runtime_identity import RuntimeModel,Digest
from product.protocols.runtime.node_runtime import ProjectId
from product.protocols.checks.business_facts import ArtifactManifestReference

ArtifactId=Annotated[str,Field(pattern=r'^pai_[0-9a-f]{32}$')]
CaptureId=Annotated[str,Field(pattern=r'^rpc_[0-9a-f]{32}$')]


class ProofArtifactInput(RuntimeModel):
    schema_version:Literal['1']='1'
    asset_id:ArtifactId
    project_id:ProjectId
    operation_id:Annotated[str,Field(pattern=r'^[0-9a-f]{32}$')]
    action_id:Annotated[str,Field(pattern=r'^bac_[0-9a-f]{32}$')]
    action_revision:int=Field(ge=1)
    resource_binding_id:Annotated[str,Field(pattern=r'^res_[0-9a-f]{32}$')]
    resource_id:str=Field(min_length=1,max_length=256)
    owner_identity_id:Annotated[str,Field(pattern=r'^tid_[0-9a-f]{32}$')]
    origin:Literal['UPLOAD','REFERENCE_CAPTURE']
    reference_capture_id:CaptureId|None=None
    state:Literal['PENDING','COMPLETE','INCOMPLETE','CANCELLED']
    manifest:ArtifactManifestReference|None=None
    created_at_us:int=Field(ge=0)
    basis_id:Annotated[str,Field(pattern=r'^pb_[0-9a-f]{64}$')]

    @model_validator(mode='after')
    def complete_input(self):
        if (self.origin=='REFERENCE_CAPTURE')!=(self.reference_capture_id is not None):raise ValueError('artifact origin mismatch')
        if (self.state=='COMPLETE')!=(self.manifest is not None):raise ValueError('complete artifact requires manifest')
        if self.manifest is not None and self.manifest.asset_id!=self.asset_id:raise ValueError('artifact manifest mismatch')
        return self
