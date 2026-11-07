"""字段写入要求及其纯比较规则；缺失和 JSON null 是两种业务事实。"""
from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

FactScalar = (Annotated[str, Field(max_length=256)]
    | Annotated[int, Field(ge=-9_007_199_254_740_991, le=9_007_199_254_740_991)]
    | Annotated[float, Field(allow_inf_nan=False)] | bool | None)
FieldPath = Annotated[tuple[Annotated[str, Field(pattern=r'^[A-Za-z_][A-Za-z0-9_]{0,63}$')], ...],
    Field(min_length=1, max_length=8)]


class FieldMutationRequirement(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, strict=True, hide_input_in_errors=True)

    path: FieldPath
    operation: Literal['CHANGE', 'ASSIGN', 'ADD', 'REMOVE'] = 'CHANGE'
    expected_value: FactScalar = None

    @field_validator('path')
    @classmethod
    def public_business_field(cls, value):
        # 这些值属于秘密引用边界，不能通过业务效果配置写入公共协议。
        denied = {'password','passwd','cookie','authorization','token','accesstoken','refreshtoken','apikey','secret','clientsecret','privatekey','credential','credentials'}
        if any(part.casefold().replace('_','') in denied for part in value):
            raise ValueError('secret fields cannot be published as mutation effects')
        return value

    @model_validator(mode='after')
    def assignment_value(self):
        if self.operation in {'CHANGE', 'REMOVE'} and self.expected_value is not None:
            raise ValueError('only ASSIGN and ADD accept an expected value')
        return self


def same_scalar(left, right):
    """JSON 布尔值不能与数字互换；整数和等值有限浮点数属于同一数字值。"""
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    return left == right


def mutation_happened(requirement, before, after, *, before_present=True, after_present=True, expected_state=None):
    changed = before_present != after_present or (before_present and not same_scalar(before, after))
    if requirement is None:
        return changed and after_present and (expected_state is None or same_scalar(after, expected_state))
    if requirement.operation == 'REMOVE':
        return before_present and not after_present
    if requirement.operation == 'ADD':
        return not before_present and after_present and same_scalar(after, requirement.expected_value)
    if requirement.operation == 'ASSIGN':
        return changed and after_present and same_scalar(after, requirement.expected_value)
    return changed
