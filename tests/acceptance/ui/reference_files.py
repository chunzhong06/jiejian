# 在生产构建中核对文件候选与恢复布局；只允许夹具计划预览，禁止执行取样及业务写入。
import json
from urllib.parse import urlparse
from playwright.sync_api import expect


def verify_reference_files(browser,origin,out,report):
    for width,theme in [(2560,'light'),(2560,'dark'),(1280,'light'),(600,'dark')]:
        project={'project_id':'reference-ui','name':'资料协作应用','status':'READY','target_type':'WEB'}
        config=dict(action_id='download',action_revision=1,effect_id='file',observation_identity_id='alice',resource_binding_id='res',
            collection='units',source_kind='REFERENCE_FILE',source_contract_id='FILE_RESPONSE_CONTENT_V1',reference_artifact=None,
            mappings={'resource_id':['resource_id'],'owner_id':['owner_id']},relative_path_template='/units/{resource_id}',
            identity_claims=[{'identity_id':'alice','application_subject_id':'alice','request_path':'/identity/current'}],
            source_files=['app.mjs'],max_response_bytes=4194304,timeout_us=5000000)
        source=dict(source_id='source',revision=1,config=config,submitted_via='MCP',client_name='Agent',adopted=False,preflight=None)
        proof=dict(project_id=project['project_id'],basis_id='pb_ui',runtime_available=True,runtime_origin='http://127.0.0.1:1234',
            sources=[source],read_scopes=[],reference_inputs=[],reference_recovery_gaps=[],
            actions=[dict(action_id='download',revision=1,label='取得完整文件',execution_identity_id='alice',recovery_identity_id='alice',
                effects=[dict(effect_id='file',label='完整文件已接收',kind='FILE_CONTENT_DELIVERY')])],
            identities=[dict(identity_id='alice',actor_id='owner',label='项目负责人',prepared=True)],
            resources=[dict(resource_binding_id='res',action_id='download',action_revision=1,resource_id='project-alpha',owner_identity_id='alice')],
            allow_permissions=[dict(intent_id='allow',action_id='download',action_revision=1,subject_actor_id='owner',owner_actor_id='owner',relation='OWNS')])
        def api(route):
            path=urlparse(route.request.url).path
            if route.request.method!='GET':
                if path.endswith('/reference-captures/preview'):
                    data=dict(project_id=project['project_id'],basis_id='pb_ui',plan_hash='hash',created_at_us=1,
                        restore={'capture_id':'original'} if route.request.post_data_json.get('restore_capture_id') else None,
                        case=dict(subject_test_identity_id='alice',resource_id='project-alpha'),
                        runtime=dict(source_fingerprint='a'*64,target=dict(base_url=proof['runtime_origin'],max_response_bytes=4194304),
                            actions=[dict(display_name='取得完整文件',state_changing=True)]))
                else:report['writes'].append(path);route.abort();return
            elif path=='/api/projects':data=[project]
            elif path.endswith('/proof-preparation'):data=proof
            elif path.endswith('/reference-captures/alignment-capture'):data=dict(capture_id='alignment-capture',action_id='download',resource_binding_id='res',state='RUNNING')
            elif path.endswith('/workspace'):data=dict(project=project,connection=dict(endpoint_status='CONFIRMED',source_analysis_status='COMPLETED'),actors=[],actions=[],areas=[],primary_task=None,active_check=None,latest_result=None)
            elif path.endswith('/preparation'):data=dict(project_id=project['project_id'],preparation_complete=False,actions=[])
            elif path.endswith('/preparation/draft'):data=dict(schema_version='1',revision=0,action_id=None,material=None)
            elif path.endswith('/check-preview'):data=dict(project_id=project['project_id'],can_execute=False,gaps=[],actions=[])
            elif path.endswith('/runs') or path=='/api/llm/profiles':data=[]
            elif path=='/api/llm/settings':data=dict(enabled=False,default_profile_name=None,updated_at_us=0)
            elif path=='/api/mcp/access':data=dict(paired=False,connection_state='UNPAIRED',project_grants=[],enabled=False)
            elif path=='/api/system/status':data=dict(api='available',worker='running',browser='available',version='1.2.0')
            else:data=dict(available=True,active=False,project_id=None,lifecycle='NOT_STARTED')
            route.fulfill(status=200,content_type='application/json',body=json.dumps(dict(schema_version='1',data=data)))
        context=browser.new_context(viewport=dict(width=width,height=1200),reduced_motion='reduce')
        try:
            context.add_init_script('localStorage.setItem("jiejian.project",'+json.dumps(json.dumps(project))+');localStorage.setItem("jiejian.theme",'+json.dumps(theme)+');')
            page=context.new_page();page.route('**/api/**',api);page.on('pageerror',lambda error:report['errors'].append(str(error)))
            page.goto(origin+'/#/tests?materials=1&proof_sources=1&proof_source=source')
            expect(page.get_by_role('region',name='文件参照准备')).to_be_visible()
            expect(page.get_by_role('button',name='Agent 协助',exact=True)).to_have_count(1)
            # 用户实际发现的缺陷发生于取样中：禁用样式不能让已选对勾偏出圆心。
            centered = """() => {
              const e=document.querySelector('.proof-reference-modes .ant-radio-checked .ant-radio-inner');
              if(!e)return false;
              const s=getComputedStyle(e,'::after'),m=new DOMMatrix(s.transform);
              return Math.abs(parseFloat(s.left)+parseFloat(s.marginLeft)+parseFloat(s.width)/2+m.e-e.clientWidth/2)<.5
                && Math.abs(parseFloat(s.top)+parseFloat(s.marginTop)+parseFloat(s.height)/2+m.f-e.clientHeight/2)<.5;
            }"""
            page.wait_for_function(centered)
            proof['reference_inputs']=[dict(asset_id='alignment-input',action_id='download',action_revision=1,resource_binding_id='res',state='PENDING',reference_capture_id='alignment-capture')]
            page.reload()
            expect(page.get_by_role('radio',name='让界鉴获取测试文件',exact=True)).to_be_disabled()
            # 原生输入框在禁用时仍透明，避免与主题绘制的圆圈/勾形叠加。
            expect(page.get_by_role('radio',name='让界鉴获取测试文件',exact=True)).to_have_css('opacity','0')
            cancel=page.get_by_role('button',name='取消这次取样',exact=True)
            expect(cancel).to_be_visible()
            assert cancel.evaluate('e=>Math.abs(e.getBoundingClientRect().right-e.parentElement.getBoundingClientRect().right)<2')
            for motion in ['no-preference','reduce']:
                page.emulate_media(reduced_motion=motion)
                page.wait_for_function(centered)
            page.get_by_role('region',name='文件参照准备').screenshot(path=str(out/f'reference-disabled-{width}-{theme}.png'))
            proof['reference_inputs']=[]
            page.reload()
            expect(page.get_by_role('radio',name='让界鉴获取测试文件',exact=True)).to_be_enabled()
            page.get_by_role('button',name='预览获取操作',exact=True).click()
            dialog=page.get_by_role('dialog',name='正常取得一份参照');expect(dialog).to_be_visible()
            expect(dialog.get_by_role('button',name='允许并开始本次取样')).to_be_disabled()
            dialog.screenshot(path=str(out/f'reference-preview-{width}-{theme}.png'))
            dialog.get_by_role('button',name='返回核对',exact=True).click()
            page.get_by_role('radio',name='使用已有测试文件',exact=True).check()
            expect(page.get_by_role('button',name='上传测试参照',exact=True)).to_be_disabled()
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
            page.screenshot(path=str(out/f'reference-input-{width}-{theme}.png'),full_page=True)
            proof['reference_recovery_gaps']=[dict(capture_id='original',action_id='download',resource_id='project-alpha',owner_identity_id='alice',reason='REFERENCE_RECOVERY_UNVERIFIED')]
            page.reload();expect(page.get_by_role('button',name='预览获取操作')).to_be_disabled()
            page.get_by_role('button',name='核对并恢复',exact=True).click()
            dialog=page.get_by_role('dialog',name='核对并恢复原资源');expect(dialog).to_be_visible()
            expect(dialog).to_contain_text('本次不会重新下载')
            dialog.screenshot(path=str(out/f'reference-restore-{width}-{theme}.png'))
            report['checks'].append(dict(width=width,theme=theme,reference_candidate=True,disabled_check_centered=True,restore_only=True,overflow=False))
        finally:context.close()
