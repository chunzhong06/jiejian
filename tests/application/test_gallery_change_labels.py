from types import SimpleNamespace
from unittest.mock import Mock

from product.backend.application.examples.change_labels import gallery_change_labels, gallery_operation_key


def test_history_names_follow_exact_receipts_not_current_stage_or_reason():
    workspace = {'workspace_id':'wsp_old', 'runtime_kind':'NODE_ESM', 'scenario_version':'FIXED'}
    saved = {gallery_operation_key('wsp_old','VULNERABLE'):SimpleNamespace(change_id='old-change'),
        gallery_operation_key('wsp_old','EXPOSE_REVOKE'):SimpleNamespace(change_id='later-change')}
    receipts = Mock(side_effect=lambda project, kind, key: saved.get(key))
    work = SimpleNamespace(sample_workspaces=SimpleNamespace(for_project=Mock(return_value=workspace)),
        development=SimpleNamespace(receipt=receipts))
    assert gallery_change_labels(work,'project',{'old-change','unrelated'}) == {'old-change':'移除内部包下载限制'}
    assert receipts.call_count == 4
    assert all(call.args[:2] == ('project','DELIVER') for call in receipts.call_args_list)
    work.sample_workspaces.for_project.assert_called_once_with('project')


def test_ordinary_or_missing_workspaces_do_not_receive_official_names():
    for workspace in (None, {'workspace_id':'other','runtime_kind':'PYTHON'}):
        receipts=Mock()
        work=SimpleNamespace(sample_workspaces=SimpleNamespace(for_project=lambda project:workspace),
            development=SimpleNamespace(receipt=receipts))
        assert gallery_change_labels(work,'project',{'change'}) == {}
        receipts.assert_not_called()
