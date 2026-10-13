# CHECK运行格式4冻结普通JSON来源，旧1/2/3保持各自reader与字节，不从当前配置补齐历史。
from typing import Literal
from pydantic import Field,model_validator
from product.protocols.checks.check_runtime import NodeCheckRuntimeBundle,CheckProofConfig,CheckActionConfig
from product.protocols.preparation.proof_sources import FrozenJsonProofSource, FrozenProofSource, proof_fingerprint
from product.protocols.web.response import ResponseExtractor
from product.protocols.web.request import ValueSlotSource


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


class CurrentCheckProofConfig(CheckProofConfig):
    effect_kind:Literal['STATE_MUTATION','DATA_DISCLOSURE','OBJECT_CREATION','EXTERNAL_DISPATCH',
        'RESTRICTED_FUNCTION_INVOCATION','CREDENTIAL_ACCESS','FILE_CONTENT_DELIVERY']


class CurrentCheckActionConfig(CheckActionConfig):
    proofs:tuple[CurrentCheckProofConfig,...]=Field(min_length=1,max_length=48)


# 当前证明与旧JSON/记录根并列；不继承旧版本只能解释内部步骤的隐含标准。
class ProofCheckRuntimeBundle(NodeCheckRuntimeBundle):
    schema_version:Literal['6']='6'
    actions:tuple[CurrentCheckActionConfig,...]=Field(min_length=1,max_length=512)
    json_sources:tuple[FrozenProofSource,...]=Field(min_length=1,max_length=256)

    @model_validator(mode='after')
    def proof_coverage(self):
        if len({source.source_id for source in self.json_sources})!=len(self.json_sources):
            raise ValueError('duplicate proof source')
        proofs={(action.action_id,proof.effect_id):proof for action in self.actions for proof in action.proofs}
        actions={action.action_id:action for action in self.actions}
        identities={item.identity_id:item for item in self.identities}
        for source in self.json_sources:
            config=source.config
            if self.schema_version=='6' and config.source_kind=='CREATED_OBJECT_RECORDS':
                raise ValueError('creation source requires runtime 7')
            proof=proofs.get((config.action_id,config.effect_id))
            if (source.source_fingerprint!=proof_fingerprint(config) or proof is None
                or actions[config.action_id].action_revision!=config.action_revision
                or proof.rule!='REGISTERED_EFFECT' or proof.descriptor_fingerprint!=source.source_fingerprint
                or proof.observer_id!='json_'+source.source_id[4:]
                or proof.observation_identity_id!=config.observation_identity_id
                or proof.effect_kind!=source.contract.approved_effect_kind
                or source.contract.contract_id!=config.source_contract_id
                or set(source.identity_roles)!={claim.identity_id for claim in config.identity_claims}
                or not set(source.identity_roles)<=set(identities)):
                raise ValueError('proof association mismatch')
            for claim in config.identity_claims:
                identity=identities.get(claim.identity_id)
                if (identity is None or identity.verification is None
                    or identity.verification.expected_application_subject_id!=claim.application_subject_id):
                    raise ValueError('proof identity association mismatch')
        return self


class CreationCheckActionConfig(CurrentCheckActionConfig):
    created_resource:ResponseExtractor|None=None

    @model_validator(mode='after')
    def output_resource(self):
        if self.created_resource is None:
            return self
        target=next(step for step in self.steps if step.purpose=='TARGET')
        if (not self.state_changing or self.recovery is None
                or self.created_resource not in target.request.response_extractors
                or self.created_resource.extractor_id!='created_resource_id'
                or self.created_resource.kind not in {'JSON_PATH','LOCATION'} or self.created_resource.secret
                or any(slot.source is ValueSlotSource.CASE_RESOURCE_ID for step in self.steps for slot in step.request.input_slots)
                or any(proof.effect_kind!='OBJECT_CREATION' or proof.rule!='REGISTERED_EFFECT' or proof.auxiliary_sources for proof in self.proofs)):
            raise ValueError('creation flow requires exact output, creation proof and recovery')
        return self


class CreationCheckRuntimeBundle(ProofCheckRuntimeBundle):
    schema_version:Literal['7']='7'
    actions:tuple[CreationCheckActionConfig,...]=Field(min_length=1,max_length=512)

    @model_validator(mode='after')
    def creation_sources(self):
        sources={'json_'+source.source_id[4:]:source for source in self.json_sources}
        for action in self.actions:
            for proof in action.proofs:
                source=sources.get(proof.observer_id)
                created=source is not None and source.config.source_kind=='CREATED_OBJECT_RECORDS'
                if (action.created_resource is not None)!=created:
                    raise ValueError('creation action requires adopted collection proof')
        if not any(action.created_resource is not None for action in self.actions):
            raise ValueError('creation runtime needs a creation action')
        return self
