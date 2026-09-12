# 默认验收的当前 API 机械链；仅消费公开控制面事实，不访问 Runner 私有工件或决定安全结论。
import hashlib
import json
from uuid import uuid4

from product.backend.core.boundary_proposal import BoundaryProposalBundle
from product.backend.workflows.business_boundaries.official_recipe import official_boundary_recipe


def _error(message):
    from .official import SampleTestError
    raise SampleTestError(message)


def _digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _boundary(client, project):
    return client.call("GET", f"/api/projects/{project}/business-boundaries")


def _policy(boundary):
    return boundary["policy_epoch"], _digest(sorted(boundary["permission_intents"], key=lambda item: item["intent_id"]))


def _proposal(payload, project):
    proposal = BoundaryProposalBundle.model_validate_json(json.dumps(payload["proposal"]))
    if proposal.project_id != project or proposal.unresolved_questions:
        _error("SAMPLE_PROPOSAL_SCOPE_INVALID")
    return proposal


def assert_official_proposal(payload, project):
    """批准前精确核对冻结配方；实现来源可来自当前发现，不能改变任何业务定义。"""
    proposal = _proposal(payload, project)
    recipe = official_boundary_recipe().proposal_command
    for name in ("proposed_actors", "proposed_actions", "proposed_permissions"):
        actual = [item.model_dump(mode="json", exclude={"source_candidate_ids"}) for item in getattr(proposal, name)]
        expected = [item.model_dump(mode="json", exclude={"source_candidate_ids"}) for item in getattr(recipe, name)]
        if actual != expected:
            _error("SAMPLE_PROPOSAL_RECIPE_MISMATCH")
    return proposal


def _approve(client, project, proposal):
    return client.call("POST", f"/api/projects/{project}/business-boundaries/proposals/{proposal.proposal_id}/approve",
        {"schema_version": "1", "expected_fingerprint": proposal.proposal_fingerprint, "reason": "确认本次受控官方示例的冻结配方或纯实现重绑"})


def _assert_rebind(proposal, boundary):
    """只允许已存在实体的 REFERENCE，逐字段核对旧业务与Permission，拒绝语义追加。"""
    actors = {item["actor_id"]: item for item in boundary["actors"]}
    actions = {item["action_id"]: item for item in boundary["actions"]}
    permissions = {item["intent_id"]: item for item in boundary["permission_intents"]}
    if (len(proposal.proposed_actors), len(proposal.proposed_actions), len(proposal.proposed_permissions)) != (len(actors), len(actions), len(permissions)):
        _error("SAMPLE_REBIND_SEMANTICS_CHANGED")
    actor_refs, action_refs, effect_refs = {}, {}, {}
    for item in proposal.proposed_actors:
        old = actors.get(item.actor_id)
        if item.write_mode != "REFERENCE" or old is None or item.expected_current_revision != old["revision"] or any(
            getattr(item, field) != old[field] for field in ("display_name", "description", "effective_state")):
            _error("SAMPLE_REBIND_SEMANTICS_CHANGED")
        actor_refs[item.item_id] = item.actor_id
    for item in proposal.proposed_actions:
        old = actions.get(item.action_id)
        if item.write_mode != "REFERENCE" or old is None or item.expected_current_revision != old["revision"] or any(
            getattr(item, field) != old[field] for field in ("display_name", "description", "primary_resource_concept", "operation_kind", "state_changing", "effective_state")):
            _error("SAMPLE_REBIND_SEMANTICS_CHANGED")
        actual_effects = sorted((effect.model_dump(mode="json", exclude={"item_id"}) for effect in item.effect_catalog), key=lambda effect: effect["effect_id"])
        if actual_effects != sorted(old["effect_catalog"], key=lambda effect: effect["effect_id"]):
            _error("SAMPLE_REBIND_EFFECT_CHANGED")
        effect_refs.update({effect.item_id: effect.effect_id for effect in item.effect_catalog})
        action_refs[item.item_id] = item.action_id
    for item in proposal.proposed_permissions:
        old = permissions.get(item.intent_id)
        if item.write_mode != "REFERENCE" or old is None or item.expected_current_revision != old["revision"]:
            _error("SAMPLE_REBIND_PERMISSION_CHANGED")
        values = dict(subject_actor_id=actor_refs[item.subject_actor_item_id], resource_owner_actor_id=actor_refs[item.resource_owner_actor_item_id],
            business_action_id=action_refs[item.business_action_item_id], expectation=item.expectation.value, relation=item.relation.value,
            effective_state=item.effective_state.value, protected_effect_ids=sorted(effect_refs[key] for key in item.protected_effect_item_ids))
        if any(old[name] != value for name, value in values.items()):
            _error("SAMPLE_REBIND_PERMISSION_CHANGED")


