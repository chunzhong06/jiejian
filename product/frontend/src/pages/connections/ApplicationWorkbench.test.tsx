import {fireEvent,render,screen,waitFor,within} from '@testing-library/react'
import {expect,it,vi} from 'vitest'
import {ApplicationWorkbench} from './ApplicationWorkbench'
import {workbenchApi,type ApplicationEnvironment,type EnvironmentContext} from '../../entities/application/api/workbench'
import {projectsApi} from '../../entities/application/api/projects'

const environment=(revision:number,name:string):ApplicationEnvironment=>({environment_id:'env',revision,name,target:{base_url:'http://127.0.0.1:18081',allowed_origins:['http://127.0.0.1:18081'],allowed_hosts:['127.0.0.1'],allowed_ports:[18081],allow_private_network:true},deployment_label:null,deployment_verification:'UNVERIFIED'})
const context=():EnvironmentContext=>({project_id:'app',revision:1,environments:[],active_environment:null,confirmed_endpoint:'http://127.0.0.1:10910',endpoint_reachable:null,endpoint_checked_at_us:null,source_available:true})

it('空环境直接配置，保存后只形成记录，不隐式采用或发送核验请求',async()=>{
  location.hash='#/application?project_id=app'
  const data=context()
  vi.spyOn(workbenchApi,'environments').mockImplementation(async()=>({...data}))
  const write=vi.spyOn(workbenchApi,'saveEnvironment').mockImplementation(async(_project,configuration)=>{data.environments=[{configuration,created_at_us:1}];return {}})
  const activate=vi.spyOn(workbenchApi,'activateEnvironment'),probe=vi.spyOn(projectsApi,'confirmEndpoint')
  render(<ApplicationWorkbench selected={{project_id:'app'}} onChanged={vi.fn()}/>)
  expect(await screen.findByRole('heading',{name:'添加环境'})).toBeVisible()
  expect(screen.queryByLabelText('已保存的环境')).not.toBeInTheDocument()
  expect(screen.queryByText('接口资料只提供调查线索；实际执行仍需要确认权限要求、主体、资源与操作范围。')).not.toBeInTheDocument()
  fireEvent.change(screen.getByLabelText('环境名称'),{target:{value:'回归环境'}})
  fireEvent.change(screen.getByLabelText('应用地址'),{target:{value:'http://127.0.0.1:18081'}})
  fireEvent.click(screen.getByRole('button',{name:'保存环境'}))
  await waitFor(()=>expect(write).toHaveBeenCalledTimes(1))
  expect(await screen.findByRole('heading',{name:'回归环境'})).toBeVisible()
  expect(screen.getByRole('button',{name:'切换到此环境'})).toBeEnabled()
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
  expect(screen.queryByLabelText('已保存的环境')).not.toBeInTheDocument()
  expect(screen.getByLabelText('环境名称')).toHaveValue(latest.name)
  fireEvent.change(screen.getByLabelText('环境名称'),{target:{value:'尚未保存'}})
  fireEvent.click(screen.getByRole('button',{name:'取消编辑'}))
  expect(within(screen.getByRole('heading',{name:old.name}).closest('section')!).getByText('当前使用')).toBeVisible()
  expect(write).not.toHaveBeenCalled();expect(activate).not.toHaveBeenCalled()
})
