import {fireEvent,render,screen,waitFor} from '@testing-library/react'
import {afterEach,expect,it,vi} from 'vitest'
import {Testing} from './Testing'
import {operationFlowsApi} from '../../entities/preparation/api/operationFlows'
import {preparationApi} from '../../entities/preparation/api/preparation'

afterEach(()=>vi.restoreAllMocks())
it('目录离开后恢复搜索、选中项和焦点，材料入口携带准确回程',async()=>{
  sessionStorage.clear()
  const action={action_id:'read',revision:1,label:'读取订单',state_changing:false,effects:[]}
  vi.spyOn(operationFlowsApi,'summary').mockResolvedValue({project_id:'directory-app',actions:[action],flows:[]})
  vi.spyOn(preparationApi,'get').mockResolvedValue({project_id:'directory-app',actions:[]} as never)
  vi.spyOn(window,'scrollTo').mockImplementation(()=>{})
  const props={projectId:'directory-app',name:'订单',official:false,refresh:vi.fn(),onError:vi.fn(),route:{path:'/testing',query:new URLSearchParams()}}
  const first=render(<Testing {...props}/>)
  const search=await screen.findByRole('searchbox',{name:'查找业务操作'})
  fireEvent.change(search,{target:{value:'订单'}})
  fireEvent.click(screen.getByRole('button',{name:/读取订单/}))
  const link=screen.getByRole('link',{name:'准备与核对材料'})
  const target=new URLSearchParams(link.getAttribute('href')!.split('?')[1])
  expect(target.get('action_id')).toBe('read')
  expect(target.get('return_to')).toBe('/testing')
  fireEvent.click(link)
  first.unmount()
  render(<Testing {...props}/>)
  expect(await screen.findByRole('searchbox',{name:'查找业务操作'})).toHaveValue('订单')
  const selected=screen.getByRole('button',{name:/读取订单/})
  expect(selected).toHaveAttribute('aria-pressed','true')
  await waitFor(()=>expect(selected).toHaveFocus())
})
