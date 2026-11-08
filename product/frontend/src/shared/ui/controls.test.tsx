import {useState} from 'react'
import {fireEvent,render,screen,waitFor,within} from '@testing-library/react'
import {expect,it,vi} from 'vitest'
import {Button} from './actions'
import {Choice} from './Choice'
import {Dialog} from './Dialog'
import {Tabs,LinkTabs} from './Tabs'
import {Field,SectionHeading} from './layout'
import {IndexSelection} from './IndexSelection'
import {Notice} from './feedback'
import {motionMilliseconds} from '../lib/motionTiming'
import {SearchField} from './SearchField'
import {FilePicker} from './FilePicker'
import {CommandMenu} from './CommandMenu'
import {Switch} from './Switch'
import {PasswordInput} from './PasswordInput'

it('字段保留已有说明，并将提示和错误关联到实际输入',()=>{
  render(<><p id="scope-help">仅用于当前应用</p><Field label="资源名称" hint="输入业务名称" error="名称不能为空"><input aria-describedby="scope-help"/></Field></>)
  const input=screen.getByRole('textbox',{name:'资源名称'})
  expect(input).toHaveAccessibleDescription('仅用于当前应用 输入业务名称 名称不能为空')
  expect(input).toHaveAttribute('aria-invalid','true')
  expect(screen.getByRole('alert')).toHaveTextContent('名称不能为空')
})

it('即时开关保留外部确认值，忙碌时不再次改变且不提交表单',()=>{
  const change=vi.fn(),submit=vi.fn()
  const view=render(<form onSubmit={submit}><Switch label="允许开发工具接入" checked={false} onCheckedChange={change}/></form>)
  const input=screen.getByRole('switch',{name:'允许开发工具接入'})
  fireEvent.click(input)
  expect(change).toHaveBeenCalledExactlyOnceWith(true)
  expect(input).not.toBeChecked();expect(submit).not.toHaveBeenCalled()
  view.rerender(<form onSubmit={submit}><Switch label="允许开发工具接入" checked busy onCheckedChange={change}/></form>)
  fireEvent.click(input)
  expect(input).toBeChecked();expect(input).toBeDisabled()
  expect(input).toHaveAttribute('aria-busy','true');expect(change).toHaveBeenCalledOnce()
})

it('显示密码不改变内容和提交，离开字段组后自动隐藏',()=>{
  const changed=vi.fn(),submit=vi.fn()
  render(<form onSubmit={submit}><Field label="数据库密码"><PasswordInput value="ephemeral-value" onChange={changed}/></Field><button>其他操作</button></form>)
  const input=screen.getByLabelText('数据库密码')
  expect(input).toHaveAttribute('type','password')
  fireEvent.click(screen.getByRole('button',{name:'显示密码'}))
  expect(input).toHaveAttribute('type','text');expect(input).toHaveValue('ephemeral-value')
  fireEvent.blur(input,{relatedTarget:screen.getByRole('button',{name:'其他操作'})})
  expect(input).toHaveAttribute('type','password')
  expect(changed).not.toHaveBeenCalled();expect(submit).not.toHaveBeenCalled()
})

it('忙碌动作保留原图文占位及按钮元素，完成标记由实际回执驱动',()=>{
  const view=render(<Button icon={<svg data-testid="original-icon"/>}>保存业务要求</Button>)
  const button=screen.getByRole('button',{name:'保存业务要求'})
  view.rerender(<Button busy icon={<svg data-testid="original-icon"/>}>保存业务要求</Button>)
  expect(screen.getByRole('button',{name:'保存业务要求'})).toBe(button)
  expect(screen.getByTestId('original-icon')).toBeInTheDocument()
  expect(button.querySelector('.jj-button-progress')).toHaveAttribute('aria-hidden','true')
  expect(button).not.toHaveAttribute('data-complete')
  view.rerender(<Button complete>已保存</Button>)
  expect(button).toHaveAttribute('data-complete','true');expect(button).toBeEnabled()
})

