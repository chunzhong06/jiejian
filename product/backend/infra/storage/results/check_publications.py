# 当前检查的唯一发布收据；安全结论与全部证据仍来自不可变文件。
from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.orm import Session
from pydantic import Field

from product.backend.infra.storage.base import Base, StorageRecord, _flush, ensure_storage_payload_safe


class CheckPublicationRow(Base):
    __tablename__ = "check_publications"
    __table_args__ = (
        UniqueConstraint("job_id", name="uq_check_publications_job_id"),
        CheckConstraint("attempt >= 1 AND fencing_token >= 1 AND published_at_us >= 0", name="publication_bounds"),
        *(CheckConstraint(f"length({name}) = 64 AND {name} NOT GLOB '*[^0-9a-f]*'", name=f"{name}_format")
          for name in ("request_hash", "result_hash", "manifest_hash")),
    )
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("runs.run_id", ondelete="RESTRICT"), primary_key=True)
    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("jobs.job_id", ondelete="RESTRICT"), nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False)
    fencing_token: Mapped[int] = mapped_column(BigInteger, nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    result_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    manifest_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    published_at_us: Mapped[int] = mapped_column(BigInteger, nullable=False)


class CheckPublicationRecord(StorageRecord):
    run_id: str = Field(pattern=r"^run_[0-9a-f]{32}$")
    job_id: str = Field(pattern=r"^job_[0-9a-f]{32}$")
    attempt: int = Field(ge=1)
    fencing_token: int = Field(ge=1)
    request_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    result_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    manifest_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    published_at_us: int = Field(ge=0)


class CheckPublicationRepository:
    """收据与 Run、Job、Evidence 共享调用者事务；重复发布由唯一键收敛。"""

    def __init__(self, session: Session, known_secrets):
        self._session = session
        self._known_secrets = known_secrets

    def get(self, run_id: str) -> CheckPublicationRecord | None:
        row = self._session.get(CheckPublicationRow, run_id)
        return None if row is None else CheckPublicationRecord(**{
            name: getattr(row, name) for name in CheckPublicationRecord.model_fields
        })

    def add(self, record: CheckPublicationRecord) -> None:
        ensure_storage_payload_safe(record.model_dump(mode="json"), self._known_secrets)
        self._session.add(CheckPublicationRow(**record.model_dump()))
        _flush(self._session)
