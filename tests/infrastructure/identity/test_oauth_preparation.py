"""受限 OAuth 准备验证实际主体，秘密只经过浏览器内存和原安全存储交接。"""
from types import SimpleNamespace as Object
import pytest
from pydantic import ValidationError
from product.backend.domain.identities.models import AuthenticationProfile,IdentityVerificationConfig
from product.backend.infrastructure.identity.browser import IdentityPreparationBrowserAdapter


@pytest.mark.parametrize('method,grant',[('OAUTH2_CLIENT_CREDENTIALS','client_credentials'),('OAUTH2_REFRESH','refresh_token')])
def test_oauth_exchange_clears_inputs_and_replaces_previous_access_token(method,grant):
    fields={'#password':'client-secret','#token':'refresh-secret'}
    profile=AuthenticationProfile(method=method,principal_kind='SERVICE',oauth_client_id='service-client',login_path='/oauth/token',token_path=('access_token',),
        verification=IdentityVerificationConfig(path='/me',subject_path=('id',),role_path=(),expected_subject='service-account',expected_role=None))
    def evaluate(script,payload):
        assert payload['url']=='http://127.0.0.1:9000/oauth/token'
        assert payload['credentials']['grant_type']==grant
        assert payload['credentials']['client_secret']=='client-secret'
        assert fields['#password']==''
        if grant=='refresh_token':
            assert payload['credentials']['refresh_token']=='refresh-secret' and fields['#token']==''
        return {'status':200,'body':{'access_token':'new-access-token'}}
    page=Object(evaluate=evaluate,locator=lambda key:Object(input_value=lambda:fields[key],fill=lambda value:fields.__setitem__(key,value)))
    cleared=[]
    request=Object(authentication=profile,target_scope=Object(allowed_origins=('http://127.0.0.1:9000',)))
    tokens={'old-access-token'}
    IdentityPreparationBrowserAdapter._submit_credentials(request,page,Object(clear_cookies=lambda:cleared.append(True)),tokens)
    assert tokens=={'new-access-token'} and cleared==[True]
    verification=IdentityPreparationBrowserAdapter._verify(request,None,tokens,20,10,response={'status':200,'body':{'id':'service-account'}})
    assert verification.status=='VERIFIED' and verification.role is None
    assert 'secret' not in verification.model_dump_json() and 'access-token' not in verification.model_dump_json()


def test_client_credentials_cannot_claim_a_user_principal():
    with pytest.raises(ValidationError):
        AuthenticationProfile(method='OAUTH2_CLIENT_CREDENTIALS',oauth_client_id='client',
            verification=IdentityVerificationConfig(path='/me',subject_path=('id',),role_path=('role',),expected_subject='user',expected_role='member'))