it('命令菜单统一键盘展开、取消和焦点返回，取消不触发业务动作',async()=>{
  const action=vi.fn()
  render(<CommandMenu menu={{items:[{key:'work',label:'接续任务'}],onClick:action}}><Button>任务操作</Button></CommandMenu>)
  const trigger=screen.getByRole('button',{name:'任务操作'})
  trigger.focus();fireEvent.keyDown(trigger,{key:'ArrowDown'})
  fireEvent.keyDown(trigger,{key:'Escape'})
  expect(trigger).toHaveAttribute('aria-expanded','false')
  expect(trigger).toHaveFocus();expect(action).not.toHaveBeenCalled()
  fireEvent.keyDown(trigger,{key:'ArrowDown'})
  const item=await screen.findByRole('menuitem',{name:'接续任务'})
  expect(trigger).toHaveAttribute('aria-expanded','true')
  fireEvent.keyDown(item,{key:'Escape'})
  await waitFor(()=>expect(trigger).toHaveAttribute('aria-expanded','false'))
  expect(trigger).toHaveFocus();expect(action).not.toHaveBeenCalled()
})

it('菜单动作先归还焦点再打开后续任务，禁用后关闭原菜单',async()=>{
  const action=vi.fn()
  function Scene({disabled=false}:{disabled?:boolean}){const [dialog,setDialog]=useState(false);return <><CommandMenu menu={{items:[{key:'work',label:'接续任务'}],onClick:()=>{action();setDialog(true)}}}><Button disabled={disabled}>任务操作</Button></CommandMenu>{dialog&&<Dialog title="接续准备" onClose={()=>setDialog(false)}>核对资料</Dialog>}</>}
  const view=render(<Scene/>),trigger=screen.getByRole('button',{name:'任务操作'})
  trigger.focus();fireEvent.click(trigger);fireEvent.click(await screen.findByRole('menuitem',{name:'接续任务'}))
  expect(action).toHaveBeenCalledOnce()
  expect(within(screen.getByRole('dialog')).getByRole('heading',{name:'接续准备'})).toHaveFocus()
  fireEvent.click(within(screen.getByRole('dialog')).getByRole('button',{name:'关闭'}))
  await waitFor(()=>expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  expect(trigger).toHaveFocus()
  fireEvent.click(trigger);await screen.findByRole('menuitem',{name:'接续任务'})
  view.rerender(<Scene disabled/>);expect(trigger).toHaveAttribute('aria-expanded','false')
  expect(trigger).toBeDisabled();expect(action).toHaveBeenCalledOnce()
})

it('文件选择沿用系统窗口，取消不清空，选择或拖放同一文件不提交表单',async()=>{
  const changed=vi.fn(),submit=vi.fn()
  const view=render(<form onSubmit={submit}><Field label="接口资料"><FilePicker label="接口资料" maxBytes={4194304} formats="JSON" accept=".json" onFileChange={changed}/></Field></form>)
  const input=view.container.querySelector('input[type=file]')!,picker=screen.getByRole('group',{name:'接口资料'})
  const native=vi.spyOn(input as HTMLInputElement,'click')
  fireEvent.click(screen.getByRole('button',{name:'选择接口资料'}));expect(native).toHaveBeenCalledOnce()
  fireEvent.change(input,{target:{files:[]}});expect(changed).not.toHaveBeenCalled()
  const file=new File(['{}'],'orders.json',{type:'application/json'})
  fireEvent.change(input,{target:{files:[file]}})
  await waitFor(()=>expect(screen.getByRole('button',{name:'选择接口资料'})).toBeEnabled())
  fireEvent.drop(picker.firstElementChild!,{dataTransfer:{files:[file],types:['Files']}})
  await waitFor(()=>expect(changed).toHaveBeenCalledTimes(2))
  expect(changed.mock.calls).toEqual([[file],[file]]);expect(submit).not.toHaveBeenCalled()
})

it('无效替换保留原文件，拖放离开即撤销反馈，移除后回到选择入口',async()=>{
  const original=new File(['original'],'original.json'),changed=vi.fn()
  function Scene(){const [file,setFile]=useState<File|undefined>(original);return <FilePicker label="接口资料" file={file} maxBytes={8} formats="JSON" accept=".json" onFileChange={value=>{changed(value);setFile(value)}}/>}
  const view=render(<Scene/>),zone=view.container.querySelector('.jj-file-picker')!
  const transfer=(files:File[])=>({dataTransfer:{files,types:['Files']}})
  fireEvent.dragEnter(zone,transfer([]));expect(zone).toHaveAttribute('data-dragging','true')
  fireEvent.dragLeave(zone);expect(zone).not.toHaveAttribute('data-dragging')
  for(const files of [[new File(['012345678'],'too-big.json')],[new File(['text'],'wrong.txt')],[new File([''],'empty.json')],[original,original]]){
    fireEvent.drop(zone,transfer(files));expect(screen.getByRole('alert')).toBeVisible()
    expect(screen.getByText('original.json')).toBeVisible();expect(changed).not.toHaveBeenCalled()
  }
  fireEvent.click(screen.getByRole('button',{name:'移除接口资料'}))
  await waitFor(()=>expect(screen.getByRole('button',{name:'选择接口资料'})).toHaveFocus())
  expect(changed).toHaveBeenCalledExactlyOnceWith(undefined)
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
})

it('读取期间阻止重复选择和拖放，外部禁用后同样不处理文件',async()=>{
  let finish!:()=>void
  const changed=vi.fn(()=>new Promise<void>(resolve=>{finish=resolve}))
  const view=render(<FilePicker label="接口资料" maxBytes={100} onFileChange={changed}/>),input=view.container.querySelector('input[type=file]')!,zone=view.container.querySelector('.jj-file-picker')!
  const file=new File(['{}'],'orders.json'),drop={dataTransfer:{files:[file],types:['Files']}}
  fireEvent.change(input,{target:{files:[file]}});fireEvent.drop(zone,drop)
  expect(changed).toHaveBeenCalledOnce();expect(screen.getByRole('button',{name:'选择接口资料'})).toBeDisabled()
  finish();await waitFor(()=>expect(screen.getByRole('button',{name:'选择接口资料'})).toBeEnabled())
  view.rerender(<FilePicker label="接口资料" maxBytes={100} onFileChange={changed} disabled/>)
  fireEvent.drop(zone,drop);fireEvent.change(input,{target:{files:[file]}})
  expect(changed).toHaveBeenCalledOnce()
})

it('搜索清除只调整所属输入并返回焦点，提交查询仍由表单发起',()=>{
  const submit=vi.fn()
  function Scene(){const [query,setQuery]=useState('订单');return <form aria-label="检查记录查询" onSubmit={event=>{event.preventDefault();submit(query)}}><SearchField label="查找检查记录" placeholder="查找业务操作或检查编号" value={query} onValueChange={setQuery}/><Button type="submit">查找</Button></form>}
  render(<Scene/>)
  const input=screen.getByRole('searchbox',{name:'查找检查记录'})
  fireEvent.click(screen.getByRole('button',{name:'清除查找检查记录'}))
  expect(input).toHaveValue('');expect(input).toHaveFocus()
  expect(submit).not.toHaveBeenCalled()
  expect(screen.queryByRole('button',{name:'清除查找检查记录'})).not.toBeInTheDocument()
  fireEvent.change(input,{target:{value:'更新资料'}})
  expect(submit).not.toHaveBeenCalled()
  fireEvent.submit(screen.getByRole('form',{name:'检查记录查询'}))
  expect(submit).toHaveBeenCalledExactlyOnceWith('更新资料')
})

it('生产压缩后的秒与源码毫秒保持相同节奏，无效值沿用调用方回退',()=>{
  expect(motionMilliseconds('200ms')).toBe(200)
  expect(motionMilliseconds(' .2s ')).toBe(200)
  expect(motionMilliseconds('.22s')).toBe(220)
  expect(motionMilliseconds('')).toBe(0)
  expect(motionMilliseconds('invalid',100)).toBe(100)
})

it('集合标题保留语义从属关系，各自的创建操作仍归属对应集合',()=>{
  const addAction=vi.fn(),addResult=vi.fn()
  render(<><SectionHeading title="业务操作" actions={<button onClick={addAction}>添加操作</button>}/><SectionHeading title="业务结果" level={3} actions={<button onClick={addResult}>添加结果</button>}/><SectionHeading title="来源说明" level={3} appearance="group"/></>)
  const actions=screen.getByRole('heading',{name:'业务操作',level:2})
  const results=screen.getByRole('heading',{name:'业务结果',level:3})
  expect(actions.className).toBe(results.className)
  expect(screen.getByRole('heading',{name:'来源说明',level:3}).className).not.toBe(results.className)
  fireEvent.click(within(results.closest('header')!).getByRole('button',{name:'添加结果'}))
  expect(addResult).toHaveBeenCalledOnce();expect(addAction).not.toHaveBeenCalled()
  expect(within(actions.closest('header')!).getByRole('button',{name:'添加操作'})).toBeVisible()
})

it('普通通知默认中性，风险提示显式声明且保留操作与状态文字',()=>{
  const retry=vi.fn()
  render(<><Notice>资料已读取</Notice><Notice tone="caution">原回执未确认<Button kind="quiet" onClick={retry}>查询原操作</Button></Notice></>)
  expect(screen.getByText('资料已读取').closest('[role=status]')).toHaveClass('is-neutral')
  expect(screen.getByText('原回执未确认').closest('[role=status]')).toHaveClass('is-caution')
  fireEvent.click(screen.getByRole('button',{name:'查询原操作'}))
  expect(retry).toHaveBeenCalledOnce()
})

it('局部索引过滤掉当前项后清除旧选择面，保留业务按钮的状态与行为',()=>{
  const change=vi.fn(),view=render(<IndexSelection as="nav" label="资料索引" identity="a"><button className="jj-index-item" aria-current="page">原资料</button><button className="jj-index-item" onClick={change}>其他资料</button></IndexSelection>)
  expect(view.container.querySelector('.jj-index-surface')).toBeInTheDocument()
  view.rerender(<IndexSelection as="nav" label="资料索引" identity="filtered"><button className="jj-index-item" onClick={change}>其他资料</button><button className="jj-index-item" disabled>不可用资料</button></IndexSelection>)
  expect(view.container.querySelector('.jj-index-surface')).toBeNull()
  fireEvent.click(screen.getByRole('button',{name:'其他资料'}))
  expect(change).toHaveBeenCalledOnce()
  expect(screen.getByRole('button',{name:'不可用资料'})).toBeDisabled()
})

it('提交期间按钮不可再次激活，并保留可访问状态',()=>{
  const action=vi.fn()
  render(<Button busy onClick={action}>提交检查</Button>)
  const button=screen.getByRole('button',{name:'提交检查'})
  fireEvent.click(button)
  expect(button).toBeDisabled();expect(button).toHaveAttribute('aria-busy','true');expect(action).not.toHaveBeenCalled()
})

it('有提示的按钮进入忙碌后保留同一元素，恢复后继续可用',()=>{
  const view=render(<Button aria-label="刷新" tip="刷新状态"/>),button=screen.getByRole('button',{name:'刷新'})
  view.rerender(<Button aria-label="刷新" tip="刷新状态" busy/> )
  expect(screen.getByRole('button',{name:'刷新'})).toBe(button)
  expect(button).toBeDisabled()
  view.rerender(<Button aria-label="刷新" tip="刷新状态"/> )
  expect(screen.getByRole('button',{name:'刷新'})).toBe(button)
  expect(button).toBeEnabled()
})

it('选择菜单展开后将所选值交给业务调用方',async()=>{
  const change=vi.fn()
  render(<Choice aria-label="当前应用" value="a" onValueChange={change}><option value="a">应用 A</option><option value="b">应用 B</option></Choice>)
  const input=screen.getByRole('combobox')
  fireEvent.mouseDown(input)
  fireEvent.click(await screen.findByRole('option',{name:'应用 B'}))
  expect(change).toHaveBeenCalledWith('b',expect.anything())
})

it('原选项失效时保留原值并提示，不自动选择可用对象',async()=>{
  const change=vi.fn()
  render(<Choice aria-label="操作账号" value="removed" onValueChange={change}><option value="owner">负责人</option></Choice>)
  expect(screen.getByText('原选项已不可用')).toBeVisible()
  expect(screen.queryByText('removed')).not.toBeInTheDocument()
  expect(change).not.toHaveBeenCalled()
  fireEvent.mouseDown(screen.getByRole('combobox'))
  const removed=await screen.findByRole('option',{name:'原选项已不可用'})
  fireEvent.click(removed)
  expect(change).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('option',{name:'负责人'}))
  expect(change).toHaveBeenCalledWith('owner',expect.anything())
})

