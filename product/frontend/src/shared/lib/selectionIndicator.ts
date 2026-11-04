import {useLayoutEffect,useState,type RefObject} from 'react'

/** 持有选中标记的目标位置；CSS从当前插值位置继续，快速切换不排队。 */
export function useSelectionIndicator(root:RefObject<HTMLElement|null>,selector:string,identity:string,kind:'underline'|'surface'='underline'){
  const [bounds,setBounds]=useState<{x:number;y:number;width:number;height:number}>()
  useLayoutEffect(()=>{
    const node=root.current
    if(!node)return
    const place=()=>{
      const item=node.querySelector<HTMLElement>(selector)
      if(!item){setBounds(undefined);return}
      const next={x:item.offsetLeft,y:item.offsetTop+(kind==='underline'?item.offsetHeight-2:0),width:item.offsetWidth,height:kind==='underline'?2:item.offsetHeight}
      setBounds(previous=>previous&&previous.x===next.x&&previous.y===next.y&&previous.width===next.width&&previous.height===next.height?previous:next)
    }
    place()
    const observer='ResizeObserver' in window?new ResizeObserver(place):undefined
    observer?.observe(node)
    node.querySelectorAll<HTMLElement>('button,a').forEach(item=>observer?.observe(item))
    return()=>observer?.disconnect()
  },[root,selector,identity,kind])
  return bounds?{width:bounds.width,height:bounds.height,transform:`translate3d(${bounds.x}px,${bounds.y}px,0)`}:undefined
}
