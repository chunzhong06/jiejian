# 生成受控本地 HTTP 检查配置；测试身份只使用环境引用，不写真实凭据。
import json

from product.protocols.check_runtime import CheckRuntimeBundle


def runtime_bundle(*, port=8765):
    request = dict(method="GET", path="/objects/{resource}", input_slots=[
        dict(slot_id="resource", source="CASE_RESOURCE_ID", consumer="PATH")])
    actor = "bar_" + "1" * 32
    identity = "tid_" + "1" * 32
    payload = dict(project_id="test", source_fingerprint="b" * 64,
        target=dict(base_url=f"http://127.0.0.1:{port}", allowed_origins=[f"http://127.0.0.1:{port}"],
            allowed_hosts=["127.0.0.1"], allowed_ports=[port], allow_private_network=True),
        budget=dict(max_requests=64, request_timeout_us=5_000_000, max_duration_us=300_000_000,
            max_response_bytes=262_144, max_cases=64, recovery_reserve_requests=4),
        identities=[dict(identity_id=identity, actor_id=actor, actor_revision=1, identity_fingerprint="1" * 64,
            label="Test identity", actor_label="Reader", binding=dict(kind="BEARER", secret_ref="env:CHECK_TEST_BEARER"),
            verification=dict(namespace="app", expected_application_subject_id="subject-1", expected_actor_id=actor,
                expected_actor_revision=1, request=dict(method="GET", path="/identity"), subject_json_path="$.subject_id"))],
        actions=[dict(action_id="bac_" + "1" * 32, action_revision=1, action_semantic_fingerprint="a" * 64, display_name="Read object", primary_resource_concept="Object", state_changing=False,
            flow_id="test-flow", flow_sha256="e" * 64, execution_binding_fingerprint="f" * 64,
            steps=[dict(step_id="target", purpose="TARGET", request=request, depends_on_step_ids=[],
                classifier=dict(accepted=[dict(kind="STATUS_IN", statuses=[200])], denied=[dict(kind="STATUS_IN", statuses=[403])]))],
            proofs=[dict(effect_id="bef_" + "1" * 32, effect_kind="OBJECT_CREATION", binding_fingerprint="d" * 64, rule="HTTP_RESOURCE_PRESENCE",
                business_label="Object created", resource_concept="Object",
                observation_identity_id=identity, request=request, source_label="Object endpoint",
                source_location="provider/object", exclusive_resource_window=True)])])
    return CheckRuntimeBundle.model_validate_json(json.dumps(payload), strict=True)