it('对话框中的选择器关联字段名称，键盘跳过禁用项，Escape 只关闭选项',async()=>{
  const close=vi.fn(),change=vi.fn()
  function Scene(){const [value,setValue]=useState('0');return <Dialog title="准备数据" onClose={close}><Field label="数据所有者"><Choice value={value} onValueChange={next=>{setValue(next);change(next)}}><option value="0">负责人</option><option value="1" disabled>已停用账号</option><option value="2">评审</option></Choice></Field></Dialog>}
  render(<Scene/>)
  const input=screen.getByRole('combobox',{name:'数据所有者'})
  fireEvent.keyDown(input,{key:'ArrowDown',keyCode:40})
  await screen.findByRole('option',{name:'负责人'})
  fireEvent.keyDown(input,{key:'ArrowDown',keyCode:40})
  fireEvent.keyDown(input,{key:'Enter',keyCode:13})
  expect(change).toHaveBeenCalledWith('2')
  fireEvent.keyDown(input,{key:'ArrowDown',keyCode:40})
  fireEvent.keyDown(input,{key:'Escape',keyCode:27})
  await waitFor(()=>expect(input).toHaveAttribute('aria-expanded','false'))
  expect(screen.getByRole('dialog',{name:'准备数据'})).toBeInTheDocument()
  expect(close).not.toHaveBeenCalled()
})

