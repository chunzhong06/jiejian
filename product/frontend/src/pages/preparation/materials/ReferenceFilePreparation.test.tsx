import {fireEvent,render,screen,waitFor} from '@testing-library/react'
import {afterEach,beforeEach,expect,it,vi} from 'vitest'
import {ReferenceFilePreparation} from './ReferenceFilePreparation'
import {proofSourcesApi as api,type ProofContext,type CapturePlan,type CaptureStatus,type ProofReceipt} from '../../../entities/preparation/api/proofSources'

const context:ProofContext={project_id:'app',basis_id:'basis',runtime_available:true,runtime_origin:'http://127.0.0.1:19000',actions:[{action_id:'download',revision:1,label:'取得公开文件',execution_identity_id:'owner',recovery_identity_id:'owner',effects:[{effect_id:'file',label:'完整文件收到',kind:'FILE_CONTENT_DELIVERY'}]}],identities:[{identity_id:'owner',actor_id:'owner-role',label:'负责人',prepared:true},{identity_id:'reviewer',actor_id:'reviewer-role',label:'评审',prepared:true}],resources:[{resource_binding_id:'binding',action_id:'download',action_revision:1,resource_id:'public-file',owner_identity_id:'owner'}],sources:[{source_id:'source',revision:2,submitted_via:'GUI',client_name:'界鉴',adopted:false,preflight:null,config:{action_id:'download',action_revision:1,effect_id:'file',observation_identity_id:'owner',resource_binding_id:'binding',read_scope_id:null,relative_path_template:'/files/{resource_id}',collection:'files',mappings:{},target_operation_path:[],source_contract_id:'contract',identity_claims:[{identity_id:'owner',application_subject_id:'alice',request_path:'/me'},{identity_id:'reviewer',application_subject_id:'judge',request_path:'/me'}],source_files:[],source_kind:'REFERENCE_FILE',max_response_bytes:65536,timeout_us:1000000}}],read_scopes:[],allow_permissions:[{intent_id:'allow',action_id:'download',action_revision:1,subject_actor_id:'owner-role',owner_actor_id:'owner-role',relation:'OWNS'}]}
const plan:CapturePlan={schema_version:'1',project_id:'app',basis_id:'basis',plan_hash:'frozen-plan',created_at_us:1,restore:null,case:{subject_test_identity_id:'owner',resource_owner_test_identity_id:'owner',resource_id:'public-file',resource_binding_id:'binding'},runtime:{source_fingerprint:'source',target:{base_url:'http://127.0.0.1:19000',max_response_bytes:65536},budget:{max_requests:20,max_duration_us:5000000},actions:[{display_name:'取得公开文件',state_changing:true,recovery:{},steps:[{}]}]}}
const complete:CaptureStatus={capture_id:'capture',action_id:'download',resource_binding_id:'binding',asset_id:'asset',state:'SUCCEEDED',target_may_have_run:true,operation_may_have_run:true,plan_hash:'frozen-plan',report:{state:'CANDIDATE',recovery_verified:true,reason_codes:[],manifest:{asset_id:'asset',size:28,sha256:'content'}}}
const receipt=(kind:string,capture='capture'):ProofReceipt=>({project_id:'app',operation_id:'operation',operation_kind:kind,result:{state:'PENDING',capture_id:capture}})
const defaults=()=>({projectId:'app',context,source:context.sources[0],busy:false,pending:false,onBack:vi.fn(),onRefresh:vi.fn(),onWrite:vi.fn(async(kind:string)=>receipt(kind)),onRecover:vi.fn(async()=>receipt('START_REFERENCE_CAPTURE'))})
beforeEach(()=>{sessionStorage.clear();vi.spyOn(api,'capturePreview').mockResolvedValue(plan);vi.spyOn(api,'captureStatus').mockResolvedValue(complete)})
afterEach(()=>vi.restoreAllMocks())

it('预览不执行，实际参与身份准确；取得文件后再次确认才保存，不自动采用',async()=>{
 const props=defaults();render(<ReferenceFilePreparation {...props}/>)
 fireEvent.click(screen.getByRole('tab',{name:'通过正常操作取得'}));fireEvent.click(screen.getByRole('button',{name:'预览本次正常操作'}))
 expect(await screen.findByRole('heading',{name:'通过正常操作取得参照'})).toBeVisible()
 expect(props.onWrite).not.toHaveBeenCalled()
 expect(api.capturePreview).toHaveBeenCalledWith('app',expect.objectContaining({allow_intent_id:'allow',identity_claims:[context.sources[0].config.identity_claims[0]]}))
 expect(screen.getByRole('button',{name:'确认执行一次'})).toBeDisabled()
 fireEvent.click(screen.getByRole('checkbox',{name:'允许执行上述正常操作并核对恢复'}));fireEvent.click(screen.getByRole('button',{name:'确认执行一次'}))
 expect(await screen.findByRole('heading',{name:'完整参照已取得'})).toBeVisible()
 expect(props.onWrite).toHaveBeenCalledTimes(1)
 expect(props.onWrite).toHaveBeenCalledWith('START_REFERENCE_CAPTURE',expect.objectContaining({plan_hash:'frozen-plan',plan_created_at_us:1,confirmed:true}))
 expect(screen.getByRole('checkbox',{name:'我已确认文件内容与上述资源对应'})).not.toBeChecked()
 expect(screen.getByRole('button',{name:'保存为本次参照'})).toBeDisabled()
 fireEvent.click(screen.getByRole('checkbox',{name:'我已确认文件内容与上述资源对应'}));fireEvent.click(screen.getByRole('button',{name:'保存为本次参照'}))
 await waitFor(()=>expect(props.onBack).toHaveBeenCalledOnce())
 expect(props.onWrite).toHaveBeenLastCalledWith('SAVE_SOURCE',expect.objectContaining({expected_revision:2,config:expect.objectContaining({reference_origin:'REFERENCE_CAPTURE',reference_artifact:complete.report!.manifest})}))
})

