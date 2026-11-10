import {fireEvent,render,screen,waitFor} from '@testing-library/react'
import {afterEach,beforeEach,expect,it,vi} from 'vitest'
import {SourceLibrary} from './SourceLibrary'
import {workbenchApi as api,type ApiSource,type ImportPreview,type SourcesContext} from '../../entities/application/api/workbench'
import {businessBoundariesApi} from '../../entities/permission/api/businessBoundaries'
import {discardProjectEditorDrafts} from '../../entities/runtime/model/handoff'

beforeEach(()=>{location.hash='#/application?view=sources&project_id=app';sessionStorage.clear()})
afterEach(()=>discardProjectEditorDrafts('app'))

it('选文件只读取本地内容，预览后无效替换仍保留原候选且不自动接受',async()=>{
  sessionStorage.clear()
  vi.spyOn(api,'sources').mockResolvedValue({project_id:'app',sources:[],annotations:[],request_references:[]})
  vi.spyOn(businessBoundariesApi,'current').mockResolvedValue({actions:[]} as never)
  const preview=vi.spyOn(api,'preview').mockResolvedValue({candidate_id:'candidate',requests:[],warnings:[],fingerprint:'f'.repeat(64),previous_revision:0,added:[],removed:[],changed:[]})
  const accept=vi.spyOn(api,'accept')
  render(<SourceLibrary projectId="app"/>)
  fireEvent.click(await screen.findByRole('button',{name:'导入接口资料或请求'}))
  const picker=screen.getByRole('group',{name:'JSON 文件'}),input=picker.querySelector('input[type=file]')!
  const file=new File(['{}'],'orders.json',{type:'application/json'})
  Object.defineProperty(file,'text',{value:async()=>'source-content'})
  fireEvent.change(input,{target:{files:[file]}})
  await screen.findByRole('button',{name:'更换JSON 文件'})
  expect(preview).not.toHaveBeenCalled();expect(accept).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button',{name:'预览导入内容'}))
  await screen.findByRole('heading',{name:'本次变化'})
  expect(preview).toHaveBeenCalledExactlyOnceWith('app','source-content','OPENAPI',undefined)
  fireEvent.change(input,{target:{files:[new File(['wrong'],'wrong.txt')]}})
  expect(screen.getByRole('alert')).toBeVisible()
  expect(screen.getByText('orders.json')).toBeVisible()
  expect(screen.getByRole('heading',{name:'本次变化'})).toBeVisible()
  expect(accept).not.toHaveBeenCalled()
})

it('来源保存回执未知时读取准确修订，已保存内容不再写入',async()=>{
  const item={item_id:'request',method:'GET',path:'/orders/{id}',label:'订单',pointer:'#/paths/orders/get',parameters:[]}
  const preview:ImportPreview={candidate_id:'candidate',requests:[item],warnings:[],fingerprint:'f'.repeat(64),previous_revision:0,added:['request'],removed:[],changed:[]}
  const source:ApiSource={source_id:'source',revision:1,kind:'OPENAPI',name:'订单接口',requests:[item],warnings:[],created_at_us:1}
  sessionStorage.setItem('jiejian.source-import:app',JSON.stringify({sourceId:'source',name:source.name,preview}))
  vi.spyOn(api,'sources').mockResolvedValue({project_id:'app',sources:[source],annotations:[],request_references:[]})
  vi.spyOn(businessBoundariesApi,'current').mockResolvedValue({project_id:'app',policy_epoch:1,actors:[],actions:[],permission_intents:[],actor_bindings:[],action_bindings:[],permission_statuses:[]})
  const receipt=vi.spyOn(api,'sourceRevision').mockResolvedValue(source),write=vi.spyOn(api,'accept')
  render(<SourceLibrary projectId="app"/> )
  fireEvent.click(await screen.findByRole('button',{name:'查看上次保存结果'}))
  fireEvent.click(await screen.findByRole('button',{name:'查看上次保存结果'}))
  await waitFor(()=>expect(receipt).toHaveBeenCalledWith('app','source',1))
  await waitFor(()=>expect(sessionStorage.getItem('jiejian.source-import:app')).toBeNull())
  expect(write).not.toHaveBeenCalled()
})

