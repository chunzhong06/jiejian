"""可交换的完整检查方案与环境绑定；旧规则选择仍由原 reader 接受。"""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from product.protocols.codec import content_hash, encode_json
from product.protocols.checks.execution_request import PermissionReference,ActorId,EffectId,IdentityId
from product.protocols.checks.scenarios import ScenarioReference


class RoutineValue(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, strict=True, hide_input_in_errors=True)


class RoutineScope(RoutineValue):
    permissions: tuple[PermissionReference, ...] = Field(default=(), max_length=4096, strict=False)
    scenario: ScenarioReference | None = None

    @model_validator(mode='after')
    def exact_scope(self):
        if bool(self.permissions) == (self.scenario is not None):
            raise ValueError('choose exact permissions or one scenario revision')
        keys = [(item.intent_id, item.revision, item.intent_hash) for item in self.permissions]
        if len(set(keys)) != len(keys):
            raise ValueError('duplicate permission reference')
        return self


class RoutineLimits(RoutineValue):
    # 请求、响应和秘密权限继续由所选环境控制；方案可进一步收紧总时长与用例数。
    max_duration_us: int = Field(default=300_000_000, ge=1_000_000, le=3_600_000_000)
    max_cases: int = Field(default=8192, ge=1, le=8192)


class RoutineActor(RoutineValue):
    actor_id: ActorId
    revision: int = Field(ge=1)


class RoutineAction(RoutineValue):
    action_id: str = Field(pattern=r'^bac_[0-9a-f]{32}$')
    revision: int = Field(ge=1)


class RoutineRequirement(RoutineValue):
    kind: Literal['ACCOUNT','RESOURCE','FLOW','PROOF']
    slot: str = Field(min_length=1,max_length=192)
    label: str = Field(min_length=1,max_length=512)
    minimum_count: int = Field(default=1,ge=1,le=8192)
    actor: RoutineActor | None = Field(default=None,exclude_if=lambda value:value is None)
    action: RoutineAction | None = Field(default=None,exclude_if=lambda value:value is None)
    effect_id: EffectId | None = Field(default=None,exclude_if=lambda value:value is None)
    normal_control_required: bool = False
    recovery_required: bool = False

    @model_validator(mode='after')
    def required_references(self):
        if (self.actor is not None)!=(self.kind in {'ACCOUNT','RESOURCE'}) or (self.action is not None)!=(self.kind!='ACCOUNT') or (self.effect_id is not None)!=(self.kind=='PROOF'):
            raise ValueError('logical requirement references')
        return self


class CheckRoutineDocument(RoutineValue):
    document_type: Literal['jiejian.check-routine'] = 'jiejian.check-routine'
    schema_version: Literal['2'] = '2'
    routine_id: str = Field(pattern=r'^csp_[0-9a-f]{32}$')
    project_id: str = Field(pattern=r'^[a-z][a-z0-9_-]{0,63}$')
    revision: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=80)
    scope: RoutineScope
    limits: RoutineLimits = RoutineLimits()
    requirements: tuple[RoutineRequirement,...] | None = Field(default=None,max_length=32768,exclude_if=lambda value:value is None)
    created_at_us: int = Field(ge=0)

    @property
    def fingerprint(self):
        return content_hash('CheckRoutine', self.model_dump(mode='json'))


class RoutineBoundAsset(RoutineValue):
    kind: Literal['ACCOUNT', 'RESOURCE', 'FLOW', 'PROOF']
    label: str = Field(min_length=1, max_length=768)
    slot: str = Field(min_length=1, max_length=192)
    reference: str = Field(min_length=1, max_length=256)
    fingerprint: str = Field(pattern=r'^[0-9a-f]{64}$')
    requirement_slot: str | None = Field(default=None,min_length=1,max_length=192,exclude_if=lambda value:value is None)
    owner_reference: IdentityId | None = Field(default=None,exclude_if=lambda value:value is None)


class RoutineBindingDocument(RoutineValue):
    document_type: Literal['jiejian.check-routine-binding'] = 'jiejian.check-routine-binding'
    schema_version: Literal['1'] = '1'
    binding_id: str = Field(pattern=r'^crb_[0-9a-f]{32}$')
    project_id: str = Field(pattern=r'^[a-z][a-z0-9_-]{0,63}$')
    routine_id: str = Field(pattern=r'^csp_[0-9a-f]{32}$')
    routine_revision: int = Field(ge=1)
    routine_fingerprint: str = Field(pattern=r'^[0-9a-f]{64}$')
    environment_id: str = Field(pattern=r'^env_[0-9a-f]{32}$')
    environment_revision: int = Field(ge=1)
    environment_fingerprint: str = Field(pattern=r'^[0-9a-f]{64}$')
    material_fingerprint: str = Field(pattern=r'^[0-9a-f]{64}$')
    assets: tuple[RoutineBoundAsset, ...] = Field(min_length=1, max_length=32768)
    created_at_us: int = Field(ge=0)

    @property
    def fingerprint(self):
        return content_hash('RoutineBinding', self.model_dump(mode='json'))


def read_routine(raw: bytes) -> CheckRoutineDocument:
    return _read(CheckRoutineDocument, raw, 1_048_576)


def read_routine_binding(raw: bytes) -> RoutineBindingDocument:
    return _read(RoutineBindingDocument, raw, 4_194_304)


def _read(model, raw, limit):
    if len(raw) > limit:
        raise ValueError('routine document budget')
    value = model.model_validate_json(raw)
    if not {'document_type', 'schema_version'} <= value.model_fields_set:
        raise ValueError('explicit routine document identity required')
    return value


def routine_bytes(value: CheckRoutineDocument | RoutineBindingDocument) -> bytes:
    return encode_json(value.model_dump(mode='json'))
