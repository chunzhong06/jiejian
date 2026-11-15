from types import SimpleNamespace
import pytest
from product.backend.application.preparation.materials.review import material_handling


@pytest.mark.parametrize('kind,status,reasons,expected',[
    ('identity','SATISFIED',(),'KEEP'),('execution','NEEDS_USER',('OPERATION_FLOW_SOURCE_STALE',),'RECHECK'),
    ('resource','STALE',('RESOURCE_OWNER_CHANGED',),'RECHECK'),('identity','BLOCKED',('IDENTITY_MATERIAL_ASSIGNMENT_CONFLICT',),'DECIDE'),
    ('evidence','NEEDS_USER',('EFFECT_EVIDENCE_REQUIRED',),'ADD'),
    ('execution','NEEDS_USER',('NEW_UNKNOWN_REASON',),'RECHECK'),
    ('identity','NEEDS_USER',('TEST_IDENTITY_LOGIN_REQUIRED',),'RECHECK'),
])
def test_material_review_uses_the_actual_reason_instead_of_repeating_setup(kind,status,reasons,expected):
    item=SimpleNamespace(status=status,reason_codes=reasons)
    view=material_handling(kind,item)
    assert view['handling']==expected
    assert view['explanation'] and view['next_step']
