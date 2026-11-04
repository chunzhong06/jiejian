import {fireEvent,render,screen,waitFor} from '@testing-library/react'
import {expect,it,vi} from 'vitest'
import {SourceLibrary} from './SourceLibrary'
import {workbenchApi as api,type ApiSource,type ImportPreview,type SourcesContext} from '../../entities/application/api/workbench'
import {businessBoundariesApi} from '../../entities/permission/api/businessBoundaries'

it('来源保存回执未知时读取准确修订，已保存内容不再写入',async()=>{
  const item={item_id:'request',method:'GET',path:'/orders/{id}',label:'订单',pointer:'#/paths/orders/get',parameters:[]}
  const preview:ImportPreview={candidate_id:'candidate',requests:[item],warnings:[],fingerprint:'f'.repeat(64),previous_revision:0,added:['request'],removed:[],changed:[]}
  const source:ApiSource={source_id:'source',revision:1,kind:'OPENAPI',name:'订单接口',requests:[item],warnings:[],created_at_us:1}
  sessionStorage.setItem('jiejian.source-import:app',JSON.stringify({sourceId:'source',name:source.name,preview}))
  vi.spyOn(api,'sources').mockResolvedValue({project_id:'app',sources:[source],annotations:[],request_references:[]})
  vi.spyOn(businessBoundariesApi,'current').mockResolvedValue({project_id:'app',policy_epoch:1,actors:[],actions:[],permission_intents:[],actor_bindings:[],action_bindings:[],permission_statuses:[]})
  const receipt=vi.spyOn(api,'sourceRevision').mockResolvedValue(source),write=vi.spyOn(api,'accept')
  render(<SourceLibrary projectId="app"/> )
  fireEvent.click(await screen.findByRole('button',{name:'核对原保存'}))
  fireEvent.click(await screen.findByRole('button',{name:'核对原保存'}))
  await waitFor(()=>expect(receipt).toHaveBeenCalledWith('app','source',1))
  await waitFor(()=>expect(sessionStorage.getItem('jiejian.source-import:app')).toBeNull())
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
  await screen.findByRole('button',{name:'关联业务动作'})
  expect(screen.queryByLabelText('请求名称')).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button',{name:'关联业务动作'}))
  fireEvent.change(screen.getByLabelText('请求名称'),{target:{value:'查看订单详情'}})
  fireEvent.click(screen.getByRole('button',{name:'查看请求：客户资料'}))
  fireEvent.click(screen.getByRole('button',{name:'查看请求：订单资料'}))
  expect(screen.getByLabelText('请求名称')).toHaveValue('查看订单详情')
  fireEvent.mouseDown(screen.getByRole('combobox',{name:'对应业务动作'}))
  fireEvent.click(await screen.findByRole('option',{name:'读取订单'}))
  fireEvent.click(screen.getByRole('button',{name:'保存业务关联'}))
  await waitFor(()=>expect(save).toHaveBeenCalledWith('app','source','orders','查看订单详情','action',3))
  await screen.findByRole('heading',{name:'查看订单详情'})
  expect(screen.queryByLabelText('请求名称')).not.toBeInTheDocument()
  fireEvent.click(screen.getByText('来源信息',{exact:true}))
  fireEvent.click(screen.getByRole('button',{name:'更新来源并查看差异'}))
  expect(screen.getByRole('combobox',{name:'保存到'}).closest('.jj-choice')).toHaveAttribute('data-value','source')
})