it('恢复从原取样起点预览，只提交恢复命令，不建立第二个正常取样',async()=>{
 sessionStorage.setItem('jiejian.reference-capture:app:source','capture')
 vi.mocked(api.captureStatus).mockResolvedValue({...complete,report:{...complete.report!,state:'INCOMPLETE',manifest:null,recovery_verified:false}})
 vi.mocked(api.capturePreview).mockResolvedValue({...plan,restore:{capture_id:'capture',resource_id:'public-file',generation:'original'}})
 const props=defaults();props.context={...context,reference_recovery_gaps:[{capture_id:'capture',action_id:'download',resource_id:'public-file',owner_identity_id:'owner',reason:'REFERENCE_RECOVERY_UNVERIFIED'}]}
 render(<ReferenceFilePreparation {...props}/>)
 fireEvent.click(await screen.findByRole('button',{name:'核对并恢复测试数据'}))
 expect(await screen.findByRole('heading',{name:'核对并恢复测试数据'})).toBeVisible()
 expect(api.capturePreview).toHaveBeenCalledWith('app',expect.objectContaining({restore_capture_id:'capture'}))
 expect(props.onWrite).not.toHaveBeenCalled()
 fireEvent.click(screen.getByRole('checkbox',{name:'允许核对并恢复上述测试数据'}));fireEvent.click(screen.getByRole('button',{name:'确认恢复一次'}))
 await waitFor(()=>expect(props.onWrite).toHaveBeenCalledOnce())
 expect(props.onWrite).toHaveBeenCalledWith('START_REFERENCE_CAPTURE',expect.objectContaining({selection:expect.objectContaining({restore_capture_id:'capture'})}))
})

it('响应未知时只查询原回执并读取原任务，不重新执行或采用',async()=>{
 const props=defaults();props.pending=true;render(<ReferenceFilePreparation {...props}/>)
 fireEvent.click(screen.getByRole('button',{name:'查询这次操作'}))
 expect(await screen.findByRole('heading',{name:'完整参照已取得'})).toBeVisible()
 expect(props.onRecover).toHaveBeenCalledOnce();expect(props.onWrite).not.toHaveBeenCalled()
 expect(api.captureStatus).toHaveBeenCalledWith('app','capture')
})

it('恢复预览明确实际恢复账号，阅读本身不提交恢复命令',async()=>{
 sessionStorage.setItem('jiejian.reference-capture:app:source','capture')
 vi.mocked(api.captureStatus).mockResolvedValue({...complete,report:{...complete.report!,state:'INCOMPLETE',manifest:null,recovery_verified:false}})
 vi.mocked(api.capturePreview).mockResolvedValue({...plan,case:{...plan.case,subject_test_identity_id:'reviewer'},restore:{capture_id:'capture',resource_id:'public-file',generation:'original'}})
 const props=defaults();props.context={...context,reference_recovery_gaps:[{capture_id:'capture',action_id:'download',resource_id:'public-file',owner_identity_id:'owner',reason:'REFERENCE_RECOVERY_UNVERIFIED'}]}
 render(<ReferenceFilePreparation {...props}/>);
 fireEvent.click(await screen.findByRole('button',{name:'核对并恢复测试数据'}))
 await screen.findByRole('heading',{name:'核对并恢复测试数据'})
 const account=screen.getByText('操作账号').closest('div')!
 expect(account).toHaveTextContent('负责人')
 expect(account).not.toHaveTextContent('评审')
 expect(props.onWrite).not.toHaveBeenCalled()
})

it('恢复已解决时保留历史输入，不把旧未完成取样重新当作当前任务',()=>{
 const props=defaults();props.context={...context,reference_recovery_gaps:[],reference_inputs:[{asset_id:'old',action_id:'download',action_revision:1,resource_binding_id:'binding',resource_id:'public-file',owner_identity_id:'owner',origin:'REFERENCE_CAPTURE',reference_capture_id:'old-capture',state:'INCOMPLETE',manifest:null,created_at_us:1}]}
 render(<ReferenceFilePreparation {...props}/>);
 expect(screen.getByRole('heading',{name:'准备完整参照文件'})).toBeVisible()
 expect(api.captureStatus).not.toHaveBeenCalled();expect(props.onWrite).not.toHaveBeenCalled()
})
