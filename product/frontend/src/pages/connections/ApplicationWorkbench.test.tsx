import {fireEvent,render,screen,waitFor,within} from '@testing-library/react'
import {afterEach,beforeEach,expect,it,vi} from 'vitest'
import {ApplicationWorkbench} from './ApplicationWorkbench'
import {workbenchApi,type ApplicationEnvironment,type EnvironmentContext} from '../../entities/application/api/workbench'
import {projectsApi} from '../../entities/application/api/projects'
import {onboardingApi} from '../../entities/application/api/onboarding'
import {savePending} from '../../shared/lib/operations'

beforeEach(()=>{vi.spyOn(projectsApi,'understanding').mockResolvedValue({project_id:'app',source_root:'D:\\review\\orders',source_analysis_authorized:false,analysis_completed_at_us:null} as never)})
afterEach(()=>{vi.restoreAllMocks();sessionStorage.clear()})

const environment=(revision:number,name:string):ApplicationEnvironment=>({environment_id:'env',revision,name,target:{base_url:'http://127.0.0.1:18081',allowed_origins:['http://127.0.0.1:18081'],allowed_hosts:['127.0.0.1'],allowed_ports:[18081],allow_private_network:true},deployment_label:null,deployment_verification:'UNVERIFIED'})
const context=():EnvironmentContext=>({project_id:'app',revision:1,environments:[],active_environment:null,confirmed_endpoint:'http://127.0.0.1:10910',endpoint_reachable:null,endpoint_checked_at_us:null,source_available:true})

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

it('空环境直接配置，保存后只形成记录，不隐式采用或发送核验请求',async()=>{
  location.hash='#/application?project_id=app'
  const data=context()
  vi.spyOn(workbenchApi,'environments').mockImplementation(async()=>({...data}))
  const write=vi.spyOn(workbenchApi,'saveEnvironment').mockImplementation(async(_project,configuration)=>{data.environments=[{configuration,created_at_us:1}];return {}})
  const activate=vi.spyOn(workbenchApi,'activateEnvironment'),probe=vi.spyOn(projectsApi,'confirmEndpoint')
  render(<ApplicationWorkbench selected={{project_id:'app'}} onChanged={vi.fn()}/>)
  expect(await screen.findByRole('heading',{name:'添加连接'})).toBeVisible()
  expect(screen.queryByLabelText('已保存的连接')).not.toBeInTheDocument()
  expect(screen.queryByText('接口资料只提供调查线索；实际执行仍需要确认权限要求、主体、资源与操作范围。')).not.toBeInTheDocument()
  fireEvent.change(screen.getByLabelText('连接名称'),{target:{value:'回归环境'}})
  fireEvent.change(screen.getByLabelText('应用地址'),{target:{value:'http://127.0.0.1:18081'}})
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
  expect(screen.queryByLabelText('已保存的连接')).not.toBeInTheDocument()
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
