# 持久化已由GUI确认的材料批次与步骤回执引用，不保存账号秘密或目标响应正文。
import json
from sqlalchemy import BigInteger, Boolean, ForeignKey, String, Text, select
from sqlalchemy.orm import Mapped, mapped_column
from product.backend.infra.storage.base import Base, _flush, ensure_storage_payload_safe


class PreparationBatchRow(Base):
    __tablename__ = 'preparation_batches'
    operation_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey('projects.project_id', ondelete='RESTRICT'))
    plan_hash: Mapped[str] = mapped_column(String(64))
    control_session_id: Mapped[str] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(24))
    cancel_requested: Mapped[bool] = mapped_column(Boolean)
    created_at_us: Mapped[int] = mapped_column(BigInteger)
    updated_at_us: Mapped[int] = mapped_column(BigInteger)
    payload: Mapped[str] = mapped_column(Text)


class PreparationBatchRepository:
    def __init__(self, session, known_secrets=()):
        self._session, self._secrets = session, known_secrets

    def get(self, project, operation):
        row = self._session.get(PreparationBatchRow, operation)
        return self._value(row) if row is not None and row.project_id == project else None

    def latest(self, project):
        row = self._session.scalar(select(PreparationBatchRow).where(PreparationBatchRow.project_id == project)
            .order_by(PreparationBatchRow.created_at_us.desc(), PreparationBatchRow.operation_id.desc()).limit(1))
        return None if row is None else self._value(row)

    def active(self, project=None):
        statement = select(PreparationBatchRow).where(PreparationBatchRow.state.in_(('RUNNING', 'CANCELLING')))
        if project is not None:
            statement = statement.where(PreparationBatchRow.project_id == project)
        return tuple(self._value(row) for row in self._session.scalars(statement.order_by(PreparationBatchRow.created_at_us).limit(32)))

    def save(self, value):
        ensure_storage_payload_safe(value, self._secrets)
        encoded = dict(value, payload=json.dumps(value['payload'], ensure_ascii=False, separators=(',', ':')))
        row = self._session.get(PreparationBatchRow, value['operation_id'])
        if row is None:
            self._session.add(PreparationBatchRow(**encoded))
        else:
            # GUI可在后台步骤运行时请求取消；较早的步骤快照不能抹掉这个决定。
            encoded['cancel_requested'] = row.cancel_requested or encoded['cancel_requested']
            if encoded['cancel_requested'] and encoded['state'] == 'RUNNING':
                encoded['state'] = 'CANCELLING'
            for key, item in encoded.items():
                setattr(row, key, item)
        _flush(self._session)

    @staticmethod
    def _value(row):
        value = {column.name: getattr(row, column.name) for column in PreparationBatchRow.__table__.columns}
        value['payload'] = json.loads(value['payload'])
        return value