it('已核实保存后目录刷新失败仍保留修订回执和准确来源入口',async()=>{
  sessionStorage.clear()
  const item={item_id:'orders',method:'GET',path:'/orders',label:'订单',pointer:'orders',parameters:[]}
  const source:ApiSource={source_id:'saved-source',revision:3,kind:'OPENAPI',name:'订单接口',requests:[item],warnings:[],created_at_us:1}
  const preview:ImportPreview={candidate_id:'candidate',requests:[item],warnings:[],fingerprint:'f'.repeat(64),previous_revision:2,added:[],removed:[],changed:[]}
  sessionStorage.setItem('jiejian.source-import:app',JSON.stringify({sourceId:source.source_id,name:source.name,preview}))
  vi.spyOn(api,'sources').mockResolvedValueOnce({project_id:'app',sources:[],annotations:[],request_references:[]}).mockRejectedValue(new Error('目录暂不可读'))
  vi.spyOn(businessBoundariesApi,'current').mockResolvedValue({actions:[]} as never)
  vi.spyOn(api,'sourceRevision').mockResolvedValue(source)
  const write=vi.spyOn(api,'accept')
  render(<SourceLibrary projectId="app"/>)
  fireEvent.click(await screen.findByRole('button',{name:'查看上次保存结果'}))
  fireEvent.click(await screen.findByRole('button',{name:'查看上次保存结果'}))
  expect(await screen.findByText(/已保存“订单接口”第 3 修订/)).toBeVisible()
  expect(await screen.findByText(/来源目录尚未更新/)).toBeVisible()
  fireEvent.click(screen.getByRole('button',{name:'查看已保存的来源'}))
  expect(location.hash).toContain('source_id=saved-source&request_id=orders')
  expect(write).not.toHaveBeenCalled()
})

it('默认阅读请求，切换时保留关联草稿，保存沿用原修订且更新指向实际来源',async()=>{
  location.hash='#/application?view=sources&project_id=app'
  const requests=[{item_id:'orders',method:'GET',path:'/orders/{id}',label:'订单资料',pointer:'#/paths/orders/get',parameters:[]},
    {item_id:'customers',method:'GET',path:'/customers/{id}',label:'客户资料',pointer:'#/paths/customers/get',parameters:[]}]
  const source:ApiSource={source_id:'source',revision:2,kind:'OPENAPI',name:'订单 API',requests,warnings:[],created_at_us:1}
  const data:SourcesContext={project_id:'app',sources:[source],annotations:[{source_id:'source',item_id:'orders',label:'订单资料',action_id:null,revision:3}],request_references:[]}
  vi.spyOn(api,'sources').mockImplementation(async()=>({...data}))
  vi.spyOn(businessBoundariesApi,'current').mockResolvedValue({actions:[{action_id:'action',display_name:'读取订单',effective_state:'ACTIVE'}]} as never)
  const save=vi.spyOn(api,'annotate').mockImplementation(async(_project,source_id,item_id,label,action_id)=>{
    const annotation={source_id,item_id,label,action_id,revision:4};data.annotations=[annotation];return annotation
  })
  render(<SourceLibrary projectId="app"/>)
  await screen.findByRole('button',{name:'关联业务操作'})
  expect(screen.queryByLabelText('请求名称')).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button',{name:'关联业务操作'}))
  fireEvent.change(screen.getByLabelText('请求名称'),{target:{value:'查看订单详情'}})
  fireEvent.click(screen.getByRole('button',{name:'查看请求：客户资料'}))
  fireEvent.click(screen.getByRole('button',{name:'查看请求：订单资料'}))
  expect(screen.getByLabelText('请求名称')).toHaveValue('查看订单详情')
  fireEvent.mouseDown(screen.getByRole('combobox',{name:'对应业务操作'}))
  fireEvent.click(await screen.findByRole('option',{name:'读取订单'}))
  fireEvent.click(screen.getByRole('button',{name:'保存业务关联'}))
  await waitFor(()=>expect(save).toHaveBeenCalledWith('app','source','orders','查看订单详情','action',3))
  await screen.findByRole('heading',{name:'查看订单详情'})
  expect(screen.queryByLabelText('请求名称')).not.toBeInTheDocument()
  fireEvent.click(screen.getByText('来源信息',{exact:true}))
  fireEvent.click(screen.getByRole('button',{name:'更新来源并查看差异'}))
  expect(screen.getByRole('combobox',{name:'保存到'}).closest('.jj-choice')).toHaveAttribute('data-value','source')
})

function sourceContext(){
 const requests=[{item_id:'orders',method:'GET',path:'/orders',label:'订单资料',pointer:'orders',parameters:[]},{item_id:'customers',method:'GET',path:'/customers',label:'客户资料',pointer:'customers',parameters:[]}]
 return {project_id:'app',sources:[{source_id:'source',revision:1,kind:'OPENAPI',name:'业务接口',requests,warnings:[],created_at_us:1}],annotations:[{source_id:'source',item_id:'orders',label:'订单资料',action_id:null,revision:3}],request_references:[]} as SourcesContext
}

