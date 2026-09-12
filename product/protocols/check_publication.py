# 当前检查的不可变发布清单；记录文件字节摘要与首次有效租约内的发布时刻。
from typing import Annotated, Literal

from pydantic import Field, model_validator

from product.protocols.execution_v3 import Hash, LogicalId, WireModel


class CheckPublishedFile(WireModel):
    path: Annotated[str, Field(pattern=r"^(?:result|request|runtime)\.json$|^evidence/ev_[0-9a-f]{64}\.json$")]
    sha256: Hash
    byte_count: int = Field(ge=1, le=1_048_576)


class CheckPublicationManifest(WireModel):
    schema_version: Literal["1"] = "1"
    project_id: LogicalId
    run_id: Annotated[str, Field(pattern=r"^run_[0-9a-f]{32}$")]
    job_id: Annotated[str, Field(pattern=r"^job_[0-9a-f]{32}$")]
    attempt: int = Field(ge=1)
    lease_owner: Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")]
    fencing_token: int = Field(ge=1)
    lease_expires_at_us: int = Field(ge=1)
    published_at_us: int = Field(ge=0)
    request_hash: Hash
    config_hash: Hash
    result_hash: Hash
    files: tuple[CheckPublishedFile, ...] = Field(min_length=3, max_length=4097)

    @model_validator(mode="after")
    def validate_files(self):
        files = {item.path: item for item in self.files}
        if len(files) != len(self.files) or tuple(sorted(files)) != tuple(item.path for item in self.files):
            raise ValueError("publication files must be unique and sorted")
        if any(name not in files or files[name].sha256 != digest for name, digest in (
            ("result.json", self.result_hash), ("request.json", self.request_hash), ("runtime.json", self.config_hash)
        )):
            raise ValueError("publication root file association")
        if self.published_at_us >= self.lease_expires_at_us:
            raise ValueError("publication must precede lease expiry")
        return self
