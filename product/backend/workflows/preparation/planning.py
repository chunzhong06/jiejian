# 将现场准备检查与当前绑定按指纹相交，装配纯计划；不执行请求或读取认证秘密。
from product.backend.core.check_plan import PreparedActionInput, PreparedIdentityAssignment, compile_project_check_plan
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.workflows.preparation.models import PreparationStatus
from product.backend.workflows.recording.source import identity_source_fingerprint


def current_plan(service, project_id, *, engine_version, config_fingerprint):
    if service._uow_factory is None:
        raise JiejianError(ErrorCode.STATE_PRECONDITION, "准备服务未装配")
    view = service.get(project_id)
    prepared = {item.action_id: item for item in view.actions}
    inputs = []
    with service._uow_factory() as work:
        boundary = service._business_boundaries.view(project_id, work=work)
        understanding = work.application_understanding.get(project_id)
        if understanding is None or understanding.source_fingerprint is None:
            raise JiejianError(ErrorCode.STATE_PRECONDITION, "准备来源已变化")
        repository = work.action_preparation
        for action in boundary.actions:
            item = prepared.get(action.action_id)
            if item is None or item.action_revision != action.revision:
                raise JiejianError(ErrorCode.STATE_PRECONDITION, "准备来源已变化")
            # 再次读取正式事实，防止前一个只读检查与快照装配之间权限发生漂移。
            permissions = tuple(p for p in boundary.permission_intents if p.business_action_id == action.action_id)
            from product.backend.core.assurance import compile_action_assurance
            contract = compile_action_assurance(action, permissions, repository.allow_controls(project_id))
            if contract.fingerprint != item.assurance_contract_fingerprint:
                raise JiejianError(ErrorCode.STATE_PRECONDITION, "准备来源已变化")
            # 在装配事务内重新检查技术来源，避免将先前 GET 的 SATISFIED 与新源码事实混用。
            technical = (service._bindings.inspect(action, contract, item.identity_requirements, work=work)
                         if service._bindings is not None else item)
            identities = []
            for slot in item.identity_requirements.slots:
                if slot.status is not PreparationStatus.SATISFIED:
                    continue
                record = work.test_identities.get(slot.test_identity_id)
                if record is not None and record.prepared_at_us is not None:
                    identities.append(PreparedIdentityAssignment(slot_id=slot.requirement.slot_id,
                        identity_id=record.identity_id, actor_id=record.actor_id, actor_revision=record.actor_revision,
                        identity_fingerprint=identity_source_fingerprint(record)))

            def checked(binding, status):
                return binding if (binding is not None and status.status is PreparationStatus.SATISFIED
                    and binding.binding_fingerprint == status.binding_fingerprint) else None

            execution = checked(repository.execution(action.action_id, action.revision), technical.execution)
            resources = tuple(binding for status in technical.resources if status.owner_test_identity_id is not None
                if (binding := checked(repository.resource(action.action_id, action.revision,
                    status.owner_test_identity_id), status)) is not None)
            evidence = tuple(binding for status in technical.effect_evidence
                if (binding := checked(repository.evidence(action.action_id, action.revision, status.effect_id), status)) is not None)
            recovery = checked(repository.recovery(action.action_id, action.revision), technical.recovery)
            capabilities = () if service._bindings is None else service._bindings.proof_capabilities(project_id, evidence)
            inputs.append(PreparedActionInput(action=action, permissions=permissions, assurance=contract,
                identities=tuple(identities), execution=execution, resources=resources, evidence=evidence,
                recovery=recovery, observer_capabilities=capabilities, reason_codes=tuple(dict.fromkeys((
                    *item.reason_codes, *(reason for status in (technical.execution, *technical.resources,
                        *technical.effect_evidence, technical.recovery) for reason in status.reason_codes))))))
        return compile_project_check_plan(project_id, source_fingerprint=understanding.source_fingerprint,
            policy_epoch=boundary.policy_epoch, engine_version=engine_version,
            config_fingerprint=config_fingerprint, actions=tuple(inputs))
