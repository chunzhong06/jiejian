from typing import Literal

from pydantic import Field, field_validator, model_validator

from product.protocols.runtime.runtime_identity import Digest, RuntimeFile, RuntimeModel


class PortableUpdateFile(RuntimeModel):
    relative_path: str
    sha256: Digest

    @field_validator('relative_path')
    @classmethod
    def path_within_release(cls, value: str) -> str:
        return RuntimeFile.safe_path(value)


class PortableWorkspaceIdentity(RuntimeModel):
    generation: int = Field(ge=1)
    revision: str = Field(min_length=1)
    schema_digest: Digest


class PortableUpdateManifest(RuntimeModel):
    schema_version: Literal['2']
    document_type: Literal['jiejian.portable-update']
    version: str = Field(pattern=r'^\d+\.\d+\.\d+$')
    workspace_generation: int = Field(ge=1)
    workspace_revision: str
    workspace_digest: Digest
    supported_workspaces: list[PortableWorkspaceIdentity] = Field(min_length=1, max_length=256)
    files: list[PortableUpdateFile] = Field(min_length=1, max_length=30000)

    @model_validator(mode='after')
    def workspace_support(self):
        identities = {(item.generation, item.revision, item.schema_digest) for item in self.supported_workspaces}
        revisions = {item.revision for item in self.supported_workspaces}
        target = (self.workspace_generation, self.workspace_revision, self.workspace_digest)
        if (target not in identities or len(revisions) != len(self.supported_workspaces)
                or any(item.generation != self.workspace_generation for item in self.supported_workspaces)):
            raise ValueError('workspace support must contain the target and unique same-generation revisions')
        return self


class PortableUpdateOperation(RuntimeModel):
    schema_version: Literal['1']
    document_type: Literal['jiejian.portable-update-operation']
    operation_id: str = Field(pattern=r'^upd_[0-9a-f]{32}$')
    workspace: str
    previous_release: str
    target_release: str
    manifest_digest: Digest
    target_version: str
    port: int = Field(ge=1, le=65535)
    created_at: float
    phase: Literal['PREVIEWED', 'WAITING_FOR_EXIT', 'STARTING', 'READY', 'FAILED']
    reason: str = ''
    return_path: str = '/workspace'
    workspace_upgrade: bool = False


class PortableExitReceipt(RuntimeModel):
    schema_version: Literal['1']
    document_type: Literal['jiejian.portable-exit']
    state: Literal['STOPPED', 'NEEDS_REVIEW']
    finished_at: float
    exit_code: int
