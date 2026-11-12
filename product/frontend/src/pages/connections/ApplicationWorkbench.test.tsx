import {discardProjectEditorDrafts} from '../../entities/runtime/model/handoff'
import {fireEvent,render,screen,waitFor,within} from '@testing-library/react'
import {afterEach,beforeEach,expect,it,vi} from 'vitest'
import {ApplicationWorkbench} from './ApplicationWorkbench'
import {workbenchApi,type ApplicationEnvironment,type EnvironmentContext} from '../../entities/application/api/workbench'
import {projectsApi} from '../../entities/application/api/projects'
import {onboardingApi} from '../../entities/application/api/onboarding'
import {savePending} from '../../shared/lib/operations'
import {ApiError} from '../../shared/api/http'

it.each([false,true])('名称明确拒绝后按原未知事实决定能否继续编辑，原未知=%s',async previous=>{
  const operation='e'.repeat(32)
  if(previous)savePending('jiejian.application.create',{operation,name:'原名称'})
  vi.spyOn(projectsApi,'projects').mockResolvedValue([])
  const create=vi.spyOn(workbenchApi,'create').mockRejectedValue(new ApiError('INPUT_INVALID','名称未被接纳',undefined,undefined,undefined,undefined,'NOT_ACCEPTED'))
  render(<ApplicationWorkbench onChanged={vi.fn()}/>)
  if(!previous)fireEvent.change(screen.getByLabelText('应用名称'),{target:{value:'原名称'}})
  fireEvent.click(screen.getByRole('button',{name:previous?'继续上次添加':'添加并配置连接'}))
  expect(await screen.findByText('名称未被接纳')).toBeVisible()
  expect(create).toHaveBeenCalledOnce()
  expect(screen.getByLabelText('应用名称')).toHaveValue('原名称')
  if(previous)expect(screen.getByLabelText('应用名称')).toBeDisabled()
  else expect(screen.getByLabelText('应用名称')).toBeEnabled()
})

it('名称按Unicode字符计数，过长时就地定位且不发送请求',async()=>{
  const create=vi.spyOn(workbenchApi,'create')
  render(<ApplicationWorkbench onChanged={vi.fn()}/>)
  fireEvent.change(screen.getByLabelText('应用名称'),{target:{value:'𠮷'.repeat(129)}})
  fireEvent.click(screen.getByRole('button',{name:'添加并配置连接'}))
  expect(await screen.findByText('应用名称需为 1—128 个字符。')).toBeVisible()
  expect(screen.getByLabelText('应用名称')).toHaveFocus()
  expect(create).not.toHaveBeenCalled()
})

beforeEach(()=>{vi.spyOn(projectsApi,'understanding').mockResolvedValue({project_id:'app',source_root:'D:\\review\\orders',source_analysis_authorized:false,analysis_completed_at_us:null} as never)})
afterEach(()=>{vi.restoreAllMocks();sessionStorage.clear();discardProjectEditorDrafts('app')})

const environment=(revision:number,name:string):ApplicationEnvironment=>({environment_id:'env',revision,name,target:{base_url:'http://127.0.0.1:18081',allowed_origins:['http://127.0.0.1:18081'],allowed_hosts:['127.0.0.1'],allowed_ports:[18081],allow_private_network:true},deployment_label:null,deployment_verification:'UNVERIFIED'})
const context=():EnvironmentContext=>({project_id:'app',revision:1,environments:[],active_environment:null,confirmed_endpoint:'http://127.0.0.1:10910',endpoint_reachable:null,endpoint_checked_at_us:null,source_available:true})

it('嵌入运行任务只保留当前层级的返回，回到源码后恢复应用连接回程',async()=>{
  location.hash='#/application?view=source&runtime_method=managed&project_id=app'
  vi.spyOn(workbenchApi,'environments').mockResolvedValue(context())
  vi.spyOn(projectsApi,'runtime').mockResolvedValue({project_id:'app',running:false,source_matches:false,configuration:null,operation:null})
  const start=vi.spyOn(projectsApi,'runtimeStart')
  render(<ApplicationWorkbench selected={{project_id:'app',name:'订单'}} onChanged={vi.fn()}/>)
  expect(await screen.findByRole('button',{name:'返回源码设置'})).toBeVisible()
  expect(screen.getByRole('heading',{level:1,name:'准备应用的本地运行'})).toBeVisible()
  await waitFor(()=>expect(screen.queryByRole('heading',{level:1,name:'应用与来源'})).not.toBeInTheDocument())
  expect(screen.getByRole('tablist',{name:'应用资料'})).toBeVisible()
  expect(screen.getByRole('tab',{name:'应用连接'})).toHaveAttribute('aria-selected','true')
  expect(screen.queryByRole('button',{name:'返回应用连接'})).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button',{name:'返回源码设置'}))
  expect(screen.getAllByRole('button',{name:'返回应用连接'})).toHaveLength(1)
  expect(await screen.findByRole('heading',{level:1,name:'应用与来源'})).toBeVisible()
  expect(screen.getByRole('tablist',{name:'应用资料'})).toBeVisible()
  expect(screen.queryByRole('button',{name:'返回源码设置'})).not.toBeInTheDocument()
  expect(start).not.toHaveBeenCalled()
})

