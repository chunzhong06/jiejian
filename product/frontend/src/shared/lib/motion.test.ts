import {afterEach,expect,it,vi} from 'vitest'
import {animateMotion,revealContent,springSample,stopAllMotion} from './motion'
import {connectMotionScene} from './motionScene'

type Recording={node:HTMLElement;frames:Keyframe[];animation:Animation;finish:()=>void}
function animations(){
  const records:Recording[]=[]
  vi.spyOn(HTMLElement.prototype,'getBoundingClientRect').mockImplementation(function(this:HTMLElement){
    const siblings=this.parentElement?Array.from(this.parentElement.children):[]
    return DOMRect.fromRect({x:0,y:siblings.indexOf(this)*40,width:200,height:40})
  })
  vi.spyOn(HTMLElement.prototype,'getClientRects').mockImplementation(function(this:HTMLElement){return [this.getBoundingClientRect()] as unknown as DOMRectList})
  Object.defineProperty(HTMLElement.prototype,'animate',{configurable:true,value:function(this:HTMLElement,frames:Keyframe[]){
    let finish!:()=>void
    const animation={cancel:vi.fn(),finished:new Promise<void>(resolve=>{finish=resolve}),playState:'running',currentTime:0} as unknown as Animation
    records.push({node:this,frames,animation,finish});return animation
  }})
  return records
}
afterEach(()=>{stopAllMotion();Reflect.deleteProperty(HTMLElement.prototype,'animate');document.body.replaceChildren()})

it('同一对象快速换目标只保留最新运动，不取消其他对象',()=>{
  const records=animations(),a=document.createElement('div'),b=document.createElement('div')
  document.body.append(a,b)
  animateMotion(a,'appearance',[{opacity:.5},{opacity:1}],{duration:200})
  animateMotion(b,'appearance',[{opacity:.5},{opacity:1}],{duration:200})
  animateMotion(a,'appearance',[{opacity:.8},{opacity:1}],{duration:200})
  expect(records[0].animation.cancel).toHaveBeenCalledOnce()
  expect(records[1].animation.cancel).not.toHaveBeenCalled()
  expect(records[2].frames[0].opacity).toBe(.8)
})

it('改向瞬间保留速度，随后收束到新目标',()=>{
  const forward=springSample(0,100,0,.04,280)
  const reverse=springSample(forward.position,0,forward.velocity,0,280)
  expect(reverse.position).toBeCloseTo(forward.position)
  expect(reverse.velocity).toBeCloseTo(forward.velocity)
  expect(springSample(reverse.position,0,reverse.velocity,1,280).position).toBeCloseTo(0,3)
})

it('减少动态时保持真实DOM，不创建替代动画',()=>{
  const records=animations(),node=document.createElement('div');document.body.append(node)
  vi.spyOn(window,'matchMedia').mockReturnValue({matches:true} as MediaQueryList)
  node.textContent='已完成2项';revealContent(node)
  expect(records).toHaveLength(0)
  expect(node.textContent).toBe('已完成2项')
})

it('列表重排补位而不重新挂载输入，停止观察后不再创建运动',async()=>{
  const records=animations(),root=document.createElement('div')
  root.innerHTML='<ul><li>原项<input value="原草稿"></li><li>另一项</li></ul>'
  document.body.append(root)
  const first=root.querySelector('li')!,input=root.querySelector('input')!,list=root.querySelector('ul')!
  const disconnect=connectMotionScene(root)
  list.append(first)
  await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))
  expect(records.some(record=>record.node===first)).toBe(true)
  expect(root.querySelector('input')).toBe(input)
  expect(input.value).toBe('原草稿')
  disconnect();const count=records.length
  list.prepend(first)
  await new Promise(resolve=>requestAnimationFrame(resolve))
  expect(records).toHaveLength(count)
})

it('同一个状态的重复通知保持静止，真实状态变化才交接',async()=>{
  const records=animations(),root=document.createElement('div')
  root.innerHTML='<span class="jj-status" data-tone="neutral">等待处理</span>'
  document.body.append(root);const state=root.firstElementChild as HTMLElement
  const disconnect=connectMotionScene(root)
  state.setAttribute('data-tone','neutral')
  await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))
  expect(records).toHaveLength(0)
  state.textContent='已就绪';state.dataset.tone='positive'
  await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))
  expect(records.some(record=>record.node===state)).toBe(true)
  disconnect()
})
