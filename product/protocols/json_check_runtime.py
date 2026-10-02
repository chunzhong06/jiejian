# CHECK运行格式4冻结普通JSON来源，旧1/2/3保持各自reader与字节，不从当前配置补齐历史。
from typing import Literal
from pydantic import Field,model_validator
from product.protocols.check_runtime import NodeCheckRuntimeBundle
from product.protocols.proof_sources import FrozenJsonProofSource,proof_fingerprint


class JsonCheckRuntimeBundle(NodeCheckRuntimeBundle):
    schema_version:Literal['4']='4'
    json_sources:tuple[FrozenJsonProofSource,...]=Field(min_length=1,max_length=256)

    @model_validator(mode='after')
    def source_coverage(self):
        if len({source.source_id for source in self.json_sources}) != len(self.json_sources):
            raise ValueError('duplicate JSON source')
        proofs = {(action.action_id,proof.effect_id):proof for action in self.actions for proof in action.proofs}
        actions = {action.action_id:action for action in self.actions}
        identities = {item.identity_id:item for item in self.identities}
        for source in self.json_sources:
            config = source.config
            if (self.schema_version == '4') != (config.source_kind == 'JSON_HTTP_RESOURCE'):
                raise ValueError('proof source does not match frozen runtime version')
            proof = proofs.get((config.action_id,config.effect_id))
            if (source.source_fingerprint != proof_fingerprint(config) or proof is None
                    or actions[config.action_id].action_revision != config.action_revision
                    or proof.rule != 'REGISTERED_EFFECT' or proof.descriptor_fingerprint != source.source_fingerprint
                    or proof.observer_id != 'json_' + source.source_id[4:]
                    or proof.observation_identity_id != config.observation_identity_id
                    or proof.effect_kind != source.contract.approved_effect_kind
                    or source.contract.contract_id != config.source_contract_id
                    or not set(source.identity_roles) <= set(identities)):
                raise ValueError('JSON proof association mismatch')
            for claim in config.identity_claims:
                identity = identities.get(claim.identity_id)
                if (identity is None or identity.verification is None
                        or identity.verification.expected_application_subject_id != claim.application_subject_id):
                    raise ValueError('JSON identity association mismatch')
        return self


class ManagedCheckRuntimeBundle(JsonCheckRuntimeBundle):
    """格式 5 冻结通用记录来源；格式 4 的已发布输入不补入新信任语义。"""
    schema_version:Literal['5']='5'
