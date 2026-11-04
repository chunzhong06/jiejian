import {useEffect,useLayoutEffect,useRef,type ReactNode} from 'react'
import {pageTransitionActive} from '../lib/pageTransition'

export function PageSurface({view,transitionKey=view,route,children}:{view:string;transitionKey?:string;route?:string;children:ReactNode}) {
  const ref=useRef<HTMLDivElement>(null),running=useRef<Animation|null>(null),previous=useRef(transitionKey)
  useLayoutEffect(()=>{
    const node=ref.current,preference=window.matchMedia('(prefers-reduced-motion: reduce)')
    if(!node?.animate||preference.matches){running.current?.cancel();return}
    let observer:MutationObserver|undefined,played=false
    const changed=previous.current!==transitionKey
    previous.current=transitionKey
    const pending=()=>node.querySelector(':scope > .jj-loading,[data-page-pending="true"]')
    const wasPending=Boolean(pending())
    const play=()=>{
      if(played||pending())return
      played=true;observer?.disconnect()
      // 原生页面过渡与内容出现只选一个；普通轮询更新不反复淡入整页。
      if(preference.matches||pageTransitionActive()||!changed&&!wasPending)return
      running.current?.cancel()
      running.current=node.animate(
        [{opacity:.4,transform:'translateY(14px)'},{opacity:1,transform:'none'}],
        {duration:240,easing:'cubic-bezier(.16,1,.3,1)'}
      )
    }
    if(pending()){
      // 等实际内容替换加载占位后再播放，不用固定延时拖住导航或猜测请求何时完成。
      running.current?.cancel()
      observer=new MutationObserver(play);observer.observe(node,{childList:true,subtree:true,attributes:true,attributeFilter:['data-page-pending']})
    }else play()
    const cancel=()=>running.current?.cancel()
    preference.addEventListener('change',cancel)
    return()=>{observer?.disconnect();running.current?.cancel();preference.removeEventListener('change',cancel)}
  },[transitionKey])
  useEffect(()=>()=>running.current?.cancel(),[])
  return <div ref={ref} className="jj-page" data-view={view} data-route={route}>{children}</div>
}
