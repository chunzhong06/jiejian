# 定义检查身份与实际应用身份的绑定，不携带凭据正文。
from typing import Annotated, Literal
from pydantic import Field, model_validator
from product.protocols.checks.execution_request import WireModel, IdentityId, ActorId, Hash, LogicalId
from product.protocols.web.identity import BearerIdentityBinding, PreparedCookieSessionIdentityBinding
from product.protocols.web.request import HttpRequestTemplate, HttpBodyKind
SafeLabel = Annotated[str, Field(min_length=1, max_length=256)]

class CheckIdentityVerification(WireModel):
    namespace: LogicalId
    expected_application_subject_id: Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")]
    expected_actor_id: ActorId
    expected_actor_revision: int = Field(ge=1)
    request: HttpRequestTemplate
    subject_json_path: Annotated[str, Field(pattern=r"^\$(?:\.[A-Za-z_][A-Za-z0-9_]{0,63}){1,8}$")]

    @model_validator(mode="after")
    def validate_read_only(self):
        if self.request.method != "GET" or self.request.input_slots or self.request.body.kind is not HttpBodyKind.EMPTY:
            raise ValueError("identity verification must be a fixed readonly request")
        return self


class CheckIdentity(WireModel):
    identity_id: IdentityId
    actor_id: ActorId
    actor_revision: int = Field(ge=1)
    identity_fingerprint: Hash
    label: SafeLabel
    actor_label: SafeLabel
    binding: Annotated[BearerIdentityBinding | PreparedCookieSessionIdentityBinding, Field(discriminator="kind")]
    verification: CheckIdentityVerification | None = None

    @model_validator(mode="after")
    def validate_verification_actor(self):
        if self.verification is not None and (
            self.verification.expected_actor_id, self.verification.expected_actor_revision
        ) != (self.actor_id, self.actor_revision):
            raise ValueError("identity verification actor must match the frozen identity")
        return self
