# 稳定权限预期与业务效果种类；枚举持久字符串不随执行链或 Python 责任位置改变。

from enum import StrEnum


class PermissionExpectation(StrEnum):
    ALLOW = "ALLOW"
    DENY = "DENY"


class BusinessEffectKind(StrEnum):
    STATE_MUTATION = "STATE_MUTATION"
    DATA_DISCLOSURE = "DATA_DISCLOSURE"
    OBJECT_CREATION = "OBJECT_CREATION"
    EXTERNAL_DISPATCH = "EXTERNAL_DISPATCH"
    RESTRICTED_FUNCTION_INVOCATION = "RESTRICTED_FUNCTION_INVOCATION"
    CREDENTIAL_ACCESS = "CREDENTIAL_ACCESS"


__all__ = ["BusinessEffectKind", "PermissionExpectation"]
