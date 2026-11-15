import {fireEvent,render,screen,waitFor} from '@testing-library/react'
import {afterEach,beforeEach,expect,it,vi} from 'vitest'
import {Sources} from './Sources'
import {proofSourcesApi as api,type ProofContext,type AdoptionPreview} from '../../../entities/preparation/api/proofSources'

const context:ProofContext={project_id:'proof-task',basis_id:'basis-task',runtime_available:true,runtime_origin:'http://127.0.0.1:19000',actions:[{action_id:'download',revision:1,label:'下载文件',effects:[{effect_id:'file',label:'公开文件已接收',kind:'FILE'}]}],identities:[{identity_id:'owner',actor_id:'owner',label:'项目负责人',prepared:true}],resources:[{resource_binding_id:'binding',action_id:'download',action_revision:1,resource_id:'public-file',owner_identity_id:'owner'}],sources:[{source_id:'source',revision:1,submitted_via:'GUI',client_name:'界鉴',adopted:false,usable:false,read_scope_confirmed:false,preflight:null,config:{action_id:'download',action_revision:1,effect_id:'file',observation_identity_id:'owner',resource_binding_id:'binding',read_scope_id:null,relative_path_template:'/proof/public-file',mappings:{},target_operation_path:[],source_contract_id:'contract',identity_claims:[{identity_id:'owner',application_subject_id:'owner-1',request_path:'/api/me'}],source_files:[],source_kind:'JSON_HTTP_RESOURCE',max_response_bytes:65536,timeout_us:1000000}}],read_scopes:[]}
const preview:AdoptionPreview={project_id:context.project_id,basis_id:context.basis_id,source_id:'source',revision:1,preflight_id:'preflight',action_label:'下载文件',effect_label:'公开文件已接收',replaces_existing:false,resource_id:'public-file',retained:['已保存的录制'],recheck:['实际资源归属'],collection:'files',mappings:{},expected_state:'已接收',protected_projection:['size'],field_mutation:null,identity_claims:context.sources[0].config.identity_claims,source_path:'/proof/public-file',read_paths:['/api/me'],gui_url:'/'}
beforeEach(()=>{sessionStorage.clear();vi.spyOn(api,'context').mockResolvedValue(context)})
afterEach(()=>vi.restoreAllMocks())

it('读取授权独立确认，回执未知时在当前任务查询原操作，不重复写入',async()=>{
 const write=vi.spyOn(api,'write').mockRejectedValue(new Error('回执连接中断'))
 const receipt=vi.spyOn(api,'receipt').mockImplementation(async(project,kind,operation)=>({project_id:project,operation_kind:kind,operation_id:operation,result:{state:'COMPLETED'}}))
 render(<Sources projectId={context.project_id} onBack={vi.fn()} onError={vi.fn()}/>)
 const open=await screen.findByRole('button',{name:'核对并允许读取'});await waitFor(()=>expect(open).toBeEnabled());fireEvent.click(open)
 expect(await screen.findByText('/api/me')).toBeVisible()
 expect(screen.getByRole('button',{name:'允许读取'})).toBeDisabled();expect(write).not.toHaveBeenCalled()
 fireEvent.click(screen.getByRole('checkbox',{name:'允许读取上述账号、资源与记录'}))
 fireEvent.click(screen.getByRole('button',{name:'允许读取'}))
 const query=await screen.findByRole('button',{name:'查询这次操作'})
 await waitFor(()=>expect(query).toBeEnabled());fireEvent.click(query)
 await waitFor(()=>expect(receipt).toHaveBeenCalledOnce())
 expect(write).toHaveBeenCalledTimes(1)
 expect(write.mock.calls[0][1]).toBe('GRANT_SCOPE')
 expect(receipt).toHaveBeenCalledWith(context.project_id,'GRANT_SCOPE',(write.mock.calls[0][2] as {operation_id:string}).operation_id)
})

it('来源可用后仍先审阅采用影响，不因展开预览自动采用',async()=>{
 vi.mocked(api.context).mockResolvedValue({...context,sources:[{...context.sources[0],usable:true,read_scope_confirmed:true,preflight:{preflight_id:'preflight',state:'SUCCEEDED',current_basis:true,report:{assessment:'USABLE',checks:[]}}}]})
 vi.spyOn(api,'adoptionPreview').mockResolvedValue(preview)
 const write=vi.spyOn(api,'write').mockImplementation(async(project,kind,body)=>({project_id:project,operation_kind:kind,operation_id:(body as {operation_id:string}).operation_id,result:{state:'COMPLETED'}}))
 render(<Sources projectId={context.project_id} onBack={vi.fn()} onError={vi.fn()}/>)
 fireEvent.click(await screen.findByRole('button',{name:'核对并用于检查'}))
 expect(await screen.findByRole('heading',{name:'确认这份证明的用途'})).toBeVisible()
 expect(screen.getByText('已保存的录制')).toBeVisible();expect(screen.getByText('实际资源归属')).toBeVisible()
 expect(screen.getByRole('button',{name:'确认用于检查'})).toBeDisabled();expect(write).not.toHaveBeenCalled()
 fireEvent.click(screen.getByRole('checkbox',{name:'我已核对数据归属和使用后的变化'}))
 fireEvent.click(screen.getByRole('button',{name:'确认用于检查'}))
 await waitFor(()=>expect(write).toHaveBeenCalledOnce())
 expect(write).toHaveBeenCalledWith(context.project_id,'ADOPT_SOURCE',expect.objectContaining({source_id:'source',revision:1,basis_id:'basis-task',preflight_id:'preflight',confirmed:true}),undefined)
})
