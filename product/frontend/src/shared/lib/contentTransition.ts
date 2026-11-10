import {useLayoutEffect,useRef} from 'react'
import {revealContent} from './motion'

/** 对象交接保留组件、草稿与原操作；共享场景不再叠加第二层入场。 */
export function useContentTransition<T extends HTMLElement=HTMLDivElement>(identity:string){
  const root=useRef<T>(null)
  useLayoutEffect(()=>{
    const node=root.current
    if(!node)return
    node.dataset.motionOwner='content'
    revealContent(node)
  },[identity])
  return root
}
