# 将持久已采用且仍有效的来源投影为现有检查注册端口；不在内存中制造持久事实。
from product.backend.workflows.checks.registry import CheckRuntimeRegistration,RegisteredCheckIdentity,RegisteredCheckProof,RegisteredResourceWindow
from product.protocols.observer import ObserverSpec,ObserverType,ObserverTarget,OwnerApiLocator,ObserverBudget,ObservationPhase


def runtime_registration(project_id, sources):
    if not sources:
        return None
    identities,proofs,windows = {},[],{}
    for source,request,effect,resource,binding in sources:
        for identity in request.identities:
            value = RegisteredCheckIdentity(identity_id=identity.identity_id,verification=identity.verification)
            if identity.identity_id in identities and identities[identity.identity_id] != value:
                # 同一账号的来源声明相互矛盾时，不能任选一个来验证实际身份。
                return None
            identities[identity.identity_id] = value
        observer_id = binding.observer_reference.observer_id
        spec = ObserverSpec(observer_id=observer_id,observer_type=ObserverType.OWNER_API,
            target=ObserverTarget(target_id=observer_id,locator=OwnerApiLocator(relative_path_template=source.config.relative_path_template),
                normalization_id='json_resource',normalization_version='1'),
            phases=(ObservationPhase.BEFORE,ObservationPhase.AFTER,ObservationPhase.EVENTUAL),required=True,
            budget=ObserverBudget(timeout_us=source.config.timeout_us,max_rows=1,max_bytes=source.config.max_response_bytes))
        proofs.append(RegisteredCheckProof(reference=binding.observer_reference,effect=effect,spec=spec,
            observation_identity_id=source.config.observation_identity_id,source_label='应用业务记录',
            source_location=source.config.relative_path_template.lstrip('/').replace('{resource_id}','resource'),
            closure_supported=True,resource_correlation_supported=True,exclusive_resource_window=False))
        windows[resource.binding_fingerprint] = RegisteredResourceWindow(binding_fingerprint=resource.binding_fingerprint,
            exclusive_resource_window=False)
    # 正式执行沿用用户已接受录制的目标范围与预算；预检查的较小请求预算不能扩大它。
    return CheckRuntimeRegistration(project_id=project_id,source_fingerprint=request.runtime_reference.source_fingerprint,
        identities=tuple(identities.values()),proofs=tuple(proofs),resource_windows=tuple(windows.values()))
