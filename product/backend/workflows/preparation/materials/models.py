# 有限材料选择、乐观并发与恢复回执；不保存秘密、准备结论或历史检查结果。
from typing import Literal

from pydantic import Field, model_validator

from product.backend.core.boundaries.entities import BoundaryModel


class MaterialReference(BoundaryModel):
    action_id: str = Field(pattern=r"^bac_[0-9a-f]{32}$")
    action_revision: int = Field(ge=1)
    kind: Literal["execution", "resource", "evidence", "recovery"]
    member_id: str | None = Field(default=None, max_length=80)


class MaterialChange(BoundaryModel):
    schema_version: Literal["1"] = "1"
    operation_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    material: MaterialReference
    expected_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_recording_id: str | None = Field(default=None, pattern=r"^rec_[0-9a-f]{32}$")


class PreparationDraft(BoundaryModel):
    schema_version: Literal["1"] = "1"
    revision: int = Field(ge=0)
    action_id: str | None = Field(default=None, pattern=r"^bac_[0-9a-f]{32}$")
    action_revision: int | None = Field(default=None, ge=1)
    material: MaterialReference | None = None
    candidate_recording_id: str | None = Field(default=None, pattern=r"^rec_[0-9a-f]{32}$")
    base_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    pending_operation_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{32}$")

    @model_validator(mode="after")
    def coherent_context(self):
        if (self.action_id is None) != (self.action_revision is None):
            raise ValueError("preparation draft requires exact action revision")
        if self.material is not None and (self.action_id, self.action_revision) != (self.material.action_id, self.material.action_revision):
            raise ValueError("material draft context mismatch")
        if (self.candidate_recording_id or self.pending_operation_id) and (self.material is None or self.base_fingerprint is None):
            raise ValueError("material choice requires captured preparation basis")
        return self
