import {useLayoutEffect,useRef} from 'react'
import {motionMilliseconds} from './motionTiming'

/** 只交接阅读内容，不通过重挂载丢弃其中的表单草稿或未知操作。 */
export function useContentTransition<T extends HTMLElement=HTMLDivElement>(identity:string){
  const root=useRef<T>(null),interrupted=useRef<number|undefined>(undefined)
  useLayoutEffect(()=>{
    const node=root.current
    const preference=matchMedia('(prefers-reduced-motion: reduce)')
    if(!node?.animate||preference.matches)return
    const style=getComputedStyle(node)
    const animation=node.animate([
      {opacity:interrupted.current??.65},
      {opacity:1},
    ],{duration:motionMilliseconds(style.getPropertyValue('--motion-content')),easing:style.getPropertyValue('--ease-enter').trim()})
    interrupted.current=undefined
    const stop=()=>{if(preference.matches)animation.cancel()}
    preference.addEventListener('change',stop)
    return()=>{
      // 快速切换从当前可读程度继续，不反复将正文打暗；不重挂表单或改写草稿。
      interrupted.current=animation.playState==='running'?Number(getComputedStyle(node).opacity):undefined
      preference.removeEventListener('change',stop);animation.cancel()
    }
  },[identity])
  return root
}