it('离开来源页后恢复原请求草稿，原始编辑内容不进入浏览器存储',async()=>{
 vi.spyOn(api,'sources').mockResolvedValue(sourceContext())
 vi.spyOn(businessBoundariesApi,'current').mockResolvedValue({actions:[]} as never)
 const first=render(<SourceLibrary projectId="app"/>)
 fireEvent.click(await screen.findByRole('button',{name:'修改名称'}))
 fireEvent.change(screen.getByLabelText('请求名称'),{target:{value:'离开后保留的订单草稿'}})
 first.unmount();render(<SourceLibrary projectId="app"/>)
 expect(await screen.findByLabelText('请求名称')).toHaveValue('离开后保留的订单草稿')
 expect(Object.values(sessionStorage).join('')).not.toContain('离开后保留的订单草稿')
})

it('筛选隐藏明确请求时保留该对象，失效请求不回退第一项',async()=>{
 location.hash='#/application?view=sources&project_id=app&source_id=source&request_id=orders'
 vi.spyOn(api,'sources').mockResolvedValue(sourceContext())
 vi.spyOn(businessBoundariesApi,'current').mockResolvedValue({actions:[]} as never)
 const view=render(<SourceLibrary projectId="app"/>)
 await screen.findByRole('heading',{name:'订单资料'})
 fireEvent.change(screen.getByRole('searchbox',{name:'查找请求'}),{target:{value:'客户'}})
 expect(await screen.findByText(/当前请求被筛选条件隐藏/)).toBeVisible()
 expect(screen.getByRole('heading',{name:'订单资料'})).toBeVisible()
 view.unmount();location.hash='#/application?view=sources&project_id=app&source_id=source&request_id=missing'
 render(<SourceLibrary projectId="app"/>)
 expect(await screen.findByText(/这条链接对应的请求已不可用/)).toBeVisible()
 expect(screen.queryByRole('heading',{name:'客户资料'})).not.toBeInTheDocument()
})

it('旧关联保存的迟到回执不清除重新打开后继续输入的草稿',async()=>{
 vi.spyOn(api,'sources').mockResolvedValue(sourceContext())
 vi.spyOn(businessBoundariesApi,'current').mockResolvedValue({actions:[]} as never)
 let finish!:(value:Awaited<ReturnType<typeof api.annotate>>)=>void
 const write=vi.spyOn(api,'annotate').mockImplementation(()=>new Promise(resolve=>{finish=resolve}))
 const first=render(<SourceLibrary projectId="app"/>)
 fireEvent.click(await screen.findByRole('button',{name:'修改名称'}))
 fireEvent.change(screen.getByLabelText('请求名称'),{target:{value:'第一次修改'}})
 fireEvent.click(screen.getByRole('button',{name:'保存请求名称'}))
 await waitFor(()=>expect(write).toHaveBeenCalledOnce())
 first.unmount();render(<SourceLibrary projectId="app"/>)
 fireEvent.change(await screen.findByLabelText('请求名称'),{target:{value:'之后继续输入的草稿'}})
 finish({source_id:'source',item_id:'orders',label:'第一次修改',action_id:null,revision:4})
 await waitFor(()=>expect(screen.getByLabelText('请求名称')).toHaveValue('之后继续输入的草稿'))
})

it('关联已保存但目录更新失败时保留回执，重新读取不重复保存',async()=>{
 vi.spyOn(api,'sources').mockResolvedValueOnce(sourceContext()).mockRejectedValue(new Error('目录暂不可读'))
 vi.spyOn(businessBoundariesApi,'current').mockResolvedValue({actions:[]} as never)
 const write=vi.spyOn(api,'annotate').mockResolvedValue({source_id:'source',item_id:'orders',label:'已保存的订单名称',action_id:null,revision:4})
 render(<SourceLibrary projectId="app"/>)
 fireEvent.click(await screen.findByRole('button',{name:'修改名称'}))
 fireEvent.change(screen.getByLabelText('请求名称'),{target:{value:'已保存的订单名称'}})
 fireEvent.click(screen.getByRole('button',{name:'保存请求名称'}))
 expect(await screen.findByText(/已保存“已保存的订单名称”的业务关联/)).toBeVisible()
 expect(await screen.findByText(/请求目录尚未更新，保存回执已保留/)).toBeVisible()
 expect(screen.getByRole('button',{name:'修改名称'})).toBeDisabled()
 fireEvent.click(screen.getByRole('button',{name:'查看此请求'}))
 expect(location.hash).toContain('source_id=source&request_id=orders')
 expect(write).toHaveBeenCalledOnce()
})