def prepare_current(client, project, *, initial=False, gui=None):
    before_runs = project_run_ids(client, project)
    if initial:
        proposal = assert_official_proposal(gui.propose() if gui is not None else client.call("POST", "/api/experience/official-sample/boundary-proposal"), project)
        gui.approve(project, proposal) if gui is not None else _approve(client, project, proposal)
    before = _boundary(client, project)
    # 普通准备页由 Workspace 门禁驱动；先按公开绑定状态复核，不能先失败一次 prepare 探测流程。
    if any(binding["status"] != "CURRENT" for kind in ("actor_bindings", "action_bindings") for binding in before[kind]):
        prefix = f"/api/projects/{project}/business-boundaries"
        draft = client.call("GET", prefix + "/maintenance-draft")
        proposal = _proposal(gui.maintenance(project) if gui is not None else client.call("POST", prefix + "/maintenance-proposals", {
            "schema_version": "1", "expected_boundary_state_fingerprint": draft["boundary_state_fingerprint"],
            "actors": draft["actors"], "actions": draft["actions"], "permissions": draft["permissions"],
            "provenance": "复核本次受控示例的当前实现映射"}, accepted=(201,)), project)
        _assert_rebind(proposal, before)
        gui.approve(project, proposal) if gui is not None else _approve(client, project, proposal)
    prepared = gui.prepare() if gui is not None else client.call("POST", "/api/experience/official-sample/prepare")
    if not prepared.get("scenario_prepared"):
        materials = client.call("GET", f"/api/projects/{project}/preparation")
        preview = client.call("GET", f"/api/projects/{project}/check-preview")
        # Sample 的安装标记不是普通准备真源；只接受同项目确实仍齐备且可执行的现有材料。
        if (materials.get("project_id") != project or materials.get("preparation_complete") is not True
                or preview.get("project_id") != project or preview.get("can_execute") is not True):
            _error("SAMPLE_PREPARATION_INCOMPLETE: " + str(prepared.get("pending_tasks", [])))
    if _policy(_boundary(client, project)) != _policy(before) or project_run_ids(client, project) != before_runs:
        _error("SAMPLE_PREPARATION_CHANGED_POLICY_OR_RUNS")
    return prepared


def project_run_ids(client, project):
    return [item["run"]["run_id"] for item in client.call("GET", f"/api/projects/{project}/runs")]


def switch_current(client, project, version, *, reference=None, gui=None):
    before = project_run_ids(client, project)
    status = gui.switch(version, reference) if gui is not None else client.call("POST", "/api/experience/official-sample/version", {
        "schema_version": "1", "version": version, "repair_reference": reference})
    if status.get("scenario_version") != version or project_run_ids(client, project) != before:
        _error("SAMPLE_SWITCH_INVALID")
    return status


def wait_published(client, run_id, job_id):
    from .official import _wait_for
    status = _wait_for(lambda: client.call("GET", f"/api/runs/{run_id}"),
        lambda item: item.get("result_integrity") in {"VALID", "INVALID"} or item.get("run", {}).get("lifecycle") in {"FAILED", "CANCELLED", "SAFETY_STOPPED"},
        timeout=180, label="当前Run发布")
    if status.get("result_integrity") != "VALID" or status.get("run", {}).get("lifecycle") != "COMPLETED":
        _error(f"L5_RUN_RESULT_UNAVAILABLE: lifecycle={status.get('run', {}).get('lifecycle')} integrity={status.get('result_integrity')} run_id={run_id} run_job_id={job_id}")
    return status


