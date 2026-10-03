# 在内存中比较冻结的受保护字段，输出一次性密钥摘要与完整性；不发布原始业务数据。
import hashlib
import hmac
import json
from collections.abc import Mapping

from product.backend.core.verification.facts import DisclosureProof


def protected_projection(value, fields, *, require_present):
    projected, complete = {}, isinstance(value, Mapping)
    for path in fields:
        current = value
        for part in path.split("."):
            if not isinstance(current, Mapping) or part not in current:
                complete = complete and not require_present
                current = None
                break
            current = current[part]
        # 空值或脱敏占位不能证明某个受保护值存在，避免双侧占位相等形成确认。
        if require_present and (current is None or (isinstance(current, str) and current in ("[REDACTED]", "<redacted>"))):
            complete = False
        projected[path] = current
    return projected, complete


def disclosure_proof(*, owner, response, fields, key, marker):
    expected, owner_complete = protected_projection(owner, fields, require_present=True)
    observed, response_complete = protected_projection(response, fields, require_present=False)
    def digest(value):
        raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        return hmac.new(key, raw, hashlib.sha256).hexdigest()
    owner_digest, response_digest = digest(expected), digest(observed)
    complete = owner_complete and response_complete
    return DisclosureProof(projection_version="v1", projection_complete=complete,
        owner_digest=owner_digest, response_digest=response_digest,
        matched=complete and hmac.compare_digest(owner_digest, response_digest),
        correlation_digest=hashlib.sha256(marker.encode()).hexdigest())
