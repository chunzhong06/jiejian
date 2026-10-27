# 验证录制整理保留因果顺序，并且不把敏感字段当成业务变量。
import pytest
from product.backend.domain.errors import JiejianError
from product.backend.application.recording.processing import FlowDraftProcessor
from product.backend.application.recording.draft_values import _replace_json,_replace_path,_walk_scalars
from tests.support.facts import identifier

def test_recording_rejects_empty_event_stream():
    with pytest.raises(JiejianError):
        FlowDraftProcessor().build(recording_id=identifier('rec',1),flow_id='download',business_action_id=identifier('bac',1),action_revision=1,subject_test_identity_id=identifier('tid',1),resource_owner_test_identity_id=identifier('tid',1),events=())

def test_value_replacement_excludes_sensitive_keys():
    matched=set()
    actual=_replace_json({'resource':'public-package','password':'public-package'},{'"public-package"':[]},matched)
    assert actual['resource'].startswith('{candidate-')
    assert actual['password']=='public-package'
    assert matched=={'"public-package"'}

def test_path_and_query_use_the_same_business_placeholder():
    matched=set()
    actual=_replace_path('/packages/public-package?resource=public-package',{'"public-package"':[]},matched)
    first=actual.split('/')[2].split('?')[0]
    assert first.startswith('{candidate-') and actual.endswith('resource='+first)

def test_nested_values_have_stable_locations_and_exclude_booleans():
    assert _walk_scalars({'z':True,'b':[3],'a':'name'})==[('$.a','name'),('$.b[0]',3)]

