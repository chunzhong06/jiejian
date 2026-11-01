from types import SimpleNamespace
import pytest
from product.backend.domain.identities.models import AuthenticationProfile,IdentityVerificationConfig
from product.backend.infrastructure.identity.browser import IdentityPreparationBrowserAdapter


@pytest.mark.parametrize(('response','expected'),[
    ({'status':200,'body':{'id':'owner','role':'supervisor'}},'VERIFIED'),
    ({'status':401,'body':{'token':'not-for-persistence'}},'AUTH_EXPIRED'),
    ({'status':200,'body':{'id':'other','role':'supervisor'}},'SUBJECT_MISMATCH'),
    ({'status':200,'body':{'id':'owner','role':'member'}},'ROLE_MISMATCH'),
    ({'status':200,'body':{'id':'owner'}},'FIELD_MISSING'),
    ({'status':0,'body':None},'UNAVAILABLE'),
])
def test_actual_identity_is_independent_from_session_saved(response,expected):
    profile=AuthenticationProfile(verification=IdentityVerificationConfig(path='/api/me',subject_path=('id',),role_path=('role',),expected_subject='owner',expected_role='supervisor'))
    request=SimpleNamespace(authentication=profile,target_scope=SimpleNamespace(allowed_origins=('http://127.0.0.1:9000',)))
    page=SimpleNamespace(evaluate=lambda *_:response)
    value=IdentityPreparationBrowserAdapter._verify(request,page,set(),20,10)
    assert value.status==expected
    assert value.session_prepared_at_us==10
    if expected!='VERIFIED':assert value.subject is None and value.role is None
    assert 'not-for-persistence' not in value.model_dump_json()