it.each([['接口来源','sources'],['业务角色与操作','business']])('运行任务保留二级入口：%s',async(label,view)=>{
  location.hash='#/application?view=source&runtime_method=managed&project_id=app'
  vi.spyOn(workbenchApi,'environments').mockResolvedValue(context())
  vi.spyOn(projectsApi,'runtime').mockResolvedValue({project_id:'app',running:false,source_matches:false,configuration:null,operation:null})
  const start=vi.spyOn(projectsApi,'runtimeStart')
  render(<ApplicationWorkbench selected={{project_id:'app',name:'订单'}} onChanged={vi.fn()}/>)
  await screen.findByRole('heading',{level:1,name:'准备应用的本地运行'})
  fireEvent.click(screen.getByRole('tab',{name:label}))
  const destination=new URLSearchParams(location.hash.split('?')[1])
  expect(destination.get('view')).toBe(view)
  expect(destination.get('project_id')).toBe('app')
  expect(start).not.toHaveBeenCalled()
})

it.each([true,false])('继续上次添加先查已有记录，未完成时沿用原内容和请求；已存在=%s',async exists=>{
  const operation='a'.repeat(32),item={project_id:'app_'+operation,name:'原应用'}
  savePending('jiejian.application.create',{operation,name:item.name})
  vi.spyOn(projectsApi,'projects').mockResolvedValue(exists?[item] as never:[])
  const create=vi.spyOn(workbenchApi,'create').mockResolvedValue(item as never),changed=vi.fn()
  render(<ApplicationWorkbench onChanged={changed}/>)
  expect(screen.getByRole('textbox',{name:'应用名称'})).toHaveValue('原应用')
  expect(screen.getByRole('textbox',{name:'应用名称'})).toBeDisabled()
  fireEvent.click(screen.getByRole('button',{name:'继续上次添加'}))
  await waitFor(()=>expect(changed).toHaveBeenCalledWith(item.project_id))
  if(exists)expect(create).not.toHaveBeenCalled()
  else expect(create).toHaveBeenCalledExactlyOnceWith(operation,item.name)
})

it('运行地址确认失败留在当前运行任务，返回源码不把失败当作源码错误',async()=>{
  location.hash='#/application?view=source&runtime_method=managed&project_id=app'
  vi.spyOn(workbenchApi,'environments').mockResolvedValue(context())
  vi.spyOn(projectsApi,'readiness').mockResolvedValue({project_id:'app',items:[]} as never)
  vi.spyOn(projectsApi,'confirmEndpoint').mockRejectedValue(new Error('地址核对未完成，原检查连接保留。'))
  render(<ApplicationWorkbench selected={{project_id:'app',name:'订单'}} onChanged={vi.fn()}/> )
  fireEvent.change(await screen.findByRole('textbox',{name:'应用地址'}),{target:{value:'http://127.0.0.1:18081'}})
  fireEvent.click(await screen.findByRole('button',{name:'使用此地址'}))
  const error=await screen.findByRole('alert')
  expect(screen.getByRole('region',{name:'准备应用的本地运行'})).toContainElement(error)
  fireEvent.click(screen.getByRole('button',{name:'返回源码设置'}))
  await screen.findByRole('heading',{level:1,name:'应用与来源'})
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
})

