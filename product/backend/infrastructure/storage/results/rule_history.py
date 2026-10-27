# 规则历史仅保存准确定位与整理进度；安全结论始终回到原发布包读取。
from __future__ import annotations
from sqlalchemy import BigInteger,Integer,String,ForeignKey,CheckConstraint,Index,select,text,delete
from sqlalchemy.orm import Mapped,mapped_column
from product.backend.infrastructure.storage.base import Base,_flush,ensure_storage_payload_safe


class RuleCheckIndexRow(Base):
    __tablename__='rule_check_index'
    __table_args__=(CheckConstraint('revision >= 1 AND created_at_us >= 0',name='bounds'),
        Index('ix_rule_check_index_rule','project_id','intent_id','revision','intent_hash','created_at_us','run_id'))
    project_id:Mapped[str]=mapped_column(String(64),ForeignKey('projects.project_id',ondelete='RESTRICT'),primary_key=True)
    intent_id:Mapped[str]=mapped_column(String(36),primary_key=True)
    revision:Mapped[int]=mapped_column(Integer,primary_key=True)
    intent_hash:Mapped[str]=mapped_column(String(64),primary_key=True)
    run_id:Mapped[str]=mapped_column(String(36),ForeignKey('runs.run_id',ondelete='RESTRICT'),primary_key=True)
    case_id:Mapped[str]=mapped_column(String(37),primary_key=True)
    manifest_hash:Mapped[str]=mapped_column(String(64),nullable=False)
    created_at_us:Mapped[int]=mapped_column(BigInteger,nullable=False)


class RuleHistoryRunRow(Base):
    __tablename__='rule_history_runs'
    run_id:Mapped[str]=mapped_column(String(36),ForeignKey('runs.run_id',ondelete='RESTRICT'),primary_key=True)
    manifest_hash:Mapped[str]=mapped_column(String(64),nullable=False)
    error_code:Mapped[str|None]=mapped_column(String(64),nullable=True)


class RuleHistoryCoverageRow(Base):
    __tablename__='rule_history_coverage'
    __table_args__=(CheckConstraint('checkpoint >= 0 AND generation >= 0 AND processed >= 0 AND failed >= 0',name='bounds'),)
    project_id:Mapped[str]=mapped_column(String(64),ForeignKey('projects.project_id',ondelete='RESTRICT'),primary_key=True)
    checkpoint:Mapped[int]=mapped_column(Integer,nullable=False)
    generation:Mapped[int]=mapped_column(Integer,nullable=False)
    upper_time:Mapped[int]=mapped_column(BigInteger,nullable=False)
    upper_run:Mapped[str]=mapped_column(String(36),nullable=False)
    cursor_time:Mapped[int]=mapped_column(BigInteger,nullable=False)
    cursor_run:Mapped[str]=mapped_column(String(36),nullable=False)
    processed:Mapped[int]=mapped_column(Integer,nullable=False)
    failed:Mapped[int]=mapped_column(Integer,nullable=False)
    complete:Mapped[bool]=mapped_column(nullable=False)


class RuleHistoryReceiptRow(Base):
    __tablename__='rule_history_receipts'
    __table_args__=(CheckConstraint('checkpoint >= 1 AND processed >= 0 AND failed >= 0',name='bounds'),)
    project_id:Mapped[str]=mapped_column(String(64),ForeignKey('projects.project_id',ondelete='RESTRICT'),primary_key=True)
    operation_id:Mapped[str]=mapped_column(String(32),primary_key=True)
    request_hash:Mapped[str]=mapped_column(String(64),nullable=False)
    checkpoint:Mapped[int]=mapped_column(Integer,nullable=False)
    processed:Mapped[int]=mapped_column(Integer,nullable=False)
    failed:Mapped[int]=mapped_column(Integer,nullable=False)
    complete:Mapped[bool]=mapped_column(nullable=False)


def _fields(row):return {column.name:getattr(row,column.name) for column in row.__table__.columns}


