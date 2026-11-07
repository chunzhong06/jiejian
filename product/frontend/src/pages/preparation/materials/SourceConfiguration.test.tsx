import {fireEvent,render,screen,waitFor,within} from '@testing-library/react'
import {afterEach,expect,it,vi} from 'vitest'
import {SourceConfiguration} from './SourceConfiguration'
import {Sources} from './Sources'
import {projectsApi} from '../../../entities/application/api/projects'
import {proofSourcesApi,type ProofContext} from '../../../entities/preparation/api/proofSources'

const context:ProofContext={project_id:'app',basis_id:'basis',runtime_available:false,runtime_origin:null,sqlite:[],actions:[],identities:[],resources:[],sources:[],read_scopes:[]}

it('文件证明可以直接配置，任务映射分类切换保留草稿并阻止不完整保存',async()=>{
    const runtime=vi.spyOn(projectsApi,'runtime')
    const fileContext:ProofContext={...context,project_id:'async-app',runtime_available:true,
        actions:[{action_id:'export',revision:1,label:'导出资料',effects:[{effect_id:'entity',label:'完整文件已接收',kind:'FILE_CONTENT_DELIVERY'}]}],
        resources:[{resource_binding_id:'r1',action_id:'export',action_revision:1,resource_id:'document',owner_identity_id:'owner'}]}
    render(<SourceConfiguration projectId="async-app" context={fileContext} onClose={()=>{}} onSave={vi.fn()}/> )
    fireEvent.change(screen.getByLabelText('资源所在的受控记录集合'),{target:{value:'documents'}})
    expect(screen.getByRole('button',{name:'保存判断方式'})).toBeEnabled()
    fireEvent.mouseDown(screen.getByRole('combobox',{name:'交付方式'}))
    fireEvent.click(await screen.findByRole('option',{name:'先创建导出任务，再接收文件'}))
    expect(screen.getByRole('button',{name:'保存判断方式'})).toBeDisabled()
    fireEvent.change(screen.getByLabelText('任务查询路径'),{target:{value:'/exports/{task_id}'}})
    fireEvent.click(screen.getByRole('tab',{name:'关联字段'}))
    expect(screen.getByLabelText('原请求关联标记')).toBeVisible()
    fireEvent.click(screen.getByRole('tab',{name:'任务与文件'}))
    expect(screen.getByLabelText('任务查询路径')).toHaveValue('/exports/{task_id}')
    expect(runtime).not.toHaveBeenCalled()
})
afterEach(()=>vi.restoreAllMocks())

it.each([true,false])('无可用数据库时根据已有配置恢复，并保留返回证明设置的位置：%s',async(configured)=>{
    location.hash='/preparation?project_id=app&proof_sources=1&source_id=source'
    vi.spyOn(projectsApi,'runtime').mockResolvedValue({project_id:'app',running:false,source_matches:false,operation:null,configuration:configured?{entry:'app.mjs',port:9000,sqlite:[{relative_path:'store.sqlite',tables:[{table:'tickets',resource_column:'id',owner_column:'owner',fields:['title']}]} ]}:null})
    const save=vi.fn(),candidate=vi.spyOn(proofSourcesApi,'sqliteCandidate'),closed=vi.fn()
    render(<SourceConfiguration projectId="app" context={context} onClose={closed} onSave={save}/> )
    expect(await screen.findByText(configured?'先启动已配置的测试应用':'先准备应用的测试数据库')).toBeVisible()
    expect(screen.queryByRole('button',{name:'保存判断方式'})).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button',{name:'核对应用运行'}))
    await waitFor(()=>expect(location.hash.startsWith('#/application?')).toBe(true))
    const destination=new URLSearchParams(location.hash.split('?')[1]).get('return_to')
    expect(new URLSearchParams(location.hash.split('?')[1]).get('runtime_method')).toBe('managed')
    expect(destination).toBe('/preparation?project_id=app&proof_sources=1&source_id=source')
    expect(closed).toHaveBeenCalledOnce()
    expect(candidate).not.toHaveBeenCalled()
    expect(save).not.toHaveBeenCalled()
})