it('空环境直接配置，保存后只形成记录，不隐式采用或发送核验请求',async()=>{
  location.hash='#/application?project_id=app'
  const data=context()
  vi.spyOn(workbenchApi,'environments').mockImplementation(async()=>({...data}))
  const write=vi.spyOn(workbenchApi,'saveEnvironment').mockImplementation(async(_project,configuration)=>{data.environments=[{configuration,created_at_us:1}];return {}})
  const activate=vi.spyOn(workbenchApi,'activateEnvironment'),probe=vi.spyOn(projectsApi,'confirmEndpoint')
  render(<ApplicationWorkbench selected={{project_id:'app'}} onChanged={vi.fn()}/>)
  expect(await screen.findByLabelText('连接名称')).toBeVisible()
  expect(screen.getByRole('heading',{name:'新增检查连接'})).toBeVisible()
  expect(screen.getByText('当前运行地址')).toBeVisible()
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(screen.queryByLabelText('已保存的连接')).not.toBeInTheDocument()
  expect(screen.queryByText('接口资料只提供调查线索；实际执行仍需要确认权限要求、主体、资源与操作范围。')).not.toBeInTheDocument()
  fireEvent.change(screen.getByLabelText('连接名称'),{target:{value:'回归环境'}})
  fireEvent.change(screen.getByLabelText('应用地址'),{target:{value:'http://127.0.0.1:18081'}})
  fireEvent.click(screen.getByText('部署说明与请求限制'))
  fireEvent.change(screen.getByLabelText('每次检查请求上限'),{target:{value:'200'}})
  fireEvent.click(screen.getByRole('button',{name:'保存连接'}))
  await waitFor(()=>expect(write).toHaveBeenCalledTimes(1))
  expect(write.mock.calls[0][1].target.max_requests).toBe(200)
  expect(await screen.findByRole('heading',{name:'回归环境'})).toBeVisible()
  expect(screen.getByRole('button',{name:'使用此连接'})).toBeEnabled()
  expect(activate).not.toHaveBeenCalled();expect(probe).not.toHaveBeenCalled()
})

it('采用旧修订与保存新修订分别呈现，编辑与取消不改变当前使用事实',async()=>{
  location.hash='#/application?project_id=app'
  const old=environment(1,'正在使用的版本'),latest=environment(2,'新保存的版本')
  vi.spyOn(workbenchApi,'environments').mockResolvedValue({...context(),active_environment:old,environments:[{configuration:latest,created_at_us:1}]})
  const activate=vi.spyOn(workbenchApi,'activateEnvironment'),write=vi.spyOn(workbenchApi,'saveEnvironment')
  render(<ApplicationWorkbench selected={{project_id:'app'}} onChanged={vi.fn()}/>)
  const oldCard=(await screen.findByRole('heading',{name:old.name})).closest('section')!
  const newCard=screen.getByRole('heading',{name:latest.name}).closest('section')!
  expect(within(oldCard).getByText('当前使用')).toBeVisible()
  expect(within(newCard).queryByText('当前使用')).not.toBeInTheDocument()
  fireEvent.click(within(newCard).getByRole('button',{name:'编辑'}))
  expect(screen.getByRole('dialog',{name:'修改检查连接'})).toBeVisible()
  expect(screen.getByLabelText('连接名称')).toHaveValue(latest.name)
  fireEvent.change(screen.getByLabelText('连接名称'),{target:{value:'尚未保存'}})
  fireEvent.click(screen.getByRole('button',{name:'取消编辑'}))
  expect(within(screen.getByRole('heading',{name:old.name}).closest('section')!).getByText('当前使用')).toBeVisible()
  expect(write).not.toHaveBeenCalled();expect(activate).not.toHaveBeenCalled()
})


it('跨分类保留结果判断草稿的回程，返回不会保存连接',async()=>{
  const origin='/preparation?proof_sources=1&configure=new&action_id=read'
  location.hash='#/application?'+new URLSearchParams({view:'environment',return_to:origin,project_id:'app'})
  vi.spyOn(workbenchApi,'environments').mockResolvedValue(context())
  const save=vi.spyOn(workbenchApi,'saveEnvironment')
  const {rerender}=render(<ApplicationWorkbench selected={{project_id:'app'}} onChanged={vi.fn()}/>)
  expect(await screen.findByRole('link',{name:'返回结果判断草稿'})).toBeVisible()
  fireEvent.click(await screen.findByRole('button',{name:'源码与运行设置'}))
  expect(new URLSearchParams(location.hash.split('?')[1]).get('return_to')).toBe(origin)
  rerender(<ApplicationWorkbench selected={{project_id:'app'}} onChanged={vi.fn()}/>)
  fireEvent.click(screen.getByRole('link',{name:'返回结果判断草稿'}))
  expect(new URLSearchParams(location.hash.split('?')[1]).get('configure')).toBe('new')
  expect(save).not.toHaveBeenCalled()
})

