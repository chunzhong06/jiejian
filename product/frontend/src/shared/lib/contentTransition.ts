import {useLayoutEffect,useRef} from 'react'

/** 只交接阅读内容，不通过重挂载丢弃其中的表单草稿或未知操作。 */
export function useContentTransition<T extends HTMLElement=HTMLDivElement>(identity:string){
  const root=useRef<T>(null)
  useLayoutEffect(()=>{
    const node=root.current
    if(!node?.animate||matchMedia('(prefers-reduced-motion: reduce)').matches)return
    const style=getComputedStyle(node)
    const animation=node.animate([
      {opacity:.65},
      {opacity:1},
    ],{duration:parseFloat(style.getPropertyValue('--motion-content')),easing:style.getPropertyValue('--ease-enter').trim()})
    return()=>animation.cancel()
  },[identity])
  return root
}
