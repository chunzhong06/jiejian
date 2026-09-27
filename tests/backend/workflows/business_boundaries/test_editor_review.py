# 验证编辑快照和原始提案对照，防止后来修订污染历史审阅。
from pathlib import Path

import pytest

from tests.backend.workflows.business_boundaries._support_business_boundary_service import (
    _core, _create_proposal, _maintenance_command,
)

pytestmark = [pytest.mark.database, pytest.mark.essential]


def test_editor_uses_one_uow_and_returns_pending_summary(tmp_path: Path):
    core, project_id = _core(tmp_path)
    try:
        proposal = _create_proposal(core, project_id)
        factory = core.business_boundaries._uow_factory
        calls = []
        def counted(*args, **kwargs):
            calls.append(True)
            return factory(*args, **kwargs)
        core.business_boundaries._uow_factory = counted
        editor = core.business_boundaries.editor(project_id)
        assert len(calls) == 1
        assert editor.maintenance_draft is None
        assert editor.boundary_state_fingerprint is None
        assert editor.pending_proposals[0].proposal_id == proposal.proposal_id
        assert "proposal" not in editor.pending_proposals[0].model_dump()
        core.business_boundaries.approve(project_id, proposal.proposal_id,
            expected_fingerprint=proposal.proposal_fingerprint, reason="确认首次边界")
        editor = core.business_boundaries.editor(project_id)
        assert editor.maintenance_draft is not None
        assert editor.boundary_state_fingerprint == editor.maintenance_draft.boundary_state_fingerprint
        assert editor.pending_proposals == ()
    finally:
        core.close()


def test_proposal_before_remains_original_after_approval(tmp_path: Path):
    core, project_id = _core(tmp_path)
    try:
        initial = _create_proposal(core, project_id)
        core.business_boundaries.approve(project_id, initial.proposal_id,
            expected_fingerprint=initial.proposal_fingerprint, reason="初始规则")
        draft = core.business_boundaries.maintenance_draft(project_id)
        action = draft.actions[0]
        updated = action.model_copy(update={"display_name": "新的导出名称", "description": "新的业务说明"})
        created = core.business_boundaries.create_maintenance_proposal(project_id,
            _maintenance_command(draft, actions=(updated,)))
        original_review = created.review
        assert original_review is not None and original_review.basis_state == "COMPLETE"
        item = next(i for i in original_review.items if i.entity_kind == "ACTION")
        assert item.before.display_name == action.display_name
        assert item.after.display_name == "新的导出名称"
        core.business_boundaries.approve(project_id, created.proposal.proposal_id,
            expected_fingerprint=created.proposal.proposal_fingerprint, reason="接受新业务说明")
        restored = core.business_boundaries.proposal(project_id, created.proposal.proposal_id)
        assert restored.review.items == original_review.items
        assert restored.review.current_state_changed
        assert restored.change_summary.permission_carry_forwards == created.change_summary.permission_carry_forwards
        permission = next(i for i in restored.review.items if i.entity_kind == "PERMISSION")
        assert permission.before.action == action.display_name
        assert permission.after.action == "新的导出名称"
    finally:
        core.close()


def test_missing_historical_revision_is_unavailable_not_create(tmp_path: Path, monkeypatch):
    core, project_id = _core(tmp_path)
    try:
        initial = _create_proposal(core, project_id)
        core.business_boundaries.approve(project_id, initial.proposal_id,
            expected_fingerprint=initial.proposal_fingerprint, reason="初始规则")
        draft = core.business_boundaries.maintenance_draft(project_id)
        created = core.business_boundaries.create_maintenance_proposal(project_id, _maintenance_command(draft))
        missing_id = draft.actors[0].actor_id
        with core.uow_factory() as work:
            repository_type = type(work.business_boundaries)
        original = repository_type.actor_revision
        monkeypatch.setattr(repository_type, "actor_revision", lambda self, identity, revision:
            None if identity == missing_id else original(self, identity, revision))
        restored = core.business_boundaries.proposal(project_id, created.proposal.proposal_id)
        assert restored.review.basis_state == "UNAVAILABLE"
        row = next(i for i in restored.review.items if i.entity_id == missing_id)
        assert row.change_kind == "REFERENCE"
        assert not row.basis_available and row.before is None
        assert restored.change_summary is None
    finally:
        core.close()
