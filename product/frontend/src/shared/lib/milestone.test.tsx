import {act,cleanup,render} from '@testing-library/react'
import {afterEach,beforeEach,expect,it,vi} from 'vitest'
import {markMilestone,useMilestoneTransition} from './milestone'
import {stopAllMotion} from './motion'

const frames:Array<{node:HTMLElement;options:KeyframeAnimationOptions}>=[]
function Surface({identity='one',complete}:{identity?:string;complete:boolean}){
  const ref=useMilestoneTransition<HTMLDivElement>(identity,complete,'report')
  return <div ref={ref}><h2 data-milestone-part="heading">业务结果</h2><footer data-milestone-part="actions">继续检查</footer></div>
}
beforeEach(()=>{
  frames.length=0
  vi.spyOn(window,'matchMedia').mockReturnValue({matches:false} as MediaQueryList)
  Object.defineProperty(HTMLElement.prototype,'animate',{configurable:true,value:function(this:HTMLElement,_frames:Keyframe[],options:KeyframeAnimationOptions){frames.push({node:this,options});return {finished:new Promise(()=>{}),cancel:vi.fn(),playState:'running'} as unknown as Animation}})
})
afterEach(()=>{cleanup();stopAllMotion();Reflect.deleteProperty(HTMLElement.prototype,'animate');vi.restoreAllMocks()})

it('初次读取历史终态不重播，同一对象的真实完成只交接一次',()=>{
  const view=render(<Surface complete/>)
  expect(frames).toHaveLength(0)
  view.rerender(<Surface complete={false}/>)
  view.rerender(<Surface complete/>)
  expect(frames).toHaveLength(4)
  expect(frames.at(-1)?.options.delay).toBeGreaterThan(frames[0].options.delay as number)
  view.rerender(<Surface complete/>)
  expect(frames).toHaveLength(4)
  view.unmount();render(<Surface complete/>)
  expect(frames).toHaveLength(4)
})
it('跨工作面的已确认回执等待同一对象，不触发其他对象',()=>{
  const view=render(<Surface identity="other" complete/>)
  act(()=>markMilestone('wanted'))
  expect(frames).toHaveLength(0)
  view.rerender(<Surface identity="wanted" complete/>)
  expect(frames).toHaveLength(4)
  view.unmount();render(<Surface identity="wanted" complete/>)
  expect(frames).toHaveLength(4)
})
it('减少动态仍交付完成事实，恢复偏好后不补播旧完成',()=>{
  vi.spyOn(window,'matchMedia').mockReturnValue({matches:true} as MediaQueryList)
  const view=render(<Surface identity="reduced" complete={false}/>)
  view.rerender(<Surface identity="reduced" complete/>)
  expect(frames).toHaveLength(0)
  vi.spyOn(window,'matchMedia').mockReturnValue({matches:false} as MediaQueryList)
  view.unmount();render(<Surface identity="reduced" complete/>)
  expect(frames).toHaveLength(0)
})