def read_result(client, run_id):
    story = client.call("GET", f"/api/runs/{run_id}/result-story")
    index = client.call("GET", f"/api/runs/{run_id}/evidence")
    evidence = [client.call("GET", f"/api/runs/{run_id}/evidence/{item['evidence_id']}") for item in index]
    if len(evidence) != len(index) or any(item["run_id"] != run_id for item in evidence):
        _error("SAMPLE_EVIDENCE_RUN_MISMATCH")
    refs = {item["evidence_id"] for item in evidence}
    for action in story["actions"]:
        for explanation in action["evidence_explanations"]:
            if not set(explanation["evidence_refs"]).issubset(refs):
                _error("SAMPLE_STORY_EVIDENCE_MISMATCH")
    return {"run_id": run_id, "story": story, "evidence_index": index, "evidence": evidence}


def run_current(client, project, state, *, name, expected, change_id=None, gui=None):
    query = "" if change_id is None else "?change_id=" + change_id
    preview = client.call("GET", f"/api/projects/{project}/check-preview" + query)
    if not preview.get("can_execute") or preview.get("action_count") != 2 or preview.get("case_count") != 3:
        _error("SAMPLE_FULL_PLAN_UNAVAILABLE")
    body = {"schema_version": "2", "expected_plan_fingerprint": preview["plan_fingerprint"],
        "idempotency_key": "sample-" + name + "-" + uuid4().hex, "change_id": change_id}
    prior_runs = set(project_run_ids(client, project)) if gui is not None else set()
    try:
        submitted = gui.submit(project, body, change_id, require_repair=name == "fixed") if gui is not None else client.call("POST", f"/api/projects/{project}/runs", body, accepted=(202,))
    except Exception as exc:
        if gui is not None:
            # GUI写入回执未知只定位本轮新增Run供精确清理，不用API再提交第二轮。
            added = set(project_run_ids(client, project)) - prior_runs
            if len(added) == 1:
                state.active_run_id = added.pop()
                current = client.call("GET", f"/api/runs/{state.active_run_id}")
                state.active_run_job_id = (current.get("job") or {}).get("job_id")
            raise
        if "无法访问" not in str(exc):
            raise
        # 回执未知先回读当前事实，再仅用原key重取幂等回执，不生成另一轮请求。
        client.call("GET", f"/api/projects/{project}/runs")
        submitted = client.call("POST", f"/api/projects/{project}/runs", body, accepted=(202,))
    run_id, job_id = submitted["run"]["run_id"], submitted["job"]["job_id"]
    state.active_run_id, state.active_run_job_id = run_id, job_id
    wait_published(client, run_id, job_id)
    result = read_result(client, run_id)
    assert_current_result(result, expected=expected)
    state.active_run_id = state.active_run_job_id = None
    return result


def assert_current_result(result, *, expected):
    run_id = result["run_id"]
    if len(result["evidence"]) != 3 or len(result["story"]["actions"]) != 3:
        _error("SAMPLE_PUBLISHED_CASES_INCOMPLETE")
    if result["story"]["verdict"] != expected:
        _error("SAMPLE_RUN_VERDICT_MISMATCH: " + json.dumps({"run_id": run_id, "expected": expected, "actual": result["story"]["verdict"]}))
    for action in result["story"]["actions"]:
        if action["permission"]["expectation"] == "DENY":
            roles = {item["source_location"]: item["observed_fact"]["level"] for item in action["evidence_explanations"]}
            expected_roles = {"observer/" + kind: "VERDICT_REQUIRED" if kind == "azure_blob_object" else "DIAGNOSIS_REQUIRED" if kind == "structured_audit_log" else "SUPPORTING"
                for kind in ("owner_api", "read_only_sqlite", "structured_audit_log", "async_task_status", "azure_queue_peek", "azure_blob_object")}
            if roles != expected_roles:
                _error("SAMPLE_SOURCE_RESPONSIBILITY_MISMATCH")
    for document in result["evidence"]:
        case = document["case"]
        if len(case["protected_effect_ids"]) != 1:
            _error("SAMPLE_EFFECT_SCOPE_MISMATCH")
        if case["permission"]["expectation"] == "DENY":
            sources = {item["observer_id"]: item["level"] for item in document["observations"]}
            if len(sources) != 6 or list(sources.values()).count("VERDICT_REQUIRED") != 1 or list(sources.values()).count("DIAGNOSIS_REQUIRED") != 1:
                _error("SAMPLE_SIX_SOURCE_ROLES_MISMATCH")

    normal = [item for item in result["evidence"] if item["case"]["permission"]["expectation"] == "ALLOW"]
    if len(normal) != 2:
        _error("SAMPLE_NORMAL_BUSINESS_MISSING")
    if expected != "INCONCLUSIVE":
        for document in normal:
            outcome = document["outcome"]
            if outcome["execution_outcome"] != "ACCEPTED" or outcome["actual_identity_status"] != "MATCH" or not all(
                outcome[name] for name in ("baseline_trusted", "recovery_verified", "run_correlated", "resource_correlated")):
                _error("SAMPLE_NORMAL_BUSINESS_UNTRUSTED")
            for proof in document["case"]["proof_requirements"]:
                if proof["level"] == "VERDICT_REQUIRED" and not any(observation["proof_fingerprint"] == proof["proof_fingerprint"]
                    and observation["phase"] in {"AFTER", "EVENTUAL"} and observation["state"] == "CONFIRMED"
                    and all(observation[name] for name in ("complete", "reliable", "correlated", "authoritative"))
                    for observation in document["observations"]):
                    _error("SAMPLE_NORMAL_EFFECT_NOT_CONFIRMED")


