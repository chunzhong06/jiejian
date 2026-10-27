import {act,render,screen,waitFor} from '@testing-library/react'
import {expect,it,vi} from 'vitest'
import {PageSurface} from './PageSurface'
import {PageSkeleton} from './PageSkeleton'
import {commitPageTransition,commitThemeTransition,pageTransitionActive} from '../lib/pageTransition'

function track(){const animate=vi.fn(()=>({cancel:vi.fn()}));Object.defineProperty(Element.prototype,'animate',{configurable:true,value:animate});return animate}

it('首次读取保留标题与内容结构，不生成虚假的业务操作',async()=>{
  const animate=track()
  const view=render(<PageSurface view="/preparation"><PageSkeleton view="/preparation"/></PageSurface>)
  expect(screen.getByRole('status',{name:'正在读取检查准备'})).toBeVisible()
  expect(screen.getByRole('heading',{name:'检查准备'})).toBeVisible()
  expect(screen.queryByRole('button')).not.toBeInTheDocument()
  expect(animate).not.toHaveBeenCalled()
  view.rerender(<PageSurface view="/preparation"><h1>检查准备</h1><p>材料已读取</p></PageSurface>)
  await waitFor(()=>expect(animate).toHaveBeenCalledTimes(1))
  view.rerender(<PageSurface view="/preparation"><h1>检查准备</h1><p>材料已刷新</p></PageSurface>)
  expect(animate).toHaveBeenCalledTimes(1)
})

it('快速离开后不播放旧对象迟到的入场',async()=>{
  const animate=track()
  const view=render(<PageSurface view="preparation"><PageSkeleton view="/preparation"/></PageSurface>)
  view.rerender(<PageSurface view="reports"><h1>检查记录</h1></PageSurface>)
  await waitFor(()=>expect(animate).toHaveBeenCalledTimes(1))
})

it('快速切换取消旧快照，旧完成回调不清除新页面的过渡状态',async()=>{
  const transitions:Array<{finished:Promise<void>;ready:Promise<void>;skipTransition:ReturnType<typeof vi.fn>;finish:()=>void}>=[]
  Object.defineProperty(document,'startViewTransition',{configurable:true,writable:true,value:vi.fn((update:()=>void)=>{
    update()
    let finish!:()=>void
    const next={finished:new Promise<void>(resolve=>{finish=resolve}),ready:Promise.resolve(),skipTransition:vi.fn(),finish:()=>finish()}
    transitions.push(next)
    return next
  })})
  const first=vi.fn(),second=vi.fn()
  act(()=>commitPageTransition(first))
  act(()=>commitPageTransition(second,'back'))
  expect(first).toHaveBeenCalledTimes(1)
  expect(second).toHaveBeenCalledTimes(1)
  expect(transitions[0].skipTransition).toHaveBeenCalledTimes(1)
  await act(async()=>transitions[0].finish())
  expect(pageTransitionActive()).toBe(true)
  expect(document.documentElement.dataset.pageDirection).toBe('back')
  await act(async()=>transitions[1].finish())
  expect(pageTransitionActive()).toBe(false)
  expect(document.documentElement.dataset.visualTransition).toBeUndefined()
  delete (document as unknown as {startViewTransition?:unknown}).startViewTransition
})

it('减少动效时立即更新，不等待动画完成',()=>{
  const update=vi.fn(),native=vi.fn()
  vi.spyOn(window,'matchMedia').mockReturnValue({matches:true,addEventListener(){},removeEventListener(){}} as unknown as MediaQueryList)
  Object.defineProperty(document,'startViewTransition',{configurable:true,writable:true,value:native})
  commitPageTransition(update)
  commitThemeTransition(update)
  expect(update).toHaveBeenCalledTimes(2)
  expect(native).not.toHaveBeenCalled()
  expect(pageTransitionActive()).toBe(false)
  delete (document as unknown as {startViewTransition?:unknown}).startViewTransition
})
