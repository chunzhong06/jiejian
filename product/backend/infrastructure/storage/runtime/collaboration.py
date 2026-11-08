import json

from sqlalchemy import BigInteger, ForeignKey, Integer, String, Text, select
from sqlalchemy.orm import Mapped, mapped_column

from product.backend.infrastructure.storage.base import Base, _flush, ensure_storage_payload_safe
from product.backend.domain.errors import ErrorCode, JiejianError
from product.backend.domain.identifiers import PROJECT_ID_PATTERN
from product.protocols.codec import decode_json
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from typing import Literal, Any


class _StoredOperation(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True,hide_input_in_errors=True)
    operation_id:str=Field(pattern=r'^[0-9a-f]{32}$')
    capability:str
    title:str
    fingerprint:str=Field(pattern=r'^[0-9a-f]{64}$')
    arguments:dict
    summary:list
    state:Literal['WAITING_USER','RUNNING','UNKNOWN','SUCCEEDED','FAILED','DECLINED','CANCELLED']
    result:Any
    error_code:str|None=None


class _StoredQuestion(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True,hide_input_in_errors=True)
    question_id:str=Field(pattern=r'^[0-9a-f]{32}$')
    question:str
    options:list[str]
    answer:str|None


class _StoredTask(BaseModel):
    """只接受持久边界；保留旧任务的数量，不在读取时裁剪历史或增加默认事实。"""
    model_config=ConfigDict(extra='forbid',strict=True,hide_input_in_errors=True)
    schema_version:Literal['1']
    task_id:str=Field(pattern=r'^ctk_[0-9a-f]{32}$')
    project_id:str=Field(pattern=PROJECT_ID_PATTERN)
    state:Literal['WAITING_AGENT','WAITING_USER','RUNNING','BLOCKED','PAUSED','CANCELLED','COMPLETED']
    revision:int=Field(ge=1)
    created_at_us:int=Field(ge=0)
    updated_at_us:int=Field(ge=0)
    request_fingerprint:str=Field(pattern=r'^[0-9a-f]{64}$')
    goal:str
    purpose:Literal['CHECK','CHECK_AND_REPAIR','REPAIR','SETUP','RULES','UNDERSTAND','MAINTENANCE']
    references:dict[str,str]
    operations:list[_StoredOperation]
    questions:list[_StoredQuestion]
    events:list[dict]
    execution:dict|None
    editor:dict|None=None
    followups:list[dict]=Field(default_factory=list)
    goal_operation_baseline:int|None=None
    read_reports:list[str]=Field(default_factory=list)
    application_read:bool=False
    outcome:dict|None=None


class CollaborationRow(Base):
    __tablename__ = 'collaboration_tasks'
    task_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey('projects.project_id', ondelete='RESTRICT'), index=True)
    state: Mapped[str] = mapped_column(String(24))
    revision: Mapped[int] = mapped_column(Integer)
    updated_at_us: Mapped[int] = mapped_column(BigInteger)
    payload: Mapped[str] = mapped_column(Text)


class CollaborationRepository:
    """在调用方 UoW 中保存任务；不自行提交，也不以任务状态替代业务仓储。"""
    def __init__(self, session, known_secrets=()):
        self.session, self.secrets = session, known_secrets

    def get(self, project, task):
        row = self.session.get(CollaborationRow, task)
        return self._read(row) if row and row.project_id == project else None

    def list(self, project, *, limit=40):
        rows = self.session.scalars(select(CollaborationRow).where(CollaborationRow.project_id == project)
            .order_by(CollaborationRow.updated_at_us.desc()).limit(limit))
        return [self._read(row) for row in rows]

    def active(self):
        rows = self.session.scalars(select(CollaborationRow).where(
            CollaborationRow.state.not_in(('COMPLETED', 'CANCELLED'))))
        return [self._read(row) for row in rows]

    def current(self, project):
        row = self.session.scalars(select(CollaborationRow).where(CollaborationRow.project_id == project,
            CollaborationRow.state.not_in(('COMPLETED', 'CANCELLED')))
            .order_by(CollaborationRow.updated_at_us.desc()).limit(1)).first()
        return None if row is None else self._read(row)

    def has_unsettled_write(self,project):
        """逐条严格接受并在首次命中时停止，避免写锁内同时持有所有任务正文。

        操作仍由原根文档拥有；不建立第二份状态索引，也不以宽松 JSON 路径
        解释代替重复键、根身份及嵌套状态的严格接受。
        """
        rows=self.session.scalars(select(CollaborationRow).where(CollaborationRow.project_id==project)
            .execution_options(yield_per=1))
        return any(item['state'] in ('RUNNING','UNKNOWN')
            for row in rows for item in self._read(row)['operations'])

    def operation_owner(self,project,operation_id):
        """调用方持有写锁；跨任务重用外部写入标识也只能回到原任务核对。"""
        rows=self.session.scalars(select(CollaborationRow).where(CollaborationRow.project_id==project)
            .execution_options(yield_per=1))
        return next((row.task_id for row in rows if any(item['operation_id']==operation_id
            for item in self._read(row)['operations'])),None)

    @staticmethod
    def _read(row):
        # 持久根只有这一处 reader；未知格式不能由当前环境补成一个可继续执行的任务。
        try:
            value = decode_json(row.payload)
            _StoredTask.model_validate(value)
            if value['schema_version'] != '1' or any(value[key] != getattr(row, key)
                for key in ('task_id', 'project_id', 'state', 'revision', 'updated_at_us')):
                raise ValueError('task root identity mismatch')
            return value
        except (ValueError, KeyError, TypeError, ValidationError):
            raise JiejianError(ErrorCode.STORAGE_STATE, '协作任务的持久格式或关联不一致') from None

    def save(self, value):
        ensure_storage_payload_safe(value, self.secrets)
        row = self.session.get(CollaborationRow, value['task_id'])
        if row is None:
            row = CollaborationRow(task_id=value['task_id'], project_id=value['project_id'])
            self.session.add(row)
        row.state, row.revision, row.updated_at_us = value['state'], value['revision'], value['updated_at_us']
        row.payload = json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
        _flush(self.session)
