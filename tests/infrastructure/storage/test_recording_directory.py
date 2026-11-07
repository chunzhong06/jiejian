"""录制目录不加载事件正文，详情仍由完整 reader 独立核验。"""
import pytest
from sqlalchemy import event
from product.backend.infrastructure.storage.preparation.recordings import RecordingSummary
from tests.support.builders.preparation.action_preparation import build_preparation_harness,add_recording


def test_recording_directory_selects_only_metadata_and_preserves_all_items(tmp_path):
    harness=build_preparation_harness(tmp_path)
    try:
        records=[add_recording(harness) for _ in range(3)]
        statements=[]
        def observed(_connection,_cursor,sql,_parameters,_context,_many):
            statements.append(sql)
        event.listen(harness.core.engine,'before_cursor_execute',observed)
        try:
            with harness.core.uow_factory() as work:
                summaries=work.recordings.list_summaries(harness.project_id)
        finally:
            event.remove(harness.core.engine,'before_cursor_execute',observed)
        assert {item.recording_id for item in summaries}=={item.recording_id for item in records}
        assert {item.model_dump_json() for item in summaries}=={
            RecordingSummary.model_validate_json(item.model_dump_json(include=set(RecordingSummary.model_fields))).model_dump_json()
            for item in records}
        assert len(statements)==1
        assert 'browser_events' not in statements[0] and 'state_events' not in statements[0]
        with harness.core.uow_factory() as work:
            assert work.recordings.list_summaries('app_'+'f'*32)==()
            assert work.recordings.get(records[0].recording_id)==records[0]
    finally:
        harness.close()


pytestmark=[pytest.mark.level3]
