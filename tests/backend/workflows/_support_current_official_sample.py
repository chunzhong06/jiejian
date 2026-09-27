# 所属业务域的共享测试构造器；不导入测试用例。

def prepare_sample(core):
    project = core.official_experience.start(consent=True).project_id
    proposal = core.official_experience.boundary_proposal()
    core.business_boundaries.approve(project, proposal.proposal.proposal_id,
        expected_fingerprint=proposal.proposal.proposal_fingerprint, reason="测试用户确认公开业务规则")
    assert core.official_experience.prepare().scenario_prepared
    return project

def prepare_changed_sample(core, project):
    from product.backend.workflows.business_boundaries.models import BoundaryMaintenanceCommand
    current = core.official_experience.prepare()
    if "HUMAN_IMPLEMENTATION_REBIND_REQUIRED" in current.pending_tasks:
        draft = core.business_boundaries.maintenance_draft(project)
        proposal = core.business_boundaries.create_maintenance_proposal(project, BoundaryMaintenanceCommand(
            expected_boundary_state_fingerprint=draft.boundary_state_fingerprint, actors=draft.actors,
            actions=draft.actions, permissions=draft.permissions, provenance="测试用户复核当前实现映射"))
        core.business_boundaries.approve(project, proposal.proposal.proposal_id,
            expected_fingerprint=proposal.proposal.proposal_fingerprint, reason="仅复核当前实现，不改业务规则")
        current = core.official_experience.prepare()
    assert current.scenario_prepared, current.pending_tasks
