import {afterEach,expect,it,vi} from 'vitest'
import {commitReadingTransition,commitThemeTransition} from './pageTransition'

afterEach(()=>{commitThemeTransition(()=>{});vi.restoreAllMocks();Reflect.deleteProperty(document,'startViewTransition');document.body.replaceChildren()})
function native(){
  const entries:Array<{finish:()=>void;skip:ReturnType<typeof vi.fn>}>=[]
  vi.spyOn(window,'matchMedia').mockReturnValue({matches:false,addEventListener:vi.fn(),removeEventListener:vi.fn()} as unknown as MediaQueryList)
  Object.defineProperty(document,'startViewTransition',{configurable:true,value:(update:()=>void)=>{
    update();let finish!:()=>void
    const finished=new Promise<void>(resolve=>{finish=resolve}),skip=vi.fn()
    entries.push({finish,skip})
    return {ready:Promise.resolve(),finished,skipTransition:skip}
  }})
  return entries
}
it('快速反向立即提交最新过滤，旧清理不会解除新快照身份',async()=>{
  const runs=native(),page=document.createElement('main'),root=document.createElement('section')
  page.className='jj-page';page.append(root);document.body.append(page)
  root.innerHTML='<button data-directory-id="first">第一项</button>'
  let value=''
  commitReadingTransition(root,()=>{value='filtered'})
  commitReadingTransition(root,()=>{value='all'})
  expect(value).toBe('all');expect(runs[0].skip).toHaveBeenCalledOnce()
  runs[0].finish();await Promise.resolve();await Promise.resolve();await Promise.resolve()
  expect(root.style.viewTransitionName).toBe('jj-reading')
  runs[1].finish();await Promise.resolve();await Promise.resolve();await Promise.resolve()
  expect(root.style.viewTransitionName).toBe('');expect(page.style.viewTransitionName).toBe('')
})
it('含编辑内容的工作面直接更新，不绘制表单或秘密快照',()=>{
  const runs=native(),root=document.createElement('section');root.innerHTML='<input value="draft">'
  const update=vi.fn();commitReadingTransition(root,update)
  expect(update).toHaveBeenCalledOnce();expect(runs).toHaveLength(0)
})
it('减少动态时立即更新，不改变业务节点寿命',()=>{
  const runs=native();vi.spyOn(window,'matchMedia').mockReturnValue({matches:true} as MediaQueryList)
  const root=document.createElement('section');root.innerHTML='<button>旧内容</button>'
  commitReadingTransition(root,()=>root.replaceChildren())
  expect(root.childElementCount).toBe(0);expect(runs).toHaveLength(0)
})