it('给已有应用补充源码：选择只填入目录，取消与不可用保留输入，确认仍归原项目',async()=>{
 location.hash='#/application?view=source&project_id=app'
 vi.spyOn(workbenchApi,'environments').mockResolvedValue({...context(),source_available:false})
 const picker=vi.spyOn(onboardingApi,'selectFolder').mockResolvedValueOnce({status:'selected',path:'D:\\review\\orders'}).mockResolvedValueOnce({status:'cancelled'}).mockResolvedValueOnce({status:'unavailable',message:'目录选择不可用，请粘贴路径。'})
 const attach=vi.spyOn(workbenchApi,'attachSource').mockResolvedValue({} as never)
 const create=vi.spyOn(workbenchApi,'create'),inspect=vi.spyOn(onboardingApi,'inspect'),changed=vi.fn()
 render(<ApplicationWorkbench selected={{project_id:'app',name:'订单系统'}} onChanged={changed}/>)
 expect(await screen.findByRole('heading',{name:'为当前应用补充源码'})).toBeVisible()
 fireEvent.click(screen.getByRole('button',{name:'选择文件夹'}))
 const input=screen.getByRole('textbox',{name:'这个应用的源码目录'})
 await waitFor(()=>expect(input).toHaveValue('D:\\review\\orders'))
 expect(attach).not.toHaveBeenCalled();expect(create).not.toHaveBeenCalled();expect(inspect).not.toHaveBeenCalled()
 fireEvent.click(screen.getByRole('button',{name:'选择文件夹'}))
 await waitFor(()=>expect(picker).toHaveBeenCalledTimes(2))
 await waitFor(()=>expect(screen.getByRole('button',{name:'选择文件夹'})).toBeEnabled())
 expect(input).toHaveValue('D:\\review\\orders')
 fireEvent.click(screen.getByRole('button',{name:'选择文件夹'}))
 expect(await screen.findByRole('alert')).toHaveTextContent('目录选择不可用')
 expect(input).toHaveValue('D:\\review\\orders')
 fireEvent.click(screen.getByRole('button',{name:'补充源码目录'}))
 await waitFor(()=>expect(attach).toHaveBeenCalledWith('app','D:\\review\\orders',1))
 expect(create).not.toHaveBeenCalled();expect(inspect).not.toHaveBeenCalled()
 expect(changed).toHaveBeenCalledWith('app')
})

it('切换连接先看影响，取消不写；确认绑定原预览依据',async()=>{
  location.hash='#/application?view=environment'
  const chosen:ApplicationEnvironment={environment_id:'env_other',revision:2,name:'修复后的部署',target:{base_url:'http://127.0.0.1:18082',allowed_origins:[],allowed_hosts:[],allowed_ports:[],allow_private_network:true},deployment_label:null,deployment_verification:'UNVERIFIED'}
  vi.spyOn(workbenchApi,'environments').mockResolvedValue({project_id:'app',revision:3,active_environment:null,environments:[{configuration:chosen,created_at_us:0}],source_available:false,confirmed_endpoint:'http://127.0.0.1:18081',endpoint_reachable:null,endpoint_checked_at_us:null})
  const preview=vi.spyOn(workbenchApi,'previewActivation').mockResolvedValue({project_id:'app',expected_revision:3,impact_fingerprint:'fingerprint',previous:null,previous_endpoint:'http://127.0.0.1:18081',chosen,changed:true,materials:{state:'RECHECK_REQUIRED',items:[{action_id:'read',action_label:'查看订单备注',action_revision:1,kind:'identity',status:'SATISFIED',reason_codes:[]}]},retained:['已有检查报告'],can_activate:true})
  const write=vi.spyOn(workbenchApi,'activateEnvironment').mockResolvedValue({} as never)
  render(<ApplicationWorkbench selected={{project_id:'app',name:'订单',source_root:null} as never} onChanged={vi.fn()}/>)
  fireEvent.click(await screen.findByRole('button',{name:'使用此连接'}))
  expect(await screen.findByRole('dialog',{name:'使用这份检查连接'})).toHaveTextContent('查看订单备注测试账号')
  expect(write).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button',{name:'保留当前连接'}))
  expect(write).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button',{name:'使用此连接'}))
  await screen.findByRole('dialog',{name:'使用这份检查连接'})
  fireEvent.click(screen.getByRole('button',{name:'确认切换连接'}))
  await waitFor(()=>expect(write).toHaveBeenCalledWith('app','env_other',2,3,'fingerprint'))
  expect(preview).toHaveBeenCalledTimes(2)
})