def run_sequence(client, project, state, *, checkpoint, gui=None):
    ui = {} if gui is None else {"gui": gui}
    policy = _policy(_boundary(client, project))
    first = run_current(client, project, state, name="problem", expected="BLOCK", **ui)
    deny = next(action for action in first["story"]["actions"] if action["permission"]["expectation"] == "DENY")
    if (deny.get("breakpoint") or {}).get("breakpoint_type") != "AUTHORIZATION_LATE":
        _error("SAMPLE_CAUSAL_BREAKPOINT_MISMATCH")
    checkpoint("problem-result", first)
    contracts = client.call("GET", f"/api/runs/{first['run_id']}/repair-contracts")
    matches = [item for item in contracts if item["source_case_id"] == deny["case_id"]]
    if len(matches) != 1:
        _error("SAMPLE_ORIGINAL_REPAIR_AMBIGUOUS")
    contract = matches[0]
    reference = {name: contract[name] for name in ("source_run_id", "source_case_id", "repair_fingerprint")}
    frozen_first = _digest(first)
    limited_status = switch_current(client, project, "EVIDENCE_LIMITED", **ui)
    prepare_current(client, project, **ui)
    checkpoint("limited-ready", limited_status)
    limited = run_current(client, project, state, name="limited", expected="INCONCLUSIVE", change_id=limited_status["vulnerable_change_id"], **ui)
    checkpoint("limited-result", limited)
    fixed_status = switch_current(client, project, "FIXED", reference=reference, **ui)
    prepare_current(client, project, **ui)
    checkpoint("fixed-ready", fixed_status)
    fixed = run_current(client, project, state, name="fixed", expected="PASS", change_id=fixed_status["repair_change_id"], **ui)
    verification = fixed["story"].get("repair_verification") or {}
    repair = client.call("GET", f"/api/projects/{project}/repair")
    if verification.get("status") != "VERIFIED" or verification.get("source_run_id") != first["run_id"] or verification.get("repair_reference") != reference["repair_fingerprint"] or repair.get("status") != "VERIFIED":
        _error("SAMPLE_ORIGINAL_REPAIR_NOT_VERIFIED")
    if _policy(_boundary(client, project)) != policy or _digest(read_result(client, first["run_id"])) != frozen_first:
        _error("SAMPLE_ORIGINAL_FACTS_CHANGED")
    runs = [first, limited, fixed]
    ids = {item["run_id"] for item in runs}
    if len(ids) != 3 or set(project_run_ids(client, project)) != ids:
        _error("SAMPLE_NEW_RUN_HISTORY_MISMATCH")
    for item in runs:
        if _digest(read_result(client, item["run_id"])) != _digest(item):
            _error("SAMPLE_PUBLISHED_HISTORY_CHANGED")
    checkpoint("fixed-result", fixed)
    return runs