it('页签键盘切换同步选中值和焦点',()=>{
  function Scene(){const [value,setValue]=useState('result');return <Tabs label="检查依据" value={value} onValueChange={setValue} items={[{value:'result',label:'业务结果'},{value:'trace',label:'操作经过'}]}/>}
  render(<Scene/>)
  fireEvent.keyDown(screen.getByRole('tab',{name:'业务结果'}),{key:'ArrowRight'})
  expect(screen.getByRole('tab',{name:'操作经过'})).toHaveFocus()
  expect(screen.getByRole('tab',{name:'操作经过'})).toHaveAttribute('aria-selected','true')
  expect(screen.getByRole('tab',{name:'业务结果'})).toHaveAttribute('tabindex','-1')
  fireEvent.keyDown(screen.getByRole('tab',{name:'操作经过'}),{key:'Home'})
  expect(screen.getByRole('tab',{name:'业务结果'})).toHaveFocus()
  expect(screen.getByRole('tab',{name:'业务结果'})).toHaveAttribute('aria-selected','true')
})

it('快速反向选择接续当前运动，减少动效立即停止且不延迟选择',()=>{
  const motions:Array<{frames:Keyframe[];animation:Animation}>=[],listeners=new Set<()=>void>()
  const preference={matches:false,addEventListener:(_type:string,listener:()=>void)=>listeners.add(listener),removeEventListener:(_type:string,listener:()=>void)=>listeners.delete(listener)}
  vi.spyOn(window,'matchMedia').mockReturnValue(preference as unknown as MediaQueryList)
  vi.spyOn(HTMLElement.prototype,'getBoundingClientRect').mockImplementation(function(this:HTMLElement){return DOMRect.fromRect({x:this.textContent==='操作经过'?120:0,y:0,width:100,height:40})})
  const nativeStyle=window.getComputedStyle
  vi.spyOn(window,'getComputedStyle').mockImplementation(node=>{const style=nativeStyle(node);style.setProperty('--motion-indicator','.2s');return style})
  const descriptor=Object.getOwnPropertyDescriptor(HTMLElement.prototype,'animate')
  Object.defineProperty(HTMLElement.prototype,'animate',{configurable:true,value:(frames:Keyframe[],options:KeyframeAnimationOptions)=>{
    expect(options.duration).toBe(300)
    const animation={currentTime:0,cancel:vi.fn(),onfinish:null} as unknown as Animation
    motions.push({frames,animation});return animation
  }})
  try{
    function Scene(){const [value,setValue]=useState('result');return <Tabs label="检查依据" value={value} onValueChange={setValue} items={[{value:'result',label:'业务结果'},{value:'trace',label:'操作经过'}]}/>}
    const view=render(<Scene/>)
    fireEvent.click(screen.getByRole('tab',{name:'操作经过'}))
    expect(motions).toHaveLength(1)
    motions[0].animation.currentTime=75
    fireEvent.click(screen.getByRole('tab',{name:'业务结果'}))
    const x=(frame:Keyframe)=>Number(String(frame.transform).match(/translate3d\(([-\d.]+)/)?.[1])
    expect(motions[0].animation.cancel).toHaveBeenCalledOnce()
    expect(x(motions[1].frames[0])).toBeGreaterThan(0)
    expect(x(motions[1].frames[0])).toBeLessThan(120)
    // 改向起点仍保有上一运动的正速度，随后收束到新目标，不能原地停顿后倒放。
    expect(x(motions[1].frames[1])).toBeGreaterThan(x(motions[1].frames[0]))
    expect(x(motions[1].frames.at(-1)!)).toBe(0)
    preference.matches=true;listeners.forEach(listener=>listener())
    expect(motions[1].animation.cancel).toHaveBeenCalledOnce()
    fireEvent.keyDown(screen.getByRole('tab',{name:'业务结果'}),{key:'ArrowRight'})
    expect(screen.getByRole('tab',{name:'操作经过'})).toHaveFocus()
    expect(screen.getByRole('tab',{name:'操作经过'})).toHaveAttribute('aria-selected','true')
    expect(motions).toHaveLength(2)
    view.unmount();expect(listeners.size).toBe(0)
  }finally{
    if(descriptor)Object.defineProperty(HTMLElement.prototype,'animate',descriptor)
    else Reflect.deleteProperty(HTMLElement.prototype,'animate')
  }
})

it('路由分类沿用链接语义，预载不切换位置或触发业务提交',()=>{
  const intent=vi.fn(),submit=vi.fn()
  render(<form onSubmit={submit}><LinkTabs label="设置分类" value="tools" onIntent={intent} items={[{value:'tools',label:'开发工具',href:'#/settings?section=tools'},{value:'storage',label:'本地存储',href:'#/settings?section=storage'}]}/><Tabs label="局部内容" value="a" items={[{value:'a',label:'当前内容'}]} onValueChange={vi.fn()}/></form>)
  const link=screen.getByRole('link',{name:'本地存储'})
  expect(screen.getByRole('link',{name:'开发工具'})).toHaveAttribute('aria-current','page')
  expect(link).toHaveAttribute('href','#/settings?section=storage')
  fireEvent.focus(link)
  expect(intent).toHaveBeenCalledWith('storage')
  expect(link).not.toHaveAttribute('aria-current')
  fireEvent.click(screen.getByRole('tab',{name:'当前内容'}))
  expect(submit).not.toHaveBeenCalled()
})

it('取消对话框不会执行提交，并在退出后返回原入口',async()=>{
  const submit=vi.fn()
  function Scene(){const [open,setOpen]=useState(false);return <><button onClick={()=>setOpen(true)}>准备操作</button>{open&&<Dialog title="确认操作" onClose={()=>setOpen(false)} actions={dismiss=><><Button onClick={dismiss}>取消</Button><Button onClick={submit}>确认</Button></>}>核对本次操作</Dialog>}</>}
  render(<Scene/>)
  const trigger=screen.getByRole('button',{name:'准备操作'})
  trigger.focus();fireEvent.click(trigger)
  fireEvent.click(within(screen.getByRole('dialog')).getByRole('button',{name:'取消'}))
  await waitFor(()=>expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  expect(submit).not.toHaveBeenCalled();await waitFor(()=>expect(trigger).toHaveFocus())
})
