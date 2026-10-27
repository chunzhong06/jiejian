import {useState} from 'react'
import {fireEvent,render,screen,waitFor,within} from '@testing-library/react'
import {expect,it,vi} from 'vitest'
import {Button} from './actions'
import {Choice} from './Choice'
import {Dialog} from './Dialog'
import {InfoPopover} from './InfoPopover'
import {Tabs} from './Tabs'

it('提交期间按钮不可再次激活，并保留可访问状态',()=>{
  const action=vi.fn()
  render(<Button busy onClick={action}>提交检查</Button>)
  const button=screen.getByRole('button',{name:'提交检查'})
  fireEvent.click(button)
  expect(button).toBeDisabled();expect(button).toHaveAttribute('aria-busy','true');expect(action).not.toHaveBeenCalled()
})

it('选择菜单展开后将所选值交给业务调用方',async()=>{
  const change=vi.fn()
  render(<Choice aria-label="当前应用" value="a" onValueChange={change}><option value="a">应用 A</option><option value="b">应用 B</option></Choice>)
  const input=screen.getByRole('combobox')
  fireEvent.mouseDown(input)
  fireEvent.click(await screen.findByRole('option',{name:'应用 B'}))
  expect(change).toHaveBeenCalledWith('b',expect.anything())
})

it('页签键盘切换同步选中值和焦点',()=>{
  const change=vi.fn()
  render(<Tabs label="检查依据" value="result" onValueChange={change} items={[{value:'result',label:'业务结果'},{value:'trace',label:'操作经过'}]}/>)
  fireEvent.keyDown(screen.getByRole('tab',{name:'业务结果'}),{key:'ArrowRight'})
  expect(change).toHaveBeenCalledWith('trace')
  expect(screen.getByRole('tab',{name:'操作经过'})).toHaveFocus()
})

it('附着运行信息浮层可关闭，并把焦点返回入口',async()=>{
  render(<InfoPopover label="本地运行环境" trigger={<button>运行状态</button>}><p>执行服务可用</p></InfoPopover>)
  const trigger=screen.getByRole('button',{name:'运行状态'})
  fireEvent.click(trigger)
  await screen.findByRole('dialog',{name:'本地运行环境'})
  fireEvent.keyDown(document,{key:'Escape'})
  await waitFor(()=>expect(screen.queryByRole('dialog',{name:'本地运行环境'})).not.toBeInTheDocument())
  expect(trigger).toHaveFocus()
})

it('取消对话框不会执行提交，并在退出后返回原入口',async()=>{
  const submit=vi.fn()
  function Scene(){const [open,setOpen]=useState(false);return <><button onClick={()=>setOpen(true)}>准备操作</button>{open&&<Dialog title="确认操作" onClose={()=>setOpen(false)} actions={dismiss=><><Button onClick={dismiss}>取消</Button><Button onClick={submit}>确认</Button></>}>核对本次操作</Dialog>}</>}
  render(<Scene/>)
  const trigger=screen.getByRole('button',{name:'准备操作'})
  trigger.focus();fireEvent.click(trigger)
  fireEvent.click(within(screen.getByRole('dialog')).getByRole('button',{name:'取消'}))
  await waitFor(()=>expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  expect(submit).not.toHaveBeenCalled();expect(trigger).toHaveFocus()
})