it('运行设置读取失败时展示重试，不把未知状态说成缺少配置',async()=>{
    vi.spyOn(projectsApi,'runtime').mockRejectedValue(new Error('运行设置暂时不可达'))
    render(<SourceConfiguration projectId="app" context={context} onClose={()=>{}} onSave={vi.fn()}/> )
    expect(await screen.findByText('运行设置暂时不可达')).toBeVisible()
    expect(screen.queryByRole('button',{name:'核对应用运行'})).not.toBeInTheDocument()
})

it('证明来源按用途切换，核对事实直接可见，管理操作仍需明确确认',async()=>{
    sessionStorage.clear()
    const sourceContext:ProofContext={...context,runtime_available:true,runtime_origin:'http://127.0.0.1:9000',
        actions:[{action_id:'download',revision:1,label:'下载文件',effects:[{effect_id:'file',label:'完整文件已接收',kind:'FILE_DELIVERY'}]}],
        identities:[{identity_id:'owner',label:'负责人',actor_id:'owner',prepared:true}],
        resources:[{resource_binding_id:'resource',action_id:'download',action_revision:1,resource_id:'file-1',owner_identity_id:'owner'}],
        sources:[{source_id:'source',revision:1,adopted:false,submitted_via:'GUI',client_name:'Web',read_scope_confirmed:true,matching_read_scope_id:'scope',
            config:{action_id:'download',action_revision:1,effect_id:'file',observation_identity_id:'owner',resource_binding_id:'resource',read_scope_id:'scope',relative_path_template:'/files/{resource_id}',mappings:{resource_id:['id']},target_operation_path:[],source_contract_id:'contract',identity_claims:[{identity_id:'owner',application_subject_id:'owner'}],source_files:[],max_response_bytes:4096,timeout_us:2000000,source_kind:'REFERENCE_FILE'},
            preflight:{preflight_id:'preflight',state:'SUCCEEDED',current_basis:true,report:{assessment:'NEEDS_CHANGES',checks:[{code:'IDENTITY_CONFIRMED',status:'CONFIRMED',mapping_key:null},{code:'RESOURCE_CORRELATED',status:'MISSING',mapping_key:null}]}}}]}
    vi.spyOn(proofSourcesApi,'context').mockResolvedValue(sourceContext)
    const write=vi.spyOn(proofSourcesApi,'write'),back=vi.fn()
    render(<Sources projectId="app" onBack={back} onError={vi.fn()}/> )
    const filePicker=await screen.findByRole('group',{name:'完整测试参照文件'})
    const fileInput=filePicker.querySelector('input[type=file]')!
    const file=new File(['reference'],'reference.pdf',{type:'application/pdf'})
    fireEvent.change(fileInput,{target:{files:[file]}})
    fireEvent.click(screen.getByRole('tab',{name:'核对记录'}))
    const checks=screen.getByRole('tabpanel',{name:'核对记录'})
    expect(within(checks).getByText('测试身份可以对应')).toBeVisible()
    expect(within(checks).getByText('已确认')).toBeInTheDocument()
    expect(within(checks).getByText('尚未确认')).toBeVisible()
    expect(screen.getByText('字段映射与技术引用')).not.toBeVisible()
    expect(filePicker).not.toBeVisible()
    fireEvent.click(screen.getByRole('tab',{name:'来源与管理'}))
    const settings=screen.getByRole('tabpanel',{name:'来源与管理'})
    expect(within(settings).getByText('/files/{resource_id}')).toBeVisible()
    expect(within(settings).getByRole('button',{name:'查看读取范围'})).toBeVisible()
    fireEvent.click(within(settings).getByRole('button',{name:'撤销读取授权'}))
    const dialog=screen.getByRole('dialog',{name:'撤销这份读取授权'})
    expect(within(dialog).getByRole('button',{name:'撤销授权'})).toBeVisible()
    expect(write).not.toHaveBeenCalled()
    fireEvent.click(within(dialog).getByRole('button',{name:'保留授权'}))
    await waitFor(()=>expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    fireEvent.click(screen.getByRole('tab',{name:'结果说明'}))
    expect(screen.getByRole('group',{name:'完整测试参照文件'}).querySelector('input[type=file]')).toBe(fileInput)
    expect(screen.getByText('reference.pdf')).toBeVisible()
    expect(write).not.toHaveBeenCalled()
    expect(back).not.toHaveBeenCalled()
})