@pytest.mark.level4
@pytest.mark.browser
@pytest.mark.process
def test_real_oauth_browser_preparation_refresh_expiry_and_recovery(caplog):
    """真实同源令牌服务与浏览器交换；内存秘密替身只代替操作系统存储。"""
    import json
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread
    from urllib.parse import parse_qs
    from uuid import uuid4
    from product.protocols.preparation.test_identity_preparation import IdentityPreparationRequest
    from product.protocols.web.target import WebTargetScope
    from tests.support.secrets import MemorySecrets

    client_secret, refresh_secret = uuid4().hex, uuid4().hex
    state = dict(token='', valid=True, reject=False, subject='service-account', grants=[])

    class TokenService(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def reply(self, status, body):
            raw=json.dumps(body).encode()
            self.send_response(status)
            self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_POST(self):
            assert self.path=='/oauth/token'
            form=parse_qs(self.rfile.read(int(self.headers['Content-Length'])).decode())
            grant=form.get('grant_type',[''])[0]
            state['grants'].append(grant)
            valid=(form.get('client_id')==['service-client'] and form.get('client_secret')==[client_secret]
                and (grant=='client_credentials' or grant=='refresh_token' and form.get('refresh_token')==[refresh_secret]))
            if state['reject'] or not valid:
                self.reply(401,dict(error='invalid_grant',description=client_secret))
                return
            state['token']=uuid4().hex
            state['valid']=True
            self.reply(200,dict(access_token=state['token'],token_type='Bearer'))

        def do_GET(self):
            assert self.path=='/me'
            valid=state['valid'] and self.headers.get('Authorization')=='Bearer '+state['token']
            self.reply(200 if valid else 401,dict(id=state['subject']) if valid else dict(error='expired'))

    server=ThreadingHTTPServer(('127.0.0.1',0),TokenService)
    thread=Thread(target=server.serve_forever,daemon=True)
    thread.start()
    store=MemorySecrets()
    adapter=IdentityPreparationBrowserAdapter()
    origin=f'http://127.0.0.1:{server.server_port}'
    scope=WebTargetScope(base_url=origin,allowed_origins=(origin,),allowed_hosts=('127.0.0.1',),
        allowed_ports=(server.server_port,),allow_private_network=True)
    identity='tid_'+uuid4().hex
    documents=[]

    def prepare(method, *, cancelled=False):
        profile=AuthenticationProfile(method=method,principal_kind='SERVICE',oauth_client_id='service-client',
            login_path='/oauth/token',token_path=('access_token',),verification=IdentityVerificationConfig(
                path='/me',subject_path=('id',),role_path=(),expected_subject='service-account',expected_role=None))
        request=IdentityPreparationRequest(schema_version='1',preparation_id='prep_'+uuid4().hex,
            project_id='oauth-browser',identity_id=identity,target_scope=scope,authentication=profile)
        def enter(page):
            page.locator('#password').fill(client_secret)
            if method=='OAUTH2_REFRESH':page.locator('#token').fill(refresh_secret)
        result=adapter.run(request,secret_store=store,ready_callback=lambda:None,save_requested=lambda:True,
            cancellation_requested=lambda:cancelled,interaction=enter,headless=True)
        documents.extend((request.model_dump_json(),result.model_dump_json()))
        return request,result

    def verify(request, prepared):
        check=request.model_copy(update=dict(preparation_id='prep_'+uuid4().hex,verify_only=True,
            existing_bearer_ref=prepared.bearer_secret_ref,session_prepared_at_us=prepared.prepared_at_us))
        result=adapter.run(check,secret_store=store,ready_callback=lambda:None,save_requested=lambda:False,
            cancellation_requested=lambda:False,headless=True)
        documents.extend((check.model_dump_json(),result.model_dump_json()))
        return result.verification.status

    try:
        request,prepared=prepare('OAUTH2_CLIENT_CREDENTIALS')
        assert prepared.result_type.value=='PREPARED' and prepared.verification.status=='VERIFIED'
        first_token=state['token']
        assert store.read(prepared.bearer_secret_ref)==first_token
        assert verify(request,prepared)=='VERIFIED'
        state['valid']=False
        assert verify(request,prepared)=='AUTH_EXPIRED'

        refresh,updated=prepare('OAUTH2_REFRESH')
        assert updated.verification.status=='VERIFIED' and state['token']!=first_token
        assert store.read(updated.bearer_secret_ref)==state['token']
        assert verify(refresh,updated)=='VERIFIED'
        stored=dict(store.values)
        state['reject']=True
        _,failed=prepare('OAUTH2_REFRESH')
        assert failed.result_type.value=='FAILED' and failed.bearer_secret_ref is None
        assert store.values==stored
        state['reject']=False
        state['subject']='another-service'
        _,mismatch=prepare('OAUTH2_REFRESH')
        assert mismatch.verification.status=='SUBJECT_MISMATCH'
        state['subject']='service-account'
        recovered_request,recovered=prepare('OAUTH2_REFRESH')
        assert verify(recovered_request,recovered)=='VERIFIED'
        grants=len(state['grants'])
        _,cancelled=prepare('OAUTH2_REFRESH',cancelled=True)
        assert cancelled.result_type.value=='CANCELLED' and len(state['grants'])==grants
        assert state['grants']==['client_credentials']+['refresh_token']*4
        public=''.join(documents)+caplog.text
        assert all(secret not in public for secret in (client_secret,refresh_secret,first_token,state['token']))
        assert client_secret not in store.values.values() and refresh_secret not in store.values.values()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)
        assert not thread.is_alive()
