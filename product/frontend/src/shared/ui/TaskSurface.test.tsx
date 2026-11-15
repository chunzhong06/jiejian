import {useState} from 'react'
import {fireEvent,render,screen,waitFor} from '@testing-library/react'
import {expect,it,vi} from 'vitest'
import {TaskSurface} from './TaskSurface'

it('进入独立任务聚焦标题，提交中禁止返回，结束后返回原入口',async()=>{
 const scroll=vi.spyOn(window,'scrollTo').mockImplementation(()=>{})
 function Example(){const [open,setOpen]=useState(false),[busy,setBusy]=useState(false);return <main><div hidden={open}><button onClick={()=>setOpen(true)}>核对并继续</button></div>{open&&<TaskSurface title="审阅实际范围" onBack={()=>setOpen(false)} backDisabled={busy}><button onClick={()=>setBusy(!busy)}>{busy?'结束提交':'开始提交'}</button></TaskSurface>}</main>}
 try{
  render(<Example/>);const origin=screen.getByRole('button',{name:'核对并继续'});origin.focus();fireEvent.click(origin)
  expect(screen.getByRole('heading',{name:'审阅实际范围'})).toHaveFocus()
  fireEvent.click(screen.getByRole('button',{name:'开始提交'}));expect(screen.getByRole('button',{name:'返回原工作'})).toBeDisabled()
  fireEvent.click(screen.getByRole('button',{name:'结束提交'}));fireEvent.click(screen.getByRole('button',{name:'返回原工作'}))
  await waitFor(()=>expect(origin).toHaveFocus());expect(origin).toBeVisible()
 }finally{scroll.mockRestore()}
})
