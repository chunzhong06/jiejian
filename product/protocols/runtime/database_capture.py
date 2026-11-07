"""普通服务数据库的有限连接与投影声明；不携带密码、任意 SQL 或连接串。"""
from typing import Annotated, Literal
import re
import hashlib
from pydantic import Field, model_validator
from product.protocols.runtime.runtime_identity import RuntimeModel

Identifier=Annotated[str,Field(pattern=r'^[A-Za-z_][A-Za-z0-9_]{0,62}$')]


def database_secret_name(project_id,connection_id):
    return 'JIEJIAN_DB_'+hashlib.sha256((project_id+'\0'+connection_id).encode()).hexdigest().upper()


class DatabaseCapture(RuntimeModel):
    connection_id: Identifier
    engine: Literal['POSTGRESQL','MYSQL']
    host: Literal['127.0.0.1']='127.0.0.1'
    port: int=Field(ge=1024,le=65535)
    database: Identifier
    namespace: Identifier
    username: Identifier
    password_env: str=Field(pattern=r'^JIEJIAN_DB_[A-Z0-9_]{1,64}$')
    table: Identifier
    resource_column: Identifier
    owner_column: Identifier
    fields: tuple[Identifier,...]=Field(min_length=1,max_length=8)

    @model_validator(mode='after')
    def finite_projection(self):
        if self.engine=='MYSQL' and self.namespace!=self.database:
            raise ValueError('MySQL namespace must be its database')
        if len(set(self.fields))!=len(self.fields) or self.resource_column==self.owner_column:
            raise ValueError('database capture columns must be distinct')
        if any(re.search(r'authorization|cookie|credential|password|passwd|secret|token|api_?key',name,re.I)
                for name in (self.resource_column,self.owner_column,*self.fields)):
            raise ValueError('secret columns cannot be captured')
        if self.table.startswith('_jj_'):
            raise ValueError('capture cannot select internal tables')
        return self
