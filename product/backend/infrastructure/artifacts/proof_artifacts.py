# 有界私有参照文件存储；仅服务端生成的project/asset定位，禁止路径、符号链接及同名覆盖。
import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4
from product.backend.domain.errors import ErrorCode,JiejianError
from product.backend.infrastructure.artifacts.checks.check_packages import reject_check_links,read_check_bytes
from product.protocols.checks.business_facts import ArtifactManifestReference
from product.protocols.preparation.proof_sources import proof_bytes
from product.protocols.preparation.reference_capture import ReferenceCaptureReport


@dataclass(frozen=True)
class ProofArtifactContent:
    raw: bytes
    sha256: str


class ProofArtifactStore:
    def __init__(self,var_dir):self.root=Path(var_dir).resolve()/'data'/'proof-artifacts'

    def directory(self,project_id,asset_id):
        if not re.fullmatch(r'[a-z][a-z0-9_-]{0,63}',project_id) or not re.fullmatch(r'pai_[0-9a-f]{32}',asset_id):
            raise JiejianError(ErrorCode.ARTIFACT_MANIFEST,'参照文件引用无效')
        path=self.root/project_id/asset_id
        reject_check_links(self.root.parent,path)
        return path

    @staticmethod
    def accept(raw,known_secrets=()) -> ProofArtifactContent:
        if type(raw) is not bytes or not 0<len(raw)<=4194304:raise JiejianError(ErrorCode.STATE_PRECONDITION,'参照文件须非空且不超过4MiB')
        if any(secret and secret.encode() in raw for secret in known_secrets) or re.search(
            rb'(?i)(?:\bBearer\s+\S+|\b(?:password|passwd|token|secret|api[_-]?key)\s*[:=]\s*\S+)',raw):
            raise JiejianError(ErrorCode.STORAGE_SECRET,'参照文件含敏感内容，未保存')
        return ProofArtifactContent(raw=raw,sha256=hashlib.sha256(raw).hexdigest())

    def save(self,project_id,asset_id,content: ProofArtifactContent):
        # 接受结果仅在本次调用中传递；独立读盘仍核对当时的字节与秘密边界。
        raw=content.raw
        manifest=ArtifactManifestReference(asset_id=asset_id,size=len(raw),sha256=content.sha256)
        directory=self.directory(project_id,asset_id)
        directory.mkdir(parents=True,exist_ok=True)
        destination=directory/'artifact.bin'
        temporary=directory/(uuid4().hex+'.tmp')
        try:
            with temporary.open('xb') as stream:
                stream.write(raw);stream.flush();os.fsync(stream.fileno())
            try:os.link(temporary,destination)
            except FileExistsError:
                reject_check_links(self.root,destination)
                try:
                    with destination.open('rb') as stream:existing=stream.read(len(raw)+1)
                except OSError:
                    raise JiejianError(ErrorCode.ARTIFACT_MANIFEST,'参照文件无法核对') from None
                if existing!=raw:
                    raise JiejianError(ErrorCode.ARTIFACT_MANIFEST,'参照文件不可覆盖') from None
        finally:
            temporary.unlink(missing_ok=True)
        return manifest

    def read(self,project_id,manifest,*,known_secrets=()):
        path=self.directory(project_id,manifest.asset_id)/'artifact.bin'
        reject_check_links(self.root,path)
        try:
            if path.stat().st_size!=manifest.size:raise ValueError('size mismatch')
            with path.open('rb') as stream:raw=stream.read(4194305)
            content=self.accept(raw,known_secrets)
            if len(raw)!=manifest.size or content.sha256!=manifest.sha256:raise ValueError('digest mismatch')
            return raw
        except (OSError,ValueError):raise JiejianError(ErrorCode.ARTIFACT_MANIFEST,'参照文件无法核对') from None

    def remove_unreferenced(self,project_id,asset_id):
        """调用者须在写锁内重查全部引用；只删除这一私有输入，保留持久操作回执。"""
        path=self.directory(project_id,asset_id)/'artifact.bin'
        reject_check_links(self.root,path)
        path.unlink(missing_ok=True)


class CaptureReportStore:
    def __init__(self,var_dir):self.root=Path(var_dir).resolve()/'data'/'capture-reports'

    def path(self,digest):
        if not re.fullmatch(r'[0-9a-f]{64}',digest):raise JiejianError(ErrorCode.ARTIFACT_MANIFEST,'取样报告引用无效')
        path=self.root/(digest+'.json');reject_check_links(self.root.parent,path)
        return path

    def save(self,report,known_secrets=()):
        raw=proof_bytes(report)
        if any(secret and secret.encode() in raw for secret in known_secrets):raise JiejianError(ErrorCode.STORAGE_SECRET,'取样报告包含敏感内容')
        digest=hashlib.sha256(raw).hexdigest();path=self.path(digest)
        path.parent.mkdir(parents=True,exist_ok=True)
        try:
            with path.open('xb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
        except FileExistsError:
            if read_check_bytes(path)!=raw:raise JiejianError(ErrorCode.ARTIFACT_MANIFEST,'取样报告不可覆盖') from None
        return digest

    def read(self,digest):
        raw=read_check_bytes(self.path(digest))
        if hashlib.sha256(raw).hexdigest()!=digest:raise JiejianError(ErrorCode.ARTIFACT_MANIFEST,'取样报告指纹不一致')
        report=ReferenceCaptureReport.model_validate_json(raw,strict=True)
        if proof_bytes(report)!=raw:raise JiejianError(ErrorCode.ARTIFACT_MANIFEST,'取样报告格式不规范')
        return report

    def publication_path(self,capture_id):
        if not re.fullmatch(r'rpc_[0-9a-f]{32}',capture_id):raise JiejianError(ErrorCode.ARTIFACT_MANIFEST,'取样引用无效')
        path=self.root/'published'/(capture_id+'.json');reject_check_links(self.root.parent,path)
        return path

    def has_publication(self,capture_id):return self.publication_path(capture_id).is_file()

    def seal_publication(self,report):
        raw=proof_bytes(report);path=self.publication_path(report.capture_id)
        path.parent.mkdir(parents=True,exist_ok=True);temporary=path.with_name(uuid4().hex+'.tmp')
        try:
            with temporary.open('xb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
            try:os.link(temporary,path)
            except FileExistsError:
                if read_check_bytes(path)!=raw:raise JiejianError(ErrorCode.ARTIFACT_MANIFEST,'取样发布事实不可覆盖') from None
        finally:temporary.unlink(missing_ok=True)

    def publication(self,capture_id):
        raw=read_check_bytes(self.publication_path(capture_id))
        report=ReferenceCaptureReport.model_validate_json(raw,strict=True)
        if report.capture_id!=capture_id or proof_bytes(report)!=raw:raise JiejianError(ErrorCode.ARTIFACT_MANIFEST,'取样发布事实不可核对')
        return report