class RuleHistoryRepository:
    def __init__(self,session,known_secrets):self._session,self._known=session,known_secrets

    def index(self,*,project_id,run_id,manifest_hash,created_at_us,permissions,error_code=None):
        # 同包重建可修复损坏索引；调用者须先校验发布收据，不能在普通GET中调用。
        self._session.execute(delete(RuleCheckIndexRow).where(RuleCheckIndexRow.run_id==run_id))
        for case_id,permission in permissions:
            value=dict(project_id=project_id,run_id=run_id,case_id=case_id,intent_id=permission.intent_id,revision=permission.revision,
                intent_hash=permission.intent_hash,manifest_hash=manifest_hash,created_at_us=created_at_us)
            ensure_storage_payload_safe(value,self._known);self._session.add(RuleCheckIndexRow(**value))
        state=self._session.get(RuleHistoryRunRow,run_id)
        if state is None:self._session.add(RuleHistoryRunRow(run_id=run_id,manifest_hash=manifest_hash,error_code=error_code))
        else:state.manifest_hash=manifest_hash;state.error_code=error_code
        _flush(self._session)

    def coverage(self,project_id):
        row=self._session.get(RuleHistoryCoverageRow,project_id)
        return dict(project_id=project_id,checkpoint=0,generation=0,upper_time=0,upper_run='',cursor_time=0,cursor_run='',processed=0,failed=0,complete=True) if row is None else _fields(row)

    def save_coverage(self,value):
        ensure_storage_payload_safe(value,self._known)
        self._session.merge(RuleHistoryCoverageRow(**value));_flush(self._session)

    def receipt(self,project_id,operation_id):
        value=self._session.get(RuleHistoryReceiptRow,(project_id,operation_id))
        return None if value is None else _fields(value)

    def save_receipt(self,value):
        ensure_storage_payload_safe(value,self._known);self._session.add(RuleHistoryReceiptRow(**value));_flush(self._session)

    def missing(self,project_id):
        return self._session.execute(text('''SELECT count(*) FROM check_publications p JOIN runs r ON r.run_id=p.run_id
            LEFT JOIN rule_history_runs i ON i.run_id=p.run_id WHERE r.project_id=:project AND
            (i.run_id IS NULL OR i.manifest_hash!=p.manifest_hash OR (i.error_code IS NULL AND EXISTS
                (SELECT 1 FROM evidence_index e WHERE e.run_id=p.run_id AND NOT EXISTS
                    (SELECT 1 FROM rule_check_index x WHERE x.run_id=e.run_id AND x.case_id=e.case_id))))'''),dict(project=project_id)).scalar_one()

    def unreadable(self,project_id):
        return self._session.execute(text('''SELECT count(*) FROM rule_history_runs i JOIN runs r ON r.run_id=i.run_id
            WHERE r.project_id=:project AND i.error_code IS NOT NULL'''),dict(project=project_id)).scalar_one()

    def upper(self,project_id):
        row=self._session.execute(text('''SELECT p.published_at_us,p.run_id FROM check_publications p JOIN runs r ON r.run_id=p.run_id
            WHERE r.project_id=:project ORDER BY p.published_at_us DESC,p.run_id DESC LIMIT 1'''),dict(project=project_id)).first()
        return (0,'') if row is None else tuple(row)

    def scan(self,project_id,*,cursor,upper,limit):
        rows=self._session.execute(text('''SELECT p.run_id,p.manifest_hash,p.published_at_us,r.created_at_us FROM check_publications p
            JOIN runs r ON r.run_id=p.run_id WHERE r.project_id=:project
            AND (p.published_at_us>:cursor_time OR (p.published_at_us=:cursor_time AND p.run_id>:cursor_run))
            AND (p.published_at_us<:upper_time OR (p.published_at_us=:upper_time AND p.run_id<=:upper_run))
            ORDER BY p.published_at_us,p.run_id LIMIT :limit'''),dict(project=project_id,cursor_time=cursor[0],cursor_run=cursor[1],upper_time=upper[0],upper_run=upper[1],limit=limit))
        return tuple(dict(row._mapping) for row in rows)

    def runs(self,project_id,reference,*,limit,before_time=None,before_run=None):
        statement=select(RuleCheckIndexRow.run_id,RuleCheckIndexRow.created_at_us).where(RuleCheckIndexRow.project_id==project_id,
            RuleCheckIndexRow.intent_id==reference[0],RuleCheckIndexRow.revision==reference[1],RuleCheckIndexRow.intent_hash==reference[2])
        if before_time is not None:
            from sqlalchemy import or_,and_
            statement=statement.where(or_(RuleCheckIndexRow.created_at_us<before_time,and_(RuleCheckIndexRow.created_at_us==before_time,RuleCheckIndexRow.run_id>before_run)))
        return tuple(row.run_id for row in self._session.execute(statement.distinct().order_by(RuleCheckIndexRow.created_at_us.desc(),RuleCheckIndexRow.run_id.asc()).limit(limit)))

    def rules(self,project_id,*,limit,after=None,include_archived=False):
        # 一次页查询连接准确业务修订及最近索引；不逐规则读取完整发布包。
        sql='''WITH selected AS (SELECT p.* FROM permission_intent_revisions p WHERE p.project_id=:project
            AND (:archived=1 OR p.revision=(SELECT max(q.revision) FROM permission_intent_revisions q WHERE q.intent_id=p.intent_id))
            AND (:archived=1 OR p.effective_state='ACTIVE')
            AND (:after IS NULL OR p.intent_id||':'||printf('%012d',p.revision)>:after)
            ORDER BY p.intent_id,p.revision LIMIT :limit)
            SELECT p.intent_id,p.revision,p.intent_hash,p.expectation,p.effective_state,p.relation,
            a.display_name AS action_label,s.display_name AS subject_label,o.display_name AS owner_label,
            (SELECT i.run_id FROM rule_check_index i WHERE i.project_id=p.project_id AND i.intent_id=p.intent_id AND i.revision=p.revision
                AND i.intent_hash=p.intent_hash ORDER BY i.created_at_us DESC,i.run_id LIMIT 1) AS latest_run_id
            FROM selected p JOIN business_action_revisions a ON a.action_id=p.business_action_id AND a.revision=p.action_revision
            JOIN business_actor_revisions s ON s.actor_id=p.subject_actor_id AND s.revision=p.subject_actor_revision
            JOIN business_actor_revisions o ON o.actor_id=p.resource_owner_actor_id AND o.revision=p.resource_owner_actor_revision
            ORDER BY p.intent_id,p.revision'''
        return tuple(dict(row._mapping) for row in self._session.execute(text(sql),dict(project=project_id,archived=int(include_archived),after=after,limit=limit)))
