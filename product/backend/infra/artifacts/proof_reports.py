# 预检查报告按内容指纹持久保存；只有数据库发布的指纹可被查询，孤立文件没有采用资格。
import hashlib
import os
import re
from pathlib import Path

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.infra.artifacts.check_packages import reject_check_links, read_check_bytes
from product.protocols.proof_sources import ProofPreflightReport, proof_bytes


class ProofReportStore:
    def __init__(self, var_dir):
        self.root = Path(var_dir).resolve() / 'data' / 'proof-reports'

    def _path(self, digest):
        if re.fullmatch(r'[0-9a-f]{64}', digest) is None:
            raise JiejianError(ErrorCode.ARTIFACT_MANIFEST, '预检查报告引用无效')
        path = self.root / (digest + '.json')
        reject_check_links(self.root.parent, path)
        return path

    def save(self, report, *, known_secrets=()):
        raw = proof_bytes(report)
        if any(secret and secret.encode() in raw for secret in known_secrets):
            raise JiejianError(ErrorCode.STORAGE_SECRET, '预检查报告包含敏感内容')
        digest = hashlib.sha256(raw).hexdigest()
        path = self._path(digest)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with path.open('xb') as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
        except FileExistsError:
            if read_check_bytes(path, known_secrets=known_secrets) != raw:
                raise JiejianError(ErrorCode.ARTIFACT_MANIFEST, '已存在报告字节不一致') from None
        return digest

    def read(self, digest):
        raw = read_check_bytes(self._path(digest))
        if hashlib.sha256(raw).hexdigest() != digest:
            raise JiejianError(ErrorCode.ARTIFACT_MANIFEST, '预检查报告指纹不一致')
        return ProofPreflightReport.model_validate_json(raw)
