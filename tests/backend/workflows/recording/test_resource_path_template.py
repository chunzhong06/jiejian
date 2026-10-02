# 验证资源路径含业务动作后缀时按批准的模板定位，未知或多资源路径保留业务歧义。
import pytest
from product.backend.workflows.recording.processing import FlowDraftProcessor
from product.protocols import RecordingEvent,RecordingEventKind

@pytest.mark.parametrize('templates,positions,automatic',[
    (('POST /api/resources/{resource_id}/publish',),['path[2]'],True),
    (('POST /api/{collection}/{resource_id}/publish',),['path[1]','path[2]'],False),
    ((),['path[0]','path[1]','path[2]','path[3]'],False),
    (('POST /api/resources/alpha/publish',),[],False),
])
def test_recorded_resource_uses_confirmed_template(templates,positions,automatic):
    events=(RecordingEvent(sequence=1,occurred_at_us=1,kind=RecordingEventKind.REQUEST,
        identity_id='actor',request_id='request_000001',url='http://127.0.0.1:3100/api/resources/alpha/publish',method='POST',body='{}'),
        RecordingEvent(sequence=2,occurred_at_us=2,kind=RecordingEventKind.RESPONSE,
        identity_id='actor',request_id='request_000001',url='http://127.0.0.1:3100/api/resources/alpha/publish',status_code=200,body='{}'))
    draft=FlowDraftProcessor().build(recording_id='rec_'+'1'*32,flow_id='flow',business_action_id='bac_'+'1'*32,
        action_revision=1,subject_test_identity_id='tid_'+'1'*32,resource_owner_test_identity_id='tid_'+'1'*32,
        events=events,action_path_templates=templates)
    assert [c.location for c in draft.steps[0].resource_candidates]==positions
    assert (draft.resource_candidate_id is not None)==automatic
