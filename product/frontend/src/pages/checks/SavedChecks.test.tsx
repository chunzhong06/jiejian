import {fireEvent,render,screen,waitFor} from '@testing-library/react'
import {afterEach,expect,it,vi} from 'vitest'
import {SavedChecks} from './SavedChecks'

afterEach(()=>vi.unstubAllGlobals())
const response=(data:unknown)=>new Response(JSON.stringify({schema_version:'1',data}))

it('沿用当前方案，规则变化的方案不会偷偷替换本次选择',async()=>{
  const refs=[{intent_id:'deny',revision:1,intent_hash:'hash'}],change=vi.fn()
  vi.stubGlobal('fetch',vi.fn(async()=>response([
    {routine_id:'current',name:'成员访问检查',current:true,selected_permissions:refs},
    {routine_id:'stale',name:'旧检查范围',current:false,stale_intents:['deny'],selected_permissions:refs},
  ])))
  render(<SavedChecks projectId="app" selected={null} disabled={false} onChange={change}/>)
  const choice=await screen.findByRole('combobox',{name:'沿用检查范围'})
  fireEvent.mouseDown(choice)
  fireEvent.click(await screen.findByText('成员访问检查'))
  expect(change).toHaveBeenCalledWith(refs)
  change.mockClear()
  fireEvent.mouseDown(choice)
  fireEvent.click(await screen.findByText('旧检查范围（需要重新选择）'))
  expect(await screen.findByText(/部分规则已变化/)).toBeVisible()
  expect(change).not.toHaveBeenCalled()
})

it('保存结果未知时沿用原请求，不把保存方案当作提交检查',async()=>{
  const identifiers:string[]=[]
  vi.stubGlobal('fetch',vi.fn(async(input:RequestInfo|URL,init?:RequestInit)=>{
    expect(String(input)).toBe('/api/projects/app/check-routines')
    if(init?.method==='POST'){
      const body=JSON.parse(String(init.body));identifiers.push(body.operation_id)
      expect(body.selected_permissions).toBeNull()
      return new Response(JSON.stringify({schema_version:'1',error:{code:'UNKNOWN',message:'保存结果未知'}}),{status:503})
    }
    return response([])
  }))
  render(<SavedChecks projectId="app" selected={null} disabled={false} onChange={vi.fn()}/>)
  fireEvent.click(screen.getByRole('button',{name:'记住当前选择'}))
  expect(await screen.findByText('保存结果未知')).toBeVisible()
  fireEvent.click(screen.getByRole('button',{name:'核对上次保存'}))
  await waitFor(()=>expect(identifiers).toHaveLength(2))
  expect(identifiers[0]).toBe(identifiers[1])
})
