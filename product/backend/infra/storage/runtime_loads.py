# 普通运行加载的不可变输入和成功回执；调度生命周期只由关联Job保存。
from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, String, Text, UniqueConstraint, select
from sqlalchemy.orm import Mapped, mapped_column

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.infra.storage.base import Base, _flush, ensure_storage_payload_safe
from product.protocols.node_runtime import NodeRuntimeLoadRequest, NodeRuntimeLoadReceipt, node_document_fingerprint


class RuntimeLoadRow(Base):
    __tablename__ = "runtime_loads"
    __table_args__ = (UniqueConstraint("project_id", "operation_id", name="uq_runtime_load_operation"),
        CheckConstraint("created_at_us >= 0", name="time_nonnegative"),)
    load_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.project_id", ondelete="RESTRICT"))
    operation_id: Mapped[str] = mapped_column(String(32))
    request_fingerprint: Mapped[str] = mapped_column(String(64))
    request_json: Mapped[str] = mapped_column(Text)
    receipt_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at_us: Mapped[int] = mapped_column(BigInteger)


class RuntimeLoadRepository:
    def __init__(self, session, known_secrets=()):
        self._session, self._secrets = session, known_secrets

    def get(self, load_id: str) -> NodeRuntimeLoadRequest | None:
        row = self._session.get(RuntimeLoadRow, load_id)
        if row is None:
            return None
        request = NodeRuntimeLoadRequest.model_validate_json(row.request_json)
        if (request.load_id != row.load_id or request.project_id != row.project_id
                or request.operation_id != row.operation_id or node_document_fingerprint(request) != row.request_fingerprint):
            raise JiejianError(ErrorCode.STORAGE_STATE, "运行加载输入关联不一致")
        return request

    def operation(self, project_id: str, operation_id: str) -> NodeRuntimeLoadRequest | None:
        row = self._session.scalar(select(RuntimeLoadRow).where(RuntimeLoadRow.project_id == project_id,
            RuntimeLoadRow.operation_id == operation_id))
        return None if row is None else self.get(row.load_id)

    def latest(self, project_id: str) -> NodeRuntimeLoadRequest | None:
        row = self._session.scalar(select(RuntimeLoadRow).where(RuntimeLoadRow.project_id == project_id)
            .order_by(RuntimeLoadRow.created_at_us.desc(), RuntimeLoadRow.load_id.desc()).limit(1))
        return None if row is None else self.get(row.load_id)

    def add(self, request: NodeRuntimeLoadRequest) -> None:
        ensure_storage_payload_safe(request.model_dump(mode="json"), self._secrets)
        self._session.add(RuntimeLoadRow(load_id=request.load_id, project_id=request.project_id,
            operation_id=request.operation_id, request_fingerprint=node_document_fingerprint(request),
            request_json=request.model_dump_json(), receipt_json=None, created_at_us=request.created_at_us))
        _flush(self._session)

    def successful_for_source(self, project_id, source_fingerprint):
        """有界回读已经核对的冻结副本；历史进程是否仍存活不影响源码材料比较。"""
        rows = self._session.scalars(select(RuntimeLoadRow).where(RuntimeLoadRow.project_id == project_id,
            RuntimeLoadRow.receipt_json.is_not(None)).order_by(RuntimeLoadRow.created_at_us.desc()).limit(256)).all()
        for row in rows:
            request = self.get(row.load_id)
            if request.source_fingerprint == source_fingerprint:
                return self.receipt(row.load_id)
        return None

    def receipt(self, load_id: str) -> NodeRuntimeLoadReceipt | None:
        row = self._session.get(RuntimeLoadRow, load_id)
        if row is None or row.receipt_json is None:
            return None
        receipt = NodeRuntimeLoadReceipt.model_validate_json(row.receipt_json)
        self._check_receipt(receipt)
        return receipt

    def publish(self, receipt: NodeRuntimeLoadReceipt) -> None:
        """调用者须在同一UoW先核对并完成Job的fence条件更新；回执不得脱离该事务发布。"""
        self._check_receipt(receipt)
        row = self._session.get(RuntimeLoadRow, receipt.load_id)
        previous = self.receipt(receipt.load_id)
        if previous is not None and previous != receipt:
            raise JiejianError(ErrorCode.STORAGE_STATE, "运行加载回执不可改写")
        ensure_storage_payload_safe(receipt.model_dump(mode="json"), self._secrets)
        row.receipt_json = receipt.model_dump_json()
        _flush(self._session)

    def _check_receipt(self, receipt):
        request = self.get(receipt.load_id)
        reference = receipt.reference
        if request is None or (receipt.request_fingerprint != node_document_fingerprint(request)
                or reference.project_id != request.project_id or reference.instance_id != request.instance_id
                or reference.source_fingerprint != request.source_fingerprint
                or reference.manifest_fingerprint != request.manifest_fingerprint
                or receipt.started_at_us < request.created_at_us):
            raise JiejianError(ErrorCode.STORAGE_STATE, "运行加载回执与原输入不一致")
