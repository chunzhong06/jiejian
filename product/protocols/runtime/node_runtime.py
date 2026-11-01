# 普通 Node 运行清单：冻结源码、模块加载、依赖和 SQLite 观察配置。
from __future__ import annotations

from typing import Annotated, Literal
import hashlib
import json
import re

from pydantic import Field, field_validator, model_validator

from product.protocols.runtime.runtime_identity import Digest, InstanceId, MAX_ARTIFACT_BYTES, RuntimeFile, RuntimeModel, runtime_source_fingerprint
ProjectId = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")]

SqliteIdentifier = Annotated[str, Field(pattern=r'^[A-Za-z_][A-Za-z0-9_]{0,63}$')]


class SqliteTableCapture(RuntimeModel):
    table: SqliteIdentifier
    resource_column: SqliteIdentifier
    owner_column: SqliteIdentifier
    fields: tuple[SqliteIdentifier, ...] = Field(min_length=1, max_length=8)

    @model_validator(mode='after')
    def distinct_fields(self):
        if len(set(self.fields)) != len(self.fields) or any(re.search(
            r'authorization|cookie|credential|password|passwd|secret|token|api_?key', value, re.I)
            for value in (self.resource_column,self.owner_column,*self.fields)):
            raise ValueError('capture fields must be distinct nonsecret columns')
        return self


class SqliteDatabaseCapture(RuntimeModel):
    relative_path: str = Field(min_length=1, max_length=512)
    tables: tuple[SqliteTableCapture, ...] = Field(min_length=1, max_length=8)

    @field_validator('relative_path')
    @classmethod
    def database_path(cls, value):
        return RuntimeFile.safe_path(value)

    @model_validator(mode='after')
    def unique_tables(self):
        if len({table.table for table in self.tables}) != len(self.tables):
            raise ValueError('duplicate captured table')
        return self


class NodePackagePlan(RuntimeModel):
    manager: Literal['npm'] = 'npm'
    lockfile: Literal['package-lock.json'] = 'package-lock.json'
    build_script: str | None = Field(default=None, pattern=r'^[A-Za-z0-9:_-]{1,64}$')
    allow_install_scripts: bool = False


class NodeRuntimeManifest(RuntimeModel):
    schema_version: Literal["1"] = "1"
    mode: Literal["CONTROLLED_NODE_ESM"] = "CONTROLLED_NODE_ESM"
    instance_id: InstanceId
    project_id: ProjectId
    entry: str = Field(min_length=1, max_length=512)
    port: int = Field(ge=1024, le=65535)
    files: tuple[RuntimeFile, ...] = Field(min_length=1, max_length=512)
    source_fingerprint: Digest
    interpreter_fingerprint: Digest
    executor_fingerprint: Digest
    module_loader: Literal['STATIC_ESM', 'NODE_STANDARD'] = Field(default='STATIC_ESM', exclude_if=lambda value: value == 'STATIC_ESM')
    package: NodePackagePlan | None = Field(default=None, exclude_if=lambda value: value is None)
    sqlite: tuple[SqliteDatabaseCapture, ...] = Field(default=(), max_length=4, exclude_if=lambda value: not value)
    sqlite_source_root: str | None = Field(default=None, max_length=32768, exclude_if=lambda value: value is None)

    @field_validator("entry")
    @classmethod
    def validate_entry(cls, value):
        RuntimeFile.safe_path(value)
        if not value.endswith(('.mjs', '.js', '.cjs')):
            raise ValueError('controlled Node entry must be JavaScript')
        return value

    @model_validator(mode="after")
    def validate_manifest(self):
        paths = tuple(item.relative_path for item in self.files)
        if paths != tuple(sorted(paths, key=lambda path: (path.casefold(), path))) or len({path.casefold() for path in paths}) != len(paths):
            raise ValueError("Node artifact paths must be sorted and unique")
        builds=self.package is not None and self.package.build_script is not None
        if (not builds and self.entry not in paths) or any(not path.endswith((".mjs", ".js", '.cjs', '.ts', '.tsx', '.jsx', '.mts', '.cts', ".json", ".html", ".css", ".svg")) for path in paths):
            raise ValueError("Node artifact has unsupported files or missing entry")
        if self.module_loader == 'STATIC_ESM' and (not self.entry.endswith('.mjs') or self.package is not None or self.sqlite):
            raise ValueError('standard runtime configuration requires the standard module loader')
        if self.package is not None and not {'package.json', self.package.lockfile}.issubset(paths):
            raise ValueError('npm runtime requires a frozen package and lockfile')
        if len({database.relative_path for database in self.sqlite}) != len(self.sqlite):
            raise ValueError('duplicate runtime database')
        if bool(self.sqlite) != bool(self.sqlite_source_root):
            raise ValueError('SQLite copy requires its authorized source root')
        if sum(item.size for item in self.files) > MAX_ARTIFACT_BYTES:
            raise ValueError("Node artifact exceeds byte budget")
        if self.source_fingerprint != runtime_source_fingerprint(self.files):
            raise ValueError("Node artifact source fingerprint mismatch")
        return self


class NodeRuntimeLoadRequest(RuntimeModel):
    schema_version: Literal["1"] = "1"
    load_id: str = Field(pattern=r"^rld_[0-9a-f]{32}$")
    project_id: ProjectId
    operation_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    control_session_id: str = Field(pattern=r"^rcs_[0-9a-f]{32}$")
    preview_fingerprint: Digest
    instance_id: InstanceId
    manifest_fingerprint: Digest
    source_fingerprint: Digest
    created_at_us: int = Field(ge=0)


# 仅作为跨进程回执中的实例事实；不能从目标自报端口或字符串声明构造。
class NodeRuntimeReference(RuntimeModel):
    mode: Literal["CONTROLLED_NODE_ESM"] = "CONTROLLED_NODE_ESM"
    project_id: ProjectId
    instance_id: InstanceId
    manifest_fingerprint: Digest
    source_fingerprint: Digest
    process_id: int = Field(gt=0)
    process_created_at: int = Field(gt=0)
    port: int = Field(ge=1024, le=65535)
    execution_fingerprint: Digest | None = Field(default=None,exclude_if=lambda value:value is None)


class NodeBuildArtifact(RuntimeModel):
    schema_version:Literal['1']='1'
    instance_id:InstanceId
    source_fingerprint:Digest
    files:tuple[RuntimeFile,...]=Field(min_length=1,max_length=512)

    @model_validator(mode='after')
    def finite_output(self):
        paths=tuple(item.relative_path for item in self.files)
        if len({value.casefold() for value in paths})!=len(paths) or sum(item.size for item in self.files)>MAX_ARTIFACT_BYTES:
            raise ValueError('build artifact exceeds its unique file budget')
        return self


class NodeRuntimeLoadReceipt(RuntimeModel):
    schema_version: Literal["1"] = "1"
    load_id: str = Field(pattern=r"^rld_[0-9a-f]{32}$")
    request_fingerprint: Digest
    reference: NodeRuntimeReference
    started_at_us: int = Field(ge=0)


class NodeRuntimeCorrespondence(RuntimeModel):
    reference: NodeRuntimeReference
    before: Literal['MATCHED','UNCONFIRMED']
    after: Literal['MATCHED','UNCONFIRMED']


def node_document_fingerprint(document: RuntimeModel) -> str:
    payload = json.dumps(document.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
