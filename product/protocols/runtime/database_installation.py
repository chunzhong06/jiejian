"""数据库安装回执独立持久化，后续读取须核对准确配置与对象定义。"""
from typing import Literal
from pydantic import Field,model_validator
from product.protocols.runtime.runtime_identity import RuntimeModel,Digest
from product.protocols.runtime.database_capture import DatabaseCapture,Identifier


class DatabaseInstallation(RuntimeModel):
    schema_version:Literal['1']='1'
    document_type:Literal['jiejian.database-installation']='jiejian.database-installation'
    project_id:str=Field(pattern=r'^[a-z][a-z0-9_-]{0,63}$')
    operation_id:str=Field(pattern=r'^ppf_[0-9a-f]{32}$')
    plan_fingerprint:Digest
    capture:DatabaseCapture
    generation:str=Field(pattern=r'^sql_[0-9a-f]{32}$')
    definitions:dict[Identifier,Digest]=Field(max_length=8)
    state:Literal['INCOMPLETE','INSTALLED','REMOVING','REMOVED']
    completed_at_us:int=Field(ge=0)

    @model_validator(mode='after')
    def matching_object_state(self):
        if self.state=='INSTALLED' and len(self.definitions)<4 or self.state=='REMOVED' and self.definitions:
            raise ValueError('database object state is inconsistent')
        return self
