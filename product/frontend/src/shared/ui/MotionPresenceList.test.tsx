// 退出画面不能继续被操作或播报；关闭动效立即卸载，重新出现采用最新数据。
import {act,render,screen} from '@testing-library/react'
import {afterEach,expect,it,vi} from 'vitest'
import {MotionPresenceList} from './MotionPresenceList'

afterEach(()=>{vi.useRealTimers();delete document.documentElement.dataset.motion})
const content=(item:{key:string;text:string})=><button>{item.text}</button>
it('移除后立即退出可访问树，短暂画面结束后卸载',()=>{
  vi.useFakeTimers();document.documentElement.dataset.motion='full'
  const view=render(<MotionPresenceList items={[{key:'a',text:'操作已完成'}]}>{content}</MotionPresenceList>)
  view.rerender(<MotionPresenceList items={[] as {key:string;text:string}[]}>{content}</MotionPresenceList>)
  expect(screen.queryByRole('button',{name:'操作已完成'})).not.toBeInTheDocument()
  expect(view.container.querySelector('[data-leaving=true]')).toHaveAttribute('inert')
  act(()=>vi.advanceTimersByTime(300))
  expect(view.container).toBeEmptyDOMElement()
})
it('同一通知在退出中重新出现时展示新内容',()=>{
  vi.useFakeTimers();document.documentElement.dataset.motion='full'
  const view=render(<MotionPresenceList items={[{key:'a',text:'旧消息'}]}>{content}</MotionPresenceList>)
  view.rerender(<MotionPresenceList items={[] as {key:string;text:string}[]}>{content}</MotionPresenceList>)
  view.rerender(<MotionPresenceList items={[{key:'a',text:'新消息'}]}>{content}</MotionPresenceList>)
  act(()=>vi.advanceTimersByTime(300))
  expect(screen.getByRole('button',{name:'新消息'})).toBeInTheDocument()
  expect(screen.queryByText('旧消息')).not.toBeInTheDocument()
})
it('关闭动效不保留退出节点',()=>{
  document.documentElement.dataset.motion='off'
  const view=render(<MotionPresenceList items={[{key:'a',text:'消息'}]}>{content}</MotionPresenceList>)
  view.rerender(<MotionPresenceList items={[] as {key:string;text:string}[]}>{content}</MotionPresenceList>)
  expect(view.container).toBeEmptyDOMElement()
})
